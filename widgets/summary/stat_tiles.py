"""
Stat Tiles style — 분리된 둥근 타일들, 큰 숫자 + 작은 라벨 (옵션 B).

자유 layout: QHBoxLayout(gap) + 각 타일 QFrame(border-radius). 사용자 정책
2026-04-30 — SUMMARY_RESERVED_H 34px 안에 fit, cell 크기 변동 0.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from widgets.summary.base import SummaryWidget, font_px, format_metrics


class SummaryStatTiles(SummaryWidget):
    HEADERS = ("Mean", "Range", "Non Unif.")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: white;")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(2, 1, 2, 1)
        outer.setSpacing(4)

        # font_px 로 font_scale 자동 비례. 라벨 base-3 (=11), 값 base (=14).
        from core.themes import FONT_SIZES
        _base = int(FONT_SIZES.get("body", 14))
        val_px = _base
        lbl_px = max(9, _base - 3)

        self._values: list[QLabel] = []
        for h in self.HEADERS:
            tile = QFrame()
            tile.setFrameShape(QFrame.Shape.NoFrame)
            tile.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            tile.setStyleSheet(
                "background-color: #f1f3f5; border-radius: 4px;"
            )
            v = QVBoxLayout(tile)
            v.setContentsMargins(2, 1, 2, 1)
            v.setSpacing(0)
            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(
                f"color: #1f3a5f; font-size: {val_px}px; font-weight: bold;"
            )
            lbl = QLabel(h)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: #666666; font-size: {lbl_px}px;"
            )
            v.addWidget(val)
            v.addWidget(lbl)
            outer.addWidget(tile, stretch=1)
            self._values.append(val)

    def update_metrics(self, metrics, decimals, percent_suffix=True):
        avg_s, range_s, nu_s = format_metrics(metrics, decimals, percent_suffix)
        for i, val in enumerate((avg_s, range_s, nu_s)):
            self._values[i].setText(val)

    def set_target_width(self, w: int) -> None:
        self.setFixedWidth(w)

    def get_natural_height(self) -> int:
        return 34
