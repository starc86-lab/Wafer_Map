"""
Pill Badge style — 라벨이 둥근 색 pill, 값 큰 폰트 (옵션 E).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from widgets.summary.base import SummaryWidget, format_metrics


_PILL_COLORS = ("#264653", "#2a9d8f", "#e76f51")


class SummaryPillBadge(SummaryWidget):
    HEADERS = ("Mean", "Range", "Non Unif.")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # 흰색 고정 — selector 없는 단순 properties + WA_StyledBackground.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: white;")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(2, 1, 2, 1)
        outer.setSpacing(0)

        from core.themes import FONT_SIZES
        _base = int(FONT_SIZES.get("body", 14))
        lbl_px = max(9, _base - 3)
        val_px = _base + 1
        pill_h = lbl_px + 4   # pill 안 텍스트 padding 포함

        self._values: list[QLabel] = []
        for i, h in enumerate(self.HEADERS):
            col_w = QWidget()
            col = QVBoxLayout(col_w)
            col.setContentsMargins(2, 0, 2, 0)
            col.setSpacing(0)
            col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            # pill 라벨 — QLabel 의 border-radius 로 둥근 모서리
            pill = QLabel(h)
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setFixedHeight(pill_h)
            pill.setStyleSheet(
                f"color: white; font-size: {lbl_px}px; font-weight: bold;"
                f" background-color: {_PILL_COLORS[i]};"
                f" border-radius: {pill_h // 2}px;"
                " padding-left: 6px; padding-right: 6px;"
            )
            # 가운데 위치 — 좌우 stretch
            pill_row = QHBoxLayout()
            pill_row.setContentsMargins(0, 0, 0, 0)
            pill_row.addStretch(1)
            pill_row.addWidget(pill)
            pill_row.addStretch(1)
            col.addLayout(pill_row)

            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(
                f"color: #111111; font-size: {val_px}px; font-weight: bold;"
            )
            col.addWidget(val)
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
