"""
DELTA 계산 — 두 `ParseResult` 사이의 WAFERID 교집합 + 좌표 일치점 A − B.

규칙 (CLAUDE.md):
- 웨이퍼 매칭 키: `WAFERID` (영구 불변)
- 점 매칭: 같은 WAFERID 내 `(X, Y)` 좌표가 tolerance 내 일치하는 점만
- 부호: **A − B 고정**
- 웨이퍼 수 불일치 허용: 교집합만 출력 (나머지는 조용히 제외)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.coords import match_points, normalize_to_mm
from main import ParseResult


@dataclass
class DeltaWafer:
    wafer_id: str
    lot_a: str
    slot_a: str
    lot_b: str
    slot_b: str
    x_mm: np.ndarray
    y_mm: np.ndarray
    delta_v: np.ndarray     # (A − B), 매칭된 점에 한함


@dataclass
class DeltaResult:
    deltas: list[DeltaWafer]
    count_a: int            # A 입력 웨이퍼 수
    count_b: int            # B 입력 웨이퍼 수
    matched: int            # WAFERID 교집합 + 좌표 매칭 성공한 웨이퍼 수
    no_coord_match: list[str] = field(default_factory=list)
    missing_parameter: list[str] = field(default_factory=list)


def compute_delta(
    a: ParseResult,
    b: ParseResult,
    value_name: str,
    x_name: str,
    y_name: str,
    tolerance_mm: float = 1e-3,
) -> DeltaResult:
    """WAFERID 교집합 + 좌표 일치 점만 A − B.

    반환의 `matched` 가 0이면 호출자가 경고 팝업 후 시각화 차단.
    """
    common = sorted(set(a.wafers) & set(b.wafers))
    deltas: list[DeltaWafer] = []
    no_match: list[str] = []
    missing: list[str] = []

    for wid in common:
        wa = a.wafers[wid]
        wb = b.wafers[wid]

        if not all(
            n in wa.parameters and n in wb.parameters
            for n in (value_name, x_name, y_name)
        ):
            missing.append(wid)
            continue

        xa, _ = normalize_to_mm(wa.parameters[x_name].values)
        ya, _ = normalize_to_mm(wa.parameters[y_name].values)
        va = np.asarray(wa.parameters[value_name].values, dtype=float)
        xb, _ = normalize_to_mm(wb.parameters[x_name].values)
        yb, _ = normalize_to_mm(wb.parameters[y_name].values)
        vb = np.asarray(wb.parameters[value_name].values, dtype=float)

        na = min(len(xa), len(ya), len(va))
        nb = min(len(xb), len(yb), len(vb))
        if na == 0 or nb == 0:
            continue
        xa, ya, va = xa[:na], ya[:na], va[:na]
        xb, yb, vb = xb[:nb], yb[:nb], vb[:nb]

        ia, ib = match_points(xa, ya, xb, yb, tolerance_mm)
        if len(ia) == 0:
            no_match.append(wid)
            continue

        deltas.append(DeltaWafer(
            wafer_id=wid,
            lot_a=wa.lot_id, slot_a=wa.slot_id,
            lot_b=wb.lot_id, slot_b=wb.slot_id,
            x_mm=xa[ia], y_mm=ya[ia],
            delta_v=va[ia] - vb[ib],
        ))

    return DeltaResult(
        deltas=deltas,
        count_a=len(a.wafers),
        count_b=len(b.wafers),
        matched=len(deltas),
        no_coord_match=no_match,
        missing_parameter=missing,
    )
