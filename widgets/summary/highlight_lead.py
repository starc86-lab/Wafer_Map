"""
Highlight Lead style — Mean 큰 강조 + 좌측 색띠, Range/NU 우측 작게 (옵션 C).

자유 layout 비대칭. SUMMARY_RESERVED_H 34px 안에 fit.
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
        self.setStyleSheet(
            "SummaryHighlightLead { background-color: white;"
            " border: 1px solid #888888; }"
        )
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # font_scale 자동 비례 — 라벨 base-3 (=11), 값 base-2 (Range/NU 보조).
        from core.themes import FONT_SIZES
        _base = int(FONT_SIZES.get("body", 14))
        lbl_px = max(9, _base - 3)
        val_px = max(10, _base - 2)
        mean_px = _base + 4   # Mean 강조

        # 좌측 색 띠
        strip = QFrame()
        strip.setFixedWidth(3)
        strip.setStyleSheet("QFrame { background-color: #e63946; }")
        outer.addWidget(strip)

        # Mean 영역 (좌측, 큰 폰트)
        left = QVBoxLayout()
        left.setContentsMargins(8, 0, 4, 0)
        left.setSpacing(0)
        self._mean_lbl = QLabel("Mean")
        self._mean_lbl.setStyleSheet(
            f"QLabel {{ color: #666; font-size: {lbl_px}px; background: transparent; }}"
        )
        self._mean_val = QLabel("—")
        self._mean_val.setStyleSheet(
            f"QLabel {{ color: #111; font-size: {mean_px}px; font-weight: bold;"
            " background: transparent; }}"
        )
        left.addWidget(self._mean_lbl)
        left.addWidget(self._mean_val)
        outer.addLayout(left, stretch=2)

        # 세퍼레이터
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("QFrame { color: #dee2e6; }")
        outer.addWidget(sep)

        # 우측 보조 (Range, NU)
        self._right_vals: list[QLabel] = []
        for name in ("Range", "Non Unif."):
            col = QVBoxLayout()
            col.setContentsMargins(4, 0, 4, 0)
            col.setSpacing(0)
            l = QLabel(name)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setStyleSheet(
                f"QLabel {{ color: #666; font-size: {lbl_px}px; background: transparent; }}"
            )
            v = QLabel("—")
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.setStyleSheet(
                f"QLabel {{ color: #111; font-size: {val_px}px; font-weight: bold;"
                " background: transparent; }}"
            )
            col.addWidget(l)
            col.addWidget(v)
            outer.addLayout(col, stretch=1)
            self._right_vals.append(v)

    def update_metrics(self, metrics, decimals, percent_suffix=True):
        avg_s, range_s, nu_s = format_metrics(metrics, decimals, percent_suffix)
        self._mean_val.setText(avg_s)
        self._right_vals[0].setText(range_s)
        self._right_vals[1].setText(nu_s)

    def set_target_width(self, w: int) -> None:
        self.setFixedWidth(w)

    def get_natural_height(self) -> int:
        return 34
