"""
Highlight Lead style — Mean 큰 강조 + 좌측 색띠, Range/NU 우측 작게 (옵션 C).
폰트 — apply_fonts 가 매 update 호출되어 font_scale 자동 반영.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from widgets.summary.base import SummaryWidget, format_metrics


class SummaryHighlightLead(SummaryWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: white;")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 좌측 색 띠
        strip = QFrame()
        strip.setFrameShape(QFrame.Shape.NoFrame)
        strip.setFixedWidth(3)
        strip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        strip.setStyleSheet("background-color: #e63946;")
        outer.addWidget(strip)

        # Mean 영역 (좌, 큰 폰트)
        left = QVBoxLayout()
        left.setContentsMargins(8, 0, 4, 0)
        left.setSpacing(0)
        self._mean_lbl = QLabel("Mean")
        self._mean_val = QLabel("—")
        left.addWidget(self._mean_lbl)
        left.addWidget(self._mean_val)
        outer.addLayout(left, stretch=2)

        # 세퍼레이터
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.NoFrame)
        sep.setFixedWidth(1)
        sep.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sep.setStyleSheet("background-color: #dee2e6;")
        outer.addWidget(sep)

        # 우측 보조 (Range, NU)
        self._right_lbls: list[QLabel] = []
        self._right_vals: list[QLabel] = []
        for name in ("Range", "Non Unif."):
            col = QVBoxLayout()
            col.setContentsMargins(4, 0, 4, 0)
            col.setSpacing(0)
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v = QLabel("—")
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(lbl)
            col.addWidget(v)
            outer.addLayout(col, stretch=1)
            self._right_lbls.append(lbl)
            self._right_vals.append(v)
        self.apply_fonts()

    def apply_fonts(self) -> None:
        from core.themes import FONT_SIZES
        _base = int(FONT_SIZES.get("body", 14))
        lbl_px = max(9, _base - 3)
        val_px = _base + 4
        lbl_ss = f"color: #666666; font-size: {lbl_px}px;"
        val_ss = f"color: #111111; font-size: {val_px}px; font-weight: bold;"
        self._mean_lbl.setStyleSheet(lbl_ss)
        self._mean_val.setStyleSheet(val_ss)
        for l in self._right_lbls:
            l.setStyleSheet(lbl_ss)
        for v in self._right_vals:
            v.setStyleSheet(val_ss)

    def update_metrics(self, metrics, decimals, percent_suffix=True):
        avg_s, range_s, nu_s = format_metrics(metrics, decimals, percent_suffix)
        self._mean_val.setText(avg_s)
        self._right_vals[0].setText(range_s)
        self._right_vals[1].setText(nu_s)

    def set_target_width(self, w: int) -> None:
        self.setFixedWidth(w)
