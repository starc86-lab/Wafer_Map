"""컬러바 자릿수 clipping 테스트용 샘플 - 5/6/7 자리 값 세트.

각 파일:
- 5 wafer, 1D X-scan (center 포함), 59 points
- 동일 M-shape profile, 다른 AVG magnitude
- NU 5% 고정 → range 도 magnitude 따라감

AVG 설정:
- cmp_5digit.csv   : AVG ≈ 12345   (max ~ 13k, 5자리)
- cmp_6digit.csv   : AVG ≈ 123456  (max ~ 130k, 6자리)
- cmp_7digit.csv   : AVG ≈ 1234567 (max ~ 1.3M, 7자리)
- cmp_neg.csv      : AVG ≈ 0, 값 -50000 ~ +50000 (음수 6자리)
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

X_START, X_END, X_STEP = -145, 145, 5
NU_PCT = 5.0
N_WAFERS = 5

HEADER = [
    "ETC1", "DATE", "MACHINE", "OPERATINID", "ETC2", "ETC3",
    "STEPDESC", "RECIPE", "LOT ID", "WAFERID", "Slot ID",
    "PARAMETER", "MAX_DATA_ID",
]


def m_shape(r: np.ndarray) -> np.ndarray:
    return 1.0 - 2.0 * ((r - 72.5) / 72.5) ** 2


def gen_wafer_v(avg: float, nu_pct: float, rng: np.random.Generator) -> np.ndarray:
    x = np.arange(X_START, X_END + 1, X_STEP, dtype=float)
    r = np.abs(x)
    shape = m_shape(r)
    target_sigma = nu_pct * avg / 100.0 / 3.0
    amp = target_sigma / (float(np.std(shape)) * avg)
    signal = avg * (1.0 + amp * shape)
    noise = rng.normal(0, target_sigma * 0.15, size=x.size)
    return signal + noise


def gen_wafer_centered(center: float, width: float, rng: np.random.Generator) -> np.ndarray:
    """center 중심, ±width/2 범위 M-shape (음수 지원용)."""
    x = np.arange(X_START, X_END + 1, X_STEP, dtype=float)
    r = np.abs(x)
    shape = m_shape(r)  # -1 ~ +1
    signal = center + (width / 2.0) * shape
    noise = rng.normal(0, width * 0.02, size=x.size)
    return signal + noise


def write_csv(path: Path, avg_per_wafer: list[float], nu_pct: float,
              lot: str, recipe: str, stepdesc: str):
    rng = np.random.default_rng(hash(path.name) & 0xFFFFFFFF)
    x_vals = np.arange(X_START, X_END + 1, X_STEP, dtype=float)
    y_vals = np.zeros_like(x_vals)
    n = x_vals.size
    data_cols = [f"DATA{i + 1}" for i in range(n)]
    rows = [HEADER + data_cols]
    for slot_idx, avg in enumerate(avg_per_wafer, start=1):
        wid = f"{lot}.{slot_idx:02d}"
        v = gen_wafer_v(avg, nu_pct, rng)
        actual = 3.0 * float(np.std(v)) / float(np.mean(v)) * 100.0
        print(f"  {wid}: AVG={avg:.1f}, NU={actual:.2f}%, "
              f"range [{v.min():.1f}, {v.max():.1f}]")
        base = ["XX", "2026-04-22 15:00", "MTCM01", "OP001", "", "",
                stepdesc, recipe, lot, wid, str(slot_idx)]
        rows.append(base + ["T1", str(n)] + [f"{x:.3f}" for x in v])
        rows.append(base + ["X", str(n)] + [f"{x:.1f}" for x in x_vals])
        rows.append(base + ["Y", str(n)] + [f"{y:.1f}" for y in y_vals])
    with path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"saved: {path}  ({len(rows)-1} rows)\n")


def write_neg(path: Path, lot: str):
    """음수 포함 - DELTA 느낌. 중심값 0 근처, 범위 ±width."""
    rng = np.random.default_rng(hash(path.name) & 0xFFFFFFFF)
    x_vals = np.arange(X_START, X_END + 1, X_STEP, dtype=float)
    y_vals = np.zeros_like(x_vals)
    n = x_vals.size
    data_cols = [f"DATA{i + 1}" for i in range(n)]
    rows = [HEADER + data_cols]
    # 5 wafer: 점점 큰 range
    widths = [1000, 10000, 100000, 500000, 1000000]
    for slot_idx, width in enumerate(widths, start=1):
        wid = f"{lot}.{slot_idx:02d}"
        v = gen_wafer_centered(0.0, width, rng)
        print(f"  {wid}: range [{v.min():.1f}, {v.max():.1f}]")
        base = ["XX", "2026-04-22 15:00", "MTCM01", "OP001", "", "",
                "DELTA TEST", "TEST_NEG", lot, wid, str(slot_idx)]
        rows.append(base + ["T1", str(n)] + [f"{x:.3f}" for x in v])
        rows.append(base + ["X", str(n)] + [f"{x:.1f}" for x in x_vals])
        rows.append(base + ["Y", str(n)] + [f"{y:.1f}" for y in y_vals])
    with path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"saved: {path}  ({len(rows)-1} rows)\n")


def main():
    out = Path(__file__).parent

    print("[5 digit - AVG ~12345]")
    write_csv(out / "cmp_5digit.csv",
              [12345, 23456, 34567, 45678, 56789],
              nu_pct=NU_PCT,
              lot="LOT5D", recipe="TEST_5D", stepdesc="5 DIGIT TEST")

    print("[6 digit - AVG ~123456]")
    write_csv(out / "cmp_6digit.csv",
              [123456, 234567, 345678, 456789, 567890],
              nu_pct=NU_PCT,
              lot="LOT6D", recipe="TEST_6D", stepdesc="6 DIGIT TEST")

    print("[7 digit - AVG ~1234567]")
    write_csv(out / "cmp_7digit.csv",
              [1234567, 2345678, 3456789, 4567890, 5678901],
              nu_pct=NU_PCT,
              lot="LOT7D", recipe="TEST_7D", stepdesc="7 DIGIT TEST")

    print("[negative range]")
    write_neg(out / "cmp_neg.csv", "LOTNEG")


if __name__ == "__main__":
    main()
