"""
좌표 프리셋 수동 추가 다이얼로그.

사용자가 RECIPE 이름 + 좌표 쌍(TSV/CSV 페이스트)을 직접 입력해 새 프리셋 등록.

입력 형식:
    X<탭>Y
    0<탭>-140
    147<탭>0
    ...
- 첫 줄이 "X", "Y"로 시작하는 헤더면 자동 스킵
- 탭/콤마/공백 모두 허용
"""
from __future__ import annotations

import re

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QVBoxLayout, QWidget,
)


_SPLIT = re.compile(r"[\t,\s]+")


def _parse_xy_text(text: str) -> tuple[np.ndarray, np.ndarray]:
    """TSV/CSV 형식의 (X, Y) 텍스트를 배열로 파싱."""
    xs: list[float] = []
    ys: list[float] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p for p in _SPLIT.split(line) if p]
        if len(parts) < 2:
            continue
        # 헤더 라인 스킵 (숫자 아니면)
        try:
            x = float(parts[0])
            y = float(parts[1])
        except ValueError:
            continue
        xs.append(x)
        ys.append(y)
    return np.array(xs, dtype=float), np.array(ys, dtype=float)


class PresetAddDialog(QDialog):
    """RECIPE + 좌표 텍스트 입력으로 프리셋 추가."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("좌표 프리셋 수동 추가")
        self.resize(480, 420)

        self._recipe = QLineEdit()
        self._recipe.setPlaceholderText("예: HT_SOC_POLAR_49PT_5mm")

        self._coords = QPlainTextEdit()
        self._coords.setPlaceholderText(
            "각 줄에 X, Y 한 쌍 (탭·콤마·공백 구분).\n"
            "예:\n"
            "  0\t-140\n"
            "  147\t0\n"
            "  -73\t73\n"
            "헤더 행 'X Y'는 자동 스킵됩니다."
        )
        self._coords.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        form = QFormLayout()
        form.addRow("RECIPE", self._recipe)
        form.addRow("좌표 (X, Y)", self._coords)

        lay = QVBoxLayout(self)
        lay.addLayout(form)

        info = QLabel(
            "좌표는 이미 mm 단위로 입력하세요. 입력 후 [추가] 를 누르면 라이브러리에 저장됩니다."
        )
        info.setStyleSheet("color: gray;")
        info.setWordWrap(True)
        lay.addWidget(info)

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

    def _on_ok(self) -> None:
        recipe = self._recipe.text().strip()
        if not recipe:
            QMessageBox.warning(self, "수동 추가", "RECIPE 이름을 입력하세요.")
            return
        x, y = _parse_xy_text(self._coords.toPlainText())
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
