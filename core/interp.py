"""
웨이퍼 격자 보간 — 측정점 집합 → 격자 heatmap 값.

**RBF 계열** (모두 convex hull 외부까지 외삽, 원형 가장자리 스무스):
- `RBF-ThinPlate` (기본) — thin-plate spline, 업계 표준
- `RBF-Multiquadric` — sqrt(1 + (εr)²)
- `RBF-Gaussian`     — exp(-(εr)²), 로컬 smoothing
- `RBF-Quintic`      — -r⁵, 매끄러운 외삽 (외삽 과격, 주의)
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import RBFInterpolator


# method 이름 → scipy RBFInterpolator kernel 이름
_RBF_KERNELS = {
    "RBF-ThinPlate":   "thin_plate_spline",
    "RBF-Multiquadric": "multiquadric",
    "RBF-Gaussian":    "gaussian",
    "RBF-Quintic":     "quintic",
}


def interpolate_wafer(
    x: np.ndarray,
    y: np.ndarray,
    v: np.ndarray,
    XG: np.ndarray,
    YG: np.ndarray,
    method: str = "RBF-ThinPlate",
    *,
    rbf_smoothing: float = 0.0,
) -> np.ndarray:
    """(x, y, v) 측정점으로 (XG, YG) 격자 값 보간.

    `x, y, v` 는 1D 동일 길이. `XG, YG` 는 meshgrid 결과.
    반환: `ZG` (XG 형상). 측정점 부족하거나 RBF 실패 시 NaN.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    v = np.asarray(v, dtype=float)
    if x.size < 3 or v.size < 3:
        return np.full(XG.shape, np.nan, dtype=float)

    # RBF 계열 — method 이름에 따라 kernel 선택 (unknown 이름은 thin_plate로 fallback)
    kernel = _RBF_KERNELS.get(method, "thin_plate_spline")
    try:
        pts = np.column_stack([x, y])
        kw: dict = {"kernel": kernel, "smoothing": rbf_smoothing}
        # multiquadric/gaussian/inverse_multiquadric는 epsilon 필수.
        # scipy RBF는 kernel(ε·r) 형태 → epsilon은 거리의 역수.
        # 측정점 간 평균 최근접 거리가 kernel의 "1 단위"가 되도록 역수로 설정.
        if kernel in ("multiquadric", "gaussian", "inverse_multiquadric"):
            from scipy.spatial import cKDTree
            tree = cKDTree(pts)
            d, _ = tree.query(pts, k=min(2, len(pts)))
            median_dist = float(np.median(d[:, 1])) if d.ndim > 1 else 10.0
            kw["epsilon"] = 1.0 / max(median_dist, 1e-3)
        rbf = RBFInterpolator(pts, v, **kw)
        grid_pts = np.column_stack([XG.ravel(), YG.ravel()])
        return rbf(grid_pts).reshape(XG.shape)
    except Exception as _e:
        # 진단용 — RBF 실패 원인 파악
        import sys
        n_nan_v = int(np.isnan(v).sum()) if v.size else 0
        n_nan_xy = int((np.isnan(x) | np.isnan(y)).sum()) if x.size else 0
        x_std = float(np.nanstd(x)) if x.size else 0.0
        y_std = float(np.nanstd(y)) if y.size else 0.0
        v_rng = (float(np.nanmin(v)), float(np.nanmax(v))) if v.size else (0.0, 0.0)
        sys.stderr.write(
            f"[interp] RBF 실패: kernel={kernel}  n_pts={x.size}  "
            f"v_nan={n_nan_v}  xy_nan={n_nan_xy}  "
            f"x_std={x_std:.4g}  y_std={y_std:.4g}  v_range={v_rng}  "
            f"err={type(_e).__name__}: {_e}\n"
        )
        sys.stderr.flush()
        return np.full(XG.shape, np.nan, dtype=float)
