"""
Settings 다이얼로그 — 디자인 설정 / 좌표 라이브러리 두 탭.

디자인 설정 탭:
  - UI 설정 카드: 테마 / 글꼴 / 크기
  - Graph 설정 카드: 2D MAP · 3D MAP 서브그룹 (각종 렌더 옵션)
좌표 라이브러리 탭: 프리셋 목록·정렬·편집·삭제·수동추가·자동정리

Apply = 즉시 반영 (앱 스타일시트 재빌드 + 라이브러리 저장).
OK = Apply + 닫기.  Cancel = 원복 후 닫기.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core import settings as settings_io
from core.coord_library import CoordLibrary, CoordPreset
from core.stylesheet import build_stylesheet
from core.themes import FONTS, FONT_SIZES, HEATMAP_COLORMAPS, THEMES


FONT_SCALE_CHOICES = [
    ("작게 (85%)",  0.85),
    ("보통 (100%)", 1.00),
    ("크게 (115%)", 1.15),
]

# 정렬 기준 — 모든 카드의 라벨·입력 폭·높이를 통일해서 열·행 맞춤
LABEL_WIDTH = 140          # 라벨 고정 폭 (좌측 정렬, 가장 긴 "부드럽게 (smooth)" 수용)
FIELD_WIDTH = 135          # 입력 위젯 고정 너비 (모든 입력란 시작·끝 동일)
FIELD_HEIGHT = 30          # 입력 위젯 고정 높이 (콤보/스핀/체크 행 높이 통일)


def _label(text: str) -> QLabel:
    """고정 폭·높이 라벨 — 좌측 정렬, 모든 카드 공통."""
    lbl = QLabel(text)
    lbl.setFixedWidth(LABEL_WIDTH)
    lbl.setFixedHeight(FIELD_HEIGHT)
    lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return lbl


def _setup_form(form: QFormLayout, *, margins: tuple[int, int, int, int] = (10, 10, 10, 10)) -> None:
    """카드의 QFormLayout 공통 정렬 세팅."""
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    form.setHorizontalSpacing(10)
    form.setVerticalSpacing(6)
    form.setContentsMargins(*margins)


def _populate_two_columns(group: QGroupBox, items: list[tuple[str, QWidget]]) -> None:
    """카드(QGroupBox) 내부에 항목들을 2 컬럼(좌·우 form)으로 균등 분배.

    좌·우 QFormLayout 을 QHBoxLayout 에 stretch 1:1 로 배치 → 카드 정중앙이 분할선.
    각 form 안의 라벨·필드 폭은 고정이라 모든 카드의 컬럼 시작·끝이 일치.
    """
    hbox = QHBoxLayout(group)
    hbox.setContentsMargins(10, 10, 10, 10)
    hbox.setSpacing(0)

    left_form = QFormLayout()
    right_form = QFormLayout()
    _setup_form(left_form, margins=(0, 0, 0, 0))
    _setup_form(right_form, margins=(0, 0, 0, 0))

    half = (len(items) + 1) // 2
    for label_text, widget in items[:half]:
        left_form.addRow(_label(label_text), widget)
    for label_text, widget in items[half:]:
        right_form.addRow(_label(label_text), widget)

    left_w = QWidget(); left_w.setLayout(left_form)
    right_w = QWidget(); right_w.setLayout(right_form)
    hbox.addWidget(left_w, stretch=1)
    hbox.addWidget(right_w, stretch=1)


def apply_global_style(app: QApplication, settings: dict[str, Any]) -> None:
    theme_name = settings.get("theme", "Light")
    font_name = settings.get("font", "Segoe UI")
    scale = float(settings.get("font_scale", 1.0) or 1.0)

    theme = THEMES.get(theme_name, THEMES["Light"])

    if abs(scale - 1.0) > 1e-6:
        orig = dict(FONT_SIZES)
        scaled = {k: max(8, int(round(v * scale))) for k, v in orig.items()}
        FONT_SIZES.update(scaled)
        try:
            qss = build_stylesheet(theme, font_name)
        finally:
            FONT_SIZES.clear()
            FONT_SIZES.update(orig)
    else:
        qss = build_stylesheet(theme, font_name)

    app.setStyleSheet(qss)


def _fix_width(widget: QWidget, px: int = FIELD_WIDTH) -> QWidget:
    """모든 입력 위젯의 폭·높이를 고정 — 시작·끝·행 높이 모두 동일."""
    widget.setFixedWidth(px)
    widget.setFixedHeight(FIELD_HEIGHT)
    return widget


# 하위 호환 alias
_limit_width = _fix_width


# ────────────────────────────────────────────────────────
# UI 설정 카드
# ────────────────────────────────────────────────────────
class UiSettingsCard(QGroupBox):
    """테마/글꼴/크기 — 콤보 변경 즉시 `changed` 시그널 emit (다이얼로그에서 즉시 Apply)."""

    changed = Signal()

    def __init__(self, settings: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__("UI 설정", parent)

        self.cb_theme = _limit_width(QComboBox())
        self.cb_theme.addItems(sorted(THEMES.keys()))
        idx = self.cb_theme.findText(settings.get("theme", "Light"))
        if idx >= 0:
            self.cb_theme.setCurrentIndex(idx)

        self.cb_font = _limit_width(QComboBox())
        self.cb_font.addItems(FONTS)
        idx = self.cb_font.findText(settings.get("font", "Segoe UI"))
        if idx >= 0:
            self.cb_font.setCurrentIndex(idx)

        self.cb_scale = _limit_width(QComboBox())
        current_scale = float(settings.get("font_scale", 1.0) or 1.0)
        nearest_idx = 1
        best_diff = abs(current_scale - FONT_SCALE_CHOICES[1][1])
        for i, (label, val) in enumerate(FONT_SCALE_CHOICES):
            self.cb_scale.addItem(label, val)
            if abs(current_scale - val) < best_diff:
                best_diff = abs(current_scale - val)
                nearest_idx = i
        self.cb_scale.setCurrentIndex(nearest_idx)

        self.chk_save_window = _fix_width(QCheckBox())
        self.chk_save_window.setChecked(bool(settings.get("window_save_enabled", True)))

        # 좌측 [테마, 윈도우 크기 저장], 우측 [글꼴, 글자 크기]
        _populate_two_columns(self, [
            ("테마", self.cb_theme),
            ("윈도우 크기 저장", self.chk_save_window),
            ("글꼴", self.cb_font),
            ("글자 크기", self.cb_scale),
        ])

        # 즉시 적용
        self.cb_theme.currentIndexChanged.connect(self.changed)
        self.cb_font.currentIndexChanged.connect(self.changed)
        self.cb_scale.currentIndexChanged.connect(self.changed)
        self.chk_save_window.toggled.connect(self.changed)

    def gather(self) -> dict[str, Any]:
        return {
            "theme": self.cb_theme.currentText(),
            "font": self.cb_font.currentText(),
            "font_scale": float(self.cb_scale.currentData()),
            "window_save_enabled": self.chk_save_window.isChecked(),
        }

    def reload(self, settings: dict[str, Any]) -> None:
        """위젯 값을 settings로 갱신. 마지막에 changed 한 번만 emit."""
        widgets = (self.cb_theme, self.cb_font, self.cb_scale, self.chk_save_window)
        for w in widgets:
            w.blockSignals(True)
        try:
            idx = self.cb_theme.findText(settings.get("theme", "Light"))
            if idx >= 0:
                self.cb_theme.setCurrentIndex(idx)
            idx = self.cb_font.findText(settings.get("font", "Segoe UI"))
            if idx >= 0:
                self.cb_font.setCurrentIndex(idx)
            target_scale = float(settings.get("font_scale", 1.0) or 1.0)
            best_i, best_d = 0, float("inf")
            for i in range(self.cb_scale.count()):
                d = abs(target_scale - float(self.cb_scale.itemData(i)))
                if d < best_d:
                    best_d, best_i = d, i
            self.cb_scale.setCurrentIndex(best_i)
            self.chk_save_window.setChecked(bool(settings.get("window_save_enabled", True)))
        finally:
            for w in widgets:
                w.blockSignals(False)
        self.changed.emit()


# ────────────────────────────────────────────────────────
# Graph 설정 카드 — 2D / 3D 서브그룹
# ────────────────────────────────────────────────────────
INTERP_METHODS = ["rbf", "cubic", "cubic_nearest", "phantom_ring"]
SHADING_MODES = ["shaded", "normalColor", "heightColor"]  # pyqtgraph.opengl 지원 셰이더


class ChartCommonGroup(QGroupBox):
    """MAP 공통 설정 — 2D/3D 양쪽에 적용. 변경 즉시 `changed` emit."""

    changed = Signal()

    def __init__(self, cfg: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__("MAP 공통 설정", parent)

        self.cb_cmap = _limit_width(QComboBox())
        self.cb_cmap.addItems(HEATMAP_COLORMAPS)
        idx = self.cb_cmap.findText(cfg.get("colormap", "turbo"))
        if idx >= 0:
            self.cb_cmap.setCurrentIndex(idx)

        self.cb_interp = _limit_width(QComboBox())
        self.cb_interp.addItems(INTERP_METHODS)
        idx = self.cb_interp.findText(cfg.get("interp_method", "rbf"))
        if idx >= 0:
            self.cb_interp.setCurrentIndex(idx)

        self.cb_grid = _limit_width(QComboBox())
        for v in (100, 150, 200, 250):
            self.cb_grid.addItem(str(v), v)
        idx = self.cb_grid.findData(int(cfg.get("grid_resolution", 100)))
        self.cb_grid.setCurrentIndex(idx if idx >= 0 else 2)

        self.chk_circle = _fix_width(QCheckBox())
        self.chk_circle.setChecked(bool(cfg.get("show_circle", True)))

        self.chk_notch = _fix_width(QCheckBox())
        self.chk_notch.setChecked(bool(cfg.get("show_notch", True)))

        # Notch Depth 콤보 + "mm" 단위 라벨
        self.cb_notch_depth = QComboBox()
        for v in (3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0):
            self.cb_notch_depth.addItem(f"{v:g}", v)
        idx = self.cb_notch_depth.findData(float(cfg.get("notch_depth_mm", 5.0)))
        self.cb_notch_depth.setCurrentIndex(idx if idx >= 0 else 4)
        depth_row = QWidget()
        _row = QHBoxLayout(depth_row)
        _row.setContentsMargins(0, 0, 0, 0); _row.setSpacing(4)
        _row.addWidget(_limit_width(self.cb_notch_depth))
        _row.addWidget(QLabel("mm"))
        _row.addStretch(1)

        _populate_two_columns(self, [
            ("컬러맵", self.cb_cmap),
            ("보간 방법", self.cb_interp),
            ("격자 해상도", self.cb_grid),
            ("경계 원", self.chk_circle),
            ("Notch 표시", self.chk_notch),
            ("Notch Depth", depth_row),
        ])

        self.cb_cmap.currentIndexChanged.connect(self.changed)
        self.cb_interp.currentIndexChanged.connect(self.changed)
        self.cb_grid.currentIndexChanged.connect(self.changed)
        self.chk_circle.toggled.connect(self.changed)
        self.chk_notch.toggled.connect(self.changed)
        self.cb_notch_depth.currentIndexChanged.connect(self.changed)

    def gather(self) -> dict[str, Any]:
        return {
            "colormap": self.cb_cmap.currentText(),
            "interp_method": self.cb_interp.currentText(),
            "grid_resolution": int(self.cb_grid.currentData()),
            "show_circle": self.chk_circle.isChecked(),
            "show_notch": self.chk_notch.isChecked(),
            "notch_depth_mm": float(self.cb_notch_depth.currentData()),
        }

    def reload(self, cfg: dict[str, Any]) -> None:
        widgets = (self.cb_cmap, self.cb_interp, self.cb_grid, self.chk_circle,
                   self.chk_notch, self.cb_notch_depth)
        for w in widgets:
            w.blockSignals(True)
        try:
            idx = self.cb_cmap.findText(cfg.get("colormap", "turbo"))
            if idx >= 0: self.cb_cmap.setCurrentIndex(idx)
            idx = self.cb_interp.findText(cfg.get("interp_method", "rbf"))
            if idx >= 0: self.cb_interp.setCurrentIndex(idx)
            idx = self.cb_grid.findData(int(cfg.get("grid_resolution", 100)))
            if idx >= 0: self.cb_grid.setCurrentIndex(idx)
            self.chk_circle.setChecked(bool(cfg.get("show_circle", True)))
            self.chk_notch.setChecked(bool(cfg.get("show_notch", True)))
            idx = self.cb_notch_depth.findData(float(cfg.get("notch_depth_mm", 5.0)))
            if idx >= 0: self.cb_notch_depth.setCurrentIndex(idx)
        finally:
            for w in widgets:
                w.blockSignals(False)
        self.changed.emit()


class Chart2DGroup(QGroupBox):
    """2D MAP 전용 — 측정점/점 크기/라벨. 변경 즉시 `changed` emit."""

    changed = Signal()

    def __init__(self, cfg: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__("2D MAP 설정", parent)

        self.chk_points = _fix_width(QCheckBox())
        self.chk_points.setChecked(bool(cfg.get("show_points", True)))

        self.cb_point = _limit_width(QComboBox())
        for v in (1, 2, 3, 4, 6, 8, 10, 12):
            self.cb_point.addItem(str(v), v)
        idx = self.cb_point.findData(int(cfg.get("point_size", 4)))
        self.cb_point.setCurrentIndex(idx if idx >= 0 else 3)

        self.chk_value_labels = _fix_width(QCheckBox())
        self.chk_value_labels.setChecked(bool(cfg.get("show_value_labels", False)))

        _populate_two_columns(self, [
            ("측정점 표시", self.chk_points),
            ("점 크기", self.cb_point),
            ("라벨 표시", self.chk_value_labels),
        ])

        self.chk_points.toggled.connect(self.changed)
        self.cb_point.currentIndexChanged.connect(self.changed)
        self.chk_value_labels.toggled.connect(self.changed)

    def gather(self) -> dict[str, Any]:
        return {
            "show_points": self.chk_points.isChecked(),
            "point_size": int(self.cb_point.currentData()),
            "show_value_labels": self.chk_value_labels.isChecked(),
        }

    def reload(self, cfg: dict[str, Any]) -> None:
        widgets = (self.chk_points, self.cb_point, self.chk_value_labels)
        for w in widgets:
            w.blockSignals(True)
        try:
            self.chk_points.setChecked(bool(cfg.get("show_points", True)))
            idx = self.cb_point.findData(int(cfg.get("point_size", 4)))
            if idx >= 0: self.cb_point.setCurrentIndex(idx)
            self.chk_value_labels.setChecked(bool(cfg.get("show_value_labels", False)))
        finally:
            for w in widgets:
                w.blockSignals(False)
        self.changed.emit()


class Chart3DGroup(QGroupBox):
    """3D MAP 옵션 — 변경 즉시 `changed` 시그널 emit."""

    changed = Signal()

    def __init__(self, cfg: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__("3D MAP 설정", parent)

        self.cb_shading = _limit_width(QComboBox())
        self.cb_shading.addItems(SHADING_MODES)
        idx = self.cb_shading.findText(cfg.get("shading", "shaded"))
        if idx >= 0:
            self.cb_shading.setCurrentIndex(idx)

        self.chk_smooth = _fix_width(QCheckBox())
        self.chk_smooth.setChecked(bool(cfg.get("smooth", True)))

        self.cb_zexag = _limit_width(QComboBox())
        self.cb_zexag.addItem("자동", None)
        for v in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 5.0):
            self.cb_zexag.addItem(f"{v:g}\u00d7", v)
        cur = cfg.get("z_exaggeration", None)
        if cur is None:
            self.cb_zexag.setCurrentIndex(0)
        else:
            try:
                idx = self.cb_zexag.findData(float(cur))
            except (TypeError, ValueError):
                idx = 0
            self.cb_zexag.setCurrentIndex(idx if idx >= 0 else 0)

        self.chk_grid = _fix_width(QCheckBox())
        self.chk_grid.setChecked(bool(cfg.get("show_grid", True)))

        _populate_two_columns(self, [
            ("쉐이딩", self.cb_shading),
            ("부드럽게 (smooth)", self.chk_smooth),
            ("Z-Height", self.cb_zexag),
            ("바닥 그리드", self.chk_grid),
        ])

        self.cb_shading.currentIndexChanged.connect(self.changed)
        self.chk_smooth.toggled.connect(self.changed)
        self.cb_zexag.currentIndexChanged.connect(self.changed)
        self.chk_grid.toggled.connect(self.changed)

    def gather(self) -> dict[str, Any]:
        return {
            "shading": self.cb_shading.currentText(),
            "smooth": self.chk_smooth.isChecked(),
            "z_exaggeration": self.cb_zexag.currentData(),  # None(자동) or float
            "show_grid": self.chk_grid.isChecked(),
        }

    def reload(self, cfg: dict[str, Any]) -> None:
        widgets = (self.cb_shading, self.chk_smooth, self.cb_zexag, self.chk_grid)
        for w in widgets:
            w.blockSignals(True)
        try:
            idx = self.cb_shading.findText(cfg.get("shading", "shaded"))
            if idx >= 0: self.cb_shading.setCurrentIndex(idx)
            self.chk_smooth.setChecked(bool(cfg.get("smooth", True)))
            cur = cfg.get("z_exaggeration", None)
            if cur is None:
                self.cb_zexag.setCurrentIndex(0)
            else:
                try:
                    idx = self.cb_zexag.findData(float(cur))
                except (TypeError, ValueError):
                    idx = 0
                self.cb_zexag.setCurrentIndex(idx if idx >= 0 else 0)
            self.chk_grid.setChecked(bool(cfg.get("show_grid", True)))
        finally:
            for w in widgets:
                w.blockSignals(False)
        self.changed.emit()


# ────────────────────────────────────────────────────────
# 디자인 설정 탭 (UI / 2D / 3D 세 카드를 flat 세로 스택)
# ────────────────────────────────────────────────────────
class DesignTab(QScrollArea):
    """UI · 2D · 3D 세 카드. 개별 카드의 changed 시그널을 통합 forward."""

    ui_changed = Signal()       # UI 설정(테마·글꼴·크기) 변경
    graph_changed = Signal()    # 2D / 3D 설정 변경

    def __init__(self, settings: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        self._ui_card = UiSettingsCard(settings)
        self._card_common = ChartCommonGroup(settings.get("chart_common", {}))
        self._card_2d = Chart2DGroup(settings.get("chart_2d", {}))
        self._card_3d = Chart3DGroup(settings.get("chart_3d", {}))
        lay.addWidget(self._ui_card)
        lay.addWidget(self._card_common)
        lay.addWidget(self._card_2d)
        lay.addWidget(self._card_3d)
        lay.addStretch(1)

        self.setWidget(container)

        self._ui_card.changed.connect(self.ui_changed)
        self._card_common.changed.connect(self.graph_changed)
        self._card_2d.changed.connect(self.graph_changed)
        self._card_3d.changed.connect(self.graph_changed)

    def gather(self) -> dict[str, Any]:
        return {
            **self._ui_card.gather(),
            "chart_common": self._card_common.gather(),
            "chart_2d": self._card_2d.gather(),
            "chart_3d": self._card_3d.gather(),
        }

    def reset_to_defaults(self) -> None:
        """4개 카드 모두 DEFAULT_SETTINGS 값으로 되돌리기."""
        from core.themes import DEFAULT_SETTINGS
        self._ui_card.reload(DEFAULT_SETTINGS)
        self._card_common.reload(DEFAULT_SETTINGS.get("chart_common", {}))
        self._card_2d.reload(DEFAULT_SETTINGS.get("chart_2d", {}))
        self._card_3d.reload(DEFAULT_SETTINGS.get("chart_3d", {}))


# ────────────────────────────────────────────────────────
# Coord Library 탭 (기존 유지, 클래스 이름만)
# ────────────────────────────────────────────────────────
SORT_OPTIONS = [
    ("RECIPE (오름차순)",       lambda p: (p.recipe.lower(), p.n_points)),
    ("측정 포인트 수",           lambda p: (p.n_points, p.recipe.lower())),
    ("이름",                    lambda p: p.name.lower()),
    ("최근 사용 (최신 우선)",    lambda p: p.last_used),
    ("최초 저장 (최신 우선)",    lambda p: p.created_at),
]


class CoordLibraryTab(QWidget):
    def __init__(self, settings: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._library = CoordLibrary()
        self._initial_presets = list(self._library.presets)

        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self._count_label = QLabel()
        top.addWidget(self._count_label)
        top.addStretch(1)
        top.addWidget(QLabel("정렬:"))
        self._cb_sort = _limit_width(QComboBox())
        for label, _ in SORT_OPTIONS:
            self._cb_sort.addItem(label)
        self._cb_sort.currentIndexChanged.connect(self._refresh_table)
        top.addWidget(self._cb_sort)
        lay.addLayout(top)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["이름", "RECIPE", "n", "최초 저장", "마지막 사용"],
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.verticalHeader().hide()
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setStretchLastSection(True)
        lay.addWidget(self._table, stretch=1)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("수동 추가")
        self.btn_rename = QPushButton("이름 변경")
        self.btn_recipe = QPushButton("RECIPE 변경")
        self.btn_delete = QPushButton("삭제")
        self.btn_delete.setProperty("class", "danger")
        for b in (self.btn_add, self.btn_rename, self.btn_recipe, self.btn_delete):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.btn_add.clicked.connect(self._on_add)
        self.btn_rename.clicked.connect(self._on_rename)
        self.btn_recipe.clicked.connect(self._on_recipe)
        self.btn_delete.clicked.connect(self._on_delete)

        limits_box = QGroupBox("자동 정리")
        limits_form = QFormLayout(limits_box)
        cl_settings = settings.get("coord_library", {}) or {}

        self._sb_max_count = _fix_width(QSpinBox())
        self._sb_max_count.setRange(0, 100_000)
        self._sb_max_count.setSpecialValueText("무제한")
        self._sb_max_count.setValue(int(cl_settings.get("max_count", 1000)))

        self._sb_max_days = _fix_width(QSpinBox())
        self._sb_max_days.setRange(0, 3650)
        self._sb_max_days.setSpecialValueText("무제한")
        self._sb_max_days.setValue(int(cl_settings.get("max_days", 1000)))

        limits_form.addRow("최대 저장 개수", self._sb_max_count)
        limits_form.addRow("최대 보관일", self._sb_max_days)
        lay.addWidget(limits_box)

        self._refresh_table()

    def _sorted_presets(self) -> list[CoordPreset]:
        idx = self._cb_sort.currentIndex()
        label, key_fn = SORT_OPTIONS[idx]
        reverse = "최신 우선" in label
        return sorted(self._library.presets, key=key_fn, reverse=reverse)

    def _refresh_table(self) -> None:
        presets = self._sorted_presets()
        self._count_label.setText(f"저장된 좌표: {len(presets)}개")
        self._table.setUpdatesEnabled(False)
        try:
            self._table.setRowCount(len(presets))
            for r, p in enumerate(presets):
                vals = (p.name, p.recipe, str(p.n_points), p.created_at, p.last_used)
                for c, text in enumerate(vals):
                    item = QTableWidgetItem(text)
                    if c == 2:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if c == 0:
                        item.setData(Qt.ItemDataRole.UserRole, p)
                    self._table.setItem(r, c, item)
        finally:
            self._table.setUpdatesEnabled(True)

    def _selected_presets(self) -> list[CoordPreset]:
        rows = sorted({i.row() for i in self._table.selectedIndexes()})
        out: list[CoordPreset] = []
        for r in rows:
            it = self._table.item(r, 0)
            if it is None:
                continue
            p = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(p, CoordPreset):
                out.append(p)
        return out

    def _on_add(self) -> None:
        from widgets.preset_add_dialog import PresetAddDialog
        dlg = PresetAddDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        result = dlg.result_values()
        if result is None:
            return
        recipe, x, y = result
        try:
            self._library.add_or_touch(recipe, x, y, save=True)
        except Exception as e:
            QMessageBox.warning(self, "추가 실패", str(e))
            return
        self._refresh_table()

    def _on_rename(self) -> None:
        sel = self._selected_presets()
        if len(sel) != 1:
            QMessageBox.information(self, "이름 변경", "프리셋 한 개를 선택하세요.")
            return
        p = sel[0]
        new_name, ok = QInputDialog.getText(self, "이름 변경", "새 이름:", text=p.name)
        if ok and new_name.strip():
            self._library.rename(p, new_name.strip(), save=True)
            self._refresh_table()

    def _on_recipe(self) -> None:
        sel = self._selected_presets()
        if len(sel) != 1:
            QMessageBox.information(self, "RECIPE 변경", "프리셋 한 개를 선택하세요.")
            return
        p = sel[0]
        new_rcp, ok = QInputDialog.getText(self, "RECIPE 변경", "새 RECIPE:", text=p.recipe)
        if ok and new_rcp.strip():
            self._library.set_recipe(p, new_rcp.strip(), save=True)
            self._refresh_table()

    def _on_delete(self) -> None:
        sel = self._selected_presets()
        if not sel:
            return
        r = QMessageBox.question(
            self, "삭제 확인",
            f"선택한 {len(sel)}개 프리셋을 삭제하시겠습니까?",
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        for p in sel:
            self._library.delete(p, save=False)
        self._library.save()
        self._refresh_table()

    def gather(self) -> dict[str, Any]:
        mc = int(self._sb_max_count.value())
        md = int(self._sb_max_days.value())
        self._library.enforce_limits(max_count=mc, max_days=md, save=True)
        self._refresh_table()
        return {"coord_library": {"max_count": mc, "max_days": md}}

    def revert_on_cancel(self) -> None:
        self._library.presets = list(self._initial_presets)
        self._library.save()


# ────────────────────────────────────────────────────────
# Settings 다이얼로그
# ────────────────────────────────────────────────────────
class SettingsDialog(QDialog):
    """논모달 Settings. Save = 파일 저장, Close = 닫기(메모리 상태 유지).

    모든 디자인 설정 변경은 즉시 런타임 캐시에 반영(`set_runtime`) + MainWindow 재렌더.
    파일 저장은 Save 버튼을 눌러야 수행 — 다음 실행 시 불러올 값이 확정됨.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(780, 700)
        self.setModal(False)

        settings = settings_io.load_settings()
        self._initial = dict(settings)

        self._tabs = QTabWidget()
        self._design = DesignTab(settings)
        self._coords = CoordLibraryTab(settings)
        self._tabs.addTab(self._design, "디자인 설정")
        self._tabs.addTab(self._coords, "좌표 라이브러리")

        # 디자인 변경 시 즉시 반영
        self._design.ui_changed.connect(self._apply_ui_runtime)
        self._design.graph_changed.connect(self._apply_graph_runtime)

        btns = QDialogButtonBox()
        self.btn_save = btns.addButton("Save", QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_close = btns.addButton("Close", QDialogButtonBox.ButtonRole.RejectRole)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_close.clicked.connect(self._on_close)

        # 하단 좌측 Default — 디자인 탭 4개 카드를 DEFAULT_SETTINGS로 리셋
        self.btn_default = QPushButton("Default")
        self.btn_default.clicked.connect(self._design.reset_to_defaults)

        # 모든 버튼 폭 통일 + default/auto-default 해제 (엔터로 dialog 닫힘 방지)
        from widgets.paste_area import HEADER_BUTTON_WIDTH
        for b in (self.btn_save, self.btn_close, self.btn_default):
            b.setFixedWidth(HEADER_BUTTON_WIDTH)
            b.setDefault(False)
            b.setAutoDefault(False)

        bottom = QHBoxLayout()
        bottom.addWidget(self.btn_default)
        bottom.addStretch(1)
        bottom.addWidget(btns)

        lay = QVBoxLayout(self)
        lay.addWidget(self._tabs, stretch=1)
        lay.addLayout(bottom)

    # ── 현재 다이얼로그의 설정 전체를 모아 반환 ──
    def _collect(self) -> dict[str, Any]:
        merged = dict(self._initial)
        merged.update(self._design.gather())
        merged.update(self._coords.gather())
        return merged

    # ── 즉시 반영 핸들러 ────────────────────────
    def _apply_ui_runtime(self) -> None:
        """UI 설정 변경 → 런타임 캐시 + 앱 스타일시트 재빌드."""
        merged = self._collect()
        settings_io.set_runtime(merged)
        app = QApplication.instance()
        if app is not None:
            apply_global_style(app, merged)

    def _apply_graph_runtime(self) -> None:
        """Graph(2D/3D) 설정 변경 → 런타임 캐시 + MainWindow 재렌더 (cell 재생성 없이).

        cell의 보간 캐시는 (interp_method, grid_resolution) 비교로 재사용 판단 →
        컬러맵·shading·점 크기 등 변경 시 RBF 50~100ms 비용 생략.
        """
        merged = self._collect()
        settings_io.set_runtime(merged)
        main = self.parent()
        if main is not None and hasattr(main, "refresh_graph"):
            main.refresh_graph()

    # ── Enter 키로 dialog가 닫히지 않게 (QSpinBox 등 자식 입력란용) ──
    def keyPressEvent(self, event) -> None:
        from PySide6.QtCore import Qt as _Qt
        if event.key() in (_Qt.Key.Key_Return, _Qt.Key.Key_Enter):
            event.accept()
            return
        super().keyPressEvent(event)

    # ── Save / Close ──────────────────────────
    def _on_save(self) -> None:
        merged = self._collect()
        settings_io.save_settings(merged)
        app = QApplication.instance()
        if app is not None:
            apply_global_style(app, merged)
        self.accept()

    def _on_close(self) -> None:
        """메모리 변경은 유지(현재 앱에 이미 반영됨). 파일 저장은 안 함."""
        self.reject()
