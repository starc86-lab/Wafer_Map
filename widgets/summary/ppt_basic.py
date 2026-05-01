"""
PPT Style (기본) — 기존 wafer_cell 의 QTableWidget(2행 × 3열) 그대로 이전.

회귀 0 보장: 기존 코드와 1:1 동일. 사용자 정책 2026-04-30 — 모든 다른
style 이 이 베이스의 동일 크기를 따라 cell 전체 width/height 불변.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHeaderView, QStyledItemDelegate,
    QTableWidget, QTableWidgetItem, QWidget,
)

from widgets.summary.base import SummaryWidget, format_metrics


class _PPTSummaryDelegate(QStyledItemDelegate):
    """Summary 표 cell painting 전담 — QSS stylesheet 이 setBackground() 를
    override 하는 Qt 버그 우회. row 별 bg + 1px 테두리 + 텍스트 직접 그림.
    """
    BG_HEADER = QColor("#f7f7f7")
    BG_VALUE = QColor("#ffffff")
    BORDER = QColor("#888888")
    TEXT = QColor("#111111")

    def paint(self, painter, option, index) -> None:
        bg = self.BG_HEADER if index.row() == 0 else self.BG_VALUE
        painter.fillRect(option.rect, bg)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text is not None:
            font = index.data(Qt.ItemDataRole.FontRole) or painter.font()
            # 사용자 정책 2026-05-01 — 폰트 -1px
            ps = font.pixelSize()
            if ps > 0:
                font.setPixelSize(max(8, ps - 1))
            painter.setFont(font)
            painter.setPen(self.TEXT)
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, str(text))
        painter.setPen(QPen(self.BORDER, 1))
        r = option.rect
        painter.drawLine(r.right(), r.top(), r.right(), r.bottom())
        painter.drawLine(r.left(), r.bottom(), r.right(), r.bottom())


class SummaryPPTBasic(SummaryWidget):
    """기존 PPT 기본 스타일 — QTableWidget 2행 × 3열 (header / values).

    헤더: Mean / Range / Non Unif.
    값: format_metrics 결과
    """

    HEADERS = ("Mean", "Range", "Non Unif.")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QVBoxLayout
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
            "QTableWidget { background-color: white;"
            " border-top: 1px solid #888888; border-left: 1px solid #888888;"
            " border-right: none; border-bottom: none; }"
        )
        self._table.setItemDelegate(_PPTSummaryDelegate(self._table))
        layout.addWidget(self._table)

        # 헤더 1회 set
        for c, lbl in enumerate(self.HEADERS):
            self._set_cell(0, c, lbl)

    def _set_cell(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, col, item)

    def update_metrics(
        self, metrics: dict, decimals: int, percent_suffix: bool = True,
    ) -> None:
        avg_s, range_s, nu_s = format_metrics(metrics, decimals, percent_suffix)
        self._set_cell(1, 0, avg_s)
        self._set_cell(1, 1, range_s)
        self._set_cell(1, 2, nu_s)
        # content 기반 높이 자동 계산
        self._table.resizeRowsToContents()
        total_h = sum(self._table.rowHeight(r) for r in range(self._table.rowCount()))
        frame = 2 * self._table.frameWidth()
        h = total_h + frame
        self._table.setFixedHeight(h)
        self.setFixedHeight(h)

    def set_target_width(self, w: int) -> None:
        self.setFixedWidth(w)
        self._table.setFixedWidth(w)

    def get_natural_height(self) -> int:
        return self.height() if self.height() > 0 else 50

    def context_menu_target(self) -> QWidget:
        """우클릭 메뉴 연결 대상 — wafer_cell 이 customContextMenuRequested 연결."""
        return self._table
