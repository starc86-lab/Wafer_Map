"""
Wafer Map 좌표 유틸.

- `normalize_to_mm`: 좌표 배열의 단위를 값 범위 기반으로 자동 mm 환산.
  (X, X_1000 등 이름·스케일 조합 무관; 이름이 아닌 **값 범위**로만 판정)
- `filter_in_wafer`: 웨이퍼 반경 밖 측정점 제거.
"""
from __future__ import annotations

import numpy as np

# 300mm 웨이퍼 기준 반경 (mm)
WAFER_RADIUS_MM = 150.0

# mm vs μm 판정 임계값
# 반도체 계측 데이터는 X·Y 좌표가 ±150mm 범위이므로
#   |max| ≤ 200         → 이미 mm
#   200 < |max| ≤ 200_000 → μm 또는 ×1000 표기 → /1000
MM_UPPER_BOUND = 200.0
UM_UPPER_BOUND = 200_000.0


def normalize_to_mm(values) -> tuple[np.ndarray, str]:
    """좌표 배열을 mm로 환산.

    Args:
        values: 1D numeric array-like.

    Returns:
        (mm_array, reason_str). reason_str은 UI 표시/로깅용 판정 근거.
        범위 밖이면 원본 그대로 반환 + 사용자 수동 오버라이드 요청 메시지.
    """
    arr = np.asarray(values, dtype=float)
    if arr.size == 0 or np.all(np.isnan(arr)):
        return arr, "empty"

    max_abs = float(np.nanmax(np.abs(arr)))
    if max_abs <= MM_UPPER_BOUND:
        return arr.copy(), f"mm (|max|={max_abs:g})"
    if max_abs <= UM_UPPER_BOUND:
        return arr / 1000.0, f"um→mm /1000 (|max|={max_abs:g})"
    return arr.copy(), f"out-of-range (|max|={max_abs:g}), 수동 오버라이드 필요"


def filter_in_wafer(
    x: np.ndarray,
    y: np.ndarray,
    v: np.ndarray,
    radius_mm: float = WAFER_RADIUS_MM,
    tolerance: float = 1e-6,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """웨이퍼 반경 밖 점 제거.

    Returns:
        (x_in, y_in, v_in, n_removed).
        n_removed가 0보다 크면 UI에서 경고 팝업 띄울 수 있음.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    v = np.asarray(v, dtype=float)
    r2 = x * x + y * y
    mask = r2 <= (radius_mm + tolerance) ** 2
    return x[mask], y[mask], v[mask], int((~mask).sum())


def match_points(
    xa: np.ndarray, ya: np.ndarray,
    xb: np.ndarray, yb: np.ndarray,
    tolerance: float = 1e-3,
) -> tuple[np.ndarray, np.ndarray]:
    """두 좌표 세트의 점 매칭 인덱스 반환 (DELTA용).

    A의 각 점에 대해 B에서 `tolerance` 내 근접 점을 찾음.
    매칭 성공한 A·B 인덱스 쌍을 반환. 매칭 안 된 A 점은 제외.

    Returns:
        (idx_a, idx_b) 같은 길이의 int 배열. 매칭 안 되면 빈 배열.
    """
    xa = np.asarray(xa, dtype=float)
    ya = np.asarray(ya, dtype=float)
    xb = np.asarray(xb, dtype=float)
    yb = np.asarray(yb, dtype=float)

    ia: list[int] = []
    ib: list[int] = []
    for i, (x, y) in enumerate(zip(xa, ya)):
        d2 = (xb - x) ** 2 + (yb - y) ** 2
        j = int(np.argmin(d2))
        if d2[j] <= tolerance * tolerance:
            ia.append(i)
            ib.append(j)
    return np.asarray(ia, dtype=int), np.asarray(ib, dtype=int)
