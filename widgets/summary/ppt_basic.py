"""
PPT Style (기본) — 기존 wafer_cell 의 QTableWidget(2행 × 3열) 그대로.

_TableSummary 베이스 사용 (사용자 정책 2026-05-01, scope 1 review #2).
시각 결과 동등성 보장 — 헤더 / 값 / delegate / stylesheet 모두 phase 1 이전과 동일.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QWidget

from widgets.summary.base import _TableSummary


class _PPTSummaryDelegate(QStyledItemDelegate):
    """Summary 표 cell painting — QSS background override 우회."""

    BG_HEADER = QColor("#f7f7f7")
    BG_VALUE = QColor("#ffffff")
    BORDER = QColor("#888888")
    TEXT = QColor("#111111")

    def paint(self, painter, option, index) -> None:
        bg = self.BG_HEADER if index.row() == 0 else self.BG_VALUE
        painter.fillRect(option.rect, bg)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text is not None:
            from PySide6.QtGui import QFont
            from core.themes import FONT_SIZES
            # 매 cell 마다 절대값 set — painter.font() sticky 누적 회피
            font = QFont(painter.font())
            font.setPixelSize(max(8, int(FONT_SIZES.get("body", 14)) - 1))
            painter.setFont(font)
            painter.setPen(self.TEXT)
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, str(text))
        painter.setPen(QPen(self.BORDER, 1))
        r = option.rect
        painter.drawLine(r.right(), r.top(), r.right(), r.bottom())
        painter.drawLine(r.left(), r.bottom(), r.right(), r.bottom())


class SummaryPPTBasic(_TableSummary):
    """PPT 기본 — 2행×3열, 첫 행 헤더 / 둘째 행 값."""

    TABLE_STYLESHEET = (
        "QTableWidget { background-color: white;"
        " border-top: 1px solid #888888; border-left: 1px solid #888888;"
        " border-right: none; border-bottom: none; }"
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def _make_delegate(self):
        return _PPTSummaryDelegate(self._table)

    def _fill_values(self, values: tuple[str, str, str]) -> None:
        for c, val in enumerate(values):
            self._set_cell(1, c, val)
