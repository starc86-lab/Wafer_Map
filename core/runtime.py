"""
런타임 상태 — 앱 부트 시 주 화면 해상도 기반으로 덮어써짐.

사용 패턴 (동적 바인딩):
    from core import runtime
    max_w = runtime.SCREEN_MAX_W
    tier  = runtime.resolution_tier()
"""

# 부트 전 기본값 (update_screen_max 호출 전)
SCREEN_MAX_W = 1920
SCREEN_MAX_H = 1080


# ────────────────────────────────────────────────────────────────
# 해상도 티어별 기본 창 크기 (Profile Vision 값 재사용)
# Orientation 무관 (긴 변 기준)
# ────────────────────────────────────────────────────────────────
WINDOW_SIZES = {
    "FHD": {"main": (900, 650),  "result": (1200, 800)},
    "QHD": {"main": (950, 700),  "result": (1280, 960)},
    "UHD": {"main": (1450, 1060), "result": (1920, 1413)},
}


def update_screen_max(w: int, h: int) -> None:
    """앱 부트 시 QGuiApplication.primaryScreen().availableGeometry()로 호출."""
    global SCREEN_MAX_W, SCREEN_MAX_H
    SCREEN_MAX_W = int(w)
    SCREEN_MAX_H = int(h)


def resolution_tier() -> str:
    """긴 변 기준 FHD / QHD / UHD 티어 판정."""
    long_edge = max(SCREEN_MAX_W, SCREEN_MAX_H)
    if long_edge < 2200:
        return "FHD"
    if long_edge < 3200:
        return "QHD"
    return "UHD"


def default_window_size(which: str = "main") -> tuple[int, int]:
    """`which` ∈ {"main", "result"} 에 대한 티어별 기본 크기."""
    return WINDOW_SIZES[resolution_tier()][which]
