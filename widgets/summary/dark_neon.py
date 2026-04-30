"""
Dark Neon style — 검정 배경 + 민트 강조 (옵션 F).

QTableWidget(2, 3) 베이스, 색만 변경. 다른 style 과 동일한 layout / 크기 정책 →
cell align 변동 0 보장 (사용자 정책 2026-04-30).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHeaderView, QStyledItemDelegate,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from widgets.summary.base import SummaryWidget, format_metrics


class _DarkNeonDelegate(QStyledItemDelegate):
    BG_HEADER = QColor("#0d1117")  # 헤더도 동일 배경 (label 작게 회색)
    BG_VALUE = QColor("#0d1117")
    BORDER = QColor("#30363d")
    TEXT_LABEL = QColor("#7d8590")
    TEXT_VALUE = QColor("#00d9a3")  # 민트 accent

    def paint(self, painter, option, index) -> None:
        bg = self.BG_HEADER if index.row() == 0 else self.BG_VALUE
        painter.fillRect(option.rect, bg)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text is not None:
            font = index.data(Qt.ItemDataRole.FontRole)
            if font is not None:
                painter.setFont(font)
            painter.setPen(self.TEXT_LABEL if index.row() == 0 else self.TEXT_VALUE)
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, str(text))
        # 세퍼레이터 (cell 사이 verticalline 만, 마지막 col 제외)
        if index.column() < 2:
            painter.setPen(QPen(self.BORDER, 1))
            r = option.rect
            painter.drawLine(r.right(), r.top() + 4, r.right(), r.bottom() - 4)


class SummaryDarkNeon(SummaryWidget):
    HEADERS = ("Mean", "Range", "Non Unif.")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table = QTableWidget(2, 3)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().hide()
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._table.setFrameShape(QFrame.Shape.NoFrame)
        self._table.setShowGrid(False)
        self._table.setStyleSheet(
            "QTableWidget { background-color: #0d1117;"
            " border: 1px solid #30363d; }"
        )
        self._table.setItemDelegate(_DarkNeonDelegate(self._table))
        layout.addWidget(self._table)

        for c, lbl in enumerate(self.HEADERS):
            self._set_cell(0, c, lbl)

    def _set_cell(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, col, item)

    def update_metrics(self, metrics, decimals, percent_suffix=True):
        avg_s, range_s, nu_s = format_metrics(metrics, decimals, percent_suffix)
        self._set_cell(1, 0, avg_s)
        self._set_cell(1, 1, range_s)
        self._set_cell(1, 2, nu_s)
        self._table.resizeRowsToContents()
        total_h = sum(self._table.rowHeight(r) for r in range(self._table.rowCount()))
        frame = 2 * self._table.frameWidth()
        h = total_h + frame
        self._table.setFixedHeight(h)
        self.setFixedHeight(h)

    def set_target_width(self, w: int) -> None:
        self.setFixedWidth(w)
        self._table.setFixedWidth(w)

    def context_menu_target(self) -> QWidget:
        return self._table
