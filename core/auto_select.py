"""
VALUE/X/Y PARAMETER 자동 선택.

- 매칭 조건: 패턴(fnmatch 와일드카드, 대소문자 무관) + 값 개수가 `required_n`과 일치.
- 우선순위: 패턴 목록 순서 → 같은 패턴 내 알파벳 순 → 매칭 안 된 것(알파벳).
- Y는 X 이름의 suffix 를 물려받아 `Y{suffix}`를 1순위로 사용.

ex.
    available_ns = {"T1": 13, "T1_B": 4, "X": 13, "Y": 13, "GOF": 13}
    select_value(available_ns, ["T*"], required_n=13) -> ("T1", ["T1", "GOF", ..., "T1_B"])
"""
from __future__ import annotations

import fnmatch
import re
from typing import Iterable, Mapping

import numpy as np


# VALUE 후보에서 자동 제외할 좌표 PARAMETER 패턴.
# X, Y 정확일치 + X_ / Y_ 로 시작 (예: X_1000, Y_1000_A).
_COORD_NAME_RE = re.compile(r"^[xyXY](_.*)?$")


def _is_coord_name(name: str) -> bool:
    return bool(_COORD_NAME_RE.match(name.strip()))


def _has_group_suffix(name: str) -> bool:
    """이름이 `_A`, `_B` 식 **1~2자 알파벳 그룹 suffix** 로 끝나는지 판정.

    예:
      - `T1`           → False
      - `T1_AVG`       → False (AVG 는 3자, 의미 suffix 로 보기엔 너무 김)
      - `T1_A`         → True  (그룹 A)
      - `T3_B`         → True
      - `X_1000`       → False (1000 은 숫자)
      - `X_1000_A`     → True  (마지막 토큰 A)
      - `REV_NIT`      → False (NIT 3자, 그룹 suffix 아님)
    """
    if "_" not in name:
        return False
    last = name.rsplit("_", 1)[-1]
    return 1 <= len(last) <= 2 and last.isalpha()


def _is_integer_valued(values: np.ndarray, tol: float = 1e-6) -> bool:
    """값이 **엄밀한 정수** 로만 구성됐는지 — die index(DIE_ROW/DIE_COL) 감지용.

    max(|residual|) 기준 — 단 하나라도 정수 아닌 값 섞여있으면 False.
    (std 기준은 GOF 0.9985 같은 near-1 부동소수를 오탐하기에 tight bound 필요)

    tol=1e-6: 실제 정수 저장 시 float 오차 범위. 측정치 (T1=1000.5) 나 GOF (0.999)
    는 residual 0 이 아니라 0.5, 0.001 수준이라 확실히 구분.
    """
    if values.size == 0:
        return False
    return bool(np.max(np.abs(values - np.round(values))) < tol)


def _matches(name: str, pattern: str) -> bool:
    """fnmatch 스타일 와일드카드 매칭 (대소문자 무관)."""
    return fnmatch.fnmatchcase(name.casefold(), pattern.casefold())


def prioritized_list(
    available_ns: dict[str, int],
    patterns: Iterable[str],
    required_n: int,
) -> tuple[list[str], set[str]]:
    """우선순위 정렬된 이름 리스트 + 매칭된 이름 집합.

    - 매칭 그룹: `n == required_n` 이면서 패턴에 맞는 이름. 알파벳 순.
    - 그 다음: 매칭 안 된 나머지 전부 (n 조건 관계없이). 알파벳 순.
    """
    ordered: list[str] = []
    matched_set: set[str] = set()
    for pat in patterns:
        group = sorted(
            name for name, n in available_ns.items()
            if n == required_n
            and name not in matched_set
            and _matches(name, pat)
        )
        ordered.extend(group)
        matched_set.update(group)
    others = sorted(set(available_ns) - matched_set)
    return ordered + others, matched_set


def _fallback_alpha_first(available_ns: dict[str, int], required_n: int) -> str | None:
    """패턴 매칭 실패 시 폴백: `n == required_n` 인 이름 중 알파벳 첫 번째."""
    candidates = sorted(
        name for name, n in available_ns.items() if n == required_n
    )
    return candidates[0] if candidates else None


def select_value(
    available_ns: dict[str, int],
    patterns: Iterable[str],
    required_n: int,
) -> tuple[str | None, list[str]]:
    """VALUE 또는 X용 자동 선택.

    1순위: 패턴 매칭 + `n == required_n` 중 (패턴 순 → 알파벳) 첫
    폴백:  `n == required_n` 중 알파벳 첫
    둘 다 실패: None

    Returns:
        (selected, ordered_list)
    """
    ordered, matched = prioritized_list(available_ns, patterns, required_n)
    selected = next((n for n in ordered if n in matched), None)
    if selected is None:
        selected = _fallback_alpha_first(available_ns, required_n)
    return selected, ordered


