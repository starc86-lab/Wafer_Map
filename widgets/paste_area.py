"""
Ctrl+V 페이스트 영역. 텍스트/표 두 뷰를 토글로 전환.

- 입력 텍스트 변경 시 `parse_wafer_csv` 자동 호출 → 요약 라벨 업데이트
- 파싱 성공 시 DataFrame을 QTableWidget 뷰에도 채움 (Table 버튼 활성)
- 텍스트 뷰는 줄바꿈 OFF + 가로 스크롤바 (원본 행 구조 유지)

Cell edit (사용자 정책 2026-05-03):
- Table 모드에서 모든 cell 직접 edit 가능 (더블 클릭 / F2 / 키 입력)
- multi-select + Del → 선택 cell 빈 값 (행/컬럼 유지)
- 우클릭 → 선택 행/컬럼 자체 삭제
- Ctrl+Z → snapshot 기반 undo
- Edit 시 즉시 text 영역에도 양방향 sync + reparse
"""
from __future__ import annotations

import pandas as pd

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QHBoxLayout, QHeaderView,
    QLabel, QMenu, QPlainTextEdit, QPushButton, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.input_summary import summarize
from core.input_validation import validate
from main import MissingColumnsError, ParseResult, _load_dataframe, parse_wafer_csv


# Snapshot 기반 undo — 모든 변경 (cell edit / Del / 행·컬럼 삭제) 통합. csv text
# 한 줄로 abstract 되니 command 종류별 분기 불필요.
_UNDO_MAX = 100  # snapshot stack 한도 — 메모리 보호 (csv 텍스트 ~50KB × 100 = 5MB)


