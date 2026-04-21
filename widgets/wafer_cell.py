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
from core.metrics import summary_metrics


BOUNDARY_SEGMENTS = 361

# 300mm 웨이퍼 notch — 실제 스펙은 ~3mm 폭/~1mm 깊이지만 화면에서 잘 보이도록 과장.
# 방향은 6시(하단, 3π/2) 고정. 깊이는 settings(chart_common.notch_depth_mm)에서 주입.
_NOTCH_ANGLE = 3 * np.pi / 2
_NOTCH_HALF_RAD = np.radians(3.0)
_NOTCH_DEFAULT_DEPTH_MM = 5.0


def _boundary_xy(
    show_notch: bool,
    depth: float = _NOTCH_DEFAULT_DEPTH_MM,
    R: float = WAFER_RADIUS_MM,
):
    """웨이퍼 경계 좌표. notch 옵션 시 6시 방향에 V자 홈 반영.

    R: 경계 원의 반지름 (기본 WAFER_RADIUS_MM=150). Settings 의 boundary_r_mm
    로 살짝 확장 가능 (150~160).
    """
    theta = np.linspace(0, 2 * np.pi, BOUNDARY_SEGMENTS)
    r = np.full_like(theta, R)
    if show_notch:
        d = np.abs(((theta - _NOTCH_ANGLE + np.pi) % (2 * np.pi)) - np.pi)
        in_notch = d < _NOTCH_HALF_RAD
        r[in_notch] = R - depth * (1 - d[in_notch] / _NOTCH_HALF_RAD)
    return r * np.cos(theta), r * np.sin(theta)


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