def select_value_by_variability(
    parameters: Mapping,
    required_n: int,
    value_patterns: Iterable[str] = ("T*",),
    *,
    exclude_names: set[str] | None = None,
) -> tuple[str | None, list[str]]:
    """VALUE 자동 선택 — |3σ/AVG| 최대 우선.

    1. `valid_count >= required_n * valid_ratio` (기본 80%) 필터
       → 단일값 (T1_AVG, T1_Range 등) + 누락 심한 파라 제외
    2. 후보들 중 |3σ / AVG| 최대 우선 — 공간적 변동 큰 측정이 맵 시각화 가치 높음
       → GOF, K[633], N[633] 같이 변동 작은 파라 자동 후순위
    3. Tie-break: `value_patterns` 매치 우선 + 알파벳

    Args:
        parameters: {name: WaferRecord} — 첫 웨이퍼 기준.
            WaferRecord 는 `values` (list[float]) 속성 가짐.
        required_n: 기준 n (보통 X 좌표의 n — coord 개수).
        value_patterns: fnmatch 패턴. tie-break 용.
        exclude_names: 후보에서 제외할 이름 (선택된 X, Y 등).

    Returns:
        (selected, ordered_list) — ordered 는 콤보 리스트.
        selected 가 None 이면 후보 0개.
    """
    excl = set(exclude_names or ())
    patterns = list(value_patterns)

    # (name, metric, pattern_score, is_int) — is_int 는 자동 선택 후순위 demote 용
    qualified: list[tuple[str, float, int, bool]] = []
    for name, rec in parameters.items():
        if name in excl:
            continue
        # 좌표 PARAMETER (X/Y, X_*, Y_*) 는 VALUE 후보에서 아예 제외
        if _is_coord_name(name):
            continue
        try:
            vals = np.asarray(rec.values, dtype=float)
        except Exception:
            continue
        valid = vals[~np.isnan(vals)] if vals.size else vals
        # n=0 또는 n=1 만 제외 (단일값/빈 파라는 맵 시각화 불가)
        if valid.size < 2:
            continue
        # 정수값 (DIE_ROW, DIE_COL) 은 **콤보엔 유지**하되 자동 선택 후순위 demote
        is_int = _is_integer_valued(valid)
        avg = float(valid.mean())
        if valid.size > 1:
            sig3 = 3.0 * float(valid.std(ddof=1))
        else:
            sig3 = 0.0
        if abs(avg) > 1e-10:
            metric = abs(sig3 / avg)
        else:
            metric = abs(sig3) * 1e-3
        pat_score = 0
        for i, pat in enumerate(patterns):
            if _matches(name, pat):
                pat_score = len(patterns) - i
                break
        qualified.append((name, metric, pat_score, is_int))

    if not qualified:
        return None, []

    # 그룹 분리: non-suffix (주) vs suffix (보조)
    main_cand = [q for q in qualified if not _has_group_suffix(q[0])]
    sub_cand = [q for q in qualified if _has_group_suffix(q[0])]

    # 자동 선택 대상: 주 그룹 우선, 없으면 보조
    primary = main_cand if main_cand else sub_cand
    # 정렬: is_int (정수/die index) 는 후순위로 밀기 → metric 내림차순 → pattern → 알파벳
    primary.sort(key=lambda t: (t[3], -t[1], -t[2], t[0]))
    selected = primary[0][0]

    # 콤보:
    #   1) 선택된 것
    #   2) 나머지 주 그룹 (알파벳) — DIE_ROW 등 정수값도 포함
    #   3) 보조 그룹 (알파벳)
    rem_main = sorted(t[0] for t in main_cand if t[0] != selected)
    sub_alpha = sorted(t[0] for t in sub_cand)
    ordered = [selected] + rem_main + sub_alpha
    return selected, ordered


