"""
Vertical Stack style — 세로 list (라벨 좌 / 값 우, 옵션 G).

_TableSummary 베이스 (3 row × 2 col 변형). 가로폭 0.87 inset, fit_to_height
로 행 높이 균등 재분배.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QTableWidgetItem, QWidget

from widgets.summary.base import _TableSummary


class _VerticalDelegate(QStyledItemDelegate):
    BG = QColor("#ffffff")
    BORDER = QColor("#e9ecef")
    TEXT_LABEL = QColor("#666666")
    TEXT_VALUE = QColor("#111111")

    def paint(self, painter, option, index) -> None:
        painter.fillRect(option.rect, self.BG)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text is not None:
            from PySide6.QtGui import QFont
            from core.themes import FONT_SIZES
            font = QFont(painter.font())
            font.setBold(index.column() == 1)
            font.setPixelSize(max(8, int(FONT_SIZES.get("body", 14)) - 1))
            painter.setFont(font)
            painter.setPen(self.TEXT_LABEL if index.column() == 0 else self.TEXT_VALUE)
            # 명시 baseline 계산 — AlignVCenter flag 가 일부 환경에서 하단 정렬되어
            # 보이는 회귀 fix (사용자 정책 2026-05-02). fontMetrics 의 ascent/descent
            # 으로 cell rect 정중앙에 텍스트 중앙선 위치.
            fm = painter.fontMetrics()
            r = option.rect
            text_str = str(text)
            text_w = fm.horizontalAdvance(text_str)
            # 세로 정중앙: top + (height - ascent - descent) / 2 + ascent
            y_baseline = r.y() + (r.height() + fm.ascent() - fm.descent()) // 2
            if index.column() == 0:
                x = r.x() + 8
            else:
                x = r.right() - 8 - text_w
            painter.drawText(x, y_baseline, text_str)
        # 행 사이 옅은 구분선 (마지막 행 제외)
        if index.row() < 2:
            painter.setPen(QPen(self.BORDER, 1))
            r = option.rect
            painter.drawLine(r.left() + 4, r.bottom(), r.right() - 4, r.bottom())


class SummaryVerticalStack(_TableSummary):
    """3행×2열 — col 0 = 라벨, col 1 = 값. 가로 0.87 inset."""

    ROWS = 3
    COLS = 2
    LABELS = ("Mean", "Range", "Non Unif.")
    TABLE_STYLESHEET = (
        "QTableWidget { background-color: white;"
        " border: 1px solid #888888; }"
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def _make_delegate(self):
        return _VerticalDelegate(self._table)

    def _populate_headers(self) -> None:
        # col 0 라벨 + col 1 placeholder
        for r, lbl in enumerate(self.LABELS):
            self._table.setItem(r, 0, QTableWidgetItem(lbl))
            self._table.setItem(r, 1, QTableWidgetItem("—"))

    def _fill_values(self, values: tuple[str, str, str]) -> None:
        for r, val in enumerate(values):
            it = self._table.item(r, 1)
            if it is None:
                self._table.setItem(r, 1, QTableWidgetItem(val))
            else:
                it.setText(val)

    def set_target_width(self, w: int) -> None:
        # vertical_stack 만 가로 0.87 — 그래프 x축 (웨이퍼 직경) 매칭
        target = int(w * 0.87)
        super().set_target_width(target)

    def fit_to_height(self, h: int) -> None:
        """3 행을 reserved 안에 균등 분배. font_scale 자동 비례."""
        if h <= 0:
            return
        frame = 2 * self._table.frameWidth()
        per_row = max(8, (h - frame) // 3)
        self._table.verticalHeader().setDefaultSectionSize(per_row)
        for r in range(3):
            self._table.setRowHeight(r, per_row)
        self._table.setFixedHeight(h)
