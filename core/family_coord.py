"""
가족 (single 입력) 좌표 정책 — 검증 + 좌표 set 결정.

가족 = 한 입력 (A 또는 B) 의 모든 wafer. 가족은 단일 RECIPE 공유 (PRE/POST 호환).
가족 내 wafer 들은 공통 좌표 set 들 공유 — 같은 RECIPE 의 같은 좌표 PARA 이름은
좌표값 동일 보장 (사용자 정책 2026-04-30).

본 모듈은 검증 (`validate_family_recipe`) + 좌표 페어 list 추출 + 페어 좌표
조회 헬퍼 제공. 시각화 흐름 (`_visualize_single` 등) 에서 호출.

순환 import 방지를 위해 widgets/main_window 의 `_pad_slot` / `_rep_suffix` 는
자체 구현.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

from core.input_validation import ValidationWarning
from core.recipe_util import recipes_compatible
from main import ParseResult


# ── helpers (main_window 와 동기, 순환 import 회피용 자체 구현) ────────────
def _pad_slot(slot) -> str:
    try:
        return f"{int(slot):02d}"
    except (ValueError, TypeError):
        return str(slot)


def _rep_suffix(wafer_id: str) -> str:
    idx = wafer_id.rfind("__rep")
    if idx < 0:
        return ""
    tail = wafer_id[idx + 2:]
    return f" ({tail})"


def _wafer_label(wafer) -> str:
    """`LX001.07` 또는 `LX001.07 (rep1)` 형식 wafer label."""
    return f"{wafer.lot_id}.{_pad_slot(wafer.slot_id)}{_rep_suffix(wafer.wafer_id)}"


# ── 가족 RECIPE 단일성 검증 ──────────────────────────────────────────────
def family_recipe(result: ParseResult) -> str:
    """가족 RECIPE — 가장 흔한 (mode) recipe 를 baseline 으로 채택.

    하나의 outlier wafer 가 baseline 을 흐트리지 않게 mode 사용. 단,
    `validate_family_recipe` 가 outlier 를 detect 하므로 baseline 자체는
    오염되지 않음.
    """
    if not result.wafers:
        return ""
    counter = Counter(w.recipe for w in result.wafers.values())
    return counter.most_common(1)[0][0]


def validate_family_recipe(result: ParseResult) -> list[ValidationWarning]:
    """가족 RECIPE 단일성 검증 — PRE/POST 베이스 비교로 호환 여부 판정.

    다른 RECIPE wafer 가 있으면 `single_recipe_mismatch` (error). 메시지에
    LOT.SLOT 라벨 + 그 wafer 의 RECIPE + 가족 baseline RECIPE 명시.
    """
    if not result.wafers:
        return []
    base = family_recipe(result)
    mismatched = [
        w for w in result.wafers.values()
        if not recipes_compatible(w.recipe, base)
    ]
    if not mismatched:
        return []
    labels = ", ".join(
        f"{_wafer_label(w)}: {w.recipe}" for w in mismatched
    )
    msg = f"RECIPE 다름 — {labels} vs 가족: {base}"
    return [ValidationWarning(
        code="single_recipe_mismatch",
        severity="error",
        message=msg,
    )]


# ── 가족 좌표 페어 list ──────────────────────────────────────────────────
@dataclass
class FamilyCoord:
    """가족이 보유한 한 좌표 페어 — fallback 시 사용.

    좌표값은 가족 내 그 페어 보유한 wafer 중 **가장 긴 N 의 wafer 좌표**
    (mm 환산 후). 사용자 정책 2026-04-30 — paste 마지막 cell 누락 edge 대응.

    source / lib_id (사용자 정책 2026-04-30, 라이브러리 통합):
      - "family": 가족 wafer 들이 자체 보유한 좌표 (lib_id=None)
      - "library": 라이브러리 entry 에서 가족 list 에 추가됨 (lib_id=entry.id)
    """
    x_name: str
    y_name: str
    n: int
    x_mm: np.ndarray
    y_mm: np.ndarray
    source: str = "family"
    lib_id: int | None = None


def compute_family_coords(
    result: ParseResult,
    added_presets: list | None = None,
) -> list[FamilyCoord]:
    """가족이 보유한 좌표 페어 list. select_xy_pairs 동일 룰로 페어 추출 후
    각 페어 별 가장 긴 N 의 wafer 좌표 (mm 환산) 채택.

    같은 RECIPE 내 같은 좌표 PARA 이름 = 좌표값 동일 보장 (사용자 정책) —
    좌표값 비교 검증 없이 가장 긴 N 채택만.

    `added_presets`: 사용자 명시 추가 / 자동 RECIPE 매칭으로 가족 list 에 추가된
    라이브러리 CoordPreset list. 가족 자체 페어 뒤에 append (사용자 정책 2026-04-30).
    """
    if not result.wafers:
        if added_presets:
            return [_preset_to_family_coord(p) for p in added_presets]
        return []

    # lazy imports — main_window 의존 없음
    from core.auto_select import select_xy_pairs
    from core.coords import normalize_to_mm
    from core.settings import load_settings

    # 가족 PARA union
    union_ns: dict[str, int] = {}
    for w in result.wafers.values():
        for name, rec in w.parameters.items():
            if name not in union_ns:
                union_ns[name] = rec.n

    auto = load_settings().get("auto_select", {})
    xpat = auto.get("x_patterns", ["X", "X*"])
    ypat = auto.get("y_patterns", ["Y", "Y*"])
    _, _, x_ord, y_ord = select_xy_pairs(union_ns, xpat, ypat)

    family_coords: list[FamilyCoord] = []
    for x_name, y_name in zip(x_ord, y_ord):
        # 페어 보유한 wafer 들 중 가장 긴 N
        best_n = 0
        best_x_mm = None
        best_y_mm = None
        for w in result.wafers.values():
            if x_name not in w.parameters or y_name not in w.parameters:
                continue
            xs = w.parameters[x_name].values
            ys = w.parameters[y_name].values
            n = min(len(xs), len(ys))
            if n > best_n:
                x_mm, _ = normalize_to_mm(np.asarray(xs[:n], dtype=float))
                y_mm, _ = normalize_to_mm(np.asarray(ys[:n], dtype=float))
                best_n = n
                best_x_mm = x_mm
                best_y_mm = y_mm
        if best_n > 0 and best_x_mm is not None:
            family_coords.append(FamilyCoord(
                x_name=x_name, y_name=y_name, n=best_n,
                x_mm=best_x_mm, y_mm=best_y_mm,
                source="family",
            ))

    # 라이브러리 추가 entries — 가족 페어 뒤에 append. 동일 (x_name, y_name) 페어가
    # 가족에 이미 있어도 중복 노출 허용 (사용자 정책: 콤보에 둘 다 보임,
    # 자동매칭은 콤보 순서 첫 번째 = 가족 우선).
    if added_presets:
        for p in added_presets:
            family_coords.append(_preset_to_family_coord(p))

    return family_coords


def _preset_to_family_coord(preset) -> FamilyCoord:
    """CoordPreset → FamilyCoord (source='library')."""
    return FamilyCoord(
        x_name=preset.x_name,
        y_name=preset.y_name,
        n=int(preset.n_points),
        x_mm=np.asarray(preset.x_mm, dtype=float),
        y_mm=np.asarray(preset.y_mm, dtype=float),
        source="library",
        lib_id=int(preset.id) if preset.id else None,
    )


def get_family_coord(
    family_coords: list[FamilyCoord], x_name: str, y_name: str,
) -> FamilyCoord | None:
    """좌표 페어 이름으로 FamilyCoord 조회."""
    for fc in family_coords:
        if fc.x_name == x_name and fc.y_name == y_name:
            return fc
    return None


def validate_family_partial(
    result: ParseResult, family_coords: list[FamilyCoord],
) -> list[ValidationWarning]:
    """가족 좌표 페어 별 wafer 누락 / N 부족 검증. info 메시지.

    각 wafer × 각 가족 페어 검사:
      - 페어 PARA 누락 → `family_coord_missing` info: `LX001.07 좌표 누락: X_A/Y_A`
      - 페어 보유했으나 N 가족 max 보다 작음 → `family_coord_short` info:
        `LX001.07 좌표 Point 부족: X (12pt, 1점 부족)`

    각 wafer 별 1건씩 (페어 하나만 누락이면 1건). 사용자 정책 2026-04-30 —
    silent 자동 fallback 이지만 사용자 인지 위해 info 알림.
    """
    if not result.wafers or not family_coords:
        return []

    warnings: list[ValidationWarning] = []
    for w in result.wafers.values():
        for fc in family_coords:
            x_name, y_name = fc.x_name, fc.y_name
            family_n = fc.n

            has_x = x_name in w.parameters
            has_y = y_name in w.parameters
            if not has_x or not has_y:
                # 페어 누락 (X 또는 Y 또는 둘 다)
                warnings.append(ValidationWarning(
                    code="family_coord_missing",
                    severity="info",
                    message=f"{_wafer_label(w)} 좌표 누락: {x_name}/{y_name}",
                ))
                continue

            # 페어 보유 — N 비교
            wn = min(
                len(w.parameters[x_name].values),
                len(w.parameters[y_name].values),
            )
            if wn < family_n:
                short = family_n - wn
                warnings.append(ValidationWarning(
                    code="family_coord_short",
                    severity="info",
                    message=(
                        f"{_wafer_label(w)} 좌표 Point 부족: "
                        f"{x_name} ({wn}pt, {short}점 부족)"
                    ),
                ))
    return warnings
