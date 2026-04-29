"""
DELTA 모드 (양쪽 입력) 정합성 검증 — 두 `ParseResult` 비교.

input_validation 이 단일 입력 검증을 담당하는 것과 같은 패턴. ParseResult 만으로
사전 판단 가능한 항목만 다룸 (compute_delta 호출 불필요).

검사 항목 (사용자 정책 2026-04-28 — 표시 정보 최소화):
- `delta_no_intersect`     — A·B 의 WAFERID 교집합 0 (severity=error, Run 차단)
- `delta_coord_unresolved` — 좌표 fallback 실패 (severity=error, Run 차단). 어느 쪽
  좌표가 없는지 메시지에 명시. fallback **성공** 케이스는 의도된 자동 동작이라
  알림 X (이전 `delta_coord_fallback` ok 제거).
- `delta_repeats_in_input` — A 또는 B 에 `__rep` 분리된 wafer 존재 (severity=warn).
- `delta_no_common_value_para` — A∩B VALUE PARA = ∅ (severity=warn).
- `delta_recipe_mismatch`  — A·B 의 RECIPE 다름 (severity=warn).

호출자:
- 호출 시점: paste 변경 직후 (양쪽 ParseResult 모두 있을 때) 한 번
- 결과 cache 후 `_refresh_controls` (Run 활성화 결정) + ReasonBar 표시 양쪽에서 재사용

ValidationWarning 은 `core.input_validation` 의 dataclass 재사용 — 같은 표시 채널
(ReasonBar / paste 라벨) 에서 일관되게 다룰 수 있도록.
"""
from __future__ import annotations

from core.auto_select import _is_coord_name, select_xy_pairs
from core.input_validation import ValidationWarning
from core.recipe_util import recipes_compatible as _recipes_compatible
from core.settings import load_settings
from main import ParseResult


def _xy_para_names(para_names: set[str]) -> set[str]:
    """주어진 PARA 이름 집합에서 좌표 PARA (X/Y, X_*, Y_*) 만 추출.

    `select_xy_pairs` 의 페어링·n 매칭은 우회 — 단순 이름 패턴 매칭만 (auto_select
    의 `_is_coord_name`). value PARA 교집합 비교 시 좌표 PARA 제외용.
    """
    return {n for n in para_names if _is_coord_name(n)}


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


