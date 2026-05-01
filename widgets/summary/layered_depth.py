"""
Layered Depth style — 3 col × 2 row (header/value), 가운데 행 sep 없음.
좌/우 가장자리 그라데이션 그림자, 모서리 rounded, 배경 투명 (cell 비춤).

사용자 정책 2026-05-01 — 백지 재설계.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from widgets.summary.base import SummaryWidget, format_metrics


class SummaryLayeredDepth(SummaryWidget):
    HEADERS = ("Mean", "Range", "Non Unif.")

    _RADIUS = 6.0       # 모서리 라운딩
    _SHADOW_W = 5       # 좌/우 그림자 폭
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
        # 좌/우 SHADOW_W 만큼 inset (그림자 영역 확보) + 상하 padding 2
        grid.setContentsMargins(self._SHADOW_W + 4, 1, self._SHADOW_W + 4, 1)
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
        rect = QRectF(self.rect())
        sw = self._SHADOW_W
        # 가운데 흰 rounded card — 좌/우 SHADOW_W 만큼 inset
        card = rect.adjusted(sw, 0, -sw, 0)
        painter.setBrush(QBrush(self._CARD))
        painter.setPen(QPen(self._BORDER, 0.8))
        painter.drawRoundedRect(card, self._RADIUS, self._RADIUS)
        # 좌측 그라데이션 그림자 (투명 → 어두움 → 투명, 가운데 위치)
        painter.setPen(Qt.PenStyle.NoPen)
        h_inset = self._RADIUS
        shadow_h_rect = QRectF(0, h_inset, sw, rect.height() - 2 * h_inset)
        grad_l = QLinearGradient(0, 0, sw, 0)
        grad_l.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad_l.setColorAt(0.5, QColor(0, 0, 0, 45))
        grad_l.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(shadow_h_rect, QBrush(grad_l))
        # 우측 그라데이션 그림자
        right_x = rect.width() - sw
        shadow_r_rect = QRectF(right_x, h_inset, sw, rect.height() - 2 * h_inset)
        grad_r = QLinearGradient(right_x, 0, rect.width(), 0)
        grad_r.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad_r.setColorAt(0.5, QColor(0, 0, 0, 45))
        grad_r.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(shadow_r_rect, QBrush(grad_r))
