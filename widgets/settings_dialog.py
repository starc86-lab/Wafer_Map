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
from core.coord_library import CoordLibrary, CoordPreset, format_dt_display
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
INTERP_METHODS = [
    "RBF-ThinPlate", "RBF-Multiquadric", "RBF-Gaussian", "RBF-Quintic",
]


class ChartCommonGroup(QGroupBox):
    """MAP 공통 설정 — 2D/3D 양쪽에 적용. 변경 즉시 `changed` emit."""

    changed = Signal()

    def __init__(self, cfg: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__("MAP 공통 설정", parent)

        self.cb_cmap = _limit_width(QComboBox())
        self.cb_cmap.addItems(HEATMAP_COLORMAPS)
        idx = self.cb_cmap.findText(cfg.get("colormap", "Turbo"))
        if idx >= 0:
            self.cb_cmap.setCurrentIndex(idx)

        self.cb_interp = _limit_width(QComboBox())
        self.cb_interp.addItems(INTERP_METHODS)
        idx = self.cb_interp.findText(cfg.get("interp_method", "RBF-ThinPlate"))
        if idx >= 0:
            self.cb_interp.setCurrentIndex(idx)

        self.cb_grid = _limit_width(QComboBox())
        for v in (100, 150, 200, 250, 300, 350, 400, 450, 500):
            self.cb_grid.addItem(str(v), v)
        idx = self.cb_grid.findData(int(cfg.get("grid_resolution", 200)))
        self.cb_grid.setCurrentIndex(idx if idx >= 0 else 2)

        self.cb_decimals = _limit_width(QComboBox())
        for v in (0, 1, 2, 3):
            self.cb_decimals.addItem(str(v), v)
        idx = self.cb_decimals.findData(int(cfg.get("decimals", 2)))
        self.cb_decimals.setCurrentIndex(idx if idx >= 0 else 2)

        # Edge cut — 웨이퍼 경계에서 안쪽으로 cut. 0=cut 없음. radial/RBF 양쪽 공통
        self.sb_edge_cut = QDoubleSpinBox()
        self.sb_edge_cut.setRange(0.0, 10.0)
        self.sb_edge_cut.setSingleStep(0.5)
        self.sb_edge_cut.setDecimals(1)
        self.sb_edge_cut.setSuffix(" mm")
        self.sb_edge_cut.setValue(float(cfg.get("edge_cut_mm", 0.0)))
        _limit_width(self.sb_edge_cut)

        self.chk_circle = _fix_width(QCheckBox())
        self.chk_circle.setChecked(bool(cfg.get("show_circle", True)))

        self.chk_notch = _fix_width(QCheckBox())
        self.chk_notch.setChecked(bool(cfg.get("show_notch", True)))

        self.chk_scale_bar = _fix_width(QCheckBox())
        self.chk_scale_bar.setChecked(bool(cfg.get("show_scale_bar", True)))

        # 그래프 크기 — 9:7 비율 고정 (360:280 기준, 0.8× ~ 1.6×)
        self.cb_chart_size = _limit_width(QComboBox())
        for w, h in ((288, 224), (360, 280), (432, 336), (504, 392), (576, 448)):
            self.cb_chart_size.addItem(f"{w}×{h}", (w, h))
        cur_w = int(cfg.get("chart_width", 360))
        cur_h = int(cfg.get("chart_height", 280))
        match_idx = 1  # 360×280 기본
        for i in range(self.cb_chart_size.count()):
            w, h = self.cb_chart_size.itemData(i)
            if w == cur_w and h == cur_h:
                match_idx = i
                break
        self.cb_chart_size.setCurrentIndex(match_idx)

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
            ("스케일바 표시", self.chk_scale_bar),
            ("그래프 크기", self.cb_chart_size),
            ("소수점 자릿수", self.cb_decimals),
            ("Edge cut", self.sb_edge_cut),
        ])

        self.cb_cmap.currentIndexChanged.connect(self.changed)
        self.cb_interp.currentIndexChanged.connect(self.changed)
        self.cb_grid.currentIndexChanged.connect(self.changed)
        self.chk_circle.toggled.connect(self.changed)
        self.chk_notch.toggled.connect(self.changed)
        self.cb_notch_depth.currentIndexChanged.connect(self.changed)
        self.chk_scale_bar.toggled.connect(self.changed)
        self.cb_chart_size.currentIndexChanged.connect(self.changed)
        self.cb_decimals.currentIndexChanged.connect(self.changed)
        self.sb_edge_cut.valueChanged.connect(self.changed)

    def gather(self) -> dict[str, Any]:
        w, h = self.cb_chart_size.currentData()
        return {
            "colormap": self.cb_cmap.currentText(),
            "interp_method": self.cb_interp.currentText(),
            "grid_resolution": int(self.cb_grid.currentData()),
            "show_circle": self.chk_circle.isChecked(),
            "show_notch": self.chk_notch.isChecked(),
            "notch_depth_mm": float(self.cb_notch_depth.currentData()),
            "show_scale_bar": self.chk_scale_bar.isChecked(),
            "chart_width": int(w),
            "chart_height": int(h),
            "decimals": int(self.cb_decimals.currentData()),
            "edge_cut_mm": float(self.sb_edge_cut.value()),
        }

    def reload(self, cfg: dict[str, Any]) -> None:
        widgets = (self.cb_cmap, self.cb_interp, self.cb_grid, self.chk_circle,
                   self.chk_notch, self.cb_notch_depth, self.chk_scale_bar,
                   self.cb_chart_size, self.cb_decimals, self.sb_edge_cut)
        for w in widgets:
            w.blockSignals(True)
        try:
            idx = self.cb_cmap.findText(cfg.get("colormap", "Turbo"))
            if idx >= 0: self.cb_cmap.setCurrentIndex(idx)
            idx = self.cb_interp.findText(cfg.get("interp_method", "RBF-ThinPlate"))
            if idx >= 0: self.cb_interp.setCurrentIndex(idx)
            idx = self.cb_grid.findData(int(cfg.get("grid_resolution", 200)))
            if idx >= 0: self.cb_grid.setCurrentIndex(idx)
            self.chk_circle.setChecked(bool(cfg.get("show_circle", True)))
            self.chk_notch.setChecked(bool(cfg.get("show_notch", True)))
            idx = self.cb_notch_depth.findData(float(cfg.get("notch_depth_mm", 5.0)))
            if idx >= 0: self.cb_notch_depth.setCurrentIndex(idx)
            self.chk_scale_bar.setChecked(bool(cfg.get("show_scale_bar", True)))
            cur_w = int(cfg.get("chart_width", 360))
            cur_h = int(cfg.get("chart_height", 280))
            for i in range(self.cb_chart_size.count()):
                w, h = self.cb_chart_size.itemData(i)
                if w == cur_w and h == cur_h:
                    self.cb_chart_size.setCurrentIndex(i)
                    break
            idx = self.cb_decimals.findData(int(cfg.get("decimals", 2)))
            if idx >= 0:
                self.cb_decimals.setCurrentIndex(idx)
            self.sb_edge_cut.setValue(float(cfg.get("edge_cut_mm", 0.0)))
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

        self.chk_smooth = _fix_width(QCheckBox())
        self.chk_smooth.setChecked(bool(cfg.get("smooth", True)))

        # Z-Height (배율) — DoubleSpinBox, 0.5~3.0, step 0.1, 소수 1자리
        self.sp_zexag = _limit_width(QDoubleSpinBox())
        self.sp_zexag.setRange(0.5, 3.0)
        self.sp_zexag.setSingleStep(0.1)
        self.sp_zexag.setDecimals(1)
        self.sp_zexag.setSuffix("×")
        cur_z = cfg.get("z_exaggeration", 1.0)
        self.sp_zexag.setValue(1.0 if cur_z is None else float(cur_z))

        self.chk_grid = _fix_width(QCheckBox())
        self.chk_grid.setChecked(bool(cfg.get("show_grid", True)))

        # 카메라 distance — SpinBox, 400~800, step 10
        self.sp_cam_dist = _limit_width(QSpinBox())
        self.sp_cam_dist.setRange(400, 800)
        self.sp_cam_dist.setSingleStep(10)
        self.sp_cam_dist.setValue(int(cfg.get("camera_distance", 550)))

        _populate_two_columns(self, [
            ("부드럽게 (smooth)", self.chk_smooth),
            ("Z-Height", self.sp_zexag),
            ("바닥 그리드", self.chk_grid),
            ("카메라 거리", self.sp_cam_dist),
        ])

        self.chk_smooth.toggled.connect(self.changed)
        self.sp_zexag.valueChanged.connect(self.changed)
        self.chk_grid.toggled.connect(self.changed)
        self.sp_cam_dist.valueChanged.connect(self.changed)

    def gather(self) -> dict[str, Any]:
        return {
            "smooth": self.chk_smooth.isChecked(),
            "z_exaggeration": float(self.sp_zexag.value()),
            "show_grid": self.chk_grid.isChecked(),
            "camera_distance": int(self.sp_cam_dist.value()),
        }

    def reload(self, cfg: dict[str, Any]) -> None:
        widgets = (self.chk_smooth, self.sp_zexag, self.chk_grid, self.sp_cam_dist)
        for w in widgets:
            w.blockSignals(True)
        try:
            self.chk_smooth.setChecked(bool(cfg.get("smooth", True)))
            cur_z = cfg.get("z_exaggeration", 1.0)
            self.sp_zexag.setValue(1.0 if cur_z is None else float(cur_z))
            self.chk_grid.setChecked(bool(cfg.get("show_grid", True)))
            self.sp_cam_dist.setValue(int(cfg.get("camera_distance", 550)))
        finally:
            for w in widgets:
                w.blockSignals(False)
        self.changed.emit()


