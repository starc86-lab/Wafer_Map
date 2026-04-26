"""
DELTA 계산 — 두 `ParseResult` 사이의 WAFERID 매칭 + (A − B).

규칙 (CLAUDE.md + 사용자 정책 2026-04-27):
- 웨이퍼 매칭 키: `WAFERID` (영구 불변)
- 좌표: 호출자가 사전 결정해서 wafer 별 dict 로 전달.
  좌표 fallback 정책 (Input A 기준):
    A 전체 좌표 있음 → A 좌표 사용 (wafer 별)
    A 전체 누락 + B 전체 있음 → B 좌표 사용
    A, B 양쪽 누락 → 라이브러리 (A RECIPE → B RECIPE)
- 점 매칭: **인덱스 매칭** (silent). 사용자 책임 — 측정 순서가 양쪽 동일하다는 가정.
  (이전 0.2.0: `match_points` 좌표 매칭. 새 정책: 좌표가 한쪽 것이라
  좌표 매칭 의미 없음 → 인덱스로 통일.)
- 부호: **A − B 고정**
- 웨이퍼 수 불일치 허용: 교집합만 출력
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

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
    delta_v: np.ndarray     # (A − B), 인덱스 매칭


@dataclass
class DeltaResult:
    deltas: list[DeltaWafer]
    count_a: int            # A 입력 웨이퍼 수
    count_b: int            # B 입력 웨이퍼 수
    matched: int            # 시각화 성공한 wafer 수
    no_coord_match: list[str] = field(default_factory=list)
    missing_parameter: list[str] = field(default_factory=list)


def compute_delta(
    a: ParseResult,
    b: ParseResult,
    value_name: str,
    coords_per_wafer: dict[str, tuple[np.ndarray, np.ndarray]],
) -> DeltaResult:
    """WAFERID 교집합 + 인덱스 기반 A − B.

    Args:
        coords_per_wafer: {wafer_id: (x_mm, y_mm)} — 호출자가 사전 결정한
            wafer 별 좌표. 좌표 fallback 로직은 호출자 책임 (`_visualize_delta`).

    Returns:
        DeltaResult. `matched=0` 이면 호출자가 시각화 차단.
    """
    common = sorted(set(a.wafers) & set(b.wafers) & coords_per_wafer.keys())
    deltas: list[DeltaWafer] = []
    no_match: list[str] = []

    for wid in common:
        wa = a.wafers[wid]
        wb = b.wafers[wid]
        x_coord, y_coord = coords_per_wafer[wid]
        x_coord = np.asarray(x_coord, dtype=float)
        y_coord = np.asarray(y_coord, dtype=float)

        has_va = value_name in wa.parameters
        has_vb = value_name in wb.parameters
        va = (np.asarray(wa.parameters[value_name].values, dtype=float)
              if has_va else None)
        vb = (np.asarray(wb.parameters[value_name].values, dtype=float)
              if has_vb else None)

        # 인덱스 매칭 — 좌표 / 측정값 길이의 최소값까지.
        n = min(len(x_coord), len(y_coord))
        if va is not None:
            n = min(n, len(va))
        if vb is not None:
            n = min(n, len(vb))
        if n == 0:
            no_match.append(wid)
            continue

        # VALUE 양쪽 다 있을 때만 실제 delta, 아니면 NaN
        if va is not None and vb is not None:
            dv = va[:n] - vb[:n]
        else:
            dv = np.full(n, np.nan, dtype=float)

        deltas.append(DeltaWafer(
            wafer_id=wid,
            lot_a=wa.lot_id, slot_a=wa.slot_id,
            lot_b=wb.lot_id, slot_b=wb.slot_id,
            x_mm=x_coord[:n], y_mm=y_coord[:n],
            delta_v=dv,
        ))

    return DeltaResult(
        deltas=deltas,
        count_a=len(a.wafers),
        count_b=len(b.wafers),
        matched=len(deltas),
        no_coord_match=no_match,
    )
