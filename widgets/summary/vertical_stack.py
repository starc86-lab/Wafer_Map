"""
Vertical Stack style — 세로 list (라벨 좌 / 값 우, 옵션 G).

기존 PPT 기본 테이블과 **동일 높이/폭** 보장 (사용자 정책 2026-04-30, align).
3 행 표시이지만 작은 폰트 (10px) + 행간 0 으로 우겨넣어 ~50px 안에 fit.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHeaderView, QStyledItemDelegate,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from widgets.summary.base import SummaryWidget, format_metrics


class _VerticalDelegate(QStyledItemDelegate):
    BG = QColor("#ffffff")
    BORDER = QColor("#e9ecef")
    TEXT_LABEL = QColor("#666666")
    TEXT_VALUE = QColor("#111111")

    def paint(self, painter, option, index) -> None:
        painter.fillRect(option.rect, self.BG)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text is not None:
            font = index.data(Qt.ItemDataRole.FontRole)
            if font is not None:
                painter.setFont(font)
            # col 0 = 라벨 (좌측 정렬, 회색), col 1 = 값 (우측 정렬, 검정 bold)
            painter.setPen(self.TEXT_LABEL if index.column() == 0 else self.TEXT_VALUE)
            r = option.rect.adjusted(8, 0, -8, 0)  # 좌우 8 padding
            align = (Qt.AlignmentFlag.AlignLeft if index.column() == 0
                     else Qt.AlignmentFlag.AlignRight) | Qt.AlignmentFlag.AlignVCenter
            painter.drawText(r, align, str(text))
        # 행 사이 옅은 구분선 (마지막 행 제외)
        if index.row() < 2:
            painter.setPen(QPen(self.BORDER, 1))
            r = option.rect
            painter.drawLine(r.left() + 4, r.bottom(), r.right() - 4, r.bottom())


class SummaryVerticalStack(SummaryWidget):
    LABELS = ("Mean", "Range", "Non Unif.")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table = QTableWidget(3, 2)
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
            "QTableWidget { background-color: white;"
            " border: 1px solid #888888;"
            " font-size: 9px; }"
        )
        self._table.setItemDelegate(_VerticalDelegate(self._table))
        # 각 행 11px — 3행 × 11 + frame 2 = 35 (ppt_basic 34 와 거의 동일,
        # SUMMARY_RESERVED_H 안에 fit). 사용자 정책 2026-04-30, cell 크기 align.
        self._table.verticalHeader().setDefaultSectionSize(11)
        layout.addWidget(self._table)

        # 라벨 1회 set
        for r, lbl in enumerate(self.LABELS):
            it = QTableWidgetItem(lbl)
            self._table.setItem(r, 0, it)
            self._table.setItem(r, 1, QTableWidgetItem("—"))

    def update_metrics(self, metrics, decimals, percent_suffix=True):
        avg_s, range_s, nu_s = format_metrics(metrics, decimals, percent_suffix)
        for r, val in enumerate((avg_s, range_s, nu_s)):
            it = self._table.item(r, 1)
            if it is None:
                self._table.setItem(r, 1, QTableWidgetItem(val))
            else:
                it.setText(val)
        # 11px × 3 + frame 2 = 35 (SUMMARY_RESERVED_H 34 와 거의 동일)
        h = 11 * 3 + 2
        self._table.setFixedHeight(h)
        self.setFixedHeight(h)

    def set_target_width(self, w: int) -> None:
        self.setFixedWidth(w)
        self._table.setFixedWidth(w)

    def context_menu_target(self) -> QWidget:
        return self._table
