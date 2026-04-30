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

from widgets.summary.base import SummaryWidget, font_px, format_metrics


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
        # 사용자 정책 2026-04-30 — Big Number 정체성 강조. 값 / 라벨 모두
        # 일반 style 보다 큼. base 받아 자체 비율 (val=base+6, lbl=base-2).
        # font_scale 자동 비례.
        from core.themes import FONT_SIZES
        _base = int(FONT_SIZES.get("body", 14))
        val_px = _base + 6   # base 14 → 20
        lbl_px = max(8, _base - 4)  # base 14 → 10
        for i, h in enumerate(self.HEADERS):
            col = QVBoxLayout()
            col.setContentsMargins(0, 1, 0, 1)
            col.setSpacing(0)
            lbl = QLabel(_spaced(h))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"QLabel {{ color: #6c757d; font-size: {lbl_px}px;"
                " font-weight: bold; background-color: transparent; }}"
            )
            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(
                f"QLabel {{ color: #111111; font-size: {val_px}px;"
                " font-weight: bold; background-color: transparent; }}"
            )
            col.addWidget(lbl)
            col.addWidget(val)
            outer.addLayout(col, stretch=1)
            self._labels.append(lbl)
            self._values.append(val)
            # 세퍼레이터 — Plain shadow 로 single line (VLine 의 default Sunken
            # 은 이중선 효과 발생, 사용자 정책 2026-04-30 fix).
            if i < len(self.HEADERS) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setFrameShadow(QFrame.Shadow.Plain)
                sep.setLineWidth(1)
                sep.setStyleSheet(
                    "QFrame { color: #dee2e6; background-color: #dee2e6; }"
                )
                sep.setFixedWidth(1)
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
