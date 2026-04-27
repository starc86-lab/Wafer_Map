"""
DELTA 계산 — 두 `ParseResult` 사이의 WAFERID 매칭 + (A − B).

규칙 (CLAUDE.md + 사용자 정책 2026-04-27):
- 웨이퍼 매칭 키: `WAFERID` (영구 불변)
- 좌표: 호출자가 사전 결정해서 wafer 별 ((xa, ya), (xb, yb)) tuple 로 전달.
  좌표 fallback 정책은 호출자 (`_visualize_delta`) 의 책임.
- 점 매칭: **좌표 합집합 + 1:1 매칭** (`union_match`) + NaN 룰
  - 양쪽 매칭 점: dv = va - vb (정상)
  - A only 점: dv = va (B 가 0 으로 가정)
  - B only 점: dv = -vb (A 가 0 으로 가정)
- VALUE PARA 도 동일 NaN 룰 — A 만 가진 PARA (예: T2) 선택 시 vb=None →
  모든 점에서 dv = va (B 측정값 0 으로 가정). 콤보에 합집합 표시되어 한쪽만
  있는 PARA 도 시각화 가능. 측정 실패 셀 (NaN) 은 그대로 NaN.
- 좌표 같은 케이스 (양쪽 동일) 는 모든 점 매칭됨 → 기존 동작과 같음.
  좌표 다른 케이스만 outlier 시각화로 사용자 인지.
- 부호: **A − B 고정**
- 웨이퍼 수 불일치 허용: 교집합만 출력
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.coords import union_match
from main import ParseResult


# 좌표 매칭 tolerance — 직선거리 mm. 사용자 정책 (2026-04-27): 측정 grid spacing
# 고려 (보통 5~30mm) + 좌표 정밀도 오차 → 1mm 가 적정.
DELTA_COORD_TOLERANCE_MM = 1.0


@dataclass
class DeltaWafer:
    wafer_id: str
    lot_a: str
    slot_a: str
    lot_b: str
    slot_b: str
    x_mm: np.ndarray
    y_mm: np.ndarray
    delta_v: np.ndarray             # (A − B), 합집합 점
    interp_indices: np.ndarray = field(default_factory=lambda: np.array([], dtype=int))
    """Δ-Interp mode 로 보간값 채워진 점의 인덱스 (시각화 마커용). 비활성 시 빈 array."""


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
    coords_per_wafer: dict[str, tuple[tuple[np.ndarray, np.ndarray],
                                       tuple[np.ndarray, np.ndarray]]],
    tolerance_mm: float = DELTA_COORD_TOLERANCE_MM,
    *,
    interp_factory=None,
) -> DeltaResult:
    """WAFERID 교집합 + 좌표 합집합 매칭 A − B.

    Args:
        coords_per_wafer: {wafer_id: ((xa, ya), (xb, yb))} — 호출자가 사전 결정.
            양쪽 좌표 같으면 동일 ndarray 두 번 (옆집 빌리기 케이스).
            양쪽 다르면 각자 좌표 → 합집합 매칭.
        tolerance_mm: 좌표 매칭 거리 (직선, mm).
        interp_factory: Δ-Interp mode 활성 시 — `(x, y, v) -> interp_obj` callable.
            None 이면 비활성 (NaN 룰 = `va` / `-vb`). 활성 시 a_only/b_only 점에서
            상대 측정값을 RBF 보간으로 채워 정상 delta. 보간 점 인덱스는
            `DeltaWafer.interp_indices` 에 기록 (시각화 마커용).

    Returns:
        DeltaResult. `matched=0` 이면 호출자가 시각화 차단.
    """
    common = sorted(set(a.wafers) & set(b.wafers) & coords_per_wafer.keys())
    deltas: list[DeltaWafer] = []
    no_match: list[str] = []

    for wid in common:
        wa = a.wafers[wid]
        wb = b.wafers[wid]
        (xa_full, ya_full), (xb_full, yb_full) = coords_per_wafer[wid]
        xa_full = np.asarray(xa_full, dtype=float)
        ya_full = np.asarray(ya_full, dtype=float)
        xb_full = np.asarray(xb_full, dtype=float)
        yb_full = np.asarray(yb_full, dtype=float)

        has_va = value_name in wa.parameters
        has_vb = value_name in wb.parameters
        va = (np.asarray(wa.parameters[value_name].values, dtype=float)
              if has_va else None)
        vb = (np.asarray(wb.parameters[value_name].values, dtype=float)
              if has_vb else None)

        # 좌표 / 측정값 길이 정렬 — 좌표가 더 긴 경우 측정값 길이만 사용
        n_a = min(len(xa_full), len(ya_full))
        if va is not None:
            n_a = min(n_a, len(va))
        n_b = min(len(xb_full), len(yb_full))
        if vb is not None:
            n_b = min(n_b, len(vb))
        if n_a == 0 and n_b == 0:
            no_match.append(wid)
            continue
        xa, ya = xa_full[:n_a], ya_full[:n_a]
        xb, yb = xb_full[:n_b], yb_full[:n_b]
        if va is not None:
            va = va[:n_a]
        if vb is not None:
            vb = vb[:n_b]

        # 합집합 매칭
        pairs, a_only, b_only = union_match(xa, ya, xb, yb, tolerance_mm)
        n_total = len(pairs) + len(a_only) + len(b_only)
        if n_total == 0:
            no_match.append(wid)
            continue

        x_out = np.zeros(n_total)
        y_out = np.zeros(n_total)
        dv = np.zeros(n_total, dtype=float)

        # 측정 없음 (PARA 자체 X 또는 인덱스 초과) → 0 처리. 단 측정 셀 NaN 은 그대로.
        def _safe_v(arr, idx):
            if arr is None or idx >= len(arr):
                return 0.0
            return float(arr[idx])

        # Δ-Interp mode — a_only / b_only 점에 상대 측정값을 RBF 보간으로 채움.
        # interp_factory(x, y, v) → 보간 obj. obj((N,2)) → values_N.
        interp_a = interp_b = None
        if interp_factory is not None and (a_only or b_only):
            if va is not None and len(xa) > 0:
                try:
                    interp_a = interp_factory(xa, ya, va)
                except Exception:
                    interp_a = None
            if vb is not None and len(xb) > 0:
                try:
                    interp_b = interp_factory(xb, yb, vb)
                except Exception:
                    interp_b = None

        interp_idx_list: list[int] = []

        k = 0
        # 양쪽 매칭 점
        for ia, ib in pairs:
            x_out[k] = xa[ia]; y_out[k] = ya[ia]
            dv[k] = _safe_v(va, ia) - _safe_v(vb, ib)
            k += 1
        # A only 점 (B 좌표 매칭 X) — dv = va - vb_interp(at A)
        for ia in a_only:
            x_out[k] = xa[ia]; y_out[k] = ya[ia]
            a_val = _safe_v(va, ia)
            if interp_b is not None:
                try:
                    pt = np.asarray([[xa[ia], ya[ia]]], dtype=float)
                    b_val = float(interp_b(pt)[0])
                    interp_idx_list.append(k)
                except Exception:
                    b_val = 0.0
            else:
                b_val = 0.0
            dv[k] = a_val - b_val
            k += 1
        # B only 점 (A 좌표 매칭 X) — dv = va_interp(at B) - vb
        for ib in b_only:
            x_out[k] = xb[ib]; y_out[k] = yb[ib]
            b_val = _safe_v(vb, ib)
            if interp_a is not None:
                try:
                    pt = np.asarray([[xb[ib], yb[ib]]], dtype=float)
                    a_val = float(interp_a(pt)[0])
                    interp_idx_list.append(k)
                except Exception:
                    a_val = 0.0
            else:
                a_val = 0.0
            dv[k] = a_val - b_val
            k += 1

        deltas.append(DeltaWafer(
            wafer_id=wid,
            lot_a=wa.lot_id, slot_a=wa.slot_id,
            lot_b=wb.lot_id, slot_b=wb.slot_id,
            x_mm=x_out, y_mm=y_out,
            delta_v=dv,
            interp_indices=np.asarray(interp_idx_list, dtype=int),
        ))

    return DeltaResult(
        deltas=deltas,
        count_a=len(a.wafers),
        count_b=len(b.wafers),
        matched=len(deltas),
        no_coord_match=no_match,
    )