def select_xy_pairs(
    available_ns: dict[str, int],
    x_patterns: Iterable[str] = ("X", "X*"),
    y_patterns: Iterable[str] = ("Y", "Y*"),
) -> tuple[str | None, str | None, list[str], list[str]]:
    """X/Y 좌표 PARAMETER pair 매칭 기반 자동 선택.

    단계:
    1. x_patterns/y_patterns 매치 이름 수집. n=1 은 제외.
    2. **suffix 기반 pair 매칭** — `X`↔`Y`, `X_1000`↔`Y_1000`, `X_A`↔`Y_A`.
       한쪽만 있는 이름(예: `X_1000_A` 인데 `Y_1000_A` 없음) → 제외.
    3. pair 의 n = min(n_x, n_y). 최대 pair_n 기준으로
       `pair_n < max_n × n_threshold_ratio` 는 제외.
    4. 선택: pattern 순서 → pair_n 큰 순 → 알파벳.
    5. 콤보: 선택된 pair 가 1순위, 나머지 pair 의 X/Y 각각 알파벳 순.

    Returns:
        (x_sel, y_sel, x_ordered, y_ordered)
    """
    xp = list(x_patterns)
    yp = list(y_patterns)

    # 1. X / Y 후보 (n>=2, 패턴 매치)
    def _collect(patterns: list[str]) -> dict[str, int]:
        """각 이름의 패턴 인덱스(낮을수록 우선)."""
        out: dict[str, int] = {}
        for name, n in available_ns.items():
            if n < 2:
                continue
            for i, pat in enumerate(patterns):
                if _matches(name, pat):
                    out[name] = i
                    break
        return out

    x_cands = _collect(xp)
    y_cands = _collect(yp)
    if not x_cands or not y_cands:
        return None, None, [], []

    # 2. suffix 기반 pair. 'x'/'y' 로 시작해야 — 이름 첫 글자 제거 후 나머지 비교
    def _suffix(name: str, first_char: str) -> str | None:
        if not name:
            return None
        if name[0].lower() != first_char:
            return None
        return name[1:].lower()

    x_by_suffix: dict[str, str] = {}
    for name in x_cands:
        sfx = _suffix(name, "x")
        if sfx is not None and sfx not in x_by_suffix:
            x_by_suffix[sfx] = name
    y_by_suffix: dict[str, str] = {}
    for name in y_cands:
        sfx = _suffix(name, "y")
        if sfx is not None and sfx not in y_by_suffix:
            y_by_suffix[sfx] = name

    pairs: list[tuple[str, str, int, int]] = []   # (x, y, pair_n, x_pattern_rank)
    for sfx, x_name in x_by_suffix.items():
        if sfx in y_by_suffix:
            y_name = y_by_suffix[sfx]
            pair_n = min(available_ns[x_name], available_ns[y_name])
            pairs.append((x_name, y_name, pair_n, x_cands.get(x_name, len(xp))))

    if not pairs:
        return None, None, [], []

    # 그룹 분리: non-suffix (주) vs suffix (보조)
    # n 상대 threshold 는 제거 — 사용자 유용 파라 제거 우려로 n=0/1 만 걸러냄 (위 단계 이미 처리)
    main_pairs = [p for p in pairs if not _has_group_suffix(p[0])]
    sub_pairs = [p for p in pairs if _has_group_suffix(p[0])]

    # 자동 선택 대상: 주 그룹 우선, 없으면 보조에서
    primary = main_pairs if main_pairs else sub_pairs
    if not primary:
        return None, None, [], []
    primary.sort(key=lambda p: (p[3], -p[2], p[0]))
    best_x, best_y, _, _ = primary[0]

    # 콤보 구성:
    #   1) 선택된 pair
    #   2) 나머지 주 그룹 (알파벳)
    #   3) 보조 그룹 (알파벳)
    remaining_main = sorted((p for p in main_pairs if p[0] != best_x), key=lambda p: p[0])
    sub_sorted = sorted(sub_pairs, key=lambda p: p[0])
    ordered_pairs = [primary[0]] + remaining_main + sub_sorted
    x_ordered = [p[0] for p in ordered_pairs]
    y_ordered = [p[1] for p in ordered_pairs]
    return best_x, best_y, x_ordered, y_ordered


def select_y_with_suffix(
    x_name: str | None,
    available_ns: dict[str, int],
    y_patterns: Iterable[str],
    required_n: int,
) -> tuple[str | None, list[str]]:
    """Y 자동 선택 — X suffix 우선, y_patterns 매칭, n 폴백 순.

    1. X가 `X{suffix}` 면 `Y{suffix}` 정확 매칭 시도 (있으면 ordered 맨 앞에 배치)
    2. 실패 시 `y_patterns` 기반 일반 매칭
    3. 그것도 실패 시 `n == required_n` 인 이름 중 알파벳 첫 폴백
    """
    ordered, matched = prioritized_list(available_ns, y_patterns, required_n)

    # 1. X suffix 매칭
    if x_name and x_name[:1].casefold() == "x":
        suffix = x_name[1:]
        preferred = f"Y{suffix}"
        hit = next(
            (
                name for name in available_ns
                if name.casefold() == preferred.casefold()
                and available_ns[name] == required_n
            ),
            None,
        )
        if hit:
            ordered = [hit] + [n for n in ordered if n != hit]
            return hit, ordered

    # 2. y_patterns 매칭
    selected = next((n for n in ordered if n in matched), None)

    # 3. n 일치 알파벳 폴백
    if selected is None:
        selected = _fallback_alpha_first(available_ns, required_n)
    return selected, ordered
