"""
좌표 프리셋 수동 추가 다이얼로그.

RECIPE + 좌표 텍스트(TSV/CSV 등 다양한 포맷)를 입력받아 프리셋 등록.

입력 포맷 4종 자동 감지 (공백/탭/콤마/세미콜론 무관):
    1) 행 + X/Y 라벨:    'x 0 74 148'  /  'y 148 74 0'
    2) 행 + 라벨 없음:   '0 74 148'    /  '148 74 0'   (위=X, 아래=Y)
    3) 열 + x/y 헤더:    'x y'  /  '0 148'  /  '74 74'  / ...
    4) 열 + 헤더 없음:   '0 148'  /  '74 74' / ...            (좌=X, 우=Y)

사용자가 페이스트하면 하단 표(행: X/Y, 열: DATA1~N)에 즉시 반영.
"""
from __future__ import annotations

import re

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)


_SPLIT = re.compile(r"[\t,;\s]+")

# 복사-붙여넣기 오염 문자 정리용
_NOISE_CHARS = {
    "\ufeff": "",      # BOM
    "\u200b": "",      # zero-width space
    "\u00a0": " ",     # non-breaking space → 일반 공백
    "\u2212": "-",     # 유니코드 minus → ASCII hyphen
}


def _is_label(tok: str, letter: str) -> bool:
    return tok.strip().lower() == letter


def _to_floats(tokens: list[str]) -> list[float] | None:
    out: list[float] = []
    for t in tokens:
        try:
            out.append(float(t))
        except ValueError:
            return None
    return out


def _is_data_row(r: list[str]) -> bool:
    """데이터/헤더로 간주할 수 있는 행 — 파싱 대상."""
    if len(r) < 2:
        return False
    # x/y 헤더 행 (열 포맷) — 순서 무관
    if len(r) == 2:
        labels = {r[0].strip().lower(), r[1].strip().lower()}
        if labels == {"x", "y"}:
            return True
    # 행 + 라벨: 'x ...' / 'y ...'
    if _is_label(r[0], "x") or _is_label(r[0], "y"):
        return _to_floats(r[1:]) is not None
    # 전 토큰 숫자
    return _to_floats(r) is not None