# ────────────────────────────────────────────────────────
# 디자인 설정 탭 (UI / 2D / 3D 세 카드를 flat 세로 스택)
# ────────────────────────────────────────────────────────
class DesignTab(QWidget):
    """UI · 2D · 3D 세 카드 + 하단 좌측 Default 버튼. 카드 changed 시그널 통합 forward."""

    ui_changed = Signal()       # UI 설정(테마·글꼴·크기) 변경
    graph_changed = Signal()    # 2D / 3D 설정 변경

    def __init__(self, settings: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        cards = QVBoxLayout(container)
        cards.setContentsMargins(8, 8, 8, 8)
        cards.setSpacing(8)

        self._ui_card = UiSettingsCard(settings)
        self._card_common = ChartCommonGroup(settings.get("chart_common", {}))
        self._card_2d = Chart2DGroup(settings.get("chart_2d", {}))
        self._card_3d = Chart3DGroup(settings.get("chart_3d", {}))
        cards.addWidget(self._ui_card)
        cards.addWidget(self._card_common)
        cards.addWidget(self._card_2d)
        cards.addWidget(self._card_3d)
        cards.addStretch(1)
        scroll.setWidget(container)

        # Default — 디자인 탭 전용. 스크롤 밖 sticky 위치
        from widgets.paste_area import HEADER_BUTTON_WIDTH
        self.btn_default = QPushButton("Default")
        self.btn_default.setFixedWidth(HEADER_BUTTON_WIDTH)
        self.btn_default.setDefault(False)
        self.btn_default.setAutoDefault(False)
        self.btn_default.clicked.connect(self.reset_to_defaults)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(8, 4, 8, 8)
        btn_row.addWidget(self.btn_default)
        btn_row.addStretch(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(scroll, stretch=1)
        lay.addLayout(btn_row)

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
        lay.addLayout(top)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["RECIPE", "X / Y", "Point", "최초 저장", "마지막 사용"],
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.verticalHeader().hide()
        hdr = self._table.horizontalHeader()
        # Interactive + content 기준 폭 계산 후 여유분 전 컬럼에 균등 분배
        # (ResizeToContents는 마지막 stretch만 가능, Stretch는 content 짤림)
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(False)
        # 헤더 클릭 → 오름/내림 토글 정렬 (n은 정수 정렬, 날짜는 ISO 문자열로 자연 정렬)
        self._table.setSortingEnabled(True)
        self._natural_widths: list[int] = []
        lay.addWidget(self._table, stretch=1)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("수동 추가")
        self.btn_recipe = QPushButton("RECIPE 변경")
        self.btn_delete = QPushButton("삭제")
        self.btn_delete.setProperty("class", "danger")
        for b in (self.btn_add, self.btn_recipe, self.btn_delete):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.btn_add.clicked.connect(self._on_add)
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

    def _refresh_table(self) -> None:
        """레코드 개별 행 표시 — (RECIPE, X/Y) 조합이 키라 같은 RECIPE 여러 행 가능."""
        presets = self._library.presets
        self._count_label.setText(f"저장된 레코드: {len(presets)}개")
        self._table.setSortingEnabled(False)
        self._table.setUpdatesEnabled(False)
        try:
            self._table.setRowCount(len(presets))
            for r, p in enumerate(presets):
                rec_item = QTableWidgetItem(p.recipe)
                rec_item.setData(Qt.ItemDataRole.UserRole, p)
                self._table.setItem(r, 0, rec_item)
                self._table.setItem(r, 1, QTableWidgetItem(f"{p.x_name} / {p.y_name}"))
                n_item = QTableWidgetItem()
                n_item.setData(Qt.ItemDataRole.DisplayRole, p.n_points)
                n_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, 2, n_item)
                self._table.setItem(r, 3, QTableWidgetItem(format_dt_display(p.created_at)))
                self._table.setItem(r, 4, QTableWidgetItem(format_dt_display(p.last_used)))
        finally:
            self._table.setUpdatesEnabled(True)
            self._table.setSortingEnabled(True)
        # content 기준 natural 폭 계산 + 여유분 분배
        self._table.resizeColumnsToContents()
        self._natural_widths = [
            self._table.columnWidth(i) for i in range(self._table.columnCount())
        ]
        self._distribute_extra_width()

    def _distribute_extra_width(self) -> None:
        """viewport 폭이 natural 합보다 크면 차이를 전 컬럼에 균등 분배. 나머지 픽셀은 마지막 컬럼."""
        if not self._natural_widths:
            return
        cols = len(self._natural_widths)
        vp = self._table.viewport().width()
        total = sum(self._natural_widths)
        if vp > total:
            diff = vp - total
            extra = diff // cols
            remainder = diff - extra * cols  # 정수 division 후 남는 픽셀
            for i in range(cols):
                add = extra + (remainder if i == cols - 1 else 0)
                self._table.setColumnWidth(i, self._natural_widths[i] + add)
        else:
            for i in range(cols):
                self._table.setColumnWidth(i, self._natural_widths[i])

    def resizeEvent(self, event) -> None:  # noqa: D401
        super().resizeEvent(event)
        self._distribute_extra_width()

    def showEvent(self, event) -> None:
        # 최초 show 시점엔 viewport 폭이 초기 default라 init의 distribute가 안 맞음 —
        # show 완료 후 이벤트 루프 한 틱 지연시켜 재계산
        super().showEvent(event)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._distribute_extra_width)

    def _selected_presets(self) -> list[CoordPreset]:
        """선택된 각 행의 preset 반환."""
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

    def _on_recipe(self) -> None:
        presets = self._selected_presets()
        if len(presets) != 1:
            QMessageBox.information(self, "RECIPE 변경", "레코드 한 개를 선택하세요.")
            return
        p = presets[0]
        new_rcp, ok = QInputDialog.getText(self, "RECIPE 변경", "새 RECIPE:", text=p.recipe)
        if ok and new_rcp.strip():
            self._library.set_recipe(p, new_rcp.strip(), save=True)
            self._refresh_table()

    def _on_delete(self) -> None:
        presets = self._selected_presets()
        if not presets:
            return
        r = QMessageBox.question(
            self, "삭제 확인",
            f"선택한 {len(presets)}개 레코드를 삭제하시겠습니까?",
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        for p in presets:
            self._library.delete(p, save=False)
        self._library.save()
        self._refresh_table()

    def gather(self) -> dict[str, Any]:
        mc = int(self._sb_max_count.value())
        md = int(self._sb_max_days.value())
        removed = self._library.enforce_limits(max_count=mc, max_days=md, save=True)
        # 실제 삭제가 있을 때만 refresh — 그래야 사용자의 헤더 정렬 상태가
        # 불필요하게 재적용(stable sort secondary가 populate 순서로 고정)되지 않음
        if removed:
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
        self.resize(760, 740)
        self.setModal(False)
        # QDialog 기본은 Qt.Dialog (parent에 transient로 묶여 항상 위). Window로 완전 대체해야
        # 메인 윈도우 뒤로 갈 수 있음. 최소화·닫기 버튼 포함.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self._main_window: QWidget | None = None  # setMainWindow로 주입

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

        # 버튼 폭 통일 + default/auto-default 해제 (엔터로 dialog 닫힘 방지)
        from widgets.paste_area import HEADER_BUTTON_WIDTH
        for b in (self.btn_save, self.btn_close):
            b.setFixedWidth(HEADER_BUTTON_WIDTH)
            b.setDefault(False)
            b.setAutoDefault(False)

        lay = QVBoxLayout(self)
        lay.addWidget(self._tabs, stretch=1)
        lay.addWidget(btns)

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
        main = self._main_window or self.parent()
        if main is not None and hasattr(main, "refresh_graph"):
            main.refresh_graph()

    def setMainWindow(self, w: QWidget) -> None:
        """parent=None 으로 생성된 경우에도 메인 윈도우 참조 유지."""
        self._main_window = w

    # ── Enter 키로 dialog가 닫히지 않게 (QSpinBox 등 자식 입력란용) ──
    def keyPressEvent(self, event) -> None:
        from PySide6.QtCore import Qt as _Qt
        if event.key() in (_Qt.Key.Key_Return, _Qt.Key.Key_Enter):
            event.accept()
            return
        super().keyPressEvent(event)

    # ── Save / Close ──────────────────────────
    def _on_save(self) -> None:
        """파일 저장만 수행 — 다이얼로그는 닫지 않음. 사용자가 값 더 바꾸고
        추가 저장하거나 Close로 닫을 수 있게."""
        merged = self._collect()
        settings_io.save_settings(merged)
        app = QApplication.instance()
        if app is not None:
            apply_global_style(app, merged)

    def _on_close(self) -> None:
        """메모리 변경은 유지(현재 앱에 이미 반영됨). 파일 저장은 안 함."""
        self.reject()
