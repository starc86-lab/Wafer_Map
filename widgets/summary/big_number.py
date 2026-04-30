"""
Big Number style — 값 매우 크게, 라벨 작은 uppercase (옵션 J).

자유 layout: QHBoxLayout(equal stretch) + 각 metric 이 QVBoxLayout(라벨↑/값↓).
크기 정책 — ppt_basic 와 동일 setFixedHeight 영역 안에 fit (사용자 정책 2026-04-30).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from widgets.summary.base import SummaryWidget, format_metrics


def _spaced(s: str) -> str:
    """uppercase + 토큰별 공백 — letterspacing 흉내."""
    return " ".join(s.upper())


class SummaryBigNumber(SummaryWidget):
    HEADERS = ("Mean", "Range", "Non Unif.")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # 외곽 가는 테두리 — 다른 style 과 시각 통일
        self.setStyleSheet(
            "SummaryBigNumber { background-color: white;"
            " border: 1px solid #888888; }"
        )
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._labels: list[QLabel] = []
        self._values: list[QLabel] = []
        for i, h in enumerate(self.HEADERS):
            col = QVBoxLayout()
            col.setContentsMargins(0, 1, 0, 1)
            col.setSpacing(0)
            lbl = QLabel(_spaced(h))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                "QLabel { color: #adb5bd; font-size: 8px; font-weight: bold;"
                " background-color: transparent; }"
            )
            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(
                "QLabel { color: #111111; font-size: 16px; font-weight: bold;"
                " background-color: transparent; }"
            )
            col.addWidget(lbl)
            col.addWidget(val)
            outer.addLayout(col, stretch=1)
            self._labels.append(lbl)
            self._values.append(val)
            # 세퍼레이터 (마지막 컬럼 제외)
            if i < len(self.HEADERS) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setStyleSheet("QFrame { color: #f1f3f5; }")
                outer.addWidget(sep)

    def update_metrics(self, metrics, decimals, percent_suffix=True):
        avg_s, range_s, nu_s = format_metrics(metrics, decimals, percent_suffix)
        for i, val in enumerate((avg_s, range_s, nu_s)):
            self._values[i].setText(val)

    def set_target_width(self, w: int) -> None:
        self.setFixedWidth(w)

    def get_natural_height(self) -> int:
        # 1 padding + 8px 라벨 + 0 spacing + 16px 값 + 1 padding + frame ≈ 34
        return 34
