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
from scipy.interpolate import RBFInterpolator, UnivariateSpline, interp1d


# method 이름 → scipy RBFInterpolator kernel 이름
_RBF_KERNELS = {
    "RBF-ThinPlate":   "thin_plate_spline",
    "RBF-Multiquadric": "multiquadric",
    "RBF-Gaussian":    "gaussian",
    "RBF-Quintic":     "quintic",
}


def is_collinear(x, y, *, rel_tol: float = 0.02) -> bool:
    """측정점이 사실상 1 개 직선 위에 놓여있는지 PCA(SVD) 로 판정.

    `rel_tol` = s[1]/s[0] 임계. 2% 이하면 collinear (직선 방향 변동 대비 수직 방향
    변동 무시 가능). 수평/수직/대각선/임의 각도 무관 동일 판정.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size < 3:
        return False
    pts = np.column_stack([x, y])
    pts_c = pts - pts.mean(axis=0)
    try:
        s = np.linalg.svd(pts_c, compute_uv=False)
    except Exception:
        return False
    if s[0] < 1e-10:
        return False
    return float(s[1] / s[0]) < rel_tol


def _estimate_noise_1d(v_u: np.ndarray) -> float:
    """1D 프로파일의 고주파 노이즈 std 추정 — 1차 차분 기반.

    실제 측정 데이터의 high-freq 성분만 분리: σ(diff(v)) / √2.
    `v_u` 는 r 순 정렬된 평균값.
    """
    if v_u.size < 3:
        return 0.0
    d = np.diff(v_u)
    return float(np.std(d) / np.sqrt(2.0))


def interpolate_radial(x, y, v, XG, YG, *, edge_cut_mm: float = 0.0) -> np.ndarray:
    """1D 라인 스캔 → 웨이퍼 중심 기준 radial symmetric 2D surface.

    가정: 측정 라인이 **웨이퍼 중심(원점)을 지남**. -150~+150 양방향 스캔이면
    같은 |r| 값에 두 개 측정이 존재 → 평균 사용.

    알고리즘:
      1. r_i = √(x_i² + y_i²) — 방향 무관, 반경만
      2. 1μm 양자화 후 같은 r 값끼리 평균 (float 노이즈 + ± 대칭 통합)
      3. 노이즈 자동 추정 → smoothing spline (cubic overshoot 링 방지)
      4. 격자 R = √(X² + Y²) → v(R) 매핑
      5. 안쪽 (R < r_min): 센터값으로 채움
      6. 바깥 (R > r_max - edge_cut_mm): NaN

    `edge_cut_mm`: 데이터 r_max 에서 안쪽으로 cut 할 mm. 0 = cut 없음 (기존 동작).
    양수면 최외각 cut_mm 영역이 NaN → 톱니/extrapolation 가시 영역 제거.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    v = np.asarray(v, dtype=float)
    r = np.sqrt(x * x + y * y)
    r_round = np.round(r, 3)  # 1μm 양자화
    r_u, inv = np.unique(r_round, return_inverse=True)
    v_u = np.zeros_like(r_u, dtype=float)
    cnt = np.zeros_like(r_u, dtype=float)
    np.add.at(v_u, inv, v)
    np.add.at(cnt, inv, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        v_u = v_u / cnt
    if r_u.size < 2:
        return np.full(XG.shape, float(v[0]), dtype=float)

    RG = np.sqrt(XG.astype(float) ** 2 + YG.astype(float) ** 2)

    # 데이터 r_max 에서 edge_cut_mm 만큼 안쪽까지만 그림
    r_outer = max(r_u[-1] - max(float(edge_cut_mm), 0.0), r_u[0])

    # 점이 너무 적으면 smoothing 불안정 → linear
    if r_u.size < 4:
        f = interp1d(r_u, v_u, kind="linear", bounds_error=False,
                     fill_value=(float(v_u[0]), np.nan))
        Z = f(RG).astype(float)
        Z = np.where(RG > r_outer, np.nan, Z)
        return Z

    # 노이즈 자동 추정 → smoothing 파라미터
    noise = _estimate_noise_1d(v_u)
    s_val = float(r_u.size) * (noise ** 2)  # scipy default s heuristic
    try:
        sp = UnivariateSpline(r_u, v_u, k=3, s=s_val, ext=3)
        Z = sp(RG)
    except Exception:
        # smoothing spline 실패 시 cubic interp 폴백
        f = interp1d(r_u, v_u, kind="cubic", bounds_error=False,
                     fill_value=(float(v_u[0]), np.nan))
        Z = f(RG)

    # 범위 처리 — 내부는 센터값, 바깥(edge_cut 반영)은 NaN
    Z = np.where(RG > r_outer, np.nan, Z)
    Z = np.where(RG < r_u[0], float(v_u[0]), Z)
    return Z.astype(float)


def interpolate_wafer(
    x: np.ndarray,
    y: np.ndarray,
    v: np.ndarray,
    XG: np.ndarray,
    YG: np.ndarray,
    method: str = "RBF-ThinPlate",
    *,
    rbf_smoothing: float = 0.0,
    radial_edge_cut_mm: float = 0.0,
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

    # 1D 라인 스캔 자동 감지 → radial symmetric 경로
    # (RBF thin_plate 는 collinear 데이터에서 polynomial augmentation 랭크 부족으로 실패)
    if is_collinear(x, y):
        import sys
        sys.stderr.write(
            f"[interp] Radial 모드 (1D 라인 스캔 감지, n_pts={x.size}, "
            f"edge_cut={radial_edge_cut_mm}mm)\n"
        )
        sys.stderr.flush()
        return interpolate_radial(x, y, v, XG, YG, edge_cut_mm=radial_edge_cut_mm)

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
