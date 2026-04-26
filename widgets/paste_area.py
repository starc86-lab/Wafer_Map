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

from core.auto_select import select_xy_pairs
from core.integrity import check_integrity
from main import (
    DelimiterDetectError, MissingColumnsError, ParseResult,
    _load_dataframe, parse_wafer_csv,
)


# 구분자 → 사용자 표기 (한국어)
_DELIM_LABEL = {
    "\t": "탭",
    ",": "콤마",
    ";": "세미콜론",
    "|": "파이프",
}

# main.py 의 REQUIRED_KEYS 내부 키 → 사용자 표기 (CSV 헤더 형식과 일치)
_REQUIRED_LABEL = {
    "waferid": "WAFERID",
    "lot_id": "LOT ID",
    "slot_id": "Slot ID",
    "parameter": "PARAMETER",
    "recipe": "RECIPE",
}


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

        # ── 요약 라벨 (한 줄 통합 — 정보·자체경고·DELTA 모두 압축) ──
        # 입력 대기 / 파싱 실패 / 파싱 OK 모든 케이스에서 라벨 1개 고정 높이라
        # 입력란 위치가 흔들리지 않음. 잘린 메시지는 setToolTip 으로 hover 시 전체 보임.
        self._summary = QLabel("— 입력 대기 —")
        self._summary.setStyleSheet("color: gray;")
        lay.addWidget(self._summary)

        # paste_b 만 외부(MainWindow)에서 DELTA 결과를 추가로 set 가능.
        # _self_text/_self_color = 자체 파싱·무결성 결과 (textChanged 트리거).
        # _delta_msg/_delta_severity = Run 클릭 후 set, paste 변경 시 자동 clear.
        # severity: "ok" (민트) / "warn" (주황) / "error" (빨강).
        self._self_text: str = "— 입력 대기 —"
        self._self_color: str = "color: gray;"
        self._delta_msg: str = ""
        self._delta_severity: str = "ok"

    # ── 외부 API ───────────────────────────────────────
    @property
    def result(self) -> ParseResult | None:
        return self._result

    def clear(self) -> None:
        self._editor.clear()

    def set_delta_status(self, msg: str | None, severity: str = "ok") -> None:
        """DELTA 결과를 _summary 끝에 합쳐 표시. msg=None 이면 DELTA 부분 제거.

        severity: "ok" (민트) / "warn" (주황, RECIPE/PARA 불일치 등) / "error"
        (빨강, 교집합 0 같은 시각화 차단). 자체 OK + DELTA 경고/오류 면 마커 ⚠
        로 강제 변경. msg 는 호출자가 축약해서 전달 (예: `DELTA OK 매칭 5`,
        `DELTA: 교집합 없음`).
        """
        self._delta_msg = msg or ""
        self._delta_severity = severity if severity in ("ok", "warn", "error") else "warn"
        self._refresh_summary()

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
        # raw text 보존 — strip 하면 trailing newline 까지 사라져 한 줄 텍스트가 되고,
        # _load_dataframe 의 텍스트/path 분기에서 path 모드로 가버려 헤더만 paste 케이스
        # (데이터 행 없음) 가 FileNotFoundError 로 잘못 잡힘.
        text = self._editor.toPlainText()
        if not text.strip():
            self._set_status(None, None, "— 입력 대기 —", "color: gray;")
            return

        df: pd.DataFrame | None = None
        try:
            df, delimiter, load_warnings = _load_dataframe(text)
            # 같은 DataFrame 재사용 (이중 파싱 회피) + 감지된 구분자/extra warning 명시 전달
            result = parse_wafer_csv(df, delimiter=delimiter, extra_warnings=load_warnings)
        except DelimiterDetectError:
            self._set_status(
                None, None, "⚠ 파싱 실패: 구분자 인식 실패",
                "color: #d32f2f;",
            )
            return
        except MissingColumnsError as e:
            # DATA 컬럼 누락 vs 메타 필수 컬럼 누락 분기
            if e.missing == [r"DATA\d+"]:
                sub = "DATA 컬럼 없음"
            else:
                labels = [_REQUIRED_LABEL.get(k, k) for k in e.missing]
                sub = f"필수 컬럼 누락 ({', '.join(labels)})"
            self._set_status(
                None, df, f"⚠ 파싱 실패: {sub}",
                "color: #d32f2f;",
            )
            return
        except Exception as e:
            # 사유 파악 불가 — Python exception 메시지 그대로
            self._set_status(None, None, f"⚠ 파싱 실패: {e}", "color: #d32f2f;")
            return

        n_wafers = len(result.wafers)
        # 헤더만 있고 데이터 행 0개 — pandas 가 0 row DataFrame 만들어 파싱 자체는 통과
        # 하지만 시각화 불가 → 파싱 실패 카테고리로 처리.
        if n_wafers == 0:
            self._set_status(
                None, df, "⚠ 파싱 실패: 데이터 행 없음",
                "color: #d32f2f;",
            )
            return

        params: set[str] = set()
        param_ns: dict[str, int] = {}
        for w in result.wafers.values():
            params.update(w.parameters)
            for name, rec in w.parameters.items():
                # 한 wafer 의 첫 발견 시 n 기록 (좌표 페어 검사용 — auto_select 와 동일 로직)
                if name not in param_ns:
                    param_ns[name] = rec.n
        # 좌표 페어 (X/Y PARAMETER) 존재 여부 — 없어도 좌표 라이브러리/프리셋으로 보충 가능
        x_sel, y_sel, _, _ = select_xy_pairs(param_ns)
        coord_str = "좌표 O" if (x_sel and y_sel) else "좌표 X"
        # 무결성 검사 (A/B/C/D-1/D-2) — 통과 시 ✓ + 정보, 위반 시 ⚠ + 정보 + 첫 경고
        integrity_warnings = check_integrity(result)
        # 정보 부분 — 축약 (WF N·PARA M·좌표 O/X). 구분자 정보는 메시지에서 제거 (자동 처리).
        info = f"WF {n_wafers}·PARA {len(params)}·{coord_str}"
        if integrity_warnings:
            marker, color = "⚠", "color: #f59e0b;"
            tail = f" 외 {len(integrity_warnings) - 1}건" if len(integrity_warnings) > 1 else ""
            msg = f"{marker} {info}·{integrity_warnings[0].message}{tail}"
        else:
            marker, color = "✓", "color: #2a9d8f;"
            msg = f"{marker} {info}"
        self._set_status(result, df, msg, color)

    def _set_status(
        self,
        result: ParseResult | None,
        df: pd.DataFrame | None,
        msg: str,
        style: str,
    ) -> None:
        """자체 파싱/무결성 결과 set. (DELTA 부분은 set_delta_status 가 별도 갱신.)

        새 입력이 왔으니 이전 DELTA 결과는 stale → 자동 clear.
        """
        self._result = result
        self._df = df
        self._self_text = msg
        self._self_color = style
        # 새 입력이라 이전 DELTA 결과 stale
        self._delta_msg = ""
        self._delta_severity = "ok"
        self._refresh_summary()

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

    def _refresh_summary(self) -> None:
        """_self_text + _delta_msg 를 한 줄에 합쳐 _summary 라벨에 표시.

        색상 규칙 — 자체 / DELTA 둘 중 가장 심각한 severity 적용.
        severity rank: error(3) > warn(2) > ok(1) > neutral(0).
        자체 ✓ 인데 DELTA 가 warn/error 면 전체 마커 ⚠ 로 강제 변경.
        """
        text = self._self_text
        if self._delta_msg:
            text = f"{text}·{self._delta_msg}"

        # 자체 severity 추론 — _self_color 의 hex 코드로 판정
        if "#d32f2f" in self._self_color:
            self_sev = 3   # error (파싱 실패)
        elif "#f59e0b" in self._self_color:
            self_sev = 2   # warn (자체 무결성 경고)
        elif "#2a9d8f" in self._self_color:
            self_sev = 1   # ok
        else:
            self_sev = 0   # neutral (빈 입력 회색)

        delta_rank = {"ok": 1, "warn": 2, "error": 3}
        delta_sev = delta_rank.get(self._delta_severity, 0) if self._delta_msg else 0

        # 가장 심각한 severity 의 색상 적용
        if self_sev >= delta_sev:
            color = self._self_color
        else:
            color_by_sev = {1: "color: #2a9d8f;", 2: "color: #f59e0b;", 3: "color: #d32f2f;"}
            color = color_by_sev[delta_sev]
            # 자체 ✓ 인데 DELTA 가 더 심각 → 전체 마커 ⚠
            if text.startswith("✓ "):
                text = "⚠ " + text[2:]

        self._summary.setText(text)
        self._summary.setStyleSheet(color)
        # 잘린 메시지 대비 — 마우스 hover 시 전체 표시
        self._summary.setToolTip(text)

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
