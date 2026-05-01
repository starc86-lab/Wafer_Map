"""
Layered Depth style — 본 카드 뒤로 어긋난 카드 2장 (스택 효과, 옵션 N).

paintEvent 로 직접 그림 — drawRoundedRect 3장 (offset 다름) + 본 카드 위
QLabel child 로 metric 표시.

SUMMARY_RESERVED_H 34px 안에 fit. cell 크기 align 보장 (사용자 정책 2026-04-30).
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from widgets.summary.base import SummaryWidget, format_metrics


class SummaryLayeredDepth(SummaryWidget):
    HEADERS = ("Mean", "Range", "Non Unif.")

    # 뒤 카드 색상 (앞에서 뒤로 갈수록 어두워짐)
    _BACK_2 = QColor("#d7dbe0")
    _BACK_1 = QColor("#c7ccd2")
    _FRONT = QColor("#ffffff")
    _FRONT_BORDER = QColor("#a8aab0")

    # offset (px) — 우하단 어긋남 (뒤로 갈수록 멀어짐)
    _OFFSET_1 = 1
    _OFFSET_2 = 2
    _RADIUS = 3.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # 외곽 layout 은 투명 — 실제 카드 그리기는 paintEvent
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        outer = QHBoxLayout(self)
        # 본 카드 영역 안쪽 padding (offset 만큼 우하단 여백 + 카드 내부 padding)
        outer.setContentsMargins(2, 1, 2 + self._OFFSET_2, 1 + self._OFFSET_2)
        outer.setSpacing(0)

        from core.themes import FONT_SIZES
        _base = int(FONT_SIZES.get("body", 14))
        lbl_px = max(9, _base - 3)
        val_px = _base

        self._values: list[QLabel] = []
        for i, h in enumerate(self.HEADERS):
            col_w = QWidget()
            col_w.setStyleSheet("background: transparent;")
            col = QVBoxLayout(col_w)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            lbl = QLabel(h)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"QLabel {{ color: #666; font-size: {lbl_px}px; background: transparent; }}"
            )
            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(
                f"QLabel {{ color: #111; font-size: {val_px}px; font-weight: bold;"
                " background: transparent; }}"
            )
            col.addWidget(lbl)
            col.addWidget(val)
            outer.addWidget(col_w, stretch=1)
            self._values.append(val)
            # 세퍼레이터 — paint 에서 그릴 수도 있지만 단순 child label 로
            if i < len(self.HEADERS) - 1:
                sep = QLabel()
                sep.setFixedWidth(1)
                sep.setStyleSheet("QLabel { background-color: #e9ecef; }")
                outer.addWidget(sep)

    def update_metrics(self, metrics, decimals, percent_suffix=True):
        avg_s, range_s, nu_s = format_metrics(metrics, decimals, percent_suffix)
        for i, val in enumerate((avg_s, range_s, nu_s)):
            self._values[i].setText(val)

    def set_target_width(self, w: int) -> None:
        self.setFixedWidth(w)

    def get_natural_height(self) -> int:
        return 34

    def paintEvent(self, event):
        """뒤 카드 2장 (offset) + 앞 카드 1장 (흰색 + border) 그리기."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        # 본 카드 영역 = 우하단 offset 만큼 줄어든 영역
        front = QRectF(
            rect.left() + 1,
            rect.top() + 1,
            rect.width() - 2 - self._OFFSET_2,
            rect.height() - 2 - self._OFFSET_2,
        )
        # 뒤 카드 2 (가장 뒤, 가장 어둡게, 가장 멀리)
        back2 = front.translated(self._OFFSET_2, self._OFFSET_2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._BACK_2))
        painter.drawRoundedRect(back2, self._RADIUS, self._RADIUS)
        # 뒤 카드 1
        back1 = front.translated(self._OFFSET_1, self._OFFSET_1)
        painter.setBrush(QBrush(self._BACK_1))
        painter.drawRoundedRect(back1, self._RADIUS, self._RADIUS)
        # 앞 카드 (흰색 + 가는 테두리)
        painter.setPen(QPen(self._FRONT_BORDER, 0.8))
        painter.setBrush(QBrush(self._FRONT))
        painter.drawRoundedRect(front, self._RADIUS, self._RADIUS)
        painter.end()
        super().paintEvent(event)
