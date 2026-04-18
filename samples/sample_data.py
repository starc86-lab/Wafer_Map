"""
샘플용 공통 가짜 웨이퍼 측정 데이터.
300mm 웨이퍼(반지름 150mm) 내부에 격자형 측정점을 만들고,
중심이 볼록한 필름 두께 분포(+작은 노이즈)를 부여한다.
"""
import numpy as np

WAFER_RADIUS = 150.0  # mm


def make_wafer_points(grid_side: int = 15, seed: int = 42):
    """(X, Y, V) 1D ndarray 반환. 단위: mm, mm, Å(두께 가상값)."""
    rng = np.random.default_rng(seed)
    xs = np.linspace(-140, 140, grid_side)
    ys = np.linspace(-140, 140, grid_side)
    X, Y = np.meshgrid(xs, ys)
    X = X.ravel()
    Y = Y.ravel()
    mask = X**2 + Y**2 <= WAFER_RADIUS**2
    X, Y = X[mask], Y[mask]
    R = np.sqrt(X**2 + Y**2)
    V = 2000.0 - 0.003 * R**2 + rng.normal(0, 3, size=X.shape)
    return X, Y, V