# 헤더 버튼(Text/Table/Clear) 폭 + 사이 spacing — 메인 윈도우의 Run Analysis가
# 같은 폭(=72*3 + 6*2)으로 우측 정렬되어야 끝/시작이 일치 (사용자 요구).
HEADER_BUTTON_WIDTH = 72   # 사용자 정책 2026-05-04, 88 → 72 (height 32→26 비율 동기)
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
        # Cell edit / undo 상태 (사용자 정책 2026-05-03)
        # _filling_table: _fill_table 진행 중 itemChanged 무시 (사용자 edit 만 trigger)
        # _undo_stack: 변경 직전 csv text 누적 (Ctrl+Z 시 pop)
        # _suppress_text_changed: editor.setPlainText 호출 시 _on_text_changed 중복 방지
        self._filling_table: bool = False
        self._undo_stack: list[str] = []
        self._suppress_text_changed: bool = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
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
        # Table 버튼 항상 활성 — 빈 입력일 때 클릭해도 빈 table 보일 뿐
        # (사용자 정책 2026-05-03, 회색 disabled 표시 제거)
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
        # Input B는 Pre-Post 워크플로 설명으로 교체 (MES-DCOL Data 설명은 Input A와 중복이라 생략)
        if title == "Input B":
            placeholder = (
                "Pre-Post 계산 시에 Input A에 Pre, 여기에 Post Data를 입력하세요.\n"
                "WAFERID가 동일한 데이터들만 선별하여 Pre-Post 계산."
            )
        else:
            placeholder = "MES-DCOL Data를 통째로 Ctrl+C, Ctrl+V."
        self._editor.setPlaceholderText(placeholder)
        # 줄바꿈 OFF → 원본 행 그대로, 긴 행은 가로 스크롤바
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._editor.textChanged.connect(self._on_text_changed)
        self._stacked.addWidget(self._editor)

        self._table = QTableWidget()
        # Cell edit 활성 (사용자 정책 2026-05-03):
        # - 더블 클릭 / F2 / 일반 키 입력 → edit mode
        # - 모든 cell editable (메타·헤더 포함). 필수 컬럼 깨지면 후속 파싱 단계에서
        #   자동 에러 메시지로 안내. 사용자 자유도 제한 X
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed,
        )
        # multi-select (Ctrl/Shift 클릭, 행/컬럼 헤더 클릭으로 단위 선택)
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection,
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectItems,
        )
        self._table.setAlternatingRowColors(True)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents,
        )
        # 사용자 정책 2026-05-04 — 행 높이 축소. Fusion 기본 (~30px) 가 padding
        # 변경에 영향 안 받아 verticalHeader 의 defaultSectionSize 직접 설정.
        self._table.verticalHeader().setDefaultSectionSize(22)
        self._table.verticalHeader().setMinimumSectionSize(18)
        # Cell edit → text 양방향 sync + reparse trigger
        self._table.itemChanged.connect(self._on_item_changed)
        # 우클릭 메뉴 — 선택 행/컬럼 자체 삭제
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        # 헤더 우클릭도 동일 메뉴 (행/컬럼 헤더 위에서 직접 삭제)
        self._table.horizontalHeader().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu,
        )
        self._table.horizontalHeader().customContextMenuRequested.connect(
            self._on_header_context_menu_h,
        )
        self._table.verticalHeader().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu,
        )
        self._table.verticalHeader().customContextMenuRequested.connect(
            self._on_header_context_menu_v,
        )
        # Del 키 — 선택 cells 빈 값 (행/컬럼 유지)
        del_act = QAction(self._table)
        del_act.setShortcut(QKeySequence.StandardKey.Delete)
        del_act.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        del_act.triggered.connect(self._on_delete_selection)
        self._table.addAction(del_act)
        # Ctrl+Z — snapshot 기반 undo
        undo_act = QAction(self._table)
        undo_act.setShortcut(QKeySequence.StandardKey.Undo)
        undo_act.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        undo_act.triggered.connect(self._on_undo)
        self._table.addAction(undo_act)
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
        # _on_item_changed 가 reconstruct 한 텍스트를 editor 에 setPlainText 할 때
        # textChanged 가 또 fire 되어 무한 reparse — guard
        if self._suppress_text_changed:
            return
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
            self._table_dirty = False
            # 뷰는 현재 상태 유지 — Clear 후 바로 Ctrl+V 하면 Table 뷰 그대로 이어짐

        self.parsed.emit(result)

    def _fill_table(self, df: pd.DataFrame) -> None:
        # 채우는 동안 ResizeToContents 끔 — setItem마다 컬럼 측정 트리거 방지
        # blockSignals — 사용자 edit 이 아닌 프로그램적 setItem 의 itemChanged 차단
        # (사용자 정책 2026-05-03, cell edit fix loop 방지)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # current cell 보존 — clear() 가 currentItem 을 reset 시켜 Del 후 다음
        # 방향키가 (0,0) 으로 가는 회귀 fix (사용자 정책 2026-05-03)
        cur_row = self._table.currentRow()
        cur_col = self._table.currentColumn()
        self._table.setUpdatesEnabled(False)
        self._table.blockSignals(True)
        self._filling_table = True
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
            self._filling_table = False
            self._table.blockSignals(False)
            self._table.setUpdatesEnabled(True)
            header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        # current cell 복원 — clamp (행/컬럼 삭제로 size 줄었을 수 있음)
        if cur_row >= 0 and cur_col >= 0:
            r = min(cur_row, self._table.rowCount() - 1)
            c = min(cur_col, self._table.columnCount() - 1)
            if r >= 0 and c >= 0:
                self._table.setCurrentCell(r, c)

    # ── Cell edit / undo (사용자 정책 2026-05-03) ──────────
    def _push_undo_snapshot(self) -> None:
        """변경 직전 csv text 를 undo stack 에 push. 한도 초과 시 가장 오래된 것 drop."""
        text = self._editor.toPlainText()
        # 직전 snapshot 과 동일하면 push 안 함 (중복 방지)
        if self._undo_stack and self._undo_stack[-1] == text:
            return
        self._undo_stack.append(text)
        if len(self._undo_stack) > _UNDO_MAX:
            self._undo_stack.pop(0)

    def _table_to_csv_text(self) -> str:
        """현재 QTableWidget 상태 → tab 구분 csv text 재구성.

        tab 구분 채택 — cell 안에 콤마 들어있어도 escape 불필요 (tab 입력 어려움 + 측정 데이터에 거의 없음).
        """
        rows: list[str] = []
        n_cols = self._table.columnCount()
        # 헤더
        headers = []
        for c in range(n_cols):
            it = self._table.horizontalHeaderItem(c)
            headers.append(it.text() if it is not None else "")
        rows.append("\t".join(headers))
        # 데이터
        for r in range(self._table.rowCount()):
            cells = []
            for c in range(n_cols):
                it = self._table.item(r, c)
                cells.append(it.text() if it is not None else "")
            rows.append("\t".join(cells))
        return "\n".join(rows)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """사용자 cell edit → snapshot push + text 양방향 sync + reparse."""
        if self._filling_table:
            return
        # 변경 직전 snapshot — Ctrl+Z 시 복원
        self._push_undo_snapshot()
        self._sync_table_to_text()

    def _sync_table_to_text(self) -> None:
        """Table 변경 후 editor 갱신 → textChanged → _on_text_changed → reparse.

        editor.setPlainText 자체가 textChanged 발화 — 평소엔 자연스러운 흐름이지만
        여기선 reparse 만 한 번 trigger 되면 충분. _on_text_changed 가 _fill_table
        다시 호출하므로 (블록되어 있어 itemChanged 안 fire). 정상 흐름.
        """
        new_text = self._table_to_csv_text()
        # editor 갱신 — textChanged 발화 → _on_text_changed → reparse + _fill_table
        # _fill_table 은 blockSignals 로 itemChanged 발화 안 함 (무한 loop 안전)
        self._editor.setPlainText(new_text)

    def _on_delete_selection(self) -> None:
        """Del 키 — 선택 cells 빈 값 (행/컬럼 자체는 유지)."""
        if not self._table.selectedItems():
            return
        self._push_undo_snapshot()
        self._table.blockSignals(True)
        try:
            for it in self._table.selectedItems():
                it.setText("")
        finally:
            self._table.blockSignals(False)
        self._sync_table_to_text()

    def _selected_rows(self) -> list[int]:
        """선택된 행 인덱스 (오름차순 unique)."""
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        return sorted(rows)

    def _selected_cols(self) -> list[int]:
        """선택된 컬럼 인덱스 (오름차순 unique)."""
        cols = {idx.column() for idx in self._table.selectedIndexes()}
        return sorted(cols)

    def _on_context_menu(self, pos) -> None:
        """cell 우클릭 메뉴 — 선택 행 삭제 / 선택 컬럼 삭제."""
        rows = self._selected_rows()
        cols = self._selected_cols()
        if not rows and not cols:
            return
        menu = QMenu(self._table)
        if rows:
            act_rows = menu.addAction(f"선택 행 {len(rows)}개 삭제")
            act_rows.triggered.connect(lambda: self._remove_rows(rows))
        if cols:
            act_cols = menu.addAction(f"선택 컬럼 {len(cols)}개 삭제")
            act_cols.triggered.connect(lambda: self._remove_columns(cols))
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _on_header_context_menu_h(self, pos) -> None:
        """가로 헤더 우클릭 — 클릭 위치 컬럼 또는 선택 컬럼 삭제."""
        col = self._table.horizontalHeader().logicalIndexAt(pos)
        if col < 0:
            return
        cols = self._selected_cols()
        if col not in cols:
            cols = [col]
        menu = QMenu(self._table)
        act = menu.addAction(f"컬럼 {len(cols)}개 삭제")
        act.triggered.connect(lambda: self._remove_columns(cols))
        menu.exec(self._table.horizontalHeader().mapToGlobal(pos))

    def _on_header_context_menu_v(self, pos) -> None:
        """세로 헤더 우클릭 — 클릭 위치 행 또는 선택 행 삭제."""
        row = self._table.verticalHeader().logicalIndexAt(pos)
        if row < 0:
            return
        rows = self._selected_rows()
        if row not in rows:
            rows = [row]
        menu = QMenu(self._table)
        act = menu.addAction(f"행 {len(rows)}개 삭제")
        act.triggered.connect(lambda: self._remove_rows(rows))
        menu.exec(self._table.verticalHeader().mapToGlobal(pos))

    def _remove_rows(self, rows: list[int]) -> None:
        """행 자체 삭제 (값 + 행 모두 제거). 역순 삭제 — index shift 안전."""
        if not rows:
            return
        self._push_undo_snapshot()
        self._table.blockSignals(True)
        try:
            for r in sorted(rows, reverse=True):
                self._table.removeRow(r)
        finally:
            self._table.blockSignals(False)
        self._sync_table_to_text()

    def _remove_columns(self, cols: list[int]) -> None:
        """컬럼 자체 삭제 (값 + 컬럼 헤더 모두 제거). 역순 삭제."""
        if not cols:
            return
        self._push_undo_snapshot()
        self._table.blockSignals(True)
        try:
            for c in sorted(cols, reverse=True):
                self._table.removeColumn(c)
        finally:
            self._table.blockSignals(False)
        self._sync_table_to_text()

    def _on_undo(self) -> None:
        """Ctrl+Z — undo stack pop → 이전 csv text 복원."""
        if not self._undo_stack:
            return
        prev_text = self._undo_stack.pop()
        # editor 직접 갱신 → textChanged → 재파싱 + table 자동 채움
        self._editor.setPlainText(prev_text)
