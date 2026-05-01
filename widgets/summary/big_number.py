"""
Big Number style — 값 매우 크게, 라벨 작은 uppercase (옵션 J).

자유 layout: QHBoxLayout(equal stretch) + 각 metric 이 QVBoxLayout(라벨↑/값↓).
크기 정책 — ppt_basic 와 동일 setFixedHeight 영역 안에 fit.
폰트 — apply_fonts 가 매 update 시 호출되어 font_scale 자동 반영
(사용자 정책 2026-05-01, scope 1 review #1).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from widgets.summary.base import SummaryWidget, format_metrics


class SummaryBigNumber(SummaryWidget):
    HEADERS = ("Mean", "Range", "Non Unif.")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: white;")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._labels: list[QLabel] = []
        self._values: list[QLabel] = []
        for i, h in enumerate(self.HEADERS):
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(4)  # 라벨/값 사이
            # 라벨 — uppercase + thin space (U+2009, 일반 space 의 절반)
            lbl = QLabel(" ".join(h.upper()))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # 라벨+값 세로 중앙 — 위/아래 stretch 균등
            col.addStretch(1)
            col.addWidget(lbl)
            col.addWidget(val)
            col.addStretch(1)
            outer.addLayout(col, stretch=1)
            self._labels.append(lbl)
            self._values.append(val)
            # 세퍼레이터 — NoFrame 직사각 (VLine 이중선 회피)
            if i < len(self.HEADERS) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.NoFrame)
                sep.setFixedWidth(1)
                sep.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                sep.setStyleSheet("background-color: #dee2e6;")
                outer.addWidget(sep)
        # init 시점 폰트 적용 — apply_fonts 가 stylesheet 박제
        self.apply_fonts()

    def apply_fonts(self) -> None:
        # Big Number 정체성 — 값 base+6, 라벨 base-4. font_scale 자동 비례.
        from core.themes import FONT_SIZES
        _base = int(FONT_SIZES.get("body", 14))
        val_px = _base + 6
        lbl_px = max(8, _base - 4)
        lbl_ss = f"color: #6c757d; font-size: {lbl_px}px; font-weight: bold;"
        val_ss = f"color: #111111; font-size: {val_px}px; font-weight: bold;"
        for lbl in self._labels:
            lbl.setStyleSheet(lbl_ss)
        for val in self._values:
            val.setStyleSheet(val_ss)

    def update_metrics(self, metrics, decimals, percent_suffix=True):
        avg_s, range_s, nu_s = format_metrics(metrics, decimals, percent_suffix)
        for i, val in enumerate((avg_s, range_s, nu_s)):
            self._values[i].setText(val)

    def set_target_width(self, w: int) -> None:
        self.setFixedWidth(w)
