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


def make_rbf(x, y, v, *, method: str = "RBF-ThinPlate", smoothing: float = 0.0):
    """method 이름으로 RBFInterpolator 생성 (epsilon 자동 처리).

    rect / radial 렌더 경로에서 공통으로 사용해 kernel 선택 로직 통일.
    """
    kernel = _RBF_KERNELS.get(method, "thin_plate_spline")
    pts = np.column_stack([np.asarray(x, dtype=float),
                            np.asarray(y, dtype=float)])
    v_arr = np.asarray(v, dtype=float)
    kw: dict = {"kernel": kernel, "smoothing": smoothing}
    if kernel in ("multiquadric", "gaussian", "inverse_multiquadric"):
        from scipy.spatial import cKDTree
        tree = cKDTree(pts)
        d, _ = tree.query(pts, k=min(2, len(pts)))
        median_dist = float(np.median(d[:, 1])) if d.ndim > 1 else 10.0
        kw["epsilon"] = 1.0 / max(median_dist, 1e-3)
    return RBFInterpolator(pts, v_arr, **kw)


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


def interpolate_radial(x, y, v, XG, YG) -> np.ndarray:
    """1D 라인 스캔 → 웨이퍼 중심 기준 radial symmetric 2D surface.

    가정: 측정 라인이 **웨이퍼 중심(원점)을 지남**.

    알고리즘 (2D RBF 와 동일한 "웨이퍼 경계까지 꽉 채우기" 스타일):
      1. r_i = √(x_i² + y_i²) — 방향 무관, 반경만
      2. 1μm 양자화 후 같은 r 값끼리 평균 (float 노이즈 + ± 대칭 통합)
      3. 노이즈 자동 추정 → smoothing spline (cubic overshoot 링 방지)
      4. 격자 R = √(X² + Y²) → v(R) 매핑, 전 구간(0~WAFER_R) 빈틈 없이 채움
      5. R < r_min (센터 방향 미측정): 센터값 (v_u[0])
      6. R > r_max (데이터 바깥): edge 값 (v_u[-1]) 으로 constant extrapolate
      → 서피스 끝이 웨이퍼 원 경계에 도달 = 2D RBF 맵과 동일한 "바닥 연결" 외관

    edge cut 은 별도로 `interpolate_wafer` 경로에서 wafer 경계 기준 mask 로 적용.
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

    # 점이 너무 적으면 smoothing 불안정 → linear
    if r_u.size < 4:
        f = interp1d(r_u, v_u, kind="linear", bounds_error=False,
                     fill_value=(float(v_u[0]), float(v_u[-1])))
        Z = f(RG).astype(float)
        return Z

    # 노이즈 자동 추정 → smoothing 파라미터
    noise = _estimate_noise_1d(v_u)
    s_val = float(r_u.size) * (noise ** 2)
    try:
        # ext=3: 범위 밖은 boundary 값으로 constant (r_max 바깥도 edge 값 유지)
        sp = UnivariateSpline(r_u, v_u, k=3, s=s_val, ext=3)
        Z = sp(RG)
    except Exception:
        f = interp1d(r_u, v_u, kind="cubic", bounds_error=False,
                     fill_value=(float(v_u[0]), float(v_u[-1])))
        Z = f(RG)

    # 센터 방향 (R < r_min) 은 센터값으로 명시 (ext=3 가 이미 처리하지만 안전)
    Z = np.where(RG < r_u[0], float(v_u[0]), Z)
    # R > r_max 는 ext=3 로 이미 v_u[-1] 상수, NaN 없음
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
    edge_cut_mm: float = 0.0,
    wafer_radius_mm: float = 150.0,
) -> np.ndarray:
    """(x, y, v) 측정점으로 (XG, YG) 격자 값 보간.

    `x, y, v` 는 1D 동일 길이. `XG, YG` 는 meshgrid 결과.
    반환: `ZG` (XG 형상). 측정점 부족하거나 RBF 실패 시 NaN.

    `edge_cut_mm`: **웨이퍼 경계에서 안쪽으로** cut 할 mm. radial / RBF 양쪽 공통.
      양수면 R > (wafer_radius_mm - edge_cut_mm) 영역을 NaN.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    v = np.asarray(v, dtype=float)
    if x.size < 3 or v.size < 3:
        return np.full(XG.shape, np.nan, dtype=float)

    # 1D 라인 스캔 자동 감지 → radial symmetric 경로
    if is_collinear(x, y):
        import sys
        sys.stderr.write(
            f"[interp] Radial 모드 (1D 라인 스캔 감지, n_pts={x.size})\n"
        )
        sys.stderr.flush()
        ZG = interpolate_radial(x, y, v, XG, YG)
    else:
        # RBF 계열
        kernel = _RBF_KERNELS.get(method, "thin_plate_spline")
        try:
            pts = np.column_stack([x, y])
            kw: dict = {"kernel": kernel, "smoothing": rbf_smoothing}
            if kernel in ("multiquadric", "gaussian", "inverse_multiquadric"):
                from scipy.spatial import cKDTree
                tree = cKDTree(pts)
                d, _ = tree.query(pts, k=min(2, len(pts)))
                median_dist = float(np.median(d[:, 1])) if d.ndim > 1 else 10.0
                kw["epsilon"] = 1.0 / max(median_dist, 1e-3)
            rbf = RBFInterpolator(pts, v, **kw)
            grid_pts = np.column_stack([XG.ravel(), YG.ravel()])
            ZG = rbf(grid_pts).reshape(XG.shape)
        except Exception as _e:
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

    # Edge cut — 웨이퍼 경계 기준 안쪽으로 cut_mm (radial/RBF 공통)
    if edge_cut_mm > 0:
        RG = np.sqrt(XG.astype(float) ** 2 + YG.astype(float) ** 2)
        cut_r = max(wafer_radius_mm - edge_cut_mm, 0.0)
        ZG = np.where(RG > cut_r, np.nan, ZG)

    return ZG
