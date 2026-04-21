"""CMP X-scan 샘플 CSV 생성 — 10 wafer, NU% (3σ/avg) = 3·6·9·12·15% 각 2 세트.

- X scan: -145 ~ +145 mm, 5mm step (59 points)
- Y = 0 (전부)
- avg 기준 3000 Å, NU% = 3σ/avg × 100
- 각 wafer 마다 T1 (두께) / X / Y 3개 PARAMETER row

**세트 1 (slot 1~5):** M-shape (center low, mid r≈72 high, edge low) + 소량 측정 노이즈
**세트 2 (slot 6~10):** 완전 랜덤 (M-shape 없이 pure Gaussian noise)

출력: samples/cmp_x_scan.csv
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

OUT = Path(__file__).parent / "cmp_x_scan.csv"

AVG = 3000.0  # Å
X_START, X_END, X_STEP = -145, 145, 5
NU_PCTS = [3.0, 6.0, 9.0, 12.0, 15.0]
WAFER_LOT = "RK2A_CMP"
RECIPE = "CMP_POLISH_LINE_SCAN"
STEPDESC = "CMP POST THK"
MACHINE = "MTCM01"
DATE = "2026-04-21 10:00"

HEADER = [
    "ETC1", "DATE", "MACHINE", "OPERATINID", "ETC2", "ETC3",
    "STEPDESC", "RECIPE", "LOT ID", "WAFERID", "Slot ID",
    "PARAMETER", "MAX_DATA_ID",
]


def m_shape(r: np.ndarray) -> np.ndarray:
    """[-1, +1] 정규화 M-shape: r=0,145 → -1, r≈72.5 → +1."""
    return 1.0 - 2.0 * ((r - 72.5) / 72.5) ** 2


def generate_wafer_v_mshape(nu_pct: float, rng: np.random.Generator) -> np.ndarray:
    """target NU% (3σ/avg) 만족하는 M-shape thickness 값."""
    x = np.arange(X_START, X_END + 1, X_STEP, dtype=float)
    r = np.abs(x)  # y=0 이므로 r = |x|
    shape = m_shape(r)
    # amp = target_sigma / (std(shape) * AVG), target_sigma = NU%*AVG/100/3
    target_sigma = nu_pct * AVG / 100.0 / 3.0
    amp = target_sigma / (float(np.std(shape)) * AVG)
    # 신호 (M shape) + 소량 측정 노이즈 (전체 NU 의 15%)
    signal = AVG * (1.0 + amp * shape)
    meas_noise = rng.normal(0, target_sigma * 0.15, size=x.size)
    v = signal + meas_noise
    return v


def generate_wafer_v_random(nu_pct: float, rng: np.random.Generator) -> np.ndarray:
    """target NU% (3σ/avg) 만족하는 완전 랜덤 thickness 값 (M-shape 없음)."""
    n = np.arange(X_START, X_END + 1, X_STEP).size
    target_sigma = nu_pct * AVG / 100.0 / 3.0
    return AVG + rng.normal(0, target_sigma, size=n)


def main() -> None:
    rng = np.random.default_rng(42)
    x_vals = np.arange(X_START, X_END + 1, X_STEP, dtype=float)
    y_vals = np.zeros_like(x_vals)
    n = x_vals.size
    data_cols = [f"DATA{i + 1}" for i in range(n)]

    rows = []
    rows.append(HEADER + data_cols)

    # 세트 1: M-shape (slot 1~5)
    print("[Set 1: M-shape]")
    for slot_idx, nu in enumerate(NU_PCTS, start=1):
        waferid = f"{WAFER_LOT}.{slot_idx:02d}"
        slot = str(slot_idx)
        v = generate_wafer_v_mshape(nu, rng)
        actual_nu = 3.0 * float(np.std(v)) / float(np.mean(v)) * 100.0
        print(f"  Wafer {waferid}: target NU={nu:.1f}%, "
              f"measured {actual_nu:.2f}%, "
              f"range [{v.min():.1f}, {v.max():.1f}] avg {v.mean():.1f}")

        base = [
            "XX", DATE, MACHINE, "OP001", "", "",
            STEPDESC, RECIPE, WAFER_LOT, waferid, slot,
        ]
        rows.append(base + ["T1", str(n)] + [f"{x:.3f}" for x in v])
        rows.append(base + ["X", str(n)] + [f"{x:.1f}" for x in x_vals])
        rows.append(base + ["Y", str(n)] + [f"{y:.1f}" for y in y_vals])

    # 세트 2: 완전 랜덤 (slot 6~10)
    print("[Set 2: Random]")
    for i, nu in enumerate(NU_PCTS):
        slot_idx = 6 + i
        waferid = f"{WAFER_LOT}.{slot_idx:02d}"
        slot = str(slot_idx)
        v = generate_wafer_v_random(nu, rng)
        actual_nu = 3.0 * float(np.std(v)) / float(np.mean(v)) * 100.0
        print(f"  Wafer {waferid}: target NU={nu:.1f}%, "
              f"measured {actual_nu:.2f}%, "
              f"range [{v.min():.1f}, {v.max():.1f}] avg {v.mean():.1f}")

        base = [
            "XX", DATE, MACHINE, "OP001", "", "",
            STEPDESC, RECIPE, WAFER_LOT, waferid, slot,
        ]
        rows.append(base + ["T1", str(n)] + [f"{x:.3f}" for x in v])
        rows.append(base + ["X", str(n)] + [f"{x:.1f}" for x in x_vals])
        rows.append(base + ["Y", str(n)] + [f"{y:.1f}" for y in y_vals])

    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerows(rows)

    print(f"\nsaved: {OUT}  ({len(rows) - 1} rows, {n} data cols)")


if __name__ == "__main__":
    main()
