"""widgets 패키지 — 공통 dialog/window helper.

`clamp_to_screen` — UI scale 변경 (UI 해상도 콤보) 시 dialog/window 가 실제
모니터보다 커져 화면 밖으로 나가 버튼 클릭 불가능 deadlock 방지 (사용자
정책 2026-05-01). 모든 hardcoded `resize(W, H)` 호출 직후 사용.
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget


def clamp_to_screen(widget: QWidget) -> None:
    """widget 의 현재 size 를 primary screen available geometry 안으로 clamp.

    Qt 의 `availableGeometry` 는 logical px (`QT_SCALE_FACTOR` 자동 반영) 라
    UI scale 1.5 환경의 FHD 모니터는 logical 1280×720 으로 잡힘 → 큰 dialog
    (예: settings 760×940) 가 자동 fit.
    """
    from PySide6.QtGui import QGuiApplication
    scr = QGuiApplication.primaryScreen()
    if scr is None:
        return
    avail = scr.availableGeometry()
    cur = widget.size()
    new_w = min(cur.width(), avail.width())
    new_h = min(cur.height(), avail.height())
    if (new_w, new_h) != (cur.width(), cur.height()):
        widget.resize(new_w, new_h)
