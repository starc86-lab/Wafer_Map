"""
Color Footer style — 값+라벨 위, 하단 색 띠 metric 별 다른 색 (옵션 I).
폰트 — apply_fonts 가 매 update 호출되어 font_scale 자동 반영.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from widgets.summary.base import SummaryWidget, format_metrics


_FOOTER_COLORS = ("#264653", "#2a9d8f", "#e76f51")


class SummaryColorFooter(SummaryWidget):
    HEADERS = ("Mean", "Range", "Non Unif.")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: white;")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._labels: list[QLabel] = []
        self._values: list[QLabel] = []
        for i, h in enumerate(self.HEADERS):
            col_w = QWidget()
            col = QVBoxLayout(col_w)
            col.setContentsMargins(0, 1, 0, 0)
            col.setSpacing(0)
            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl = QLabel(h)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            footer = QFrame()
            footer.setFrameShape(QFrame.Shape.NoFrame)
            footer.setFixedHeight(3)
            footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            footer.setStyleSheet(f"background-color: {_FOOTER_COLORS[i]};")
            col.addWidget(val)
            col.addWidget(lbl)
            col.addWidget(footer)
            outer.addWidget(col_w, stretch=1)
            self._values.append(val)
            self._labels.append(lbl)
            # 세퍼레이터
            if i < len(self.HEADERS) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.NoFrame)
                sep.setFixedWidth(1)
                sep.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                sep.setStyleSheet("background-color: #dee2e6;")
                outer.addWidget(sep)
        self.apply_fonts()

    def apply_fonts(self) -> None:
        from core.themes import FONT_SIZES
        _base = int(FONT_SIZES.get("body", 14))
        lbl_px = max(10, _base - 2)  # 라벨 12px (사용자 정책 2026-05-03)
        val_px = _base
        val_ss = f"color: #111111; font-size: {val_px}px; font-weight: bold;"
        lbl_ss = f"color: #666666; font-size: {lbl_px}px;"
        for v in self._values:
            v.setStyleSheet(val_ss)
        for l in self._labels:
            l.setStyleSheet(lbl_ss)

    def update_metrics(self, metrics, decimals, percent_suffix=True):
        avg_s, range_s, nu_s = format_metrics(metrics, decimals, percent_suffix)
        for i, val in enumerate((avg_s, range_s, nu_s)):
            self._values[i].setText(val)

    def set_target_width(self, w: int) -> None:
        self.setFixedWidth(w)
