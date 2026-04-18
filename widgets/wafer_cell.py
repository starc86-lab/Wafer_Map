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
        self._gl_3d.setCameraPosition(distance=480, elevation=28, azimuth=135)
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
        # 캐시 — 한 번 그려진 모드는 재계산 없이 인덱스 토글만
        self._rendered_2d = False
        self._rendered_3d = False
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

    # ── 렌더 ────────────────────────────────────────
    def _render(self) -> None:
        d = self._display
        n = min(len(d.x_mm), len(d.y_mm), len(d.values))
        if n == 0:
            self._clear_chart()
            return
        x_mm = np.asarray(d.x_mm[:n], dtype=float)
        y_mm = np.asarray(d.y_mm[:n], dtype=float)
        v = np.asarray(d.values[:n], dtype=float)

        x_in, y_in, v_in, _ = filter_in_wafer(x_mm, y_mm, v)
        self._x_in, self._y_in, self._v_in = x_in, y_in, v_in

        # 데이터/설정이 바뀌었으니 양쪽 캐시 무효화
        self._rendered_2d = False
        self._rendered_3d = False
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
        """GLViewWidget 안의 모든 item 제거 (위젯 자체는 유지)."""
        for it in list(self._gl_3d.items):
            self._gl_3d.removeItem(it)

    def _interp_grid(self, x_in, y_in, v_in, common):
        """공통 보간: (XG, YG, ZG, inside, xg, yg) 반환."""
        G = int(common.get("grid_resolution", 200))
        xg = np.linspace(-WAFER_RADIUS_MM, WAFER_RADIUS_MM, G)
        yg = np.linspace(-WAFER_RADIUS_MM, WAFER_RADIUS_MM, G)
        XG, YG = np.meshgrid(xg, yg, indexing="ij")
        method = common.get("interp_method", "rbf")
        ZG = interpolate_wafer(x_in, y_in, v_in, XG, YG, method=method)
        inside = XG * XG + YG * YG <= WAFER_RADIUS_MM * WAFER_RADIUS_MM
        return XG, YG, ZG, inside, xg, yg

    def _render_2d(self, x_in, y_in, v_in, settings) -> None:
        common = settings.get("chart_common", {})
        chart = settings.get("chart_2d", {})
        XG, YG, ZG, inside, xg, yg = self._interp_grid(x_in, y_in, v_in, common)
        ZG = np.where(inside, ZG, np.nan)

        plot = self._plot_2d
        self._reset_2d_items()

        cmap_name = common.get("colormap", "CET-L17")
        img = pg.ImageItem(ZG)
        img.setRect(QRectF(
            -WAFER_RADIUS_MM, -WAFER_RADIUS_MM,
            2 * WAFER_RADIUS_MM, 2 * WAFER_RADIUS_MM,
        ))
        cmap = pg.colormap.get(cmap_name) or pg.colormap.get("viridis")
        img.setLookupTable(cmap.getLookupTable())
        plot.addItem(img)

        if common.get("show_circle", True):
            theta = np.linspace(0, 2 * np.pi, BOUNDARY_SEGMENTS)
            plot.plot(
                WAFER_RADIUS_MM * np.cos(theta),
                WAFER_RADIUS_MM * np.sin(theta),
                pen=pg.mkPen("k", width=2),
            )
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

        XG, YG, ZG, inside, xg, yg = self._interp_grid(x_in, y_in, v_in, common)

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
        cmap_name = common.get("colormap", "CET-L17")
        cmap = pg.colormap.get(cmap_name) or pg.colormap.get("viridis")
        lut = cmap.getLookupTable(0.0, 1.0, 256)  # (256, 4) ubyte
        norm = (ZG - vmin) / z_range
        norm = np.where(inside, norm, 0.0)
        idx_arr = np.clip((norm * 255).astype(int), 0, 255)
        colors = np.empty(ZG.shape + (4,), dtype=np.float32)
        colors[..., :3] = lut[idx_arr, :3] / 255.0
        colors[..., 3] = 1.0
        colors[~inside] = (1.0, 1.0, 1.0, 0.0)

        gview = self._gl_3d
        self._reset_3d_items()

        if chart3d.get("show_grid", True):
            grid = gl.GLGridItem()
            grid.setSize(x=350, y=350)
            grid.setSpacing(x=50, y=50)
            grid.setColor((140, 140, 140, 200))
            gview.addItem(grid)

        surf = gl.GLSurfacePlotItem(
            x=xg, y=yg, z=z_disp.astype(np.float32),
            colors=colors.reshape(-1, 4),
            shader=str(chart3d.get("shading", "shaded")),
            smooth=bool(chart3d.get("smooth", True)),
            computeNormals=True,
            glOptions="opaque",
        )
        gview.addItem(surf)

        if common.get("show_circle", True):
            theta = np.linspace(0, 2 * np.pi, BOUNDARY_SEGMENTS)
            circ = np.column_stack([
                WAFER_RADIUS_MM * np.cos(theta),
                WAFER_RADIUS_MM * np.sin(theta),
                np.zeros(BOUNDARY_SEGMENTS),
            ])
            # glOptions='opaque' → depth test ON, surface 뒤쪽 라인 가려짐
            line = gl.GLLinePlotItem(
                pos=circ, color=(0, 0, 0, 1), width=2,
                antialias=True, glOptions="opaque",
            )
            gview.addItem(line)

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
                chart.setCameraPosition(distance=480, elevation=28, azimuth=135)
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
