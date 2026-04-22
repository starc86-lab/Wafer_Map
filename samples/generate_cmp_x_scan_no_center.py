"""CMP X-scan 샘플 — **센터 지나지 않는** 오프셋 라인 스캔.

- X scan: -140 ~ +140 mm, 5mm step (57 points)
- **Y = 20 고정 (offset)** → r_min = 20, 센터 측정 없음
- 5 wafer, NU% (3σ/avg) = 3·6·9·12·15%
- Profile: M-shape (기존 center-included 샘플과 동일 radial profile)

센터 영역 (r < 20) 은 측정 없음 → RadialInterp 기존엔 flat, mirror spline 은 smooth.

출력: samples/cmp_x_scan_no_center.csv
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

OUT = Path(__file__).parent / "cmp_x_scan_no_center.csv"

AVG = 3000.0
X_START, X_END, X_STEP = -140, 140, 5
Y_OFFSET = 20.0   # 센터 비껴 지남
NU_PCTS = [3.0, 6.0, 9.0, 12.0, 15.0]
WAFER_LOT = "RK2A_CMP_OFF"
RECIPE = "CMP_POLISH_OFFSET_LINE"
STEPDESC = "CMP POST THK OFFSET"
MACHINE = "MTCM02"
DATE = "2026-04-22 14:00"

HEADER = [
    "ETC1", "DATE", "MACHINE", "OPERATINID", "ETC2", "ETC3",
    "STEPDESC", "RECIPE", "LOT ID", "WAFERID", "Slot ID",
    "PARAMETER", "MAX_DATA_ID",
]


def m_shape(r: np.ndarray) -> np.ndarray:
    """[-1, +1] 정규화 M-shape: r=0/145 → -1, r≈72.5 → +1."""
    return 1.0 - 2.0 * ((r - 72.5) / 72.5) ** 2


def generate_wafer_v(nu_pct: float, rng: np.random.Generator) -> np.ndarray:
    x = np.arange(X_START, X_END + 1, X_STEP, dtype=float)
    y = np.full_like(x, Y_OFFSET)
    r = np.sqrt(x * x + y * y)
    shape = m_shape(r)
    target_sigma = nu_pct * AVG / 100.0 / 3.0
    amp = target_sigma / (float(np.std(shape)) * AVG)
    signal = AVG * (1.0 + amp * shape)
    meas_noise = rng.normal(0, target_sigma * 0.15, size=x.size)
    return signal + meas_noise


def main() -> None:
    rng = np.random.default_rng(2026)
    x_vals = np.arange(X_START, X_END + 1, X_STEP, dtype=float)
    y_vals = np.full_like(x_vals, Y_OFFSET)
    n = x_vals.size
    data_cols = [f"DATA{i + 1}" for i in range(n)]

    rows = [HEADER + data_cols]
    for slot_idx, nu in enumerate(NU_PCTS, start=1):
        waferid = f"{WAFER_LOT}.{slot_idx:02d}"
        v = generate_wafer_v(nu, rng)
        actual_nu = 3.0 * float(np.std(v)) / float(np.mean(v)) * 100.0
        r_vals = np.sqrt(x_vals**2 + y_vals**2)
        print(f"  {waferid}: target NU={nu:.1f}%, measured {actual_nu:.2f}%, "
              f"r_min={r_vals.min():.1f}mm, n={n}")
        base = [
            "XX", DATE, MACHINE, "OP002", "", "",
            STEPDESC, RECIPE, WAFER_LOT, waferid, str(slot_idx),
        ]
        rows.append(base + ["T1", str(n)] + [f"{x:.3f}" for x in v])
        rows.append(base + ["X", str(n)] + [f"{x:.1f}" for x in x_vals])
        rows.append(base + ["Y", str(n)] + [f"{y:.1f}" for y in y_vals])

    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerows(rows)
    print(f"\nsaved: {OUT}  ({len(rows) - 1} rows, n={n}, y_offset={Y_OFFSET}mm)")


if __name__ == "__main__":
    main()
