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
        # paintEvent 가 카드 그림 — widget 자체 흰 배경 (cell 동일).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: white;")
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
            col = QVBoxLayout(col_w)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            lbl = QLabel(h)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: #666666; font-size: {lbl_px}px;"
            )
            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(
                f"color: #111111; font-size: {val_px}px; font-weight: bold;"
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
        """앞 카드 + 뒤 카드 2장 (우/하만 offset, 좌/상 일치) — 우하단 그림자.

        이전 translated 방식은 좌/상도 함께 offset 되어 좌측 그림자 보이고
        모서리 어긋남. 좌/상 = front 와 동일, 우/하 만 +offset 으로 변경
        (사용자 정책 2026-05-01).
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        # 본 카드 — 우하단 offset 만큼 줄어든 영역
        front = QRectF(
            rect.left() + 1,
            rect.top() + 1,
            rect.width() - 2 - self._OFFSET_2,
            rect.height() - 2 - self._OFFSET_2,
        )
        # 뒤 카드 2 (가장 뒤) — 좌/상 = front, 우/하 = front +OFFSET_2
        back2 = QRectF(
            front.left(), front.top(),
            front.width() + self._OFFSET_2,
            front.height() + self._OFFSET_2,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._BACK_2))
        painter.drawRoundedRect(back2, self._RADIUS, self._RADIUS)
        # 뒤 카드 1 — 좌/상 = front, 우/하 = front +OFFSET_1
        back1 = QRectF(
            front.left(), front.top(),
            front.width() + self._OFFSET_1,
            front.height() + self._OFFSET_1,
        )
        painter.setBrush(QBrush(self._BACK_1))
        painter.drawRoundedRect(back1, self._RADIUS, self._RADIUS)
        # 앞 카드 (흰색 + 가는 테두리)
        painter.setPen(QPen(self._FRONT_BORDER, 0.8))
        painter.setBrush(QBrush(self._FRONT))
        painter.drawRoundedRect(front, self._RADIUS, self._RADIUS)
        painter.end()
        super().paintEvent(event)
