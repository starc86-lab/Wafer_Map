"""
좌표 프리셋 수정 다이얼로그 — 미리보기 다이얼로그 형태 (좌: 맵 / 우: 표).

CoordPreviewDialog 와 동일 레이아웃이지만 RECIPE QLineEdit + 표 cell 편집
가능. 표에서 X/Y 값 변경 시 좌측 맵 즉시 refresh.

- 상단: RECIPE QLineEdit (편집 가능, 기존 값 미리 채움)
- 좌: 웨이퍼 맵 (경계 + 좌표 산점도 + 좌표번호)
- 우: 3 컬럼 표 (Point / X (mm) / Y (mm)) — X/Y cell 편집 가능
- 하단: 저장 / 취소

사용자 정책 2026-04-30 — 좌표 라이브러리 탭 "좌표 수정" 버튼/더블클릭 진입점.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QStyledItemDelegate, QTableWidget, QTableWidgetItem, QWidget,
)


_BOUNDARY_R = 153.0
_NOTCH_DEPTH = 3.0
_NOTCH_ANGLE = 3 * np.pi / 2
_NOTCH_HALF_RAD = 3 * np.pi / 180
_BOUNDARY_SEGMENTS = 361


def _boundary_xy(R: float = _BOUNDARY_R, depth: float = _NOTCH_DEPTH) -> tuple[np.ndarray, np.ndarray]:
    theta = np.linspace(0, 2 * np.pi, _BOUNDARY_SEGMENTS)
    r = np.full_like(theta, R)
    d = np.abs(((theta - _NOTCH_ANGLE + np.pi) % (2 * np.pi)) - np.pi)
    in_notch = d < _NOTCH_HALF_RAD
    r[in_notch] = R - depth * (1 - d[in_notch] / _NOTCH_HALF_RAD)
    return r * np.cos(theta), r * np.sin(theta)


class _FloatDelegate(QStyledItemDelegate):
    """X/Y cell 편집 시 float 만 입력 허용."""

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setValidator(QDoubleValidator(parent))
        return editor


class PresetEditDialog(QDialog):
    """좌표 미리보기 형태 + RECIPE/좌표 편집."""

    def __init__(
        self,
        recipe: str,
        x_mm,
        y_mm,
        x_name: str = "X",
        y_name: str = "Y",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("좌표 수정")

        x = np.asarray(x_mm, dtype=float)
        y = np.asarray(y_mm, dtype=float)
        n = min(x.size, y.size)
        self._x = x[:n].astype(float, copy=True)
        self._y = y[:n].astype(float, copy=True)
        self._x_name = x_name
        self._y_name = y_name

        # 테마 색상 (CoordPreviewDialog 와 동일 처리)
        from core import settings as settings_io
        from core.themes import THEMES, FONT_SIZES
        _s = settings_io.load_settings()
        _t = THEMES.get(_s.get("theme", "Light"), THEMES["Light"])
        _border = _t.get("border", "#888")
        _text_sub = _t.get("text_sub", "#555")
        _bg = _t.get("bg", "#ffffff").lstrip("#")
        try:
            _lum = (int(_bg[0:2], 16) + int(_bg[2:4], 16) + int(_bg[4:6], 16)) / 3
            _is_dark = _lum < 128
        except Exception:
            _is_dark = False
        _map_bg = "#f0f0f0" if _is_dark else "white"
        _body_px = FONT_SIZES.get("body", 14)

        lay = QGridLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setHorizontalSpacing(10)
        lay.setVerticalSpacing(6)

        # ── row 0: RECIPE 입력 (col 0~1 span) ─────────
        recipe_row = QHBoxLayout()
        recipe_lbl = QLabel("RECIPE")
        recipe_lbl.setStyleSheet(f"font-size: {_body_px}px;")
        self._recipe = QLineEdit(recipe)
        self._recipe.setPlaceholderText("RECIPE 이름")
        recipe_row.addWidget(recipe_lbl)
        recipe_row.addWidget(self._recipe, stretch=1)
        recipe_w = QWidget()
        recipe_w.setLayout(recipe_row)
        lay.addWidget(recipe_w, 0, 0, 1, 2)

        # ── row 1: 체크박스 (좌) | info (우) ─────────
        self.chk_show_numbers = QCheckBox("좌표번호 표시")
        self.chk_show_numbers.setChecked(True)
        self.chk_show_numbers.setStyleSheet(f"QCheckBox {{ font-size: {_body_px}px; }}")
        self.chk_show_numbers.toggled.connect(self._on_show_numbers_toggled)

        self._info = QLabel(f"총 {n} 포인트")
        self._info.setStyleSheet(f"color: {_text_sub}; font-size: {_body_px}px;")

        lay.addWidget(self.chk_show_numbers, 1, 0)
        lay.addWidget(self._info, 1, 1)

        # ── row 2: plot (좌) | table (우) ─────────
        self._plot = pg.PlotWidget()
        self._plot.setBackground(_map_bg)
        self._plot.setMouseEnabled(False, False)
        self._plot.setMenuEnabled(False)
        self._plot.hideButtons()
        self._plot.setAspectLocked(True)
        self._plot.showGrid(x=False, y=False)
        vb = self._plot.getViewBox()
        vb.setRange(xRange=(-170, 170), yRange=(-170, 170), padding=0)
        pi = self._plot.getPlotItem()
        for ax_name in ("left", "bottom", "top", "right"):
            pi.hideAxis(ax_name)
        pi.layout.setContentsMargins(0, 0, 0, 0)
        self._plot.setStyleSheet(f"border: 1px solid {_border};")

        # 경계 원 + notch
        bx, by = _boundary_xy()
        self._plot.plot(bx, by, pen=pg.mkPen("#666", width=1.5))

        # 산점도 — 편집 시 setData 로 갱신
        self._scatter = self._plot.plot(
            self._x, self._y,
            pen=None,
            symbol="o",
            symbolBrush=pg.mkBrush("#111"),
            symbolPen=pg.mkPen("#111"),
            symbolSize=4,
        )

        # 좌표 번호 텍스트 — 편집 시 setPos 로 위치 갱신
        self._num_items: list[pg.TextItem] = []
        _pt_font = QFont()
        _pt_font.setPixelSize(10)
        for i in range(n):
            txt = pg.TextItem(text=str(i + 1), color="#444", anchor=(-0.1, 1.1))
            txt.setFont(_pt_font)
            txt.setPos(float(self._x[i]), float(self._y[i]))
            self._plot.addItem(txt, ignoreBounds=True)
            self._num_items.append(txt)

        # ── 표 ───────────────────────────────────
        self._table = QTableWidget(n, 3)
        self._table.setHorizontalHeaderLabels(["Point", f"{x_name} (mm)", f"{y_name} (mm)"])
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self._table.verticalHeader().hide()
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._table.setItemDelegate(_FloatDelegate(self._table))
        hh = self._table.horizontalHeader()
        _col_xy_w = 90
        _col_pt_w = int(_col_xy_w * 0.7)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(0, _col_pt_w)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for i in range(n):
            it_p = QTableWidgetItem(str(i + 1))
            # Point 컬럼은 편집 불가 (행 식별용)
            it_p.setFlags(it_p.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it_x = QTableWidgetItem(f"{float(self._x[i]):.3f}")
            it_y = QTableWidgetItem(f"{float(self._y[i]):.3f}")
            for it in (it_p, it_x, it_y):
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, 0, it_p)
            self._table.setItem(i, 1, it_x)
            self._table.setItem(i, 2, it_y)

        self._table.setStyleSheet(f"""
            QTableWidget {{
                border: 1px solid {_border};
                gridline-color: {_border};
                background-color: white;
                color: #111;
            }}
            QTableWidget::item {{
                color: #111;
            }}
            QHeaderView::section {{
                background-color: #f0f0f0;
                color: #111;
                border: none;
                border-right: 1px solid {_border};
                border-bottom: 1px solid {_border};
                padding: 4px;
                font-weight: bold;
            }}
            QHeaderView::section:last {{
                border-right: none;
            }}
        """)

        _row_h = 24
        self._table.verticalHeader().setDefaultSectionSize(_row_h)
        _hdr_h = self._table.horizontalHeader().sizeHint().height()
        _table_h = int(_row_h * 8.5) + _hdr_h + 2
        self._table.setFixedHeight(_table_h)
        self._table.setFixedWidth(_table_h)
        self._plot.setFixedSize(_table_h, _table_h)

        # cell 편집 시 맵 즉시 refresh
        self._table.itemChanged.connect(self._on_item_changed)
        # RECIPE editingFinished — 사용자 입력 commit 시점에 history push
        self._recipe.editingFinished.connect(self._push_state)

        lay.addWidget(self._plot, 2, 0)
        lay.addWidget(self._table, 2, 1)

        # ── row 3: Undo (좌) | Save/Cancel (우) ─────────
        # Undo: 무제한 stack — 매 변경마다 snapshot push, pop 으로 단계별 복원.
        # 초기 상태에 도달하면 자동 disabled (사용자 정책 2026-04-30).
        self.btn_undo = QPushButton("Undo")
        self.btn_undo.clicked.connect(self._on_undo)
        # Ctrl+Z dialog-level shortcut — WindowShortcut context 로 cell editor /
        # RECIPE LineEdit 활성 시에도 가로채임 없이 작동 (사용자 정책 2026-04-30).
        self._sc_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self._sc_undo.setContext(Qt.ShortcutContext.WindowShortcut)
        self._sc_undo.activated.connect(self._on_undo)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("저장")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        btn_row.addWidget(btns)

        undo_row = QHBoxLayout()
        undo_row.addWidget(self.btn_undo)
        undo_row.addStretch(1)
        undo_w = QWidget()
        undo_w.setLayout(undo_row)
        lay.addWidget(undo_w, 3, 0)

        btn_w = QWidget()
        btn_w.setLayout(btn_row)
        lay.addWidget(btn_w, 3, 1)

        lay.setRowStretch(0, 0)
        lay.setRowStretch(1, 0)
        lay.setRowStretch(2, 1)
        lay.setRowStretch(3, 0)
        lay.setColumnStretch(0, 1)
        lay.setColumnStretch(1, 0)

        self._result_recipe: str | None = None

        # Undo history — 초기 상태 push. 매 cell/recipe 변경 시 push, Undo 시 pop.
        # stack 크기 제한 없음 (좌표 데이터 작아 메모리 부담 X).
        self._history: list[tuple[str, np.ndarray, np.ndarray]] = []
        self._push_state()
        self.adjustSize()
        from widgets import clamp_to_screen
        clamp_to_screen(self)

    # ── slots ──────────────────────────────────
    def _on_show_numbers_toggled(self, checked: bool) -> None:
        for it in self._num_items:
            it.setVisible(bool(checked))

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """X/Y cell 편집 → 내부 array 갱신 + 산점도/번호 텍스트 위치 갱신 + history push."""
        col = item.column()
        if col not in (1, 2):
            return
        row = item.row()
        try:
            val = float(item.text())
        except ValueError:
            # 잘못된 입력 — 원래 값으로 되돌림. push 안 함.
            self._table.blockSignals(True)
            try:
                old = self._x[row] if col == 1 else self._y[row]
                item.setText(f"{float(old):.3f}")
            finally:
                self._table.blockSignals(False)
            return
        if col == 1:
            self._x[row] = val
        else:
            self._y[row] = val
        # 입력 즉시 .3f 포맷 재표시 — Undo 시점에야 포맷이 맞춰져 다른 cell 도
        # 변경된 것처럼 보이는 시각적 혼란 방지 (사용자 정책 2026-04-30).
        self._table.blockSignals(True)
        try:
            item.setText(f"{val:.3f}")
        finally:
            self._table.blockSignals(False)
        # 산점도 + 번호 위치 갱신
        self._scatter.setData(self._x, self._y)
        if 0 <= row < len(self._num_items):
            self._num_items[row].setPos(float(self._x[row]), float(self._y[row]))
        self._push_state()

    def _push_state(self) -> None:
        """현재 (recipe, x, y) snapshot 을 history 에 push. 직전과 동일하면 skip."""
        cur = (
            self._recipe.text().strip(),
            self._x.copy(),
            self._y.copy(),
        )
        if self._history:
            last = self._history[-1]
            if (last[0] == cur[0]
                    and np.array_equal(last[1], cur[1])
                    and np.array_equal(last[2], cur[2])):
                return
        self._history.append(cur)
        self._update_undo_button()

    def _update_undo_button(self) -> None:
        """초기 상태만 남으면 (len==1) Undo 비활성."""
        self.btn_undo.setEnabled(len(self._history) > 1)

    def _on_undo(self) -> None:
        """history pop → stack[-1] 상태로 UI 복원. signal block 으로 push 재트리거 차단."""
        if len(self._history) <= 1:
            return
        self._history.pop()
        recipe, x, y = self._history[-1]
        self._x = x.copy()
        self._y = y.copy()
        # UI 복원 — itemChanged / editingFinished 차단해서 push 재발 방지
        self._table.blockSignals(True)
        self._recipe.blockSignals(True)
        try:
            self._recipe.setText(recipe)
            for i in range(len(self._x)):
                xi = self._table.item(i, 1)
                yi = self._table.item(i, 2)
                if xi is not None:
                    xi.setText(f"{float(self._x[i]):.3f}")
                if yi is not None:
                    yi.setText(f"{float(self._y[i]):.3f}")
        finally:
            self._table.blockSignals(False)
            self._recipe.blockSignals(False)
        # 맵 갱신
        self._scatter.setData(self._x, self._y)
        for i, txt in enumerate(self._num_items):
            if i < len(self._x):
                txt.setPos(float(self._x[i]), float(self._y[i]))
        self._update_undo_button()

    def _on_ok(self) -> None:
        recipe = self._recipe.text().strip()
        if not recipe:
            QMessageBox.warning(self, "좌표 수정", "RECIPE 이름을 입력하세요.")
            return
        self._result_recipe = recipe
        self.accept()

    def result_values(self) -> tuple[str, np.ndarray, np.ndarray] | None:
        if self._result_recipe is None:
            return None
        return self._result_recipe, self._x.copy(), self._y.copy()
