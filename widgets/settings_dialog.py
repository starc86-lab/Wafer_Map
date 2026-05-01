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

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core import settings as settings_io
from core.coord_library import CoordLibrary, CoordPreset, format_dt_display
from core.stylesheet import build_stylesheet
from core.themes import BASE_FONT_SIZES, FONTS, FONT_SIZES, HEATMAP_COLORMAPS, THEMES


FONT_SCALE_CHOICES = [
    ("작게 (85%)",  0.85),
    ("보통 (100%)", 1.00),
    ("크게 (115%)", 1.15),
]

# 정렬 기준 — 모든 카드의 라벨·입력 폭·높이를 통일해서 열·행 맞춤
LABEL_WIDTH = 140          # 라벨 고정 폭 (좌측 정렬, 가장 긴 "부드럽게 (smooth)" 수용)
FIELD_WIDTH = 135          # 입력 위젯 고정 너비 (모든 입력란 시작·끝 동일)
FIELD_HEIGHT = 30          # 입력 위젯 고정 높이 (콤보/스핀/체크 행 높이 통일)


class _NoWheelFilter(QObject):
    """Settings 내 사용자 입력 위젯(QSpinBox/QDoubleSpinBox/QComboBox) 의 휠
    이벤트를 차단 — 마우스 휠 실수로 값 변경되는 UX 방지.

    eventFilter 가 True 반환 → 위젯 내부 wheelEvent 호출 skip. ev.ignore() 로
    부모 (스크롤 영역) 에 propagate → 스크롤 기능은 정상 유지.
    """
    def eventFilter(self, obj: QObject, ev) -> bool:
        if ev.type() == QEvent.Type.Wheel:
            ev.ignore()
            return True
        return False


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

    def _add(form, entry):
        label_or_text, widget = entry
        lbl = label_or_text if isinstance(label_or_text, QLabel) else _label(label_or_text)
        form.addRow(lbl, widget)

    for entry in items[:half]:
        _add(left_form, entry)
    for entry in items[half:]:
        _add(right_form, entry)

    left_w = QWidget(); left_w.setLayout(left_form)
    right_w = QWidget(); right_w.setLayout(right_form)
    hbox.addWidget(left_w, stretch=1)
    hbox.addWidget(right_w, stretch=1)


