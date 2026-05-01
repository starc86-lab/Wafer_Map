"""
Color Footer style — 값+라벨 위, 하단 색 띠 metric 별 다른 색 (옵션 I).
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
        self.setStyleSheet(
            "SummaryColorFooter { background-color: white;"
            " border: 1px solid #dee2e6; }"
        )
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        from core.themes import FONT_SIZES
        _base = int(FONT_SIZES.get("body", 14))
        lbl_px = max(9, _base - 3)
        val_px = _base

        self._values: list[QLabel] = []
        for i, h in enumerate(self.HEADERS):
            col_w = QWidget()
            col = QVBoxLayout(col_w)
            col.setContentsMargins(0, 1, 0, 0)
            col.setSpacing(0)
            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(
                f"color: #111111; font-size: {val_px}px; font-weight: bold;"
            )
            lbl = QLabel(h)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: #666666; font-size: {lbl_px}px;"
            )
            footer = QFrame()
            footer.setFixedHeight(3)
            footer.setStyleSheet(
                f"background-color: {_FOOTER_COLORS[i]}; border: none;"
            )
            col.addWidget(val)
            col.addWidget(lbl)
            col.addWidget(footer)
            outer.addWidget(col_w, stretch=1)
            self._values.append(val)
            # 세퍼레이터 — Plain shadow 로 single line (사용자 정책 2026-05-01 fix)
            if i < len(self.HEADERS) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setFrameShadow(QFrame.Shadow.Plain)
                sep.setLineWidth(1)
                sep.setFixedWidth(1)
                sep.setStyleSheet(
                    "background-color: #dee2e6;"
                )
                outer.addWidget(sep)

    def update_metrics(self, metrics, decimals, percent_suffix=True):
        avg_s, range_s, nu_s = format_metrics(metrics, decimals, percent_suffix)
        for i, val in enumerate((avg_s, range_s, nu_s)):
            self._values[i].setText(val)

    def set_target_width(self, w: int) -> None:
        self.setFixedWidth(w)

    def get_natural_height(self) -> int:
        return 34
