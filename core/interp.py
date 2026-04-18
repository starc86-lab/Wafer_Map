"""
웨이퍼 격자 보간 — 측정점 집합 → 격자 heatmap 값.

기본 `method="rbf"` (thin-plate spline) — convex hull 외부까지 외삽해
웨이퍼 경계까지 **원형**으로 채움 (8각형 효과 해소).

대안:
- "cubic": griddata cubic — convex hull 내부만 보간, 외부 NaN
- "cubic_nearest": cubic 내부 + 외부는 nearest 값으로 채움 (계단 경계)
- "phantom_ring": 원 둘레에 가상점(최인접 값) 추가 후 cubic
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import RBFInterpolator, griddata


def interpolate_wafer(
    x: np.ndarray,
    y: np.ndarray,
    v: np.ndarray,
    XG: np.ndarray,
    YG: np.ndarray,
    method: str = "rbf",
    *,
    rbf_kernel: str = "thin_plate_spline",
    rbf_smoothing: float = 0.0,
    ring_radius: float | None = None,
    ring_points: int = 32,
) -> np.ndarray:
    """(x, y, v) 측정점으로 (XG, YG) 격자 값 보간.

    `x, y, v` 는 1D 동일 길이. `XG, YG` 는 meshgrid 결과.
    반환: `ZG` (XG 형상), 보간 실패 지점은 NaN.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    v = np.asarray(v, dtype=float)
    if x.size < 3 or v.size < 3:
        return np.full(XG.shape, np.nan, dtype=float)

    if method == "rbf":
        try:
            pts = np.column_stack([x, y])
            rbf = RBFInterpolator(
                pts, v, kernel=rbf_kernel, smoothing=rbf_smoothing,
            )
            grid_pts = np.column_stack([XG.ravel(), YG.ravel()])
            return rbf(grid_pts).reshape(XG.shape)
        except Exception:
            pass  # 아래 cubic fallback

    if method == "cubic_nearest":
        zc = griddata((x, y), v, (XG, YG), method="cubic")
        zn = griddata((x, y), v, (XG, YG), method="nearest")
        return np.where(np.isnan(zc), zn, zc)

    if method == "phantom_ring":
        if ring_radius is None:
            ring_radius = float(np.nanmax(np.sqrt(x * x + y * y)))
        theta = np.linspace(0, 2 * np.pi, ring_points, endpoint=False)
        rx = ring_radius * np.cos(theta)
        ry = ring_radius * np.sin(theta)
        # 각 가상점 값 = 가장 가까운 실제 측정점 값
        from scipy.spatial import cKDTree
        tree = cKDTree(np.column_stack([x, y]))
        _, idx = tree.query(np.column_stack([rx, ry]), k=1)
        rv = v[idx]
        ax = np.concatenate([x, rx])
        ay = np.concatenate([y, ry])
        av = np.concatenate([v, rv])
        return griddata((ax, ay), av, (XG, YG), method="cubic")

    # 기본: cubic
    return griddata((x, y), v, (XG, YG), method="cubic")