def _parse_coords(text: str) -> tuple[np.ndarray, np.ndarray]:
    """4가지 형식 자동 감지 → (X, Y) 배열.

    감지 우선순위:
      1) 행 + 라벨: 2행이고 각 행 첫 토큰이 'x'/'y'
      2) 열 + 헤더: 첫 행이 정확히 ['x','y']
      3) 행 + 라벨 없음: 정확히 2행, 모든 토큰 숫자
      4) 열 + 헤더 없음: 각 행 2 토큰 이상 숫자

    노이즈 허용: BOM/NBSP/zero-width, 유니코드 minus, 토큰 양끝 따옴표,
                 leading/trailing 비데이터 행(타이틀·코멘트 동반 복사).
    """
    # 오염 문자 치환
    for bad, good in _NOISE_CHARS.items():
        text = text.replace(bad, good)

    rows: list[list[str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip("'\"") for p in _SPLIT.split(line) if p]
        parts = [p for p in parts if p]  # 따옴표 제거 후 빈 토큰 재필터
        if parts:
            rows.append(parts)

    # leading/trailing 비데이터 행 제거 — 타이틀/코멘트 선·후미 오염 방지
    while rows and not _is_data_row(rows[0]):
        rows.pop(0)
    while rows and not _is_data_row(rows[-1]):
        rows.pop()

    if not rows:
        return np.array([], dtype=float), np.array([], dtype=float)

    # Case 1: 행 + X/Y 라벨 (정확히 2행, 순서 무관 — y-first 허용)
    if (len(rows) == 2
            and len(rows[0]) >= 2 and len(rows[1]) >= 2):
        l0 = rows[0][0].strip().lower()
        l1 = rows[1][0].strip().lower()
        if {l0, l1} == {"x", "y"}:
            vals0 = _to_floats(rows[0][1:])
            vals1 = _to_floats(rows[1][1:])
            if vals0 is not None and vals1 is not None:
                if l0 == "x":
                    return np.array(vals0), np.array(vals1)
                else:
                    return np.array(vals1), np.array(vals0)

    # Case 2: 열 + x/y 헤더 (순서 무관 — 'y x' 허용)
    if len(rows) >= 2 and len(rows[0]) == 2:
        h0 = rows[0][0].strip().lower()
        h1 = rows[0][1].strip().lower()
        if {h0, h1} == {"x", "y"}:
            x_col = 0 if h0 == "x" else 1
            y_col = 1 - x_col
            xs, ys = [], []
            for r in rows[1:]:
                if len(r) < 2:
                    continue
                try:
                    xs.append(float(r[x_col]))
                    ys.append(float(r[y_col]))
                except ValueError:
                    continue
            return np.array(xs), np.array(ys)

    # Case 3: 행 + 라벨 없음 (정확히 2행, 모두 숫자)
    if len(rows) == 2:
        x = _to_floats(rows[0])
        y = _to_floats(rows[1])
        if x is not None and y is not None and len(x) > 0 and len(y) > 0:
            return np.array(x), np.array(y)

    # Case 4: 열 + 헤더 없음 (각 행 2 토큰 숫자)
    xs, ys = [], []
    for r in rows:
        if len(r) < 2:
            continue
        try:
            xs.append(float(r[0]))
            ys.append(float(r[1]))
        except ValueError:
            continue
    return np.array(xs), np.array(ys)


class PresetAddDialog(QDialog):
    """RECIPE + 좌표 텍스트 입력으로 프리셋 추가. 4포맷 자동 감지 + 미리보기 표."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("좌표 프리셋 수동 추가")
        self.resize(720, 560)

        self._recipe = QLineEdit()
        self._recipe.setPlaceholderText("예: HT_SOC_POLAR_49PT_5mm")

        self._coords = QPlainTextEdit()
        self._coords.setPlaceholderText(
            "좌표를 통째로 Ctrl+C, Ctrl+V로 입력하세요.\n"
            "모든 형식을 지원합니다.\n"
            "- 공백, 비데이터 자동 필터링.\n"
            "- Row 형식, Column 형식 자동 인식.\n"
            "- X, Y 명시 없는 경우 순서대로 X, Y로 자동 인식."
        )
        self._coords.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._coords.textChanged.connect(self._refresh_preview)

        form = QFormLayout()
        form.addRow("RECIPE", self._recipe)
        form.addRow("좌표 입력", self._coords)

        lay = QVBoxLayout(self)
        lay.addLayout(form)

        # 미리보기 — 2행(X/Y) × (N+1)열(DATA1~DATAN)
        self._preview = QTableWidget(2, 0)
        self._preview.setVerticalHeaderLabels(["X", "Y"])
        self._preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._preview.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._preview.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self._preview.setAlternatingRowColors(True)
        lay.addWidget(QLabel("미리보기"))
        lay.addWidget(self._preview, stretch=1)

        self._status = QLabel("")
        self._status.setStyleSheet("color: gray;")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("추가")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._x: np.ndarray | None = None
        self._y: np.ndarray | None = None

    def _refresh_preview(self) -> None:
        x, y = _parse_coords(self._coords.toPlainText())
        n = min(len(x), len(y))
        self._preview.setColumnCount(n)
        self._preview.setHorizontalHeaderLabels([f"DATA{i+1}" for i in range(n)])
        for col in range(n):
            self._set_cell(0, col, x[col])
            self._set_cell(1, col, y[col])
        if len(x) == 0 and len(y) == 0:
            self._status.setText("")
        elif len(x) != len(y):
            self._status.setText(
                f"⚠ X({len(x)}) · Y({len(y)}) 개수 불일치 — 앞 {n}개만 표시"
            )
        else:
            self._status.setText(f"✓ {n}개 점 파싱")

    def _set_cell(self, r: int, c: int, val: float) -> None:
        item = QTableWidgetItem(f"{val:g}")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setItem(r, c, item)

    def _on_ok(self) -> None:
        recipe = self._recipe.text().strip()
        if not recipe:
            QMessageBox.warning(self, "수동 추가", "RECIPE 이름을 입력하세요.")
            return
        x, y = _parse_coords(self._coords.toPlainText())
        if len(x) == 0:
            QMessageBox.warning(self, "수동 추가", "유효한 (X, Y) 쌍이 없습니다.")
            return
        if len(x) != len(y):
            QMessageBox.warning(
                self, "수동 추가",
                f"X({len(x)})·Y({len(y)}) 개수 불일치.",
            )
            return
        self._x, self._y = x, y
        self.accept()

    def result_values(self) -> tuple[str, np.ndarray, np.ndarray] | None:
        if self._x is None or self._y is None:
            return None
        return self._recipe.text().strip(), self._x, self._y
