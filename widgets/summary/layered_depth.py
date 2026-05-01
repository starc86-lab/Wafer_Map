"""
Layered Depth style — 3 col × 2 row (header/value), 가운데 행 sep 없음.
좌/우 가장자리 그라데이션 그림자, 모서리 rounded, 배경 투명 (cell 비춤).

사용자 정책 2026-05-01 — 백지 재설계.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from widgets.summary.base import SummaryWidget, format_metrics


class SummaryLayeredDepth(SummaryWidget):
    HEADERS = ("Mean", "Range", "Non Unif.")

    _RADIUS = 6.0       # 모서리 라운딩
    _CARD = QColor("#ffffff")
    _BORDER = QColor("#c0c4c8")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # widget 자체 투명 — paintEvent 가 카드 + 그림자만 그림. cell 부모
        # (capture_container 흰색) 비춤.

        from core.themes import FONT_SIZES
        _base = int(FONT_SIZES.get("body", 14))
        lbl_px = max(9, _base - 3)
        val_px = _base

        grid = QGridLayout(self)
        grid.setContentsMargins(8, 1, 8, 1)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(0)

        self._values: list[QLabel] = []
        for c, h in enumerate(self.HEADERS):
            lbl = QLabel(h)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: #666666; font-size: {lbl_px}px;")
            grid.addWidget(lbl, 0, c)

            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(
                f"color: #111111; font-size: {val_px}px; font-weight: bold;"
            )
            grid.addWidget(val, 1, c)
            self._values.append(val)

    def update_metrics(self, metrics, decimals, percent_suffix=True):
        avg_s, range_s, nu_s = format_metrics(metrics, decimals, percent_suffix)
        for i, val in enumerate((avg_s, range_s, nu_s)):
            self._values[i].setText(val)

    def set_target_width(self, w: int) -> None:
        self.setFixedWidth(w)

    def get_natural_height(self) -> int:
        return 34

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        # 흰 rounded card — 그림자 없음 (사용자 정책 2026-05-01)
        painter.setBrush(QBrush(self._CARD))
        painter.setPen(QPen(self._BORDER, 0.8))
        painter.drawRoundedRect(rect, self._RADIUS, self._RADIUS)
