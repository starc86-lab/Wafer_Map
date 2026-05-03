"""
Rounded Card (key: layered_depth) — 3 col × 2 row, 행 sep 없음, 모서리 rounded,
컬럼 sep 75% 세로. 폰트 — apply_fonts 매 update 시.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from widgets.summary.base import SummaryWidget, format_metrics


class SummaryLayeredDepth(SummaryWidget):
    HEADERS = ("Mean", "Range", "Non Unif.")

    _RADIUS = 6.0
    _CARD = QColor("#ffffff")
    _BORDER = QColor("#c0c4c8")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # widget 투명 — paintEvent 가 흰 rounded card 그림. 부모 비춤.
        grid = QGridLayout(self)
        grid.setContentsMargins(8, 1, 8, 1)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(0)

        self._labels: list[QLabel] = []
        self._values: list[QLabel] = []
        for c, h in enumerate(self.HEADERS):
            lbl = QLabel(h)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(lbl, 0, c)
            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(val, 1, c)
            self._labels.append(lbl)
            self._values.append(val)
        self.apply_fonts()

    def apply_fonts(self) -> None:
        from core.themes import FONT_SIZES
        _base = int(FONT_SIZES.get("body", 14))
        lbl_px = max(11, _base - 1)  # 라벨 13px (사용자 정책 2026-05-04, +1)
        val_px = _base + 1
        lbl_ss = f"color: #666666; font-size: {lbl_px}px;"
        val_ss = f"color: #1f3a5f; font-size: {val_px}px; font-weight: bold;"
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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(QBrush(self._CARD))
        painter.setPen(QPen(self._BORDER, 0.8))
        painter.drawRoundedRect(rect, self._RADIUS, self._RADIUS)
        # 컬럼 sep 75%
        painter.setPen(QPen(QColor("#dee2e6"), 1))
        margin_v = rect.height() * 0.125
        y0 = rect.top() + margin_v
        y1 = rect.bottom() - margin_v
        for k in (1, 2):
            x = rect.left() + (rect.width() / 3.0) * k
            painter.drawLine(QPointF(x, y0), QPointF(x, y1))