def _build_radial_surface_mesh(
    xs: np.ndarray, ys: np.ndarray, z_raw: np.ndarray,
    rings: int, seg: int,
    vmin: float, z_range: float, factor: float,
    cmap: pg.ColorMap,
    *, cut_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """원형 radial mesh — pre-evaluated (xs, ys, z_raw) 로 정점 구성.

    (rings+1) × seg 정점 순서: i*seg + j (ring i, angle j)
    - face: 인접 링 사이 사각형을 2 삼각형으로
    - 외곽 링이 정확히 r=R 이므로 경계가 부드러운 원 (격자 기반 카디널 스트라이프 없음)
    - cut_mask: True 인 정점은 z=0 + 흰색 (edge_cut shelf / notch V 영역 제거용).
    """
    # RBF 외삽으로 vmin 아래 값이 나올 수 있음 → 바닥(z=0) 뚫지 않도록 clamp.
    z_disp = np.clip((z_raw - vmin) * factor, 0.0, None).astype(np.float32)

    # 잘려야 할 정점 z=0 으로 강제
    if cut_mask is not None:
        z_disp[cut_mask] = 0.0

    verts = np.column_stack([xs.astype(np.float32), ys.astype(np.float32), z_disp])

    # Faces — 각 (i,j) 사각형: a=(i,j), b=(i,j+1), c=(i+1,j+1), d=(i+1,j)
    N = rings * seg  # 사각형 개수
    a = np.empty(N, dtype=np.uint32)
    b = np.empty(N, dtype=np.uint32)
    c = np.empty(N, dtype=np.uint32)
    d = np.empty(N, dtype=np.uint32)
    k = 0
    for i in range(rings):
        for j in range(seg):
            j_next = (j + 1) % seg
            a[k] = i * seg + j
            b[k] = i * seg + j_next
            c[k] = (i + 1) * seg + j_next
            d[k] = (i + 1) * seg + j
            k += 1
    # 각 쿼드를 2 trig 으로
    faces = np.empty((2 * N, 3), dtype=np.uint32)
    faces[0::2, 0] = a; faces[0::2, 1] = b; faces[0::2, 2] = c
    faces[1::2, 0] = a; faces[1::2, 1] = c; faces[1::2, 2] = d

    # Colors — vertex color 기반 interpolation
    rng = max(z_range, 1e-9)
    norm = np.clip((z_raw - vmin) / rng, 0.0, 1.0)
    lut = cmap.getLookupTable(0.0, 1.0, 256)
    idx = np.clip((norm * 255).astype(int), 0, 255)
    rgb = lut[idx, :3].astype(np.float32) / 255.0
    colors = np.concatenate([rgb, np.ones((rgb.shape[0], 1), dtype=np.float32)], axis=1)

    # cut 영역 정점은 흰색 (배경 매치) — rect mode 의 alpha=0 white 와 동일 효과
    if cut_mask is not None and cut_mask.any():
        colors[cut_mask] = (1.0, 1.0, 1.0, 1.0)

    return verts, faces, colors


def _build_smooth_cylinder_wall(
    xs: np.ndarray, ys: np.ndarray, z_raw: np.ndarray,
    seg: int,
    vmin: float, z_range: float, factor: float,
    cmap: pg.ColorMap,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """매끈 원통 벽 — pre-evaluated (xs, ys, z_raw) 외곽 링 기반, bottom z=0.

    radial surface 외곽 링과 top z 공유 → 이음새 매끈.
    """
    xs32 = xs.astype(np.float32)
    ys32 = ys.astype(np.float32)
    # 음수 clamp — 바닥 아래로 뚫고 내려가는 문제 방지
    z_top = np.clip((z_raw - vmin) * factor, 0.0, None).astype(np.float32)

    top = np.column_stack([xs32, ys32, z_top])
    bot = np.column_stack([xs32, ys32, np.zeros(seg, dtype=np.float32)])
    verts = np.vstack([top, bot])

    # faces: 각 세그먼트별 (top_i, top_nxt, bot_nxt) / (top_i, bot_nxt, bot_i)
    idx = np.arange(seg, dtype=np.uint32)
    nxt = ((idx + 1) % seg).astype(np.uint32)
    top_i, top_n = idx, nxt
    bot_i, bot_n = idx + seg, nxt + seg
    face_a = np.stack([top_i, top_n, bot_n], axis=1)
    face_b = np.stack([top_i, bot_n, bot_i], axis=1)
    faces = np.concatenate([face_a, face_b], axis=0)

    # 색: top 은 data z 기반, bottom 은 vmin(colormap 가장 밑) 쪽
    rng = max(z_range, 1e-9)
    norm_top = np.clip((z_raw - vmin) / rng, 0.0, 1.0)
    lut = cmap.getLookupTable(0.0, 1.0, 256)
    idx_top = np.clip((norm_top * 255).astype(int), 0, 255)
    rgb_top = lut[idx_top, :3].astype(np.float32) / 255.0
    rgb_bot = np.tile(lut[0:1, :3].astype(np.float32) / 255.0, (seg, 1))
    rgb = np.vstack([rgb_top, rgb_bot])
    alpha = np.ones((rgb.shape[0], 1), dtype=np.float32)
    colors = np.concatenate([rgb, alpha], axis=1)
    return verts, faces, colors


class _LockedGLView(gl.GLViewWidget):
    """Shift+드래그 카메라 동기화 지원 GLViewWidget.

    - 휠 줌: GLViewWidget 기본 동작 사용 (카메라 distance 조정)
    - 좌 드래그: orbit (회전)
    - Ctrl+좌 드래그: pan (위치 이동) — GLViewWidget 기본
    - Shift+좌클릭: 클릭 순간 전 셀 카메라 스냅 동기. 이어서 Shift 유지 드래그 → 실시간 전파
    - 4x MSAA — surface edge·GLLinePlotItem(경계원·grid) 계단 제거
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

        s = settings_io.load_settings().get("chart_3d", {})
        cam_dist = float(s.get("camera_distance", 550))

        # 2D top-view (radial) — plain GLViewWidget (Shift 동기 없음, 2D 는 의미 X).
        # 카메라는 3D 와 동일 파라미터 (distance, fov) — elevation 만 90 (top-down),
        # azimuth=-90 으로 notch 를 6시(화면 하단)로 정렬.
        # → 3D 를 top 각도로 돌려 봤을 때와 동일 크기.
        self._gl_2d = gl.GLViewWidget()
        self._gl_2d.setBackgroundColor("w")
        self._gl_2d.setCameraPosition(distance=cam_dist, elevation=90, azimuth=-90)
        self._gl_2d.opts["fov"] = 45
        self._gl_2d.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._gl_2d.customContextMenuRequested.connect(self._show_plot_menu)
        self._chart_box_layout.addWidget(self._gl_2d)    # index 0

        # 3D radial view
        self._gl_3d = _LockedGLView()
        self._gl_3d.setBackgroundColor("w")
        self._gl_3d.setCameraPosition(distance=cam_dist, elevation=28, azimuth=-135)
        self._gl_3d.opts["fov"] = 45
        self._gl_3d.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._gl_3d.customContextMenuRequested.connect(self._show_plot_menu)
        self._chart_box_layout.addWidget(self._gl_3d)    # index 1

        self._chart_widget: QWidget = self._gl_2d  # 활성 위젯 추적

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
        # 3D radial mesh slot — GLMeshItem (surface + cylinder wall)
        self._gl_surface = None      # radial surface mesh
        self._gl_wall = None         # smooth cylinder wall
        self._gl_boundary = None     # 경계 원 (notch 포함)
        self._gl_grid = None         # 바닥 grid
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
        """
        self._rendered_3d = False
        self._hide_3d_items()
        if self._view_mode == "3D":
            self._activate_current_view()

    def refresh(self) -> None:
        """Settings(컬러맵·보간·mesh 옵션 등) 변경 시 호출 — 양쪽 view 재렌더."""
        self._rendered_2d = False
        self._rendered_3d = False
        self._hide_3d_items()
        settings = settings_io.load_settings()
        self._apply_chart_size(settings.get("chart_common", {}))
        self._activate_current_view()

    def prefetch_interp(self) -> None:
        """호환 유지용 — radial 경로에선 별도 캐시 없이 렌더 시 직접 RBF.

        이전 rect 경로의 _ensure_interp 병렬화를 위해 ResultPanel 이 호출했던 훅.
        radial 은 RBF fit 자체가 ~1ms 로 충분히 빨라 병렬화 이득 미미. no-op.
        """
        return

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
            self._hide_3d_items()
            return
        x_mm = np.asarray(d.x_mm[:n], dtype=float)
        y_mm = np.asarray(d.y_mm[:n], dtype=float)
        v = np.asarray(d.values[:n], dtype=float)

        x_in, y_in, v_in, _ = filter_in_wafer(x_mm, y_mm, v)
        self._x_in, self._y_in, self._v_in = x_in, y_in, v_in

        # 새 데이터 — 렌더 캐시 무효화
        self._rendered_2d = False
        self._rendered_3d = False
        self._hide_3d_items()

        settings = settings_io.load_settings()
        self._update_table(v_in, settings.get("table", {}))
        self._activate_current_view()

    def _hide_3d_items(self) -> None:
        """3D items 숨김 (widget 자체는 유지, setData 로 다음 렌더 시 즉시 재사용)."""
        for it in (self._gl_surface, self._gl_wall,
                    self._gl_boundary, self._gl_grid):
            if it is not None:
                it.setVisible(False)

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
            self._chart_widget = self._gl_2d
            if not self._rendered_2d and self._v_in.size > 0:
                self._render_2d(self._x_in, self._y_in, self._v_in, settings)
                self._rendered_2d = True

    def _render_2d(self, x_in, y_in, v_in, settings) -> None:
        """2D top-view radial mesh — RBF 1회 평가, _gl_2d 위젯 사용.

        3D radial 과 동일한 mesh 데이터를 z=0 평면으로 깔아서 위에서 내려다 본 모습.
        측정점/값 라벨/경계 원 모두 GL 객체로 그림.
        """
        from core.interp import make_rbf

        common = settings.get("chart_common", {})
        chart = settings.get("chart_2d", {})
        rings = max(5, int(common.get("radial_rings", 20)))
        seg = max(60, int(common.get("radial_seg", 180)))
        edge_cut_mm = float(common.get("edge_cut_mm", 0.0))
        R = float(WAFER_RADIUS_MM)
        effective_R = max(R - edge_cut_mm, 1.0) if edge_cut_mm > 0 else R
        apply_cut = edge_cut_mm > 0 and effective_R < R

        gview = self._gl_2d

        # 카메라 distance — 3D 와 동일 값으로 동기화 (top view 가 3D 크기와 일치)
        chart3d = settings.get("chart_3d", {})
        dist = float(chart3d.get("camera_distance", 550))
        if gview.opts.get("distance") != dist:
            gview.setCameraPosition(distance=dist)

        # 기존 모든 item 제거 (top view 는 매 렌더 깨끗이 다시 그림 — overhead 작음)
        for it in list(gview.items):
            gview.removeItem(it)

        # RBF fit — settings 의 interp_method 반영
        pts = np.column_stack([np.asarray(x_in, dtype=float), np.asarray(y_in, dtype=float)])
        vals = np.asarray(v_in, dtype=float)
        m = ~np.isnan(vals) & ~np.isnan(pts[:, 0]) & ~np.isnan(pts[:, 1])
        if m.sum() < 2:
            return
        method = str(common.get("interp_method", "RBF-ThinPlate"))
        try:
            rbf = make_rbf(pts[m, 0], pts[m, 1], vals[m], method=method)
        except Exception:
            return

        # 링 배치 (3D radial 과 동일 — edge_cut shelf 1 ring 추가)
        if apply_cut:
            r_arr = np.concatenate([np.linspace(0.0, effective_R, rings + 1), [R]])
        else:
            r_arr = np.linspace(0.0, R, rings + 1)
        n_rings = len(r_arr) - 1

        theta = np.linspace(0.0, 2.0 * np.pi, seg, endpoint=False)
        Rm, Tm = np.meshgrid(r_arr, theta, indexing="ij")
        xs_all = (Rm * np.cos(Tm)).ravel()
        ys_all = (Rm * np.sin(Tm)).ravel()
        z_raw_all = rbf(np.column_stack([xs_all, ys_all]))

        # vmin/vmax — 공통 스케일 모드 우선, 아니면 radial 평가값 기반
        if self._display.z_range is not None:
            vmin, vmax = self._display.z_range
        else:
            finite = z_raw_all[np.isfinite(z_raw_all)]
            if finite.size == 0:
                return
            vmin = float(finite.min())
            vmax = float(finite.max())
        z_range = vmax - vmin if vmax > vmin else 1.0

        # 2D top view: z=0 평면 (높이 표현 없음, 색만)
        # cut mask — edge_cut 만 (notch 는 boundary 원에만 표시)
        eff_r_seg = np.full(seg, effective_R, dtype=float)
        vert_theta_idx = np.arange(xs_all.size) % seg
        r_flat = np.sqrt(xs_all ** 2 + ys_all ** 2)
        cut_mask_all = r_flat > eff_r_seg[vert_theta_idx] + 1e-6

        cmap = resolve_colormap(common.get("colormap", "Turbo"))
        # 정점 색 — z_raw 기반 normalize
        rng = max(z_range, 1e-9)
        norm = np.clip((z_raw_all - vmin) / rng, 0.0, 1.0)
        lut = cmap.getLookupTable(0.0, 1.0, 256)
        idx_arr = np.clip((norm * 255).astype(int), 0, 255)
        rgb = lut[idx_arr, :3].astype(np.float32) / 255.0
        colors = np.concatenate([rgb, np.ones((rgb.shape[0], 1), dtype=np.float32)], axis=1)
        if cut_mask_all.any():
            colors[cut_mask_all] = (1.0, 1.0, 1.0, 1.0)

        # Faces
        N = n_rings * seg
        a = np.empty(N, dtype=np.uint32); b = np.empty(N, dtype=np.uint32)
        c = np.empty(N, dtype=np.uint32); d = np.empty(N, dtype=np.uint32)
        k = 0
        for i in range(n_rings):
            for j in range(seg):
                jn = (j + 1) % seg
                a[k] = i * seg + j
                b[k] = i * seg + jn
                c[k] = (i + 1) * seg + jn
                d[k] = (i + 1) * seg + j
                k += 1
        faces = np.empty((2 * N, 3), dtype=np.uint32)
        faces[0::2, 0] = a; faces[0::2, 1] = b; faces[0::2, 2] = c
        faces[1::2, 0] = a; faces[1::2, 1] = c; faces[1::2, 2] = d

        # 정점 — z=0 평면
        verts = np.column_stack([
            xs_all.astype(np.float32),
            ys_all.astype(np.float32),
            np.zeros(xs_all.size, dtype=np.float32),
        ])
        mesh = gl.GLMeshItem(
            vertexes=verts, faces=faces, vertexColors=colors,
            smooth=True, drawEdges=False, glOptions="opaque",
        )
        gview.addItem(mesh)

        # 경계 원 (notch 표시) — mesh 위에 살짝 띄움
        if common.get("show_circle", True):
            bx, by = _boundary_xy(
                common.get("show_notch", True),
                float(common.get("notch_depth_mm", _NOTCH_DEFAULT_DEPTH_MM)),
                R=float(common.get("boundary_r_mm", WAFER_RADIUS_MM)),
            )
            circ = np.column_stack([bx, by, np.full_like(bx, 0.5)])
            line = gl.GLLinePlotItem(
                pos=circ, color=(0, 0, 0, 1), width=2,
                antialias=True, glOptions="opaque",
            )
            gview.addItem(line)

        # 측정점
        if chart.get("show_points", True):
            pts3d = np.column_stack([
                np.asarray(x_in, dtype=np.float32),
                np.asarray(y_in, dtype=np.float32),
                np.full(len(x_in), 0.7, dtype=np.float32),
            ])
            scatter = gl.GLScatterPlotItem(
                pos=pts3d, color=(0.0, 0.0, 0.0, 0.85),
                size=float(chart.get("point_size", 4)),
                pxMode=True, glOptions="opaque",
            )
            gview.addItem(scatter)

        # 값 라벨
        if chart.get("show_value_labels", False):
            tbl = settings.get("table", {})
            decimals = int(common.get("decimals", tbl.get("decimals", 2)))
            # 라벨 폰트 크기 — chart_2d.label_font_scale (0.85 / 1.0 / 1.15) × base 8pt
            scale = float(chart.get("label_font_scale", 0.85))
            from PySide6.QtGui import QFont
            label_font = QFont()
            label_font.setPointSize(max(5, int(round(8 * scale))))
            for x, y, val in zip(x_in, y_in, v_in):
                if np.isnan(val):
                    continue
                try:
                    ti = gl.GLTextItem(
                        pos=(float(x), float(y), 1.0),
                        text=f"{val:.{decimals}f}",
                        color=(40, 40, 40, 255),
                        font=label_font,
                    )
                    gview.addItem(ti)
                except Exception:
                    pass

        # colorbar
        self._update_colorbar(common, None, vmin=vmin, vmax=vmax)

    def _render_3d(self, x_in, y_in, v_in, settings) -> None:
        """radial 원형 fan mesh 기반 3D 렌더 — (r, θ) mesh + 매끈 원통 벽.

        비용: RBF 정점 (rings+1)×seg + seg 개 재평가.
        """
        from core.interp import make_rbf

        common = settings.get("chart_common", {})
        chart3d = settings.get("chart_3d", {})

        # 카메라 distance — Settings 변경 시 즉시 반영. FOV 45°, elevation/azimuth 는
        # 드래그로 사용자 조작 유지 (_LockedGLView).
        opts = self._gl_3d.opts
        dist = float(chart3d.get("camera_distance", 550))
        if opts.get("distance") != dist:
            self._gl_3d.setCameraPosition(distance=dist)
            self._gl_3d.update()

        rings = max(5, int(common.get("radial_rings", 20)))
        seg = max(60, int(common.get("radial_seg", 180)))

        # RBF fit — settings 의 interp_method 반영
        pts = np.column_stack([np.asarray(x_in, dtype=float), np.asarray(y_in, dtype=float)])
        vals = np.asarray(v_in, dtype=float)
        mask = ~np.isnan(vals) & ~np.isnan(pts[:, 0]) & ~np.isnan(pts[:, 1])
        if mask.sum() < 2:
            return
        method = str(common.get("interp_method", "RBF-ThinPlate"))
        try:
            rbf = make_rbf(pts[mask, 0], pts[mask, 1], vals[mask], method=method)
        except Exception:
            # RBF 실패 (collinear 등) — 조용히 skip. rect 모드 이용 권장.
            return

        R = float(WAFER_RADIUS_MM)

        # edge_cut 먼저 결정 (링 배치에 영향)
        edge_cut_mm = float(common.get("edge_cut_mm", 0.0))
        effective_R = max(R - edge_cut_mm, 1.0) if edge_cut_mm > 0 else R
        apply_cut = edge_cut_mm > 0 and effective_R < R

        # Radial 링 배치:
        # - edge_cut 없음: 0 ~ R 균등 (rings+1 개 링)
        # - edge_cut 적용: 0 ~ effective_R 균등 (rings+1 개 interior 링) + R (shelf 링 1개)
        #   → shelf 영역이 하나의 얇은 band 로 렌더됨
        if apply_cut:
            r_arr = np.concatenate([
                np.linspace(0.0, effective_R, rings + 1),
                [R],
            ])
        else:
            r_arr = np.linspace(0.0, R, rings + 1)
        n_rings = len(r_arr) - 1   # face rings 수

        theta = np.linspace(0.0, 2.0 * np.pi, seg, endpoint=False)
        Rm, Tm = np.meshgrid(r_arr, theta, indexing="ij")
        xs_all = (Rm * np.cos(Tm)).ravel()
        ys_all = (Rm * np.sin(Tm)).ravel()
        z_raw_all = rbf(np.column_stack([xs_all, ys_all]))

        # Z 범위 — 공통 스케일 모드 우선, 아니면 radial 평가값 기반
        if self._display.z_range is not None:
            vmin, vmax = self._display.z_range
        else:
            finite = z_raw_all[np.isfinite(z_raw_all)]
            if finite.size == 0:
                return
            vmin = float(finite.min())
            vmax = float(finite.max())
        z_range = vmax - vmin if vmax > vmin else 1.0

        # Z 과장 배율
        z_exag = chart3d.get("z_exaggeration", None)
        target_height = WAFER_RADIUS_MM * 0.4
        factor = (target_height / z_range) * (float(z_exag) if z_exag is not None else 1.0)

        cmap = resolve_colormap(common.get("colormap", "Turbo"))

        gview = self._gl_3d

        # 바닥 grid — 재사용
        if chart3d.get("show_grid", True):
            if self._gl_grid is None:
                self._gl_grid = gl.GLGridItem()
                self._gl_grid.setSize(x=320, y=320)
                self._gl_grid.setSpacing(x=50, y=50)
                self._gl_grid.setColor((205, 205, 205, 150))
                gview.addItem(self._gl_grid)
            self._gl_grid.setVisible(True)
        elif self._gl_grid is not None:
            self._gl_grid.setVisible(False)

        # radial mode 는 notch 를 mesh 에 반영하지 않음 (반경 분해능 부족으로 계단 모양).
        # notch 는 boundary line 에만 표시 (아래 _boundary_xy 참고).
        # per-angle effective r = R (notch 없음) - edge_cut
        eff_r_seg = np.full(seg, max(R - (edge_cut_mm if apply_cut else 0.0), 1.0), dtype=float)

        # Per-vertex cut mask — edge_cut 만 반영
        vert_theta_idx = np.arange(xs_all.size) % seg
        r_flat = np.sqrt(xs_all ** 2 + ys_all ** 2)
        cut_mask_all = r_flat > eff_r_seg[vert_theta_idx] + 1e-6

        # Radial surface mesh — pre-evaluated (xs_all, ys_all, z_raw_all) 재사용
        smooth = bool(chart3d.get("smooth", True))
        v_s, f_s, c_s = _build_radial_surface_mesh(
            xs_all, ys_all, z_raw_all, n_rings, seg,
            vmin, z_range, factor, cmap,
            cut_mask=cut_mask_all if cut_mask_all.any() else None,
        )
        # shader="shaded" — lighting 적용으로 smooth=True/False 차이 시각화
        # (shader 없으면 vertex color 그대로 → smooth 차이 안 보임)
        if self._gl_surface is None:
            self._gl_surface = gl.GLMeshItem(
                vertexes=v_s, faces=f_s, vertexColors=c_s,
                smooth=smooth, shader="shaded",
                drawEdges=False, glOptions="opaque",
            )
            gview.addItem(self._gl_surface)
        else:
            self._gl_surface.setMeshData(
                vertexes=v_s, faces=f_s, vertexColors=c_s, smooth=smooth,
            )
        self._gl_surface.setVisible(True)

        # Smooth cylinder wall — 각 angle 별 eff_r 에 배치 → notch 영역 안쪽으로 dip.
        wall_xs = eff_r_seg * np.cos(theta)
        wall_ys = eff_r_seg * np.sin(theta)
        wall_z_raw = rbf(np.column_stack([wall_xs, wall_ys]))
        v_w, f_w, c_w = _build_smooth_cylinder_wall(
            wall_xs, wall_ys, wall_z_raw, seg,
            vmin, z_range, factor, cmap,
        )
        if self._gl_wall is None:
            self._gl_wall = gl.GLMeshItem(
                vertexes=v_w, faces=f_w, vertexColors=c_w,
                smooth=True, shader="shaded",
                drawEdges=False, glOptions="opaque",
            )
            gview.addItem(self._gl_wall)
        else:
            self._gl_wall.setMeshData(
                vertexes=v_w, faces=f_w, vertexColors=c_w, smooth=True,
            )
        self._gl_wall.setVisible(True)

        # boundary line (재사용)
        if common.get("show_circle", True):
            bx, by = _boundary_xy(
                common.get("show_notch", True),
                float(common.get("notch_depth_mm", _NOTCH_DEFAULT_DEPTH_MM)),
                R=float(common.get("boundary_r_mm", WAFER_RADIUS_MM)),
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
            ("Average",   _fmt(m['avg'], decimals)),
            ("Range",     _fmt(m['range'], decimals)),
            ("Non Unif.", nu_s),
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
            s = settings_io.load_settings().get("chart_3d", {})
            dist = float(s.get("camera_distance", 550))
            from pyqtgraph import Vector
            if chart is self._gl_2d:
                chart.setCameraPosition(
                    pos=Vector(0, 0, 0),
                    distance=dist, elevation=90, azimuth=-90,
                )
            else:  # _gl_3d
                chart.setCameraPosition(
                    pos=Vector(0, 0, 0),
                    distance=dist, elevation=28, azimuth=-135,
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
