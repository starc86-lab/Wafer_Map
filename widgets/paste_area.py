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

from core.input_summary import summarize
from core.input_validation import validate
from main import MissingColumnsError, ParseResult, _load_dataframe, parse_wafer_csv


# 헤더 버튼(Text/Table/Clear) 폭 + 사이 spacing — 메인 윈도우의 Run Analysis가
# 같은 폭(=72*3 + 6*2)으로 우측 정렬되어야 끝/시작이 일치 (사용자 요구).
HEADER_BUTTON_WIDTH = 88
HEADER_BUTTON_SPACING = 6


class PasteArea(QWidget):
    """Ctrl+V 페이스트 + 텍스트/표 뷰 토글."""

    parsed = Signal(object)  # ParseResult | None

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._result: ParseResult | None = None
        self._df: pd.DataFrame | None = None
        self._validation: list = []          # 마지막 input_validation 결과
        self._table_dirty = False  # df는 있는데 _fill_table 미실행 상태

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        # ── 헤더: 타이틀 + 뷰 토글 ──
        header = QHBoxLayout()
        header.setSpacing(HEADER_BUTTON_SPACING)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold;")
        header.addWidget(title_label)
        header.addStretch(1)

        self._btn_text = QPushButton("Text")
        self._btn_table = QPushButton("Table")
        self._btn_clear = QPushButton("Clear")
        for b in (self._btn_text, self._btn_table, self._btn_clear):
            b.setFixedWidth(HEADER_BUTTON_WIDTH)
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
        header.addWidget(self._btn_clear)
        lay.addLayout(header)

        # ── Stacked: Text / Table ──
        self._stacked = QStackedWidget()

        self._editor = QPlainTextEdit()
        # Input B는 Pre-Post 워크플로 설명으로 교체 (MES DCOL 설명은 Input A와 중복이라 생략)
        if title == "Input B":
            placeholder = (
                "Pre-Post 계산 시에 Input A에 Pre, 여기에 Post Data를 입력하세요.\n"
                "WAFERID가 동일한 데이터들만 선별하여 Pre-Post 계산."
            )
        else:
            placeholder = "MES DCOL DATA를 통째로 Ctrl+C, Ctrl+V."
        self._editor.setPlaceholderText(placeholder)
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

        # ── 요약 라벨 — 카운트 · 실패 사유 한 줄. warning 은 ReasonBar 로 통합 ──
        # 폰트 11px 로 축소 (눈에 덜 띄도록, 사용자 정책 2026-04-28)
        self._summary = QLabel("— 입력 대기 —")
        self._summary.setStyleSheet("color: gray; font-size: 11px;")
        lay.addWidget(self._summary)

    # ── 외부 API ───────────────────────────────────────
    @property
    def result(self) -> ParseResult | None:
        return self._result

    @property
    def is_valid(self) -> bool:
        """Run 가능 여부.

        - 빈 입력 (텍스트 자체 X): True — 이 paste 자체로 Run 차단 안 함.
          (다른 paste 가 정상이면 단일 모드 시각화 가능)
        - 텍스트 있음 + 파싱 실패 (필수 컬럼 누락 등): False
        - 텍스트 + 파싱 성공 + error severity 위반: False
        - 텍스트 + 파싱 성공 + warn/info 만: True
        """
        if not self._editor.toPlainText().strip():
            return True
        if self._result is None:
            return False
        return not any(w.severity == "error" for w in self._validation)

    def clear(self) -> None:
        self._editor.clear()

    # ── 슬롯 ──────────────────────────────────────────
    def _on_view_changed(self, idx: int) -> None:
        self._stacked.setCurrentIndex(idx)
        # Table 뷰로 들어왔는데 아직 채우지 않은 상태면 그때 채움 (lazy)
        if idx == 1 and self._table_dirty and self._df is not None:
            self._fill_table(self._df)
            self._table_dirty = False

    def _on_clear_clicked(self) -> None:
        self._editor.clear()

    def _paste_from_clipboard(self) -> None:
        """클립보드 텍스트를 editor에 세팅 → textChanged로 자동 파싱."""
        text = QApplication.clipboard().text()
        if text:
            self._editor.setPlainText(text)

    def text(self) -> str:
        """현재 입력 텍스트 (strip 전). Run 변경 감지 용 signature 입력."""
        return self._editor.toPlainText()

    def _on_text_changed(self) -> None:
        text = self._editor.toPlainText().strip()
        if not text:
            self._set_status(None, None, "— 입력 대기 —", "color: gray;")
            return

        df: pd.DataFrame | None = None
        try:
            df, meta = _load_dataframe(text)
            # 같은 DataFrame 재사용 + raw 처리 메타 보존
            result = parse_wafer_csv(df, metadata=meta)
        except MissingColumnsError as e:
            self._set_status(
                None, df,
                f"⚠ 필수 컬럼 부족: {', '.join(e.missing)}",
                "color: #d32f2f;",
            )
            return
        except Exception as e:
            # 정확한 원인 파악용 — stderr 에 traceback 출력 (사용자가 콘솔에서 확인)
            import traceback
            traceback.print_exc()
            self._set_status(None, None, f"⚠ 파싱 실패: {e}", "color: #d32f2f;")
            return

        # 빈 결과 (wafer 0) — 파싱 성공했지만 데이터 행이 모두 무효
        if not result.wafers:
            self._set_status(
                None, df,
                "⚠ 데이터 없음 — 헤더만 있거나 데이터 행이 모두 무효",
                "color: #d32f2f;",
            )
            return

        # 검증 결과는 paste_area 가 보관만 (UI 표시는 ReasonBar — main_window 가 처리)
        warns = validate(result)
        s = summarize(result)
        sep_str = f" · 구분자: {result.metadata.delimiter}" if result.metadata.delimiter else ""
        coord_str = "좌표 있음" if s.n_coord_pairs > 0 else "좌표 없음"
        self._set_status(
            result, df,
            f"웨이퍼 {s.n_wafers}장 · Parameter {s.n_parameter}개 · "
            f"{coord_str}{sep_str}",
            "color: #2a9d8f;",
            warns,
        )

    def _set_status(
        self,
        result: ParseResult | None,
        df: pd.DataFrame | None,
        msg: str,
        style: str,
        warnings: list | None = None,
    ) -> None:
        # paste 라벨 = 카운트 / 실패 사유 한 줄. warning 은 ReasonBar 로 통합 (UI 표시 X).
        # `_validation` 은 main_window 가 ReasonBar 빌드 시 가져다 씀.
        self._result = result
        self._df = df
        self._validation = warnings or []
        self._summary.setText(msg)
        # font-size 11px 항상 적용 (호출자가 color 만 지정 — 폰트는 일관 유지)
        self._summary.setStyleSheet(f"{style} font-size: 11px;")

        if df is not None and len(df) > 0:
            self._btn_table.setEnabled(True)
            # Table 뷰가 이미 활성이면 즉시 채우기, 아니면 dirty만 표시(lazy fill)
            if self._stacked.currentIndex() == 1:
                self._fill_table(df)
                self._table_dirty = False
            else:
                self._table_dirty = True
        else:
            self._table.clear()
            self._table.setRowCount(0)
            self._table.setColumnCount(0)
            self._btn_table.setEnabled(False)
            self._table_dirty = False
            # 뷰는 현재 상태 유지 — Clear 후 바로 Ctrl+V 하면 Table 뷰 그대로 이어짐

        self.parsed.emit(result)

    def _fill_table(self, df: pd.DataFrame) -> None:
        # 채우는 동안 ResizeToContents 끔 — setItem마다 컬럼 측정 트리거 방지
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.setUpdatesEnabled(False)
        try:
            self._table.clear()
            self._table.setRowCount(len(df))
            self._table.setColumnCount(len(df.columns))
            self._table.setHorizontalHeaderLabels([str(c) for c in df.columns])
            # df.values로 한 번에 ndarray 추출 — iat보다 훨씬 빠름
            arr = df.values
            for r in range(arr.shape[0]):
                for c in range(arr.shape[1]):
                    v = arr[r, c]
                    text = "" if pd.isna(v) else str(v)
                    self._table.setItem(r, c, QTableWidgetItem(text))
        finally:
            self._table.setUpdatesEnabled(True)
            header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
