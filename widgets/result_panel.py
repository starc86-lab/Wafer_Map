"""
결과 패널 — 상단 summary 라벨 + 하단 가로 스크롤 Cell 나열.

외부 API:
    panel.set_displays(displays, value_name, summary_line="")
    panel.clear()
"""
from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from widgets.wafer_cell import WaferCell, WaferDisplay


class ResultPanel(QWidget):
    """상단 summary(DELTA 모드용) + 하단 가로 스크롤 Cells."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet(
            "color: #2a9d8f; font-weight: bold; padding: 6px 10px;"
        )
        self._summary_label.hide()
        root.addWidget(self._summary_label)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self._container = QWidget()
        self._layout = QHBoxLayout(self._container)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(8)
        self._scroll.setWidget(self._container)
        root.addWidget(self._scroll, stretch=1)

        self._show_placeholder()

    def _show_placeholder(self) -> None:
        self._summary_label.hide()
        self._clear_layout()
        ph = QLabel(
            "결과 영역 — Visualize 누르면 여기에 MAP + Summary 표가 가로로 나열됩니다"
        )
        ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph.setStyleSheet("color: gray; padding: 40px;")
        self._layout.addWidget(ph)

    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def clear(self) -> None:
        self._show_placeholder()

    def set_displays(
        self,
        displays: Iterable[WaferDisplay],
        value_name: str,
        view_mode: str = "2D",
        summary_line: str = "",
    ) -> None:
        displays = list(displays)
        self._clear_layout()
        if not displays:
            self._show_placeholder()
            return

        if summary_line:
            self._summary_label.setText(summary_line)
            self._summary_label.show()
        else:
            self._summary_label.hide()

        for d in displays:
            cell = WaferCell(d, value_name, view_mode=view_mode)
            self._layout.addWidget(cell)
        self._layout.addStretch(1)
