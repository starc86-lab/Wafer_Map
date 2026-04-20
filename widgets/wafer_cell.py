"""
한 웨이퍼(또는 한 DELTA) 결과 = 2D heatmap + Summary 4행×2열 표 묶음.

`WaferDisplay` 를 받아 렌더. 단일 시각화와 DELTA 시각화가 공통 사용.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import pyqtgraph as pg
import pyqtgraph.opengl as gl
from PySide6.QtCore import QMimeData, QPoint, QRect, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QImage, QLinearGradient, QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QMenu, QStackedLayout, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core import settings as settings_io
from core.coords import WAFER_RADIUS_MM, filter_in_wafer
from core.interp import interpolate_wafer
from core.metrics import summary_metrics


BOUNDARY_SEGMENTS = 361

# 300mm 웨이퍼 notch — 실제 스펙은 ~3mm 폭/~1mm 깊이지만 화면에서 잘 보이도록 과장.
# 방향은 6시(하단, 3π/2) 고정. 깊이는 settings(chart_common.notch_depth_mm)에서 주입.
_NOTCH_ANGLE = 3 * np.pi / 2
_NOTCH_HALF_RAD = np.radians(3.0)
_NOTCH_DEFAULT_DEPTH_MM = 5.0


def _boundary_xy(show_notch: bool, depth: float = _NOTCH_DEFAULT_DEPTH_MM):
    """웨이퍼 경계 좌표. notch 옵션 시 6시 방향에 V자 홈 반영."""
    theta = np.linspace(0, 2 * np.pi, BOUNDARY_SEGMENTS)
    r = np.full_like(theta, WAFER_RADIUS_MM)
    if show_notch:
        d = np.abs(((theta - _NOTCH_ANGLE + np.pi) % (2 * np.pi)) - np.pi)
        in_notch = d < _NOTCH_HALF_RAD
        r[in_notch] = WAFER_RADIUS_MM - depth * (1 - d[in_notch] / _NOTCH_HALF_RAD)
    return r * np.cos(theta), r * np.sin(theta)


def _points_inside_wafer(XG, YG, show_notch: bool, depth: float = _NOTCH_DEFAULT_DEPTH_MM):
    """격자점이 웨이퍼 내부인가. notch 옵션 시 V자 + margin까지 제외.

    margin은 cell의 반지름(0.5 픽셀)만큼 — V자 **경계선과 교차하는** cell만 추가 투명화.
    해상도 무관하게 V자 "영역 크기"는 동일 (고해상도엔 부드럽게, 저해상도엔 계단).
    """
    r = np.sqrt(XG * XG + YG * YG)
    inside = r <= WAFER_RADIUS_MM
    if show_notch:
        cell = abs(XG[1, 0] - XG[0, 0]) if XG.shape[0] > 1 else 3.0
        theta = np.arctan2(YG, XG)
        d = np.abs(((theta - _NOTCH_ANGLE + np.pi) % (2 * np.pi)) - np.pi)
        angle_margin = 0.5 * cell / WAFER_RADIUS_MM
        in_notch_angle = d < _NOTCH_HALF_RAD + angle_margin
        boundary_r = WAFER_RADIUS_MM - depth * (1 - d / _NOTCH_HALF_RAD)
        boundary_r_render = boundary_r - 0.5 * cell
        inside &= ~(in_notch_angle & (r > boundary_r_render))
    return inside


# ── 커스텀 컬러맵 — pyqtgraph 기본 목록에 없는 것 ──────
# 이름은 core.themes.HEATMAP_COLORMAPS에 함께 등록.
def _reversed_pg_cmap(name: str) -> pg.ColorMap:
    """pyqtgraph 기본 컬러맵을 min↔max 뒤집어 새 ColorMap 반환.

    pg 기본은 color가 float64(0~1). 새 ColorMap 생성자는 float 입력을 정상
    처리 못 해 uint8(0~255)로 변환 후 넘긴다.
    """
    cm = pg.colormap.get(name)
    color_u8 = (cm.color[::-1] * 255).astype(np.uint8)
    return pg.ColorMap(pos=cm.pos, color=color_u8)


_CUSTOM_CMAPS: dict[str, pg.ColorMap] = {
    # 2-stop gradient (min=White)
    "Red-White":      pg.ColorMap([0.0, 1.0], [(255, 255, 255), (220,  30,  30)]),
    "Blue-White":     pg.ColorMap([0.0, 1.0], [(255, 255, 255), ( 30,  70, 220)]),
    "Black-White":    pg.ColorMap([0.0, 1.0], [(255, 255, 255), ( 20,  20,  20)]),
    "Navy-White":     pg.ColorMap([0.0, 1.0], [(255, 255, 255), ( 20,  35, 110)]),
    "Pink-White":     pg.ColorMap([0.0, 1.0], [(255, 255, 255), (230,  70, 150)]),
    "Brown-White":    pg.ColorMap([0.0, 1.0], [(255, 255, 255), (130,  75,  40)]),
    "Charcoal-White": pg.ColorMap([0.0, 1.0], [(255, 255, 255), ( 65,  70,  80)]),
    # 뒤집힌 변형 (Turbo 제외)
    "Reverse-Viridis": _reversed_pg_cmap("viridis"),
    "Reverse-Plasma":  _reversed_pg_cmap("plasma"),
    "Reverse-Inferno": _reversed_pg_cmap("inferno"),
    "Reverse-Magma":   _reversed_pg_cmap("magma"),
    "Reverse-Cividis": _reversed_pg_cmap("cividis"),
}


def _compute_smooth_vertex_normals(vertexes: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """smooth vertex normals — numpy vectorized.

    pyqtgraph `MeshData.vertexNormals()`는 vertex 수만큼 Python for loop을 돌아
    62,500 vertex 기준 cell당 500ms 이상 소요. 같은 결과를 numpy로 5ms 내외에
    계산한 뒤 `_meshdata._vertexNormals`에 직접 주입해 lazy 경로를 우회.
    """
    v0 = vertexes[faces[:, 0]]
    v1 = vertexes[faces[:, 1]]
    v2 = vertexes[faces[:, 2]]
    face_n = np.cross(v1 - v0, v2 - v0)
    fl = np.linalg.norm(face_n, axis=1, keepdims=True)
    fl[fl < 1e-9] = 1.0
    face_n /= fl

    vert_n = np.zeros_like(vertexes, dtype=np.float32)
    np.add.at(vert_n, faces[:, 0], face_n)
    np.add.at(vert_n, faces[:, 1], face_n)
    np.add.at(vert_n, faces[:, 2], face_n)
    vl = np.linalg.norm(vert_n, axis=1, keepdims=True)
    vl[vl < 1e-9] = 1.0
    vert_n /= vl
    return vert_n.astype(np.float32)


class _LockedGLView(gl.GLViewWidget):
    """휠 줌 차단 GLViewWidget — chart 크기 고정을 위함. 드래그 회전/팬은 허용.

    Shift+좌클릭 누르면 클릭 시점에 모든 다른 셀을 자신의 카메라와 동일 각도로 스냅.
    이어서 Shift 유지하며 드래그하면 회전이 나머지 셀로 실시간 전파.

    4x MSAA — surface edge·GLLinePlotItem(경계원·grid) 계단 제거 시도.
    """
    import weakref
    _instances: "weakref.WeakSet[_LockedGLView]" = weakref.WeakSet()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from PySide6.QtGui import QSurfaceFormat
        fmt = self.format()
        fmt.setSamples(4)
        self.setFormat(fmt)
        _LockedGLView._instances.add(self)
        self._sync_active: bool = False

    def wheelEvent(self, ev):
        ev.ignore()

    def _broadcast_camera(self) -> None:
        """자신의 카메라 opts를 다른 살아있는 _LockedGLView 인스턴스에 복사 + update."""
        keys = ("elevation", "azimuth", "distance", "center", "fov")
        my = {k: self.opts.get(k) for k in keys if k in self.opts}
        for other in list(_LockedGLView._instances):
            if other is self:
                continue
            try:
                if not other.isVisible():
                    continue
                other.opts.update(my)
                other.update()
            except RuntimeError:
                # widget deleted
                continue

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and (ev.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            # 즉시 전 셀을 현재 카메라와 동일 각도로 스냅 (회전 시작 전 정렬)
            self._sync_active = True
            self._broadcast_camera()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        super().mouseMoveEvent(ev)
        if self._sync_active and (ev.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._broadcast_camera()

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        self._sync_active = False


class _ColorBar(QWidget):
    """QWidget + QPainter 기반 경량 컬러맵 스케일바.

    pg.PlotWidget 버전은 cell당 ~18ms 생성 비용. 이 구현은 ~0.1ms.
    20-stop QLinearGradient(GPU 가속)로 충분히 부드러운 그라데이션 + tick 라벨 5개.
    """

    _BAR_RIGHT = 5  # 색상바 우측 margin (bar는 우측, 라벨은 좌측)
    _BAR_W = 17     # 색상바 폭 (14 × 1.2)
    _LABEL_GAP = 4  # bar와 라벨 사이 간격
    _MARGIN_V = 12  # 상하 여유 (라벨 잘림 방지)
    _N_STOPS = 20   # QLinearGradient stop 수
    _N_TICKS = 5    # 라벨 수

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(60)
        self._cmap: pg.ColorMap | None = None
        self._vmin: float = 0.0
        self._vmax: float = 1.0
        self._has_data: bool = False

    def update_bar(self, cmap: pg.ColorMap, vmin: float, vmax: float) -> None:
        if (vmin is None or vmax is None
                or not np.isfinite(vmin) or not np.isfinite(vmax)
                or vmin == vmax):
            return
        self._cmap = cmap
        self._vmin = float(vmin)
        self._vmax = float(vmax)
        self._has_data = True
        self.update()

    def paintEvent(self, ev) -> None:
        if not self._has_data or self._cmap is None:
            return
        p = QPainter(self)
        try:
            p.fillRect(self.rect(), QColor("white"))
            w = self.width()
            h = self.height()
            bar_top = self._MARGIN_V
            bar_bottom = h - self._MARGIN_V
            bar_h = bar_bottom - bar_top
            if bar_h <= 0:
                return
            bar_x = w - self._BAR_RIGHT - self._BAR_W
            # 세로 gradient — top=max 색, bottom=min 색
            grad = QLinearGradient(0, bar_top, 0, bar_bottom)
            lut = self._cmap.getLookupTable(0.0, 1.0, self._N_STOPS)
            for i in range(self._N_STOPS):
                t = i / (self._N_STOPS - 1)     # 0=top, 1=bottom
                idx = self._N_STOPS - 1 - i     # top=LUT 마지막(max)
                rgb = lut[idx]
                grad.setColorAt(t, QColor(int(rgb[0]), int(rgb[1]), int(rgb[2])))
            bar_rect = QRect(bar_x, bar_top, self._BAR_W, bar_h)
            p.fillRect(bar_rect, grad)
            # White 계열 컬러맵일 때 배경과 안 구분되는 것 방지 — 연한 회색 테두리
            p.setPen(QPen(QColor(220, 220, 220)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(bar_rect)
            # tick 라벨 (5개, top=max) — bar 좌측에 우측 정렬
            # tick 간격(range / (N-1))에 맞춰 decimals 동적 결정 —
            # 예: range 0.02 → tick_step 0.005 → 3 decimals, range 20 → 5 → 0
            import math
            tick_step = (self._vmax - self._vmin) / (self._N_TICKS - 1)
            decimals = max(0, -int(math.floor(math.log10(tick_step))))
            fmt = f"{{:.{decimals}f}}"
            font = QFont("Arial", 8)
            p.setFont(font)
            p.setPen(QPen(QColor(40, 40, 40)))
            fm = QFontMetrics(font)
            text_right = bar_x - self._LABEL_GAP
            for i in range(self._N_TICKS):
                t = i / (self._N_TICKS - 1)
                val = self._vmax - t * (self._vmax - self._vmin)
                y = bar_top + t * bar_h
                text = fmt.format(val)
                tw = fm.horizontalAdvance(text)
                p.drawText(text_right - tw, int(y + fm.height() / 3), text)
        finally:
            p.end()


def resolve_colormap(name: str) -> pg.ColorMap:
    """이름 → pg.ColorMap. 커스텀 먼저, pyqtgraph는 대소문자 무관 lookup. fallback: viridis."""
    if name in _CUSTOM_CMAPS:
        return _CUSTOM_CMAPS[name]
    # pyqtgraph 기본(plasma/turbo 등)은 소문자라, 대문자 표기도 받아들이도록 소문자 재시도
    for candidate in (name, name.lower()):
        try:
            cm = pg.colormap.get(candidate)
            if cm is not None:
                return cm
        except Exception:
            continue
    return pg.colormap.get("viridis")


@dataclass
class WaferDisplay:
    """WaferCell 에 넘기는 표시 데이터.

    좌표(`x_mm`, `y_mm`)는 **이미 mm 환산된** 상태여야 함.
    반경 필터는 `WaferCell` 내부에서 수행.
    `z_range` 가 주어지면 3D 렌더 시 colormap 정규화 기준으로 사용 (다중 웨이퍼 공통 스케일).
    """
    title: str
    meta_label: str
    x_mm: np.ndarray
    y_mm: np.ndarray
    values: np.ndarray
    z_range: tuple[float, float] | None = None


def _fmt(v, decimals: int) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{decimals}f}"


class WaferCell(QFrame):
    """2D heatmap + 4행×2열 Summary 표. 컨테이너 grab → Copy Graph 합성 이미지.

    title + chart_box + table 전체가 하나의 패널 (border 박스)로 묶임.
    """

    def __init__(
        self,
        display: WaferDisplay,
        value_name: str,
        view_mode: str = "2D",
        parent: QWidget | None = None,
        defer_render: bool = False,
    ) -> None:
        super().__init__(parent)
        self._display = display
        self._value_name = value_name
        self._view_mode = view_mode  # "2D" | "3D"
        self._deferred = defer_render

        # cell 전체를 하나의 흰 패널 + 테두리로 묶음 (ID selector로 자식 위젯 영향 차단)
        self.setObjectName("waferCell")
        self.setStyleSheet(
            "#waferCell { background: white; border: 1px solid #bfbfbf; }"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        self._title = QLabel(display.title)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 전역 QSS의 QWidget { font-size } 가 setFont()를 이기므로 인라인 CSS로 강제.
        # FONT_SIZES['body']는 font_scale 반영된 값이라 +4도 스케일 따라감.
        from core.themes import FONT_SIZES
        title_px = FONT_SIZES.get("body", 13) + 4
        self._title.setStyleSheet(
            f"font-weight: bold; color: #444; font-size: {title_px}px;"
        )
        lay.addWidget(self._title)

        # 차트 컨테이너 — [stacked(2D/3D)] + [colorbar] 좌우 배치. 하나의 패널로 통합.
        # stacked: 2D/3D 위젯 둘 다 미리 생성, QStackedLayout으로 인덱스만 토글.
        # colorbar: 2D/3D 공통, 매 렌더 시 (cmap, vmin, vmax)로 업데이트.
        self._chart_box = QWidget()
        _hbox = QHBoxLayout(self._chart_box)
        _hbox.setContentsMargins(0, 0, 0, 0); _hbox.setSpacing(0)

        self._chart_area = QWidget()
        self._chart_box_layout = QStackedLayout(self._chart_area)
        self._chart_box_layout.setContentsMargins(0, 0, 0, 0)
        _hbox.addWidget(self._chart_area, stretch=1)

        self._colorbar = _ColorBar()
        _hbox.addWidget(self._colorbar)

        lay.addWidget(self._chart_box, stretch=1)

        self._plot_2d = pg.PlotWidget()
        self._plot_2d.setBackground("w")
        self._plot_2d.setAspectLocked(True)
        self._plot_2d.setFrameShape(QFrame.Shape.NoFrame)
        # 300mm 웨이퍼는 항상 -150~+150 mm이라 축 눈금 불필요
        self._plot_2d.getPlotItem().hideAxis("bottom")
        self._plot_2d.getPlotItem().hideAxis("left")
        # 마우스 줌/팬/메뉴 차단 + 웨이퍼 전체가 꽉 차도록 range 고정
        self._plot_2d.setMouseEnabled(False, False)
        self._plot_2d.getPlotItem().setMenuEnabled(False)
        # 좌하단 [A] auto-range 버튼 숨김 — 누르면 enableAutoRange로 크기 바뀜
        self._plot_2d.getPlotItem().hideButtons()
        self._plot_2d.getPlotItem().setDefaultPadding(0)
        self._plot_2d.setRange(
            xRange=(-WAFER_RADIUS_MM, WAFER_RADIUS_MM),
            yRange=(-WAFER_RADIUS_MM, WAFER_RADIUS_MM),
            padding=0.05,
        )
        self._plot_2d.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._plot_2d.customContextMenuRequested.connect(self._show_plot_menu)
        self._chart_box_layout.addWidget(self._plot_2d)  # index 0

        self._gl_3d = _LockedGLView()
        self._gl_3d.setBackgroundColor("w")
        # 초기 카메라 — FOV 45° 하드, distance는 settings 값
        s = settings_io.load_settings().get("chart_3d", {})
        self._gl_3d.setCameraPosition(
            distance=float(s.get("camera_distance", 500)),
            elevation=28, azimuth=-135,
        )
        self._gl_3d.opts["fov"] = 45
        self._gl_3d.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._gl_3d.customContextMenuRequested.connect(self._show_plot_menu)
        self._chart_box_layout.addWidget(self._gl_3d)    # index 1

        self._chart_widget: QWidget = self._plot_2d  # 활성 위젯 추적

        self._table = QTableWidget(3, 2)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().hide()
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        # 스크롤바 항상 OFF — 높이는 populate 후 content 기반으로 동적 계산
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 테마 영향 차단 — 흰색 배경 + 짙은 회색 텍스트 고정 (PPT 호환)
        self._table.setStyleSheet(
            "QTableWidget { background-color: white; color: #222;"
            " gridline-color: #cccccc; border: 1px solid #bfbfbf; }"
            "QTableWidget::item { background-color: white; color: #222; }"
            "QHeaderView::section { background-color: white; color: #222; }"
        )
        lay.addWidget(self._table)

        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_table_menu)

        self._x_in = np.array([])
        self._y_in = np.array([])
        self._v_in = np.array([])
        # 렌더 캐시 — 한 번 그려진 모드는 재계산 없이 인덱스 토글만
        self._rendered_2d = False
        self._rendered_3d = False
        # 보간 캐시 — 같은 데이터 + 같은 (interp_method, grid_resolution)이면 ZG 재사용
        self._interp_cache: tuple | None = None   # (XG, YG, ZG, xg, yg)
        self._interp_key: tuple | None = None     # (method, G)
        # mask 캐시 — (show_notch, notch_depth) 따로 관리. depth만 바꿔도 ZG 보존
        self._mask_cache: np.ndarray | None = None
        self._mask_key: tuple | None = None       # (G, show_notch, depth)
        # 3D GL items — 재사용 slot (setData로 데이터만 교체, GPU buffer 유지)
        self._gl_surface = None
        self._surface_key: tuple | None = None    # (shader, smooth) — 바뀌면 재생성
        # z_sig: 이전 surface의 z 값 signature. 동일하면 z 재전달 안 함 → normals 재계산 생략
        # (smooth=True 에서 z 업데이트는 매우 비쌈: 250² vertex normals 계산)
        self._surface_z_sig: tuple | None = None
        self._gl_boundary = None
        self._gl_grid = None
        # 데이터 필터는 즉시 (가벼움) — 렌더는 defer면 ResultPanel이 병렬 prefetch 후 호출
        self._load_data()
        if not defer_render:
            self.render_initial()

    def _load_data(self) -> None:
        """display → filter_in_wafer → _x_in/_y_in/_v_in 설정. 가벼움(<1ms)."""
        d = self._display
        n = min(len(d.x_mm), len(d.y_mm), len(d.values))
        if n == 0:
            return
        x_mm = np.asarray(d.x_mm[:n], dtype=float)
        y_mm = np.asarray(d.y_mm[:n], dtype=float)
        v = np.asarray(d.values[:n], dtype=float)
        x_in, y_in, v_in, _ = filter_in_wafer(x_mm, y_mm, v)
        self._x_in, self._y_in, self._v_in = x_in, y_in, v_in

    def render_initial(self) -> None:
        """defer된 초기 렌더를 수행. ResultPanel이 병렬 prefetch 후 호출."""
        if self._v_in.size == 0:
            return
        settings = settings_io.load_settings()
        self._apply_chart_size(settings.get("chart_common", {}))
        self._update_table(self._v_in, settings)
        self._activate_current_view()
        self._deferred = False

    def _apply_chart_size(self, common: dict) -> None:
        """cell 전체를 컨텐츠에 딱 맞춘 고정 크기로 — 리사이즈 시 간격 stretch 없음.

        스케일바 유무와 **무관하게 cell 전체 폭도, chart_area 크기도 동일** —
        3D 크기는 카메라 distance로만 변함. 스케일바 해제 시 chart_area가
        좌우로 중앙 정렬만 될 뿐(좌우 margin 대칭).
        """
        w = int(common.get("chart_width", 360))
        h = int(common.get("chart_height", 280))
        show_bar = bool(common.get("show_scale_bar", True))
        bar_w = 60  # colorbar fixed width (0.8× of 75)
        self._chart_area.setFixedSize(w, h)   # 항상 동일 → 3D viewport 고정
        self._colorbar.setFixedHeight(h)
        # 스케일바 해제 시엔 좌/우 margin으로 chart_area 중앙 정렬
        hbox = self._chart_box.layout()
        if show_bar:
            hbox.setContentsMargins(0, 0, 0, 0)
        else:
            hbox.setContentsMargins(bar_w // 2, 0, bar_w // 2, 0)
        title_h = self._title.sizeHint().height()
        table_h = self._table.height()
        total_h = title_h + h + table_h + 6 * 2 + 4 * 2
        total_w = w + bar_w + 6 * 2  # show_bar 무관 고정
        self.setFixedSize(total_w, total_h)

    # ── 외부 API ───────────────────────────────────
    @property
    def display(self) -> WaferDisplay:
        return self._display

    def set_view_mode(self, mode: str) -> None:
        """View 토글 — 첫 진입이면 그리고 캐시, 캐시 있으면 인덱스만 토글(0ms)."""
        if mode == self._view_mode:
            return
        self._view_mode = mode
        self._activate_current_view()

    def invalidate_3d(self) -> None:
        """3D 캐시만 무효화 — z_range 변경 등 3D만 영향받을 때.

        현재 view가 3D면 즉시 재렌더, 2D면 다음 3D 진입 시 그림.
        2D 캐시는 그대로 유지.
        """
        self._rendered_3d = False
        self._reset_3d_items()
        if self._view_mode == "3D":
            self._activate_current_view()

    def refresh(self) -> None:
        """Settings(컬러맵·shading·격자 옵션 등) 변경 시 호출.

        렌더 캐시는 reset하되 **보간 캐시는 유지** — interp_method/grid_resolution이
        바뀐 경우에만 `_ensure_interp`가 내부적으로 재계산. 덕분에 RBF 50~100ms 비용 생략.
        """
        self._rendered_2d = False
        self._rendered_3d = False
        self._reset_2d_items()
        self._reset_3d_items()
        settings = settings_io.load_settings()
        self._apply_chart_size(settings.get("chart_common", {}))
        self._activate_current_view()

    def prefetch_interp(self) -> None:
        """보간 캐시만 미리 채움 (GUI 미접근) — ResultPanel 병렬 보간용.

        GIL 해제되는 scipy RBF C 코드를 여러 cell에서 동시에 돌려 wall-clock 단축.
        렌더는 이후 메인 스레드에서 순차 수행.
        """
        if self._v_in.size == 0:
            return
        settings = settings_io.load_settings()
        common = settings.get("chart_common", {})
        self._ensure_interp(self._x_in, self._y_in, self._v_in, common)

    def prefetch_inactive_view(self) -> None:
        """현재 view_mode와 반대 view를 미리 렌더 (캐시만 채움).

        Run Analysis 완료 후 다음 이벤트 tick에 호출 → 사용자가 2D 보는 사이
        3D도 미리 준비 → 콤보 토글 시 setCurrentIndex만으로 즉시 전환.

        3D prefetch 시 `grabFramebuffer()`로 **hidden 상태에서도 GL 컨텍스트
        초기화 + 첫 paint**를 강제. 덕분에 깜빡임 없이 GPU 업로드 비용을 이
        시점에 흡수 → 이후 show 시 0 딜레이.
        """
        if self._v_in.size == 0:
            return
        settings = settings_io.load_settings()
        if self._view_mode == "2D" and not self._rendered_3d:
            self._render_3d(self._x_in, self._y_in, self._v_in, settings)
            self._rendered_3d = True
            # hidden 상태에서 GL 초기화 + 한 번 paint — 깜빡임 없음
            try:
                self._gl_3d.grabFramebuffer()
            except Exception:
                pass
        elif self._view_mode == "3D" and not self._rendered_2d:
            self._render_2d(self._x_in, self._y_in, self._v_in, settings)
            self._rendered_2d = True

    # ── 렌더 ────────────────────────────────────────
    def _render(self) -> None:
        d = self._display
        n = min(len(d.x_mm), len(d.y_mm), len(d.values))
        if n == 0:
            self._reset_2d_items()
            self._reset_3d_items()
            return
        x_mm = np.asarray(d.x_mm[:n], dtype=float)
        y_mm = np.asarray(d.y_mm[:n], dtype=float)
        v = np.asarray(d.values[:n], dtype=float)

        x_in, y_in, v_in, _ = filter_in_wafer(x_mm, y_mm, v)
        self._x_in, self._y_in, self._v_in = x_in, y_in, v_in

        # 새 데이터이므로 렌더/보간 캐시 모두 무효화
        self._rendered_2d = False
        self._rendered_3d = False
        self._interp_cache = None
        self._interp_key = None
        self._mask_cache = None
        self._mask_key = None
        self._reset_2d_items()
        self._reset_3d_items()

        settings = settings_io.load_settings()
        self._update_table(v_in, settings.get("table", {}))
        self._activate_current_view()

    def _activate_current_view(self) -> None:
        """현재 _view_mode 인덱스로 stack 토글, 캐시 없으면 그때 한 번 그림."""
        settings = settings_io.load_settings()
        if self._view_mode == "3D":
            self._chart_box_layout.setCurrentIndex(1)
            self._chart_widget = self._gl_3d
            if not self._rendered_3d and self._v_in.size > 0:
                self._render_3d(self._x_in, self._y_in, self._v_in, settings)
                self._rendered_3d = True
        else:
            self._chart_box_layout.setCurrentIndex(0)
            self._chart_widget = self._plot_2d
            if not self._rendered_2d and self._v_in.size > 0:
                self._render_2d(self._x_in, self._y_in, self._v_in, settings)
                self._rendered_2d = True

    def _reset_2d_items(self) -> None:
        """plot 안의 모든 item 제거 (위젯 자체는 유지)."""
        self._plot_2d.getPlotItem().clear()

    def _reset_3d_items(self) -> None:
        """3D items는 slot에 보관되어 setData로 재사용 — 여기선 가시성만 OFF.

        items 자체를 제거하면 GPU buffer 재할당이 발생해 grid=250에서 cell당 수백 ms.
        hide만 해두면 다음 render에서 setData로 즉시 교체.
        """
        for it in (self._gl_surface, self._gl_boundary, self._gl_grid):
            if it is not None:
                it.setVisible(False)

    def _ensure_interp(self, x_in, y_in, v_in, common):
        """보간 결과를 캐시 — (method, grid_resolution)이 그대로면 재사용.

        컬러맵·shading 등은 interp 결과에 영향 없으므로 캐시 히트 경로로 수 ms 처리.
        """
        method = common.get("interp_method", "RBF-ThinPlate")
        G = int(common.get("grid_resolution", 100))
        show_notch = bool(common.get("show_notch", True))
        depth = float(common.get("notch_depth_mm", _NOTCH_DEFAULT_DEPTH_MM))
        edge_cut = float(common.get("edge_cut_mm", 0.0))
        # edge_cut 은 radial 경로에서만 유효하지만 일반 캐시 key 에도 포함 — 바뀌면 무효화
        interp_key = (method, G, edge_cut)
        mask_key = (G, show_notch, depth)

        # 보간(RBF/Radial) — key 그대로면 ZG 재사용
        if self._interp_cache is None or self._interp_key != interp_key:
            xg = np.linspace(-WAFER_RADIUS_MM, WAFER_RADIUS_MM, G)
            yg = np.linspace(-WAFER_RADIUS_MM, WAFER_RADIUS_MM, G)
            XG, YG = np.meshgrid(xg, yg, indexing="ij")
            ZG = interpolate_wafer(
                x_in, y_in, v_in, XG, YG,
                method=method,
                edge_cut_mm=edge_cut,
                wafer_radius_mm=float(WAFER_RADIUS_MM),
            )
            self._interp_cache = (XG, YG, ZG, xg, yg)
            self._interp_key = interp_key
            self._mask_cache = None  # G 바뀌면 mask도 재계산
        XG, YG, ZG, xg, yg = self._interp_cache

        # mask — (G, show_notch, depth) 별도 관리. depth만 바꿔도 RBF는 안 돎
        if self._mask_cache is None or self._mask_key != mask_key:
            self._mask_cache = _points_inside_wafer(XG, YG, show_notch, depth)
            self._mask_key = mask_key

        return XG, YG, ZG, self._mask_cache, xg, yg

    def _render_2d(self, x_in, y_in, v_in, settings) -> None:
        common = settings.get("chart_common", {})
        chart = settings.get("chart_2d", {})
        XG, YG, ZG, inside, xg, yg = self._ensure_interp(x_in, y_in, v_in, common)
        ZG = np.where(inside, ZG, np.nan)

        plot = self._plot_2d
        self._reset_2d_items()

        cmap_name = common.get("colormap", "Turbo")
        img = pg.ImageItem(ZG)
        img.setRect(QRectF(
            -WAFER_RADIUS_MM, -WAFER_RADIUS_MM,
            2 * WAFER_RADIUS_MM, 2 * WAFER_RADIUS_MM,
        ))
        cmap = resolve_colormap(cmap_name)
        img.setLookupTable(cmap.getLookupTable())
        # Z-Scale 공통 모드면 display.z_range로 levels 고정 → 2D에도 공통 스케일 반영
        if self._display.z_range is not None:
            img.setLevels(self._display.z_range)
        plot.addItem(img)

        if common.get("show_circle", True):
            bx, by = _boundary_xy(
                common.get("show_notch", True),
                float(common.get("notch_depth_mm", _NOTCH_DEFAULT_DEPTH_MM)),
            )
            plot.plot(bx, by, pen=pg.mkPen("k", width=2))
        if chart.get("show_points", True):
            plot.addItem(pg.ScatterPlotItem(
                x_in, y_in, pen=None,
                brush=pg.mkBrush(0, 0, 0, 220),
                size=int(chart.get("point_size", 4)),
            ))

        if chart.get("show_value_labels", False):
            # 측정점 value label 소수점은 chart_common.decimals 사용 (Summary 표와 동일)
            tbl = settings.get("table", {})
            decimals = int(common.get("decimals", tbl.get("decimals", 2)))
            for x, y, val in zip(x_in, y_in, v_in):
                if np.isnan(val):
                    continue
                txt = pg.TextItem(
                    f"{val:.{decimals}f}",
                    color=(40, 40, 40),
                    anchor=(0.5, 1.2),
                )
                txt.setPos(float(x), float(y))
                plot.addItem(txt)

        # colorbar 갱신 — 공통 스케일이면 display.z_range, 아니면 ZG inside 유효값
        if self._display.z_range is not None:
            self._update_colorbar(common, None, vmin=self._display.z_range[0], vmax=self._display.z_range[1])
        else:
            self._update_colorbar(common, ZG[inside])

    def _render_3d(self, x_in, y_in, v_in, settings) -> None:
        common = settings.get("chart_common", {})
        chart3d = settings.get("chart_3d", {})

        # 카메라 distance — Settings 변경 시 즉시 반영. FOV는 45° 하드코딩.
        # (elevation/azimuth는 드래그로 사용자 조작 유지)
        opts = self._gl_3d.opts
        dist = float(chart3d.get("camera_distance", 500))
        if opts.get("distance") != dist:
            self._gl_3d.setCameraPosition(distance=dist)
            self._gl_3d.update()

        XG, YG, ZG, inside, xg, yg = self._ensure_interp(x_in, y_in, v_in, common)

        # Z 범위 (공통 스케일이면 display.z_range, 아니면 자체 데이터)
        if self._display.z_range is not None:
            vmin, vmax = self._display.z_range
        else:
            valid = ZG[inside & ~np.isnan(ZG)]
            if valid.size == 0:
                return
            vmin = float(valid.min())
            vmax = float(valid.max())
        z_range = vmax - vmin if vmax > vmin else 1.0

        # Z 과장 배율: None 자동, float 고정
        z_exag = chart3d.get("z_exaggeration", None)
        target_height = WAFER_RADIUS_MM * 0.4  # X/Y(±150)의 ~40%
        if z_exag is None:
            factor = target_height / z_range
        else:
            base_factor = target_height / z_range
            factor = base_factor * float(z_exag)

        z_disp = (ZG - vmin) * factor
        z_disp = np.where(inside, z_disp, 0.0)

        # 컬러: 정점마다 RGBA (공통 컬러맵)
        cmap_name = common.get("colormap", "Turbo")
        cmap = resolve_colormap(cmap_name)
        lut = cmap.getLookupTable(0.0, 1.0, 256)  # (256, 4) ubyte
        norm = (ZG - vmin) / z_range
        norm = np.where(inside, norm, 0.0)
        idx_arr = np.clip((norm * 255).astype(int), 0, 255)
        colors = np.empty(ZG.shape + (4,), dtype=np.float32)
        colors[..., :3] = lut[idx_arr, :3] / 255.0
        colors[..., 3] = 1.0
        colors[~inside] = (1.0, 1.0, 1.0, 0.0)

        gview = self._gl_3d

        # ── grid (바닥) — 재사용 ──
        if chart3d.get("show_grid", True):
            if self._gl_grid is None:
                self._gl_grid = gl.GLGridItem()
                self._gl_grid.setSize(x=350, y=350)
                self._gl_grid.setSpacing(x=50, y=50)
                self._gl_grid.setColor((205, 205, 205, 150))
                gview.addItem(self._gl_grid)
            self._gl_grid.setVisible(True)
        elif self._gl_grid is not None:
            self._gl_grid.setVisible(False)

        # ── surface — shader/smooth 변경 시만 재생성, 그 외엔 setData로 데이터만 교체 ──
        shader = "shaded"  # 하드코딩 — 다른 shader(normalColor/heightColor)는 컬러맵 무시라 UX 혼란
        smooth = bool(chart3d.get("smooth", True))
        surf_key = (shader, smooth)
        z_f32 = z_disp.astype(np.float32)
        colors_flat = colors.reshape(-1, 4)
        # z signature — (보간 cache key, mask cache key, vmin/vmax, factor)
        z_sig = (self._interp_key, self._mask_key, vmin, vmax, factor)
        if self._gl_surface is None or self._surface_key != surf_key:
            if self._gl_surface is not None:
                gview.removeItem(self._gl_surface)
            self._gl_surface = gl.GLSurfacePlotItem(
                x=xg, y=yg, z=z_f32, colors=colors_flat,
                shader=shader, smooth=smooth,
                computeNormals=True, glOptions="opaque",
            )
            gview.addItem(self._gl_surface)
            self._surface_key = surf_key
            self._surface_z_sig = None  # 아래서 주입 트리거
        elif self._surface_z_sig == z_sig:
            # z 동일 → colors만 교체 (normals 재사용)
            # 단 setData(colors=only)는 pyqtgraph 내부에서 meshDataChanged 호출이
            # 빠져서 GPU에 반영 안 됨 → 명시 트리거 필요
            self._gl_surface.setData(colors=colors_flat)
            self._gl_surface.meshDataChanged()
        else:
            self._gl_surface.setData(x=xg, y=yg, z=z_f32, colors=colors_flat)
            self._surface_z_sig = None  # 아래서 주입

        # z 변경되었으면 normals 재주입 (pyqtgraph 기본 Python 루프보다 100× 빠름)
        if smooth and self._surface_z_sig != z_sig:
            verts = self._gl_surface._vertexes.reshape(-1, 3)
            faces = self._gl_surface._faces
            vn = _compute_smooth_vertex_normals(verts, faces)
            md = self._gl_surface._meshdata
            md._vertexNormals = vn
            md._vertexNormalsIndexedByFaces = None
            self._surface_z_sig = z_sig
        self._gl_surface.setVisible(True)

        # ── boundary line — 재사용 ──
        if common.get("show_circle", True):
            bx, by = _boundary_xy(
                common.get("show_notch", True),
                float(common.get("notch_depth_mm", _NOTCH_DEFAULT_DEPTH_MM)),
            )
            circ = np.column_stack([bx, by, np.zeros_like(bx)])
            if self._gl_boundary is None:
                self._gl_boundary = gl.GLLinePlotItem(
                    pos=circ, color=(0, 0, 0, 1), width=2,
                    antialias=True, glOptions="opaque",
                )
                gview.addItem(self._gl_boundary)
            else:
                self._gl_boundary.setData(pos=circ)
            self._gl_boundary.setVisible(True)
        elif self._gl_boundary is not None:
            self._gl_boundary.setVisible(False)

        # colorbar 갱신 (3D용 범위 = vmin~vmax. display.z_range가 있으면 그걸 사용)
        self._update_colorbar(common, None, vmin=vmin, vmax=vmax)

    def _update_colorbar(self, common: dict, values=None, vmin=None, vmax=None) -> None:
        """show_scale_bar 옵션 반영 + 컬러맵/범위로 스케일바 갱신."""
        if not bool(common.get("show_scale_bar", True)):
            self._colorbar.setVisible(False)
            return
        self._colorbar.setVisible(True)
        if vmin is None or vmax is None:
            if values is None or values.size == 0:
                return
            valid = values[~np.isnan(values)]
            if valid.size == 0:
                return
            vmin = float(valid.min())
            vmax = float(valid.max())
        cmap = resolve_colormap(common.get("colormap", "Turbo"))
        self._colorbar.update_bar(cmap, vmin, vmax)

    def _update_table(self, v: np.ndarray, settings: dict) -> None:
        # 소수점은 chart_common.decimals (사용자 요청: 공통 항목). 없으면 기존 table.decimals fallback.
        common = settings.get("chart_common", {})
        tbl_cfg = settings.get("table", {})
        decimals = int(common.get("decimals", tbl_cfg.get("decimals", 2)))
        percent_suffix = bool(tbl_cfg.get("nu_percent_suffix", True))
        m = summary_metrics(v)

        nu = m["nu_pct"]
        if np.isnan(nu):
            nu_s = "—"
        elif percent_suffix:
            nu_s = f"{nu:.{decimals}f}%"
        else:
            nu_s = f"{nu / 100.0:.{decimals + 2}f}"

        rows = [
            ("Average",      _fmt(m['avg'], decimals)),
            ("Non Unif.",    nu_s),
            ("Range, 3Sig",  f"{_fmt(m['range'], decimals)}, {_fmt(m['sig3'], decimals)}"),
        ]
        for r, (label, value) in enumerate(rows):
            self._set_cell(r, 0, label)
            self._set_cell(r, 1, value)
        # content 기반 높이 자동 계산 — 스크롤바 안 뜨게
        self._table.resizeRowsToContents()
        total_h = sum(self._table.rowHeight(r) for r in range(self._table.rowCount()))
        frame = 2 * self._table.frameWidth()
        self._table.setFixedHeight(total_h + frame)
        # 테이블 높이가 바뀌었으니 cell 전체 크기도 재계산 (chart_area는 그대로, 전체 높이만)
        self._apply_chart_size(settings.get("chart_common", {}))

    def _set_cell(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, col, item)

    # ── 우클릭 메뉴 ────────────────────────────────
    def _show_plot_menu(self, pos: QPoint) -> None:
        chart = self._chart_widget
        if chart is None:
            return
        menu = QMenu(self)
        a_reset = menu.addAction("Reset")
        a_graph = menu.addAction("Copy Graph")
        a_data = menu.addAction("Copy Data")
        chosen = menu.exec(chart.mapToGlobal(pos))
        if chosen is a_reset:
            if isinstance(chart, pg.PlotWidget):
                # enableAutoRange는 content 기반 padding 재계산이라 초기 setRange와
                # 미묘하게 달라짐. 초기와 동일한 범위로 재설정 → 크기 변화 없음
                chart.setRange(
                    xRange=(-WAFER_RADIUS_MM, WAFER_RADIUS_MM),
                    yRange=(-WAFER_RADIUS_MM, WAFER_RADIUS_MM),
                    padding=0.05,
                )
            elif isinstance(chart, gl.GLViewWidget):
                s = settings_io.load_settings().get("chart_3d", {})
                chart.setCameraPosition(
                    distance=float(s.get("camera_distance", 500)),
                    elevation=28, azimuth=-135,
                )
                chart.opts["fov"] = 45
                chart.update()
        elif chosen is a_graph:
            self._copy_graph()
        elif chosen is a_data:
            self._copy_data()

    def _show_table_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        a_table = menu.addAction("Copy Table")
        chosen = menu.exec(self._table.mapToGlobal(pos))
        if chosen is a_table:
            self._copy_table()

    # ── Copy ──────────────────────────────────────
    def _copy_graph(self) -> None:
        """WaferCell 영역을 화면에서 직접 픽셀 캡처해 클립보드로.

        `QScreen.grabWindow`는 OS 합성 결과를 그대로 가져와서 Qt 일반 grab의
        GL-transparent 이슈(검은 fb)와 grabFramebuffer의 alpha/jaggies 이슈를
        모두 우회. 화면에 보이는 픽셀 그대로 = paste 결과.
        """
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            QApplication.clipboard().setPixmap(self.grab())
            return

        # 전체 스크린을 grab한 뒤 WaferCell 영역만 crop (device pixel ratio 반영)
        full_pm = screen.grabWindow(0)
        dpr = full_pm.devicePixelRatio()
        tl_global = self.mapToGlobal(QPoint(0, 0))
        screen_tl = screen.geometry().topLeft()
        x = int((tl_global.x() - screen_tl.x()) * dpr)
        y = int((tl_global.y() - screen_tl.y()) * dpr)
        w = int(self.width() * dpr)
        h = int(self.height() * dpr)
        cropped = full_pm.copy(x, y, w, h)
        cropped.setDevicePixelRatio(dpr)
        QApplication.clipboard().setPixmap(cropped)

    def _copy_data(self) -> None:
        lines = [f"X\tY\t{self._value_name}"]
        for x, y, v in zip(self._x_in, self._y_in, self._v_in):
            lines.append(f"{x}\t{y}\t{v}")
        QApplication.clipboard().setText("\n".join(lines))

    def _copy_table(self) -> None:
        rows: list[list[str]] = []
        for r in range(self._table.rowCount()):
            row_cells: list[str] = []
            for c in range(self._table.columnCount()):
                it = self._table.item(r, c)
                row_cells.append(it.text() if it else "")
            rows.append(row_cells)
        tsv = "\n".join("\t".join(r) for r in rows)
        html_rows = "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
        )
        html = (
            "<table border='1' cellpadding='4' cellspacing='0'>"
            f"<tbody>{html_rows}</tbody></table>"
        )
        mime = QMimeData()
        mime.setText(tsv)
        mime.setHtml(html)
        QApplication.clipboard().setMimeData(mime)
