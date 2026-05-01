"""
Minimal Underline style — gridline 없음, 값 아래 색 underline 만 (옵션 D).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from widgets.summary.base import SummaryWidget, format_metrics


class SummaryMinimalUnderline(SummaryWidget):
    HEADERS = ("Mean", "Range", "Non Unif.")
    ACCENT = "#0077b6"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # 흰색 고정 — 테마 (다크 등) 영향 차단 (사용자 정책 2026-05-01).
        self.setStyleSheet(
            "SummaryMinimalUnderline { background-color: white;"
            " border: 1px solid #888888; }"
        )
        outer = QHBoxLayout(self)
        outer.setContentsMargins(2, 1, 2, 1)
        outer.setSpacing(0)

        from core.themes import FONT_SIZES
        _base = int(FONT_SIZES.get("body", 14))
        lbl_px = max(9, _base - 3)
        val_px = _base

        self._values: list[QLabel] = []
        for h in self.HEADERS:
            col_w = QWidget()
            col = QVBoxLayout(col_w)
            col.setContentsMargins(2, 0, 2, 0)
            col.setSpacing(0)
            lbl = QLabel(h)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: #999999; font-size: {lbl_px}px;"
            )
            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(
                f"color: #111111; font-size: {val_px}px; font-weight: bold;"
            )
            ul = QFrame()
            ul.setFixedHeight(2)
            ul.setStyleSheet(
                f"background-color: {self.ACCENT}; border: none;"
            )
            col.addWidget(lbl)
            col.addWidget(val)
            col.addWidget(ul)
            outer.addWidget(col_w, stretch=1)
            self._values.append(val)

    def update_metrics(self, metrics, decimals, percent_suffix=True):
        avg_s, range_s, nu_s = format_metrics(metrics, decimals, percent_suffix)
        for i, val in enumerate((avg_s, range_s, nu_s)):
            self._values[i].setText(val)

    def set_target_width(self, w: int) -> None:
        self.setFixedWidth(w)

    def get_natural_height(self) -> int:
        return 34
