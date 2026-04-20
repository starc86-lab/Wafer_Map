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
    valid_ratio: float = 0.8,
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
    min_valid = max(int(required_n * valid_ratio), 1)
    patterns = list(value_patterns)

    qualified: list[tuple[str, float, int]] = []  # (name, metric, pattern_score)
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
        # 단일값 / 심한 누락 파라 (예: T1_AVG) 도 콤보에서 완전 배제
        if valid.size < min_valid:
            continue
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
        qualified.append((name, metric, pat_score))

    if not qualified:
        return None, []

    # 1순위: metric 최대 → tie-break (pattern, 알파벳)
    qualified.sort(key=lambda t: (-t[1], -t[2], t[0]))
    selected = qualified[0][0]
    # 콤보: 선택된 1 순위 먼저, 나머지 후보는 **알파벳 순** (사용자가 찾기 쉽게)
    rest_alpha = sorted(t[0] for t in qualified[1:])
    ordered = [selected] + rest_alpha
    return selected, ordered


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
