"""
한 웨이퍼(또는 한 DELTA) 결과 = 2D heatmap + Summary 4행×2열 표 묶음.

`WaferDisplay` 를 받아 렌더. 단일 시각화와 DELTA 시각화가 공통 사용.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import pyqtgraph as pg
import pyqtgraph.opengl as gl
from PySide6.QtCore import QMimeData, QPoint, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QHeaderView, QLabel, QMenu,
    QStackedLayout, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
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


# ── 커스텀 컬러맵 — pyqtgraph 기본 목록에 없는 2-stop gradient ──────
# 이름은 core.themes.HEATMAP_COLORMAPS에 함께 등록. 값은 0..1 정규화 기준.
_CUSTOM_CMAPS: dict[str, pg.ColorMap] = {
    "Red-White":   pg.ColorMap([0.0, 1.0], [(255, 255, 255), (220,  30,  30)]),
    "Blue-White":  pg.ColorMap([0.0, 1.0], [(255, 255, 255), ( 30,  70, 220)]),
    "Black-White": pg.ColorMap([0.0, 1.0], [(255, 255, 255), ( 20,  20,  20)]),
    "Navy-White":  pg.ColorMap([0.0, 1.0], [(255, 255, 255), ( 20,  35, 110)]),
    "Pink-White":  pg.ColorMap([0.0, 1.0], [(255, 255, 255), (230,  70, 150)]),
    "Brown-White": pg.ColorMap([0.0, 1.0], [(255, 255, 255), (130,  75,  40)]),
    "Charcoal-White": pg.ColorMap([0.0, 1.0], [(255, 255, 255), ( 65,  70,  80)]),
}


def resolve_colormap(name: str) -> pg.ColorMap:
    """이름 → pg.ColorMap. 커스텀 dict 먼저, 없으면 pyqtgraph 기본. 최종 fallback은 viridis."""
    if name in _CUSTOM_CMAPS:
        return _CUSTOM_CMAPS[name]
    try:
        cm = pg.colormap.get(name)
        if cm is not None:
            return cm
    except Exception:
        pass
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


class WaferCell(QWidget):
    """2D heatmap + 4행×2열 Summary 표. 컨테이너 grab → Copy Graph 합성 이미지."""

    def __init__(
        self,
        display: WaferDisplay,
        value_name: str,
        view_mode: str = "2D",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._display = display
        self._value_name = value_name
        self._view_mode = view_mode  # "2D" | "3D"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        self._title = QLabel(display.title)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet("font-weight: bold;")
        lay.addWidget(self._title)

        # 차트 컨테이너 — 2D/3D 위젯 둘 다 미리 생성, QStackedLayout으로 인덱스만 토글
        # 효과: 토글 즉시 swap (위젯 파괴/생성 없음), 첫 3D 진입 시 깜빡임 제거
        self._chart_box = QWidget()
        self._chart_box.setMinimumSize(280, 280)
        self._chart_box_layout = QStackedLayout(self._chart_box)
        self._chart_box_layout.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._chart_box, stretch=1)

        self._plot_2d = pg.PlotWidget()
        self._plot_2d.setBackground("w")
        self._plot_2d.setAspectLocked(True)
        self._plot_2d.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._plot_2d.customContextMenuRequested.connect(self._show_plot_menu)
        self._chart_box_layout.addWidget(self._plot_2d)  # index 0

        self._gl_3d = gl.GLViewWidget()
        self._gl_3d.setBackgroundColor("w")
        self._gl_3d.setCameraPosition(distance=480, elevation=28, azimuth=-135)
        self._gl_3d.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._gl_3d.customContextMenuRequested.connect(self._show_plot_menu)
        self._chart_box_layout.addWidget(self._gl_3d)    # index 1

        self._chart_widget: QWidget = self._plot_2d  # 활성 위젯 추적

        self._table = QTableWidget(4, 2)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().hide()
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self._table.setFixedHeight(4 * 28 + 4)
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
        self._render()

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
        method = common.get("interp_method", "rbf")
        G = int(common.get("grid_resolution", 100))
        show_notch = bool(common.get("show_notch", True))
        depth = float(common.get("notch_depth_mm", _NOTCH_DEFAULT_DEPTH_MM))
        interp_key = (method, G)
        mask_key = (G, show_notch, depth)

        # 보간(RBF) — (method, G) 그대로면 ZG 재사용
        if self._interp_cache is None or self._interp_key != interp_key:
            xg = np.linspace(-WAFER_RADIUS_MM, WAFER_RADIUS_MM, G)
            yg = np.linspace(-WAFER_RADIUS_MM, WAFER_RADIUS_MM, G)
            XG, YG = np.meshgrid(xg, yg, indexing="ij")
            ZG = interpolate_wafer(x_in, y_in, v_in, XG, YG, method=method)
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

        cmap_name = common.get("colormap", "turbo")
        img = pg.ImageItem(ZG)
        img.setRect(QRectF(
            -WAFER_RADIUS_MM, -WAFER_RADIUS_MM,
            2 * WAFER_RADIUS_MM, 2 * WAFER_RADIUS_MM,
        ))
        cmap = resolve_colormap(cmap_name)
        img.setLookupTable(cmap.getLookupTable())
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
            tbl = settings.get("table", {})
            decimals = int(tbl.get("decimals", 3))
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

    def _render_3d(self, x_in, y_in, v_in, settings) -> None:
        common = settings.get("chart_common", {})
        chart3d = settings.get("chart_3d", {})

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
        cmap_name = common.get("colormap", "turbo")
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
        shader = str(chart3d.get("shading", "shaded"))
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
            self._surface_z_sig = z_sig
        elif self._surface_z_sig == z_sig:
            # z 동일 → colors만 교체 (normals 재계산 생략, smooth=True에서 큰 이득)
            # 단 setData(colors=only)는 pyqtgraph 내부에서 meshDataChanged 호출이
            # 빠져서 GPU에 반영 안 됨 → 명시 트리거 필요
            self._gl_surface.setData(colors=colors_flat)
            self._gl_surface.meshDataChanged()
        else:
            self._gl_surface.setData(x=xg, y=yg, z=z_f32, colors=colors_flat)
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

    def _update_table(self, v: np.ndarray, tbl_cfg: dict) -> None:
        decimals = int(tbl_cfg.get("decimals", 3))
        percent_suffix = bool(tbl_cfg.get("nu_percent_suffix", True))
        m = summary_metrics(v)

        nu = m["nu_pct"]
        if np.isnan(nu):
            nu_s = "—"
        elif percent_suffix:
            nu_s = f"{nu:.2f}%"
        else:
            nu_s = f"{nu / 100.0:.4f}"

        rows = [
            ("LOT ID / SLOT", self._display.meta_label),
            ("AVG / NU",      f"{_fmt(m['avg'], decimals)} / {nu_s}"),
            ("MIN ~ MAX",     f"{_fmt(m['min'], decimals)} ~ {_fmt(m['max'], decimals)}"),
            ("RANGE / 3SIG",  f"{_fmt(m['range'], decimals)} / {_fmt(m['sig3'], decimals)}"),
        ]
        for r, (label, value) in enumerate(rows):
            self._set_cell(r, 0, label)
            self._set_cell(r, 1, value)

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
        a_reset = menu.addAction("Reset Zoom")
        a_graph = menu.addAction("Copy Graph")
        a_data = menu.addAction("Copy Data")
        chosen = menu.exec(chart.mapToGlobal(pos))
        if chosen is a_reset:
            if isinstance(chart, pg.PlotWidget):
                chart.getPlotItem().enableAutoRange()
            elif isinstance(chart, gl.GLViewWidget):
                chart.setCameraPosition(distance=480, elevation=28, azimuth=-135)
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
        """MAP + Summary 표 합성 이미지를 클립보드에 PNG 로.

        3D(GLViewWidget)는 일반 grab 시 OpenGL 영역이 검게 나올 수 있으므로,
        framebuffer 를 별도로 떠서 동일 위치에 합성한다.
        """
        chart = self._chart_widget
        if isinstance(chart, gl.GLViewWidget):
            base = self.grab()
            try:
                fb_img: QImage = chart.grabFramebuffer()
            except Exception:
                fb_img = None
            if fb_img is not None and not fb_img.isNull():
                pixmap = QPixmap(base)
                pos = chart.mapTo(self, chart.rect().topLeft())
                painter = QPainter(pixmap)
                painter.drawImage(pos, fb_img)
                painter.end()
                QApplication.clipboard().setPixmap(pixmap)
                return
        QApplication.clipboard().setPixmap(self.grab())

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
