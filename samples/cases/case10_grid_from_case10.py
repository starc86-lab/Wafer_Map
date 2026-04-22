"""case10 의 radial 좌표 데이터를 바둑판식(grid) 좌표로 재배치.

각 wafer 의 (r_meas, T1_meas) → 1D spline 적합 → 30mm 격자점에서 재평가.
N=70 → grid ~78 points (wafer 반경 145 안).
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from scipy.interpolate import UnivariateSpline

SRC = Path(__file__).parent / "case10_delta_A_preEtch_6wafers.csv"
DST = Path(__file__).parent / "case10_grid_A_preEtch_6wafers.csv"

GRID_STEP = 30.0
GRID_MAX = 145.0  # wafer 반경 안쪽만
SHIFT_X = 3.0     # 격자 원점 오프셋 (r overlap 방지)
SHIFT_Y = 2.0


def load_wafers() -> dict[str, dict[str, np.ndarray]]:
    with SRC.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    h = rows[0]
    iw = h.index("WAFERID"); ip = h.index("PARAMETER"); im = h.index("MAX_DATA_ID")
    data0 = im + 1
    wafers: dict[str, dict[str, np.ndarray]] = {}
    meta: dict[str, list[str]] = {}
    for r in rows[1:]:
        wid = r[iw]; n = int(r[im])
        vals = np.array([float(x) for x in r[data0:data0 + n]])
        wafers.setdefault(wid, {})[r[ip]] = vals
        meta[wid] = r[:im + 1]  # META 부분 (ETC~MAX_DATA_ID 까지 원본 유지)
    return wafers, meta, h


def grid_xy() -> tuple[np.ndarray, np.ndarray]:
    g = np.arange(-150 + GRID_STEP / 2, 150, GRID_STEP)
    X, Y = np.meshgrid(g + SHIFT_X, g + SHIFT_Y)
    X = X.ravel(); Y = Y.ravel()
    r = np.sqrt(X * X + Y * Y)
    m = r <= GRID_MAX
    return X[m], Y[m]


def resample_wafer(wafer: dict, gx: np.ndarray, gy: np.ndarray,
                   rng: np.random.Generator) -> np.ndarray:
    x = wafer["X"]; y = wafer["Y"]; t1 = wafer["T1"]
    r_meas = np.sqrt(x * x + y * y)
    # quantize + 같은 r 평균 → r_u, v_u
    r_round = np.round(r_meas, 3)
    r_u, inv = np.unique(r_round, return_inverse=True)
    v_u = np.zeros_like(r_u, dtype=float); cnt = np.zeros_like(r_u, dtype=float)
    np.add.at(v_u, inv, t1); np.add.at(cnt, inv, 1)
    v_u = v_u / cnt
    # 적당한 smoothing 으로 1D 프로파일 적합
    s_val = len(r_u) * float(np.std(np.diff(v_u)) ** 2 / 2.0) * 3.0
    try:
        sp = UnivariateSpline(r_u, v_u, k=3, s=s_val, ext=3)
    except Exception:
        from scipy.interpolate import interp1d
        sp = interp1d(r_u, v_u, kind="cubic", bounds_error=False,
                      fill_value=(v_u[0], v_u[-1]))
    r_grid = np.sqrt(gx * gx + gy * gy)
    v_grid = sp(r_grid)
    # 원본 측정 노이즈 수준 ~ σ 계산해서 추가
    meas_noise_sigma = float(np.std(t1 - sp(r_meas)))
    v_grid = v_grid + rng.normal(0, meas_noise_sigma, size=v_grid.size)
    return v_grid


def main() -> None:
    wafers, meta, header = load_wafers()
    gx, gy = grid_xy()
    n = gx.size
    rng = np.random.default_rng(2026)

    iw = header.index("WAFERID")
    ip = header.index("PARAMETER")
    im = header.index("MAX_DATA_ID")

    data_cols = [f"DATA{i + 1}" for i in range(n)]
    new_header = header[:im + 1] + data_cols

    out_rows = [new_header]
    for wid in sorted(wafers.keys()):
        wf = wafers[wid]
        if "T1" not in wf or "X" not in wf or "Y" not in wf:
            continue
        t1_grid = resample_wafer(wf, gx, gy, rng)
        # GOF 는 단순 복제 (없어도 앱 파싱 OK — 필수 아님)
        # META 원본에서 첫 번째 T1 row 를 꺼내 모양만 복사
        base_meta = meta[wid][:im + 1]
        # PARAMETER 컬럼이 meta 에 포함돼 있음 → 각 row 마다 해당 값으로 대체
        # X row
        r = list(base_meta); r[ip] = "X"; r[im] = str(n)
        out_rows.append(r + [f"{v:.3f}" for v in gx])
        r = list(base_meta); r[ip] = "Y"; r[im] = str(n)
        out_rows.append(r + [f"{v:.3f}" for v in gy])
        r = list(base_meta); r[ip] = "T1"; r[im] = str(n)
        out_rows.append(r + [f"{v:.3f}" for v in t1_grid])
        print(f"{wid}: n={n}, T1 range [{t1_grid.min():.1f}, {t1_grid.max():.1f}]")

    with DST.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerows(out_rows)
    print(f"\nsaved: {DST}  ({len(out_rows) - 1} rows, n={n})")


if __name__ == "__main__":
    main()
