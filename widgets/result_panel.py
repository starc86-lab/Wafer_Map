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

        # 첫 Run Analysis 시 GLViewWidget이 추가되며 ancestor가 native window로
        # 일괄 승격되는 시점의 윈도우 깜빡임 제거 — startup에 미리 영구 자식 1개 두기
        import pyqtgraph.opengl as gl
        self._gl_anchor = gl.GLViewWidget(self._container)
        self._gl_anchor.resize(1, 1)
        self._gl_anchor.hide()

        self._cells: list[WaferCell] = []
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
        self._cells.clear()

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
            self._cells.append(cell)
            self._layout.addWidget(cell)
        self._layout.addStretch(1)

    def set_view_mode(self, mode: str) -> None:
        """View 토글 — 모든 cell에 forward (cell이 캐시 보유, 재계산 없음)."""
        for c in self._cells:
            c.set_view_mode(mode)

    @property
    def cells(self) -> list[WaferCell]:
        return self._cells

    def invalidate_3d(self) -> None:
        """3D 캐시 무효화 — z_range 변경 시. 2D 캐시는 그대로."""
        for c in self._cells:
            c.invalidate_3d()

    def refresh_all(self) -> None:
        """Settings 변경 시 — 모든 cell 렌더 캐시 reset.

        보간 캐시는 각 cell이 (method, grid) 비교로 알아서 재사용/재계산 결정.
        """
        for c in self._cells:
            c.refresh()