def _wafer_has_xy(wafer) -> bool:
    """단일 wafer 에 X/Y 페어가 페어로 있는지 — `select_xy_pairs` 동일 룰 사용.

    paste 시점 부분 누락 검출용 — 사용자가 선택한 정확한 X/Y 이름을 모르므로
    generic 'X/Y 페어 PARA 가 wafer 자체에 있는지' 만 판정.
    """
    ns: dict[str, int] = {n: rec.n for n, rec in wafer.parameters.items()}
    if not ns:
        return False
    auto = load_settings().get("auto_select", {})
    xpat = auto.get("x_patterns", ["X", "X*"])
    ypat = auto.get("y_patterns", ["Y", "Y*"])
    _, _, x_ord, _ = select_xy_pairs(ns, xpat, ypat)
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
            message="WAFERID 교집합 없음",
        ))

    # delta_repeats_in_input — A/B 에 __rep 분리된 wafer 존재
    # 사내 시스템 정책: 첫 set 이 시간상 가장 최신 측정 → 첫 set 사용 = 최신 측정 사용
    a_reps = sum(1 for k in a_keys if "__rep" in k)
    b_reps = sum(1 for k in b_keys if "__rep" in k)
    if a_reps or b_reps:
        if a_reps and b_reps:
            msg = (f"A 웨이퍼 중복 {a_reps}건, B 웨이퍼 중복 {b_reps}건, "
                   "최신 측정 데이터 사용")
        elif a_reps:
            msg = f"A에 웨이퍼 중복 {a_reps}건, 최신 측정 데이터 사용"
        else:
            msg = f"B에 웨이퍼 중복 {b_reps}건, 최신 측정 데이터 사용"
        warnings.append(ValidationWarning(
            code="delta_repeats_in_input",
            severity="warn",
            message=msg,
        ))

    # delta_coord_unresolved — 좌표 fallback **실패** 케이스만 표시 (사용자 정책
    # 2026-04-28). fallback 성공 (옆집 / 라이브러리) 은 의도된 자동 동작이라 알림 X.
    a_has = _has_coord_paras(a)
    b_has = _has_coord_paras(b)
    ra = _first_recipe(a)
    rb = _first_recipe(b)
    can_borrow = _recipes_compatible(ra, rb)

    def _lib_has(recipe: str) -> bool:
        from core.coord_library import CoordLibrary
        return bool(recipe) and bool(CoordLibrary().find_by_recipe(recipe))

    if not (a_has and b_has):
        # 어느 한쪽 (또는 양쪽) 좌표 누락 — fallback 매트릭스에서 실패 분기만 메시지
        if a_has and not b_has:
            if not can_borrow and not _lib_has(rb):
                warnings.append(ValidationWarning(
                    code="delta_coord_unresolved", severity="error",
                    message="B 좌표 없음",
                ))
        elif b_has and not a_has:
            if not can_borrow and not _lib_has(ra):
                warnings.append(ValidationWarning(
                    code="delta_coord_unresolved", severity="error",
                    message="A 좌표 없음",
                ))
        else:  # 양쪽 모두 누락
            failed = (
                (can_borrow and not (_lib_has(ra) or _lib_has(rb))) or
                (not can_borrow and not (_lib_has(ra) and _lib_has(rb)))
            )
            if failed:
                warnings.append(ValidationWarning(
                    code="delta_coord_unresolved", severity="error",
                    message="A, B 좌표 없음",
                ))

    # delta_partial_coord — A 또는 B 의 일부 wafer 만 좌표 PARA 누락 (사용자 정책
    # 2026-04-30). _resolve_delta_coords 가 all-or-nothing per side 로 동작 →
    # 부분 누락 시 silently 다른 fallback 매트릭스 branch 따라가서 사용자 데이터
    # 의도와 다를 수 있음 (자기 좌표 있는 wafer 까지 옆집 좌표로 덮임).
    if common:
        total = len(common)
        a_miss = [wid for wid in common if not _wafer_has_xy(a.wafers[wid])]
        b_miss = [wid for wid in common if not _wafer_has_xy(b.wafers[wid])]
        if 0 < len(a_miss) < total:
            warnings.append(ValidationWarning(
                code="delta_a_partial_coord", severity="warn",
                message=f"A 일부 wafer 좌표 누락 ({len(a_miss)}/{total})",
            ))
        if 0 < len(b_miss) < total:
            warnings.append(ValidationWarning(
                code="delta_b_partial_coord", severity="warn",
                message=f"B 일부 wafer 좌표 누락 ({len(b_miss)}/{total})",
            ))

    # delta_no_common_value_para — A∩B VALUE PARA = ∅
    # 좌표 PARA (X/Y) 는 제외하고 비교. 한쪽만 가진 PARA 도 union 으로 콤보에
    # 노출되어 시각화 가능 (NaN 룰 적용) — 그래도 사용자 인지를 위해 알림.
    if common:
        a_paras: set[str] = set()
        b_paras: set[str] = set()
        for wid in common:
            a_paras.update(a.wafers[wid].parameters.keys())
            b_paras.update(b.wafers[wid].parameters.keys())
        # 좌표 PARA 제외 (X*, Y*) — 측정값 PARA 만 비교
        a_value_paras = a_paras - _xy_para_names(a_paras)
        b_value_paras = b_paras - _xy_para_names(b_paras)
        if a_value_paras and b_value_paras and not (a_value_paras & b_value_paras):
            warnings.append(ValidationWarning(
                code="delta_no_common_value_para",
                severity="warn",
                message="공통 PARA 없음",
            ))

    # delta_recipe_mismatch — RECIPE 다름 (PRE/POST 호환 룰 적용 후)
    if ra and rb and not _recipes_compatible(ra, rb):
        warnings.append(ValidationWarning(
            code="delta_recipe_mismatch",
            severity="warn",
            message="RECIPE 다름",
        ))

    return warnings
