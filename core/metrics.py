"""
Summary 메트릭 — Wafer Map에서 사용하는 6종.

- AVG   : 측정점 VALUE 산술 평균
- MAX   : 최댓값
- MIN   : 최솟값
- RANGE : MAX − MIN
- 3SIG  : 3 × 표본 표준편차 (ddof=1)
- NU%   : (MAX − MIN) / (2 × |AVG|) × 100  (반도체 half-range 방식)

NaN 값은 계산에서 자동 제외. 유효 값이 없으면 모두 NaN 반환.
"""
from __future__ import annotations

import numpy as np


def summary_metrics(values) -> dict[str, float]:
    arr = np.asarray(values, dtype=float)
    v = arr[~np.isnan(arr)]
    if v.size == 0:
        return dict.fromkeys(
            ("avg", "max", "min", "range", "sig3", "nu_pct"), float("nan"),
        )
    avg = float(v.mean())
    mx = float(v.max())
    mn = float(v.min())
    rng = mx - mn
    sig3 = 3.0 * float(v.std(ddof=1)) if v.size > 1 else 0.0
    nu = (rng / (2.0 * abs(avg)) * 100.0) if avg != 0.0 else float("nan")
    return {"avg": avg, "max": mx, "min": mn, "range": rng, "sig3": sig3, "nu_pct": nu}
