"""
Ctrl+V 페이스트 영역. 텍스트/표 두 뷰를 토글로 전환.

- 입력 텍스트 변경 시 `parse_wafer_csv` 자동 호출 → 요약 라벨 업데이트
- 파싱 성공 시 DataFrame을 QTableWidget 뷰에도 채움 (Table 버튼 활성)
- 텍스트 뷰는 줄바꿈 OFF + 가로 스크롤바 (원본 행 구조 유지)
"""
from __future__ import annotations

import pandas as pd

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QHBoxLayout, QHeaderView,
    QLabel, QPlainTextEdit, QPushButton, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from main import MissingColumnsError, ParseResult, _load_dataframe, parse_wafer_csv


class PasteArea(QWidget):
    """Ctrl+V 페이스트 + 텍스트/표 뷰 토글."""

    parsed = Signal(object)  # ParseResult | None

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._result: ParseResult | None = None
        self._df: pd.DataFrame | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        # ── 헤더: 타이틀 + 뷰 토글 ──
        header = QHBoxLayout()
        header.setSpacing(4)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold;")
        header.addWidget(title_label)
        header.addStretch(1)

        self._btn_text = QPushButton("Text")
        self._btn_table = QPushButton("Table")
        self._btn_clear = QPushButton("Clear")
        for b in (self._btn_text, self._btn_table, self._btn_clear):
            b.setFixedHeight(24)
            b.setStyleSheet(
                "QPushButton { padding: 2px 10px; min-height: 24px; max-height: 24px; "
                "font-weight: normal; }"
            )
        for b in (self._btn_text, self._btn_table):
            b.setCheckable(True)
        self._btn_text.setChecked(True)
        self._btn_table.setEnabled(False)
        self._btn_clear.clicked.connect(self._on_clear_clicked)

        self._view_group = QButtonGroup(self)
        self._view_group.setExclusive(True)
        self._view_group.addButton(self._btn_text, 0)
        self._view_group.addButton(self._btn_table, 1)
        self._view_group.idClicked.connect(self._on_view_changed)

        header.addWidget(self._btn_text)
        header.addWidget(self._btn_table)
        header.addSpacing(8)
        header.addWidget(self._btn_clear)
        lay.addLayout(header)

        # ── Stacked: Text / Table ──
        self._stacked = QStackedWidget()

        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText(
            "여기에 클립보드 데이터를 Ctrl+V 로 붙여넣기"
        )
        # 줄바꿈 OFF → 원본 행 그대로, 긴 행은 가로 스크롤바
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._editor.textChanged.connect(self._on_text_changed)
        self._stacked.addWidget(self._editor)

        self._table = QTableWidget()
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents,
        )
        # Table 뷰에서도 Ctrl+V 동작: 클립보드 → editor → 자동 파싱
        paste_act = QAction(self._table)
        paste_act.setShortcut(QKeySequence.StandardKey.Paste)
        paste_act.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        paste_act.triggered.connect(self._paste_from_clipboard)
        self._table.addAction(paste_act)
        self._stacked.addWidget(self._table)

        lay.addWidget(self._stacked, stretch=1)

        # ── 요약 라벨 ──
        self._summary = QLabel("— 입력 대기 —")
        self._summary.setStyleSheet("color: gray;")
        lay.addWidget(self._summary)

    # ── 외부 API ───────────────────────────────────────
    @property
    def result(self) -> ParseResult | None:
        return self._result

    def clear(self) -> None:
        self._editor.clear()

    # ── 슬롯 ──────────────────────────────────────────
    def _on_view_changed(self, idx: int) -> None:
        self._stacked.setCurrentIndex(idx)

    def _on_clear_clicked(self) -> None:
        self._editor.clear()

    def _paste_from_clipboard(self) -> None:
        """클립보드 텍스트를 editor에 세팅 → textChanged로 자동 파싱."""
        text = QApplication.clipboard().text()
        if text:
            self._editor.setPlainText(text)

    def _on_text_changed(self) -> None:
        text = self._editor.toPlainText().strip()
        if not text:
            self._set_status(None, None, "— 입력 대기 —", "color: gray;")
            return

        df: pd.DataFrame | None = None
        try:
            df = _load_dataframe(text)
            result = parse_wafer_csv(df)  # 같은 DataFrame 재사용
        except MissingColumnsError as e:
            self._set_status(
                None, df,
                f"⚠ 필수 컬럼 부족: {', '.join(e.missing)}",
                "color: #d32f2f;",
            )
            return
        except Exception as e:
            self._set_status(None, None, f"⚠ 파싱 실패: {e}", "color: #d32f2f;")
            return

        n_wafers = len(result.wafers)
        params: set[str] = set()
        for w in result.wafers.values():
            params.update(w.parameters)
        warn = f"  ({len(result.warnings)} 경고)" if result.warnings else ""
        self._set_status(
            result, df,
            f"▶ 웨이퍼 {n_wafers}장 · PARAMETER {len(params)}개{warn}",
            "color: #2a9d8f;",
        )

    def _set_status(
        self,
        result: ParseResult | None,
        df: pd.DataFrame | None,
        msg: str,
        style: str,
    ) -> None:
        self._result = result
        self._df = df
        self._summary.setText(msg)
        self._summary.setStyleSheet(style)

        if df is not None and len(df) > 0:
            self._fill_table(df)
            self._btn_table.setEnabled(True)
        else:
            self._table.clear()
            self._table.setRowCount(0)
            self._table.setColumnCount(0)
            self._btn_table.setEnabled(False)
            # 뷰는 현재 상태 유지 — Clear 후 바로 Ctrl+V 하면 Table 뷰 그대로 이어짐

        self.parsed.emit(result)

    def _fill_table(self, df: pd.DataFrame) -> None:
        self._table.setUpdatesEnabled(False)
        try:
            self._table.clear()
            self._table.setRowCount(len(df))
            self._table.setColumnCount(len(df.columns))
            self._table.setHorizontalHeaderLabels([str(c) for c in df.columns])
            for r in range(len(df)):
                for c in range(len(df.columns)):
                    v = df.iat[r, c]
                    text = "" if pd.isna(v) else str(v)
                    self._table.setItem(r, c, QTableWidgetItem(text))
        finally:
            self._table.setUpdatesEnabled(True)
