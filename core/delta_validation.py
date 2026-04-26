"""
DELTA 모드 (양쪽 입력) 정합성 검증 — 두 `ParseResult` 비교.

input_validation 이 단일 입력 검증을 담당하는 것과 같은 패턴. ParseResult 만으로
사전 판단 가능한 항목만 다룸 (compute_delta 호출 불필요).

검사 항목:
- `delta_no_intersect`     — A·B 의 WAFERID 교집합 0 (severity=error, Run 차단)
- `delta_repeats_in_input` — A 또는 B 에 `__rep` 분리된 wafer 가 존재 (severity=warn).
  base 끼리만 매칭한다는 명시적 알림. compute_delta 가 wafer_id 문자열 그대로
  매칭하므로 `__rep1` 은 자동으로 매칭 후보 안 됨 — 본 검사는 사용자 인지용.
- `delta_coord_fallback`   — A 또는 B 의 *전체* 좌표 PARA 누락 (severity=warn).
  A 일부 wafer 만 좌표 누락은 input_validation 의 `coord_para_missing` 영역.
  본 검사는 양쪽 비교만 — 전체 누락 시 어느 fallback (다른 쪽 / 라이브러리) 로
  가는지 메시지 분기.

호출자:
- 호출 시점: paste 변경 직후 (양쪽 ParseResult 모두 있을 때) 한 번
- 결과 cache 후 `_refresh_controls` (Run 활성화 결정) + ReasonBar 표시 양쪽에서 재사용

ValidationWarning 은 `core.input_validation` 의 dataclass 재사용 — 같은 표시 채널
(ReasonBar / paste 라벨) 에서 일관되게 다룰 수 있도록.
"""
from __future__ import annotations

from core.auto_select import select_xy_pairs
from core.input_validation import ValidationWarning
from core.settings import load_settings
from main import ParseResult


def _has_coord_paras(result: ParseResult) -> bool:
    """ParseResult 의 wafer 들에 좌표 PARA (X/Y 페어 매칭 가능한 이름) 가 하나라도
    있는지. union 기준 — 한 wafer 라도 좌표 가지면 True.
    """
    union_ns: dict[str, int] = {}
    for w in result.wafers.values():
        for name, rec in w.parameters.items():
            if name not in union_ns:
                union_ns[name] = rec.n
    if not union_ns:
        return False
    auto = load_settings().get("auto_select", {})
    xpat = auto.get("x_patterns", ["X", "X*"])
    ypat = auto.get("y_patterns", ["Y", "Y*"])
    _, _, x_ord, _ = select_xy_pairs(union_ns, xpat, ypat)
    return bool(x_ord)


def _first_recipe(result: ParseResult) -> str:
    """ParseResult 의 첫 wafer 의 recipe — 라이브러리 조회용 대표값."""
    for w in result.wafers.values():
        if w.recipe:
            return w.recipe
    return ""


def _library_can_resolve(a: ParseResult, b: ParseResult) -> bool:
    """A RECIPE 또는 B RECIPE 로 라이브러리에서 좌표 매칭 가능한지.

    `_visualize_delta` 의 좌표 fallback 마지막 단계와 동일 로직 — 양쪽 모두
    좌표 누락 시 라이브러리에서 가져올 수 있는지 사전 판정.
    """
    from core.coord_library import CoordLibrary  # lazy
    library = CoordLibrary()
    for r in (_first_recipe(a), _first_recipe(b)):
        if not r:
            continue
        if library.find_by_recipe(r):
            return True
    return False


def validate_delta(
    a: ParseResult, b: ParseResult,
) -> list[ValidationWarning]:
    """양쪽 ParseResult 비교 검증. 빈 리스트 = OK."""
    warnings: list[ValidationWarning] = []

    a_keys = set(a.wafers.keys())
    b_keys = set(b.wafers.keys())

    # delta_no_intersect — 교집합 0 → Run 차단
    common = a_keys & b_keys
    if not common:
        warnings.append(ValidationWarning(
            code="delta_no_intersect",
            severity="error",
            message=f"DELTA: WAFERID 교집합 없음 (A {len(a_keys)}장, B {len(b_keys)}장)",
        ))

    # delta_repeats_in_input — A/B 에 __rep 분리된 wafer 존재
    a_reps = sum(1 for k in a_keys if "__rep" in k)
    b_reps = sum(1 for k in b_keys if "__rep" in k)
    if a_reps or b_reps:
        if a_reps and b_reps:
            msg = (f"DELTA: A {a_reps}건 + B {b_reps}건 WAFERID 중복 — "
                   "첫 측정 set 끼리 계산")
        elif a_reps:
            msg = f"DELTA: A 에 WAFERID 중복 {a_reps}건 — 첫 측정 set 끼리 계산"
        else:
            msg = f"DELTA: B 에 WAFERID 중복 {b_reps}건 — 첫 측정 set 끼리 계산"
        warnings.append(ValidationWarning(
            code="delta_repeats_in_input",
            severity="warn",
            message=msg,
        ))

    # delta_coord_fallback — A/B 의 전체 좌표 누락 시 fallback 경로 알림.
    # 사용자 정책 (2026-04-27): A 기준 → A 있으면 A, A 없고 B 있으면 B, 양쪽 다
    # 없으면 라이브러리. 라이브러리 매칭 실패 시 error → Run 비활성.
    a_has = _has_coord_paras(a)
    b_has = _has_coord_paras(b)
    if not a_has and b_has:
        warnings.append(ValidationWarning(
            code="delta_coord_fallback",
            severity="warn",
            message="DELTA: A 좌표 누락 — B 좌표 사용",
        ))
    elif not a_has and not b_has:
        if _library_can_resolve(a, b):
            warnings.append(ValidationWarning(
                code="delta_coord_fallback",
                severity="warn",
                message="DELTA: 양쪽 좌표 누락 — 라이브러리 좌표 사용",
            ))
        else:
            warnings.append(ValidationWarning(
                code="delta_coord_unresolved",
                severity="error",
                message="DELTA: 양쪽 좌표 누락 + 라이브러리 매칭 없음 — 시각화 불가",
            ))
    # A 있고 B 전체 누락 케이스: A 좌표 사용. 별도 메시지 없음 (정상 처리).
    # A 일부 누락 / B 일부 누락은 input_validation case 3 (paste 메시지) 영역.

    return warnings