def apply_global_style(app: QApplication, settings: dict[str, Any]) -> None:
    theme_name = settings.get("theme", "Light")
    font_name = settings.get("font", "Segoe UI")
    scale = float(settings.get("font_scale", 1.0) or 1.0)

    theme = THEMES.get(theme_name, THEMES["Light"])

    # BASE_FONT_SIZES 에서 scale 적용해 FONT_SIZES 영구 갱신 — 이후 FONT_SIZES 를
    # 읽는 모든 코드 (차트 제목, 컬러바, 1D 축 폰트 등) 가 현재 scale 반영된 값
    # 을 얻음. 이전엔 QSS 빌드 직후 원복해 연동 안 됐음.
    scaled = {k: max(8, int(round(v * scale))) for k, v in BASE_FONT_SIZES.items()}
    FONT_SIZES.clear()
    FONT_SIZES.update(scaled)
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
    """테마/글꼴/크기 — 콤보 변경 즉시 `changed` 시그널 emit (다이얼로그에서 즉시 Apply).

    table_style 만 별도 `table_style_changed(str)` — graph_changed 흐름과 분리해
    cell.swap_summary_style 만 호출 (RBF / GL 재렌더 회피, 사용자 정책 2026-04-30).
    """

    changed = Signal()
    table_style_changed = Signal(str)

    def __init__(self, settings: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__("UI 설정", parent)

        # 테마 / 글꼴 콤보 — DEFAULT_SETTINGS 의 값에 ` (기본)` 접미 표시.
        # itemData 는 bare name 유지 (settings.json 저장값 안전).
        from core.themes import DEFAULT_SETTINGS as _DEF
        default_theme = _DEF.get("theme", "Light")
        default_font = _DEF.get("font", "Segoe UI")

        self.cb_theme = _limit_width(QComboBox())
        for name in sorted(THEMES.keys()):
            label = f"{name} (기본)" if name == default_theme else name
            self.cb_theme.addItem(label, name)
        idx = self.cb_theme.findData(settings.get("theme", default_theme))
        if idx >= 0:
            self.cb_theme.setCurrentIndex(idx)

        self.cb_font = _limit_width(QComboBox())
        for name in FONTS:
            label = f"{name} (기본)" if name == default_font else name
            self.cb_font.addItem(label, name)
        idx = self.cb_font.findData(settings.get("font", default_font))
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

        # Summary 표 스타일 — 카탈로그 lazy enumerate. STYLES dict 등록된 항목만
        # 노출 (phase 별 점진 추가, 사용자 정책 2026-04-30).
        from widgets.summary import available_styles
        self.cb_table_style = _limit_width(QComboBox())
        for key, display in available_styles():
            self.cb_table_style.addItem(display, key)
        cur_style = settings.get("table", {}).get("style", "ppt_basic")
        idx = self.cb_table_style.findData(cur_style)
        if idx >= 0:
            self.cb_table_style.setCurrentIndex(idx)

        # UI 모드 (해상도 scale) — 사용자 정책 2026-05-01. 변경 시 재시작 필요.
        from core.themes import UI_MODES, UI_MODE_DISPLAY
        self.cb_ui_mode = _limit_width(QComboBox())
        for key in UI_MODES:
            self.cb_ui_mode.addItem(UI_MODE_DISPLAY.get(key, key), key)
        cur_mode = settings.get("ui_mode", "auto")
        idx = self.cb_ui_mode.findData(cur_mode)
        if idx >= 0:
            self.cb_ui_mode.setCurrentIndex(idx)

        # 좌: [테마, 윈도우 크기 저장, 표 스타일], 우: [글꼴, 글자 크기, UI 모드]
        _populate_two_columns(self, [
            ("테마", self.cb_theme),
            ("윈도우 크기 저장", self.chk_save_window),
            ("표 스타일", self.cb_table_style),
            ("글꼴", self.cb_font),
            ("글자 크기", self.cb_scale),
            ("UI 모드 (재시작)", self.cb_ui_mode),
        ])

        # 즉시 적용
        self.cb_theme.currentIndexChanged.connect(self.changed)
        self.cb_font.currentIndexChanged.connect(self.changed)
        self.cb_scale.currentIndexChanged.connect(self.changed)
        self.chk_save_window.toggled.connect(self.changed)
        # table_style 은 별도 시그널 — RBF/GL 재렌더 없이 _summary 위젯만 swap
        self.cb_table_style.currentIndexChanged.connect(
            lambda: self.table_style_changed.emit(self.cb_table_style.currentData())
        )
        # ui_mode 도 changed (cache 갱신만 — 재시작 후 적용, 사용자 정책 2026-05-01)
        self.cb_ui_mode.currentIndexChanged.connect(self.changed)

    def gather(self) -> dict[str, Any]:
        return {
            "theme": self.cb_theme.currentData(),
            "font": self.cb_font.currentData(),
            "font_scale": float(self.cb_scale.currentData()),
            "window_save_enabled": self.chk_save_window.isChecked(),
            "table": {"style": self.cb_table_style.currentData()},
            "ui_mode": self.cb_ui_mode.currentData(),
        }

    def reload(self, settings: dict[str, Any]) -> None:
        """위젯 값을 settings로 갱신. 마지막에 changed 한 번만 emit."""
        widgets = (self.cb_theme, self.cb_font, self.cb_scale, self.chk_save_window)
        for w in widgets:
            w.blockSignals(True)
        try:
            idx = self.cb_theme.findData(settings.get("theme", "Light"))
            if idx >= 0:
                self.cb_theme.setCurrentIndex(idx)
            idx = self.cb_font.findData(settings.get("font", "Segoe UI"))
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

# Radial 1D 보간 알고리즘 콤보 옵션. core.interp.RADIAL_METHODS 와 **반드시 동기 유지**.
# core.interp 가 scipy.interpolate / signal 전체를 끌어와 무거우므로 (~1초)
# 단순 문자열 리스트는 settings_dialog 에 inline 으로 둬서 import 회피.
RADIAL_METHODS = [
    "Univariate Spline",
    "Cubic Spline",
    "PCHIP",
    "Akima",
    "Savitzky-Golay",
    "LOWESS",
    "Polynomial",
]


class ChartCommonGroup(QGroupBox):
    """MAP 공통 설정 — 2D/3D 양쪽에 적용. 변경 즉시 `changed` emit."""

    changed = Signal()

    def __init__(self, cfg: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__("MAP 공통 설정", parent)

        # UI 제거된 개발자 고정값 키들(show_circle/show_notch/notch_depth_mm/
        # boundary_r_mm/show_scale_bar/radial_line_width_mm 등)을 gather() 때 다시
        # 돌려주기 위한 원본 snapshot. reload() 시에도 갱신.
        self._cfg_snapshot: dict[str, Any] = dict(cfg)

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

        # Map Size — 카메라 거리 (작을수록 확대). 2D top view / 3D 공통 적용.
        # 사용자 관점에서 "Map 크기" 가 직관적이라 라벨을 이렇게 표기.
        self.sp_cam_dist = _limit_width(QSpinBox())
        self.sp_cam_dist.setRange(400, 800)
        self.sp_cam_dist.setSingleStep(10)
        self.sp_cam_dist.setValue(int(cfg.get("camera_distance", 620)))

        # radial mesh 밀도 (2D·3D 공통)
        self.sp_rings = _limit_width(QSpinBox())
        self.sp_rings.setRange(5, 60)
        self.sp_rings.setSingleStep(5)
        self.sp_rings.setValue(int(cfg.get("radial_rings", 20)))

        self.sp_rseg = _limit_width(QSpinBox())
        self.sp_rseg.setRange(60, 720)
        self.sp_rseg.setSingleStep(60)
        self.sp_rseg.setValue(int(cfg.get("radial_seg", 180)))

        # 공통 카드: 10 items, half=5. 좌: 5 / 우: 5
        _populate_two_columns(self, [
            ("컬러맵", self.cb_cmap),
            ("보간 방법", self.cb_interp),
            ("그래프 크기", self.cb_chart_size),
            ("소수점 자릿수", self.cb_decimals),
            ("Map Size", self.sp_cam_dist),
            ("Radial: rings", self.sp_rings),
            ("Radial: seg", self.sp_rseg),
            ("Edge cut", self.sb_edge_cut),
        ])

        self.cb_cmap.currentIndexChanged.connect(self.changed)
        self.cb_interp.currentIndexChanged.connect(self.changed)
        self.sp_rings.valueChanged.connect(self.changed)
        self.sp_rseg.valueChanged.connect(self.changed)
        self.cb_chart_size.currentIndexChanged.connect(self.changed)
        self.cb_decimals.currentIndexChanged.connect(self.changed)
        self.sb_edge_cut.valueChanged.connect(self.changed)
        self.sp_cam_dist.valueChanged.connect(self.changed)

    def gather(self) -> dict[str, Any]:
        w, h = self.cb_chart_size.currentData()
        # UI 미관리 키(show_circle/notch/boundary_r_mm/...) 는 snapshot 에서 유지.
        result = dict(self._cfg_snapshot)
        result.update({
            "colormap": self.cb_cmap.currentText(),
            "interp_method": self.cb_interp.currentText(),
            "radial_rings": int(self.sp_rings.value()),
            "radial_seg": int(self.sp_rseg.value()),
            "chart_width": int(w),
            "chart_height": int(h),
            "decimals": int(self.cb_decimals.currentData()),
            "edge_cut_mm": float(self.sb_edge_cut.value()),
            "camera_distance": int(self.sp_cam_dist.value()),
        })
        return result

    def reload(self, cfg: dict[str, Any]) -> None:
        self._cfg_snapshot = dict(cfg)
        widgets = (self.cb_cmap, self.cb_interp,
                   self.sp_rings, self.sp_rseg,
                   self.cb_chart_size, self.cb_decimals,
                   self.sb_edge_cut, self.sp_cam_dist)
        for w in widgets:
            w.blockSignals(True)
        try:
            idx = self.cb_cmap.findText(cfg.get("colormap", "Turbo"))
            if idx >= 0: self.cb_cmap.setCurrentIndex(idx)
            idx = self.cb_interp.findText(cfg.get("interp_method", "RBF-ThinPlate"))
            if idx >= 0: self.cb_interp.setCurrentIndex(idx)
            self.sp_rings.setValue(int(cfg.get("radial_rings", 20)))
            self.sp_rseg.setValue(int(cfg.get("radial_seg", 180)))
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
            self.sp_cam_dist.setValue(int(cfg.get("camera_distance", 620)))
        finally:
            for w in widgets:
                w.blockSignals(False)
        self.changed.emit()


class Chart1DRadialGroup(QGroupBox):
    """1D Radial Graph 설정 — 표시 토글 + 보간 알고리즘 선택 + 튜닝 파라.

    레이아웃 (사용자 요청):
    1행: [1D Graph 표시 체크] | [Radial 방법 콤보]
    2~: 각 방법별 파라 (좌/우 분배) — 선택 method 에 따라 활성/비활성.
    """

    changed = Signal()

    def __init__(self, cfg: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__("1D Graph, Radial Symmetry 설정", parent)
        # 주의: 이 카드는 **chart_common 의 1D 관련 키만** 소유. snapshot 을
        # chart_common 전체로 보관하면 DesignTab.gather merge 시 공통 카드의 최신
        # UI 값을 stale snapshot 으로 덮어쓰는 버그 발생 → snapshot 없음.

        self.chk_1d_radial = _fix_width(QCheckBox())
        self.chk_1d_radial.setChecked(bool(cfg.get("show_1d_radial", False)))

        self.cb_radial_method = _limit_width(QComboBox())
        self.cb_radial_method.addItems(RADIAL_METHODS)
        idx = self.cb_radial_method.findText(cfg.get("radial_method", "Univariate Spline"))
        self.cb_radial_method.setCurrentIndex(idx if idx >= 0 else 0)

        self.sp_radial_smooth = _limit_width(QDoubleSpinBox())
        self.sp_radial_smooth.setRange(0.0, 15.0)
        self.sp_radial_smooth.setSingleStep(0.1)
        self.sp_radial_smooth.setDecimals(1)
        self.sp_radial_smooth.setValue(float(cfg.get("radial_smoothing_factor", 5.0)))

        self.sp_savgol_win = _limit_width(QSpinBox())
        self.sp_savgol_win.setRange(3, 101)
        self.sp_savgol_win.setSingleStep(2)
        self.sp_savgol_win.setValue(int(cfg.get("savgol_window", 11)))

        self.sp_savgol_poly = _limit_width(QSpinBox())
        self.sp_savgol_poly.setRange(1, 5)
        self.sp_savgol_poly.setSingleStep(1)
        self.sp_savgol_poly.setValue(int(cfg.get("savgol_polyorder", 3)))

        self.sp_lowess_frac = _limit_width(QDoubleSpinBox())
        self.sp_lowess_frac.setRange(0.05, 1.0)
        self.sp_lowess_frac.setSingleStep(0.05)
        self.sp_lowess_frac.setDecimals(2)
        self.sp_lowess_frac.setValue(float(cfg.get("lowess_frac", 0.3)))

        self.sp_polyfit_deg = _limit_width(QSpinBox())
        self.sp_polyfit_deg.setRange(1, 6)
        self.sp_polyfit_deg.setSingleStep(1)
        self.sp_polyfit_deg.setValue(int(cfg.get("polyfit_degree", 3)))

        # Moving Avg Window 전처리 — 각 측정점 중심 ±w/2 mm 내 평균으로 v 치환.
        # 0 = 비활성, 1~25 mm. exact 보간 3종 (Cubic/PCHIP/Akima) + Univariate
        # Spline 에서만 활성. SavGol/LOWESS 는 내부가 이미 sliding 이라 중복,
        # Polynomial 은 전역 fit 이라 효과 미미 → 비활성 처리.
        self.sp_bin_size = _limit_width(QSpinBox())
        self.sp_bin_size.setRange(0, 25)
        self.sp_bin_size.setSingleStep(1)
        self.sp_bin_size.setSuffix(" mm")
        self.sp_bin_size.setValue(int(cfg.get("radial_bin_size_mm", 0)))

        self.lbl_bin_size = _label("Moving Avg Window")

        # 라벨 인스턴스 — setEnabled(False) 시 QSS :disabled 규칙으로 회색화
        self.lbl_smooth = _label("Univariate Smoothing")
        self.lbl_savgol_win = _label("SavGol Window")
        self.lbl_savgol_poly = _label("SavGol Polyorder")
        self.lbl_lowess_frac = _label("LOWESS Frac")
        self.lbl_polyfit = _label("Polyfit Degree")

        # 8 items, half=4 → 좌 4 / 우 4.
        # 좌: 1D Graph 표시 · Univariate Smoothing · SavGol Window · SavGol Polyorder
        # 우: Fitting 방법    · Moving Avg Window   · LOWESS Frac    · Polyfit Degree
        _populate_two_columns(self, [
            ("1D Graph 표시", self.chk_1d_radial),
            (self.lbl_smooth, self.sp_radial_smooth),
            (self.lbl_savgol_win, self.sp_savgol_win),
            (self.lbl_savgol_poly, self.sp_savgol_poly),
            ("Fitting 방법", self.cb_radial_method),
            (self.lbl_bin_size, self.sp_bin_size),
            (self.lbl_lowess_frac, self.sp_lowess_frac),
            (self.lbl_polyfit, self.sp_polyfit_deg),
        ])

        self._sync_param_enable()
        self.cb_radial_method.currentTextChanged.connect(self._sync_param_enable)

        self.chk_1d_radial.toggled.connect(self.changed)
        self.cb_radial_method.currentIndexChanged.connect(self.changed)
        self.sp_radial_smooth.valueChanged.connect(self.changed)
        self.sp_savgol_win.valueChanged.connect(self.changed)
        self.sp_savgol_poly.valueChanged.connect(self.changed)
        self.sp_lowess_frac.valueChanged.connect(self.changed)
        self.sp_polyfit_deg.valueChanged.connect(self.changed)
        self.sp_bin_size.valueChanged.connect(self.changed)

    def _sync_param_enable(self) -> None:
        """Fitting 방법 선택에 따라 관련 파라만 활성. 나머지는 라벨·위젯 회색.

        Moving Avg Window 는 모든 method 에서 항상 활성 — 사용자가 0 입력하면
        비활성이라 method-aware 로직 불필요 (사용자 판단에 맡김).
        """
        m = self.cb_radial_method.currentText()
        mapping = {
            "Univariate Spline": {self.lbl_smooth, self.sp_radial_smooth},
            "Savitzky-Golay":    {self.lbl_savgol_win, self.sp_savgol_win,
                                  self.lbl_savgol_poly, self.sp_savgol_poly},
            "LOWESS":            {self.lbl_lowess_frac, self.sp_lowess_frac},
            "Polynomial":        {self.lbl_polyfit, self.sp_polyfit_deg},
        }
        active = mapping.get(m, set())
        # method 별 disable 대상 (Moving Avg Window 는 제외 — 항상 활성)
        all_items = (
            self.lbl_smooth, self.sp_radial_smooth,
            self.lbl_savgol_win, self.sp_savgol_win,
            self.lbl_savgol_poly, self.sp_savgol_poly,
            self.lbl_lowess_frac, self.sp_lowess_frac,
            self.lbl_polyfit, self.sp_polyfit_deg,
        )
        for w in all_items:
            w.setEnabled(w in active)

    def gather(self) -> dict[str, Any]:
        # 1D 관련 키만 반환. DesignTab merge 시 ChartCommonGroup 의 공통 키를
        # stale 값으로 덮어쓰지 않도록 snapshot 사용 금지.
        return {
            "show_1d_radial": self.chk_1d_radial.isChecked(),
            "radial_method": self.cb_radial_method.currentText(),
            "radial_smoothing_factor": float(self.sp_radial_smooth.value()),
            "savgol_window": int(self.sp_savgol_win.value()),
            "savgol_polyorder": int(self.sp_savgol_poly.value()),
            "lowess_frac": float(self.sp_lowess_frac.value()),
            "polyfit_degree": int(self.sp_polyfit_deg.value()),
            "radial_bin_size_mm": int(self.sp_bin_size.value()),
        }

    def reload(self, cfg: dict[str, Any]) -> None:
        widgets = (self.chk_1d_radial, self.cb_radial_method,
                   self.sp_radial_smooth, self.sp_savgol_win, self.sp_savgol_poly,
                   self.sp_lowess_frac, self.sp_polyfit_deg, self.sp_bin_size)
        for w in widgets:
            w.blockSignals(True)
        try:
            self.chk_1d_radial.setChecked(bool(cfg.get("show_1d_radial", False)))
            idx = self.cb_radial_method.findText(cfg.get("radial_method", "Univariate Spline"))
            if idx >= 0: self.cb_radial_method.setCurrentIndex(idx)
            self.sp_radial_smooth.setValue(float(cfg.get("radial_smoothing_factor", 5.0)))
            self.sp_savgol_win.setValue(int(cfg.get("savgol_window", 11)))
            self.sp_savgol_poly.setValue(int(cfg.get("savgol_polyorder", 3)))
            self.sp_lowess_frac.setValue(float(cfg.get("lowess_frac", 0.3)))
            self.sp_polyfit_deg.setValue(int(cfg.get("polyfit_degree", 3)))
            self.sp_bin_size.setValue(int(cfg.get("radial_bin_size_mm", 0)))
        finally:
            self._sync_param_enable()
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

        # 라벨 폰트 크기 — 작게 / 보통 / 크게
        self.cb_label_scale = _limit_width(QComboBox())
        for label, val in (("작게 (85%)", 0.85), ("보통 (100%)", 1.00), ("크게 (115%)", 1.15)):
            self.cb_label_scale.addItem(label, val)
        cur_scale = float(cfg.get("label_font_scale", 0.85))
        best_i, best_d = 0, float("inf")
        for i in range(self.cb_label_scale.count()):
            d = abs(cur_scale - float(self.cb_label_scale.itemData(i)))
            if d < best_d:
                best_d, best_i = d, i
        self.cb_label_scale.setCurrentIndex(best_i)

        # 좌: 체크(측정 좌표 표시·라벨 표시) / 우: 콤보(점 크기·라벨 크기)
        _populate_two_columns(self, [
            ("측정 좌표 표시", self.chk_points),
            ("라벨 표시", self.chk_value_labels),
            ("점 크기", self.cb_point),
            ("라벨 크기", self.cb_label_scale),
        ])

        self.chk_points.toggled.connect(self.changed)
        self.cb_point.currentIndexChanged.connect(self.changed)
        self.chk_value_labels.toggled.connect(self.changed)
        self.cb_label_scale.currentIndexChanged.connect(self.changed)

    def gather(self) -> dict[str, Any]:
        return {
            "show_points": self.chk_points.isChecked(),
            "point_size": int(self.cb_point.currentData()),
            "show_value_labels": self.chk_value_labels.isChecked(),
            "label_font_scale": float(self.cb_label_scale.currentData()),
        }

    def reload(self, cfg: dict[str, Any]) -> None:
        widgets = (self.chk_points, self.cb_point, self.chk_value_labels,
                   self.cb_label_scale)
        for w in widgets:
            w.blockSignals(True)
        try:
            self.chk_points.setChecked(bool(cfg.get("show_points", True)))
            idx = self.cb_point.findData(int(cfg.get("point_size", 4)))
            if idx >= 0: self.cb_point.setCurrentIndex(idx)
            self.chk_value_labels.setChecked(bool(cfg.get("show_value_labels", False)))
            target = float(cfg.get("label_font_scale", 0.85))
            best_i, best_d = 0, float("inf")
            for i in range(self.cb_label_scale.count()):
                d = abs(target - float(self.cb_label_scale.itemData(i)))
                if d < best_d:
                    best_d, best_i = d, i
            self.cb_label_scale.setCurrentIndex(best_i)
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
        self.sp_zexag.setRange(0.1, 3.0)
        self.sp_zexag.setSingleStep(0.1)
        self.sp_zexag.setDecimals(1)
        self.sp_zexag.setSuffix("×")
        cur_z = cfg.get("z_exaggeration", 1.0)
        self.sp_zexag.setValue(1.0 if cur_z is None else float(cur_z))

        self.chk_grid = _fix_width(QCheckBox())
        self.chk_grid.setChecked(bool(cfg.get("show_grid", True)))

        # View angle: Elevation — 수직 시점각 (-90~90°). 0=수평, 90=정면위.
        self.sp_elevation = _limit_width(QDoubleSpinBox())
        self.sp_elevation.setRange(-90.0, 90.0)
        self.sp_elevation.setSingleStep(1.0)
        self.sp_elevation.setDecimals(0)
        self.sp_elevation.setSuffix("°")
        self.sp_elevation.setValue(float(cfg.get("elevation", 28)))

        # View angle: Azimuth — 수평 회전 (-180~180°). -135=notch 4~5시 방향.
        self.sp_azimuth = _limit_width(QDoubleSpinBox())
        self.sp_azimuth.setRange(-180.0, 180.0)
        self.sp_azimuth.setSingleStep(1.0)
        self.sp_azimuth.setDecimals(0)
        self.sp_azimuth.setSuffix("°")
        self.sp_azimuth.setValue(float(cfg.get("azimuth", -135)))

        # 좌: 스핀(Elevation·Azimuth·Z-Height) / 우: 체크(부드럽게·그리드)
        # half=3 → 좌 3개, 우 2개.
        _populate_two_columns(self, [
            ("View angle: Elevation", self.sp_elevation),
            ("View angle: Azimuth", self.sp_azimuth),
            ("Z-Height", self.sp_zexag),
            ("부드럽게 (smooth)", self.chk_smooth),
            ("바닥 그리드", self.chk_grid),
        ])

        self.chk_smooth.toggled.connect(self.changed)
        self.sp_zexag.valueChanged.connect(self.changed)
        self.chk_grid.toggled.connect(self.changed)
        self.sp_elevation.valueChanged.connect(self.changed)
        self.sp_azimuth.valueChanged.connect(self.changed)

    def gather(self) -> dict[str, Any]:
        return {
            "smooth": self.chk_smooth.isChecked(),
            "z_exaggeration": float(self.sp_zexag.value()),
            "show_grid": self.chk_grid.isChecked(),
            "elevation": float(self.sp_elevation.value()),
            "azimuth": float(self.sp_azimuth.value()),
        }

    def reload(self, cfg: dict[str, Any]) -> None:
        widgets = (self.chk_smooth, self.sp_zexag, self.chk_grid,
                   self.sp_elevation, self.sp_azimuth)
        for w in widgets:
            w.blockSignals(True)
        try:
            self.chk_smooth.setChecked(bool(cfg.get("smooth", True)))
            cur_z = cfg.get("z_exaggeration", 1.0)
            self.sp_zexag.setValue(1.0 if cur_z is None else float(cur_z))
            self.chk_grid.setChecked(bool(cfg.get("show_grid", True)))
            self.sp_elevation.setValue(float(cfg.get("elevation", 28)))
            self.sp_azimuth.setValue(float(cfg.get("azimuth", -135)))
        finally:
            for w in widgets:
                w.blockSignals(False)
        self.changed.emit()


# ────────────────────────────────────────────────────────
# 디자인 설정 탭 (UI / 2D / 3D 세 카드를 flat 세로 스택)
# ────────────────────────────────────────────────────────
class DesignTab(QWidget):
    """UI · 2D · 3D 세 카드 + 하단 좌측 Default 버튼. 카드 changed 시그널 통합 forward."""

    ui_changed = Signal()              # UI 설정(테마·글꼴·크기) 변경
    graph_changed = Signal()           # 2D / 3D 설정 변경
    table_style_changed = Signal(str)  # 표 스타일만 (cell.swap_summary_style 직결)

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
        # 1D Radial Graph 설정 — chart_common 과 같은 dict 에 저장. 카드만 분리.
        self._card_1d = Chart1DRadialGroup(settings.get("chart_common", {}))

        cards.addWidget(self._ui_card)
        cards.addWidget(self._card_common)
        cards.addWidget(self._card_2d)
        cards.addWidget(self._card_3d)
        cards.addWidget(self._card_1d)
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
        self._ui_card.table_style_changed.connect(self.table_style_changed)
        self._card_common.changed.connect(self.graph_changed)
        self._card_2d.changed.connect(self.graph_changed)
        self._card_3d.changed.connect(self.graph_changed)
        self._card_1d.changed.connect(self.graph_changed)

    def gather(self) -> dict[str, Any]:
        # chart_common 은 두 카드(_card_common + _card_1d) 의 dict 를 merge.
        # 같은 키는 _card_1d 가 우선 (1D 전용 파라들).
        common_merged = {**self._card_common.gather(), **self._card_1d.gather()}
        return {
            **self._ui_card.gather(),
            "chart_common": common_merged,
            "chart_2d": self._card_2d.gather(),
            "chart_3d": self._card_3d.gather(),
        }

    def reset_to_defaults(self) -> None:
        """그래프 카드만 DEFAULT_SETTINGS 값으로 되돌리기.

        UI 설정 카드 (테마·글꼴·윈도우 크기 저장·글자 크기) 는 제외 — 디자인 취향
        영역이라 사용자 마지막 값 유지 (사용자 정책 2026-04-29). UI 초기값은
        settings.json 누락 시에만 적용됨 (load_settings 의 DEFAULT_SETTINGS merge).
        """
        from core.themes import DEFAULT_SETTINGS
        self._card_common.reload(DEFAULT_SETTINGS.get("chart_common", {}))
        self._card_2d.reload(DEFAULT_SETTINGS.get("chart_2d", {}))
        self._card_3d.reload(DEFAULT_SETTINGS.get("chart_3d", {}))
        self._card_1d.reload(DEFAULT_SETTINGS.get("chart_common", {}))


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

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["#", "RECIPE", "X / Y", "Point", "최초 저장", "마지막 사용"],
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
        self.btn_edit = QPushButton("좌표 수정")
        self.btn_preview = QPushButton("미리보기")
        self.btn_delete = QPushButton("삭제")
        self.btn_delete.setProperty("class", "danger")
        for b in (self.btn_add, self.btn_edit, self.btn_preview, self.btn_delete):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_preview.clicked.connect(self._on_preview)
        self.btn_delete.clicked.connect(self._on_delete)
        # 행 더블클릭 → 좌표 수정 (RECIPE + 좌표값 통합 편집, 사용자 정책 2026-04-30)
        self._table.doubleClicked.connect(self._on_row_dbl_click)
        # 우클릭 → 컨텍스트 메뉴 (좌표 미리보기)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)

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
        """레코드 개별 행 표시 — (RECIPE, X/Y) 조합이 키라 같은 RECIPE 여러 행 가능.

        # 컬럼 = 라이브러리 entry id (영구 고유 번호, 사용자 정책 2026-04-30).
        기본 정렬은 id 오름차순 — 헤더 클릭 시 다른 컬럼 기준 정렬 가능.
        """
        presets = sorted(self._library.presets, key=lambda p: p.id)
        self._count_label.setText(f"저장된 레코드: {len(presets)}개")
        self._table.setSortingEnabled(False)
        self._table.setUpdatesEnabled(False)
        try:
            self._table.setRowCount(len(presets))
            for r, p in enumerate(presets):
                # # (id) — DisplayRole 정수로 헤더 클릭 시 숫자 정렬, UserRole 에 preset
                id_item = QTableWidgetItem()
                id_item.setData(Qt.ItemDataRole.DisplayRole, p.id)
                id_item.setData(Qt.ItemDataRole.UserRole, p)
                id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, 0, id_item)
                self._table.setItem(r, 1, QTableWidgetItem(p.recipe))
                self._table.setItem(r, 2, QTableWidgetItem(f"{p.x_name} / {p.y_name}"))
                n_item = QTableWidgetItem()
                n_item.setData(Qt.ItemDataRole.DisplayRole, p.n_points)
                n_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, 3, n_item)
                self._table.setItem(r, 4, QTableWidgetItem(format_dt_display(p.created_at)))
                self._table.setItem(r, 5, QTableWidgetItem(format_dt_display(p.last_used)))
        finally:
            self._table.setUpdatesEnabled(True)
            self._table.setSortingEnabled(True)
        # 기본 정렬: id (column 0) 오름차순. setSortingEnabled(True) 가 이전
        # sort indicator state 를 끌어와 내림차순으로 보이는 회귀 fix.
        self._table.sortItems(0, Qt.SortOrder.AscendingOrder)
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

    def _on_row_dbl_click(self, index) -> None:
        """행 더블클릭 → 좌표 수정 (RECIPE + 좌표값 통합 편집, 사용자 정책 2026-04-30).

        미리보기는 우클릭 메뉴 또는 '미리보기' 버튼으로.
        """
        row = index.row() if index is not None else -1
        if row < 0:
            return
        # 단일 선택 보장 — 더블클릭한 행만 선택
        self._table.selectRow(row)
        self._on_edit()

    def _on_table_context_menu(self, pos) -> None:
        """우클릭 → 컨텍스트 메뉴 (좌표 미리보기)."""
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu
        idx = self._table.indexAt(pos)
        if idx.row() < 0:
            return
        # 우클릭 시 해당 행 자동 선택 (기존 다중 선택 유지)
        if not self._table.item(idx.row(), 0).isSelected():
            self._table.selectRow(idx.row())
        menu = QMenu(self._table)
        act_preview = QAction("좌표 미리보기", menu)
        act_preview.triggered.connect(self._on_preview)
        menu.addAction(act_preview)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _on_preview(self) -> None:
        """선택된 첫 행의 좌표를 별도 다이얼로그에 표시."""
        presets = self._selected_presets()
        if not presets:
            return
        p = presets[0]
        from widgets.coord_preview_dialog import CoordPreviewDialog
        dlg = CoordPreviewDialog(
            p.x_mm, p.y_mm,
            title=f"{p.recipe} · {p.x_name}/{p.y_name} · {p.n_points}pt",
            parent=self,
        )
        dlg.exec()

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

    def _on_edit(self) -> None:
        """좌표 수정 — RECIPE + 좌표값 통합 편집 다이얼로그 (사용자 정책 2026-04-30).

        이전 _on_recipe (RECIPE 만 QInputDialog) 폐기. PresetEditDialog 가
        미리보기 형태 (좌: 맵 / 우: 표) 로 RECIPE LineEdit + 표 cell 직접 편집.
        """
        presets = self._selected_presets()
        if len(presets) != 1:
            QMessageBox.information(self, "좌표 수정", "레코드 한 개를 선택하세요.")
            return
        p = presets[0]
        from widgets.preset_edit_dialog import PresetEditDialog
        dlg = PresetEditDialog(
            recipe=p.recipe,
            x_mm=p.x_mm, y_mm=p.y_mm,
            x_name=p.x_name, y_name=p.y_name,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        result = dlg.result_values()
        if result is None:
            return
        new_recipe, new_x, new_y = result
        if new_recipe != p.recipe:
            self._library.set_recipe(p, new_recipe, save=False)
        # 좌표값 변경 — 길이 같고 값만 바뀌면 자체 갱신, n_points 도 함께 set.
        if (len(new_x) != len(p.x_mm)
                or any(float(a) != float(b) for a, b in zip(new_x, p.x_mm))
                or any(float(a) != float(b) for a, b in zip(new_y, p.y_mm))):
            self._library.set_coords(p, list(new_x), list(new_y), save=False)
        self._library.save()
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
        # 5개 카드 (UI / Chart Common / 2D / 3D / 1D Radial) 모두 스크롤 없이 보이는 높이
        self.resize(760, 940)
        self.setModal(False)
        # FBO 캡처 경로 도입으로 Settings 창이 Copy Graph 에 포함되던 이슈 해결됨.
        # QDialog 기본 windowFlags (Qt.Dialog + transient owner 관계) 사용.
        self._main_window: QWidget | None = None  # setMainWindow 호환성용 (현재 parent() 사용)

        settings = settings_io.load_settings()
        self._initial = dict(settings)

        self._tabs = QTabWidget()
        self._design = DesignTab(settings)
        self._coords = CoordLibraryTab(settings)
        self._tabs.addTab(self._design, "디자인 설정")
        self._tabs.addTab(self._coords, "좌표 라이브러리")

        # 디자인 변경 시 즉시 반영
        self._design.ui_changed.connect(self._apply_ui_runtime)
        # UI 변경 (font_scale 등) 도 cell 내부 폰트 (title/colorbar/1D axis) 에 반영
        # 되도록 graph refresh 도 같이 트리거.
        self._design.ui_changed.connect(self._apply_graph_runtime)
        self._design.graph_changed.connect(self._apply_graph_runtime)
        # 표 스타일만 별도 — RBF/GL 재렌더 회피, _summary 위젯만 swap
        self._design.table_style_changed.connect(self._apply_table_style)

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

        # 모든 입력 위젯(QSpinBox/QDoubleSpinBox/QComboBox/QCheckBox) 의 마우스
        # 휠 차단 — scrollarea 안에서 스크롤 중 커서가 위젯 위에 올라가도 값이
        # 바뀌지 않음. QCheckBox 는 기본적으로 휠 이벤트 소비 안 하지만 명시적
        # 통일을 위해 포함.
        self._no_wheel_filter = _NoWheelFilter(self)
        for w in self.findChildren(QWidget):
            if isinstance(w, (QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox)):
                w.installEventFilter(self._no_wheel_filter)

    # ── 현재 다이얼로그의 설정 전체를 모아 반환 ──
    def _collect(self) -> dict[str, Any]:
        merged = dict(self._initial)
        merged.update(self._design.gather())
        merged.update(self._coords.gather())
        # 세션 휘발 키들 (다이얼로그가 소유하지 않음) — stale _initial 로 덮어쓰는
        # 사고 방지를 위해 현재 runtime cache 값으로 강제 동기.
        # r_symmetry_mode: 메인 체크박스만 소유 — non-modal dialog 열어둔 채
        # 메인에서 토글하면 _initial 과 cache 괴리 → 다이얼로그에서 아무 값만
        # 바꿔도 _collect 가 stale _initial 값으로 덮어써 상태가 튐.
        cur = settings_io.load_settings()
        merged["r_symmetry_mode"] = bool(cur.get("r_symmetry_mode", False))
        return merged

    # ── 즉시 반영 핸들러 ────────────────────────
    def _apply_ui_runtime(self) -> None:
        """UI 설정 변경 → 런타임 캐시 + 앱 스타일시트 재빌드.

        font_scale 변경 시 — apply_fonts_all() 로 모든 cell 의 _summary stylesheet
        만 재 set (가벼움). 이전 set_table_style swap 은 _summary 위젯 재 init
        이라 무거웠음 (사용자 정책 2026-05-01, scope 2 fix #2).
        """
        import os, time
        bench = bool(os.environ.get("WAFERMAP_BENCH"))
        t0 = time.perf_counter() if bench else 0.0

        merged = self._collect()
        if bench:
            t1 = time.perf_counter()
        settings_io.set_runtime(merged)
        app = QApplication.instance()
        if app is not None:
            apply_global_style(app, merged)
        if bench:
            t2 = time.perf_counter()
        # 가벼운 폰트 갱신 — swap 비용 회피
        main = self._main_window or self.parent()
        if main is not None:
            rp = getattr(main, "_result_panel", None)
            if rp is not None and hasattr(rp, "apply_fonts_all"):
                rp.apply_fonts_all()
        if bench:
            t3 = time.perf_counter()
            import sys
            sys.stderr.write(
                f"[bench ui] collect={1000*(t1-t0):.1f}ms  "
                f"apply_global_style={1000*(t2-t1):.1f}ms  "
                f"apply_fonts_all={1000*(t3-t2):.1f}ms  "
                f"total={1000*(t3-t0):.1f}ms\n"
            )

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

    def _apply_table_style(self, style: str) -> None:
        """표 스타일만 변경 → 모든 cell 의 _summary 위젯만 swap.
        RBF / GL 캐시 유지 (사용자 정책 2026-04-30, table style 카탈로그).
        """
        merged = self._collect()
        settings_io.set_runtime(merged)
        main = self._main_window or self.parent()
        if main is None:
            return
        rp = getattr(main, "_result_panel", None)
        if rp is not None and hasattr(rp, "set_table_style"):
            rp.set_table_style(style)

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
