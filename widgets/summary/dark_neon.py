"""
Dark Neon style — 검정 배경 + 민트 강조 (옵션 F).

_TableSummary 베이스 사용. 색만 다름 (delegate + stylesheet).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QWidget

from widgets.summary.base import _TableSummary


class _DarkNeonDelegate(QStyledItemDelegate):
    BG_HEADER = QColor("#4a5460")
    BG_VALUE = QColor("#404a55")
    BORDER = QColor("#5a6470")
    TEXT_LABEL = QColor("#d8dde3")
    TEXT_VALUE = QColor("#00d9a3")

    def paint(self, painter, option, index) -> None:
        bg = self.BG_HEADER if index.row() == 0 else self.BG_VALUE
        painter.fillRect(option.rect, bg)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text is not None:
            from PySide6.QtGui import QFont
            from core.themes import FONT_SIZES
            font = QFont(painter.font())
            font.setPixelSize(max(8, int(FONT_SIZES.get("body", 14)) - 1))
            painter.setFont(font)
            painter.setPen(self.TEXT_LABEL if index.row() == 0 else self.TEXT_VALUE)
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, str(text))
        if index.column() < 2:
            painter.setPen(QPen(self.BORDER, 1))
            r = option.rect
            painter.drawLine(r.right(), r.top() + 4, r.right(), r.bottom() - 4)


class SummaryDarkNeon(_TableSummary):
    TABLE_STYLESHEET = (
        "QTableWidget { background-color: #404a55;"
        " border: 1px solid #5a6470; }"
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def _make_delegate(self):
        return _DarkNeonDelegate(self._table)

    def _fill_values(self, values: tuple[str, str, str]) -> None:
        for c, val in enumerate(values):
            self._set_cell(1, c, val)
