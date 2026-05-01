"""
Minimal Underline style — gridline 없음, 값 아래 색 underline 만 (옵션 D).
폰트 — apply_fonts 가 매 update 호출되어 font_scale 자동 반영.
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
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: white;")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(2, 1, 2, 1)
        outer.setSpacing(0)

        self._labels: list[QLabel] = []
        self._values: list[QLabel] = []
        for h in self.HEADERS:
            col_w = QWidget()
            col = QVBoxLayout(col_w)
            col.setContentsMargins(2, 0, 2, 0)
            col.setSpacing(0)
            lbl = QLabel(h)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ul = QFrame()
            ul.setFrameShape(QFrame.Shape.NoFrame)
            ul.setFixedHeight(2)
            ul.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            ul.setStyleSheet(f"background-color: {self.ACCENT};")
            # underline 짧게 — col 가로 20% (stretch 2:1:2)
            ul_row = QHBoxLayout()
            ul_row.setContentsMargins(0, 0, 0, 0)
            ul_row.addStretch(2)
            ul_row.addWidget(ul, 1)
            ul_row.addStretch(2)
            col.addWidget(lbl)
            col.addWidget(val)
            col.addLayout(ul_row)
            outer.addWidget(col_w, stretch=1)
            self._labels.append(lbl)
            self._values.append(val)
        self.apply_fonts()

    def apply_fonts(self) -> None:
        from core.themes import FONT_SIZES
        _base = int(FONT_SIZES.get("body", 14))
        lbl_px = max(9, _base - 3)
        val_px = _base
        lbl_ss = f"color: #999999; font-size: {lbl_px}px;"
        val_ss = f"color: #111111; font-size: {val_px}px; font-weight: bold;"
        for l in self._labels:
            l.setStyleSheet(lbl_ss)
        for v in self._values:
            v.setStyleSheet(val_ss)

    def update_metrics(self, metrics, decimals, percent_suffix=True):
        avg_s, range_s, nu_s = format_metrics(metrics, decimals, percent_suffix)
        for i, val in enumerate((avg_s, range_s, nu_s)):
            self._values[i].setText(val)

    def set_target_width(self, w: int) -> None:
        self.setFixedWidth(w)
