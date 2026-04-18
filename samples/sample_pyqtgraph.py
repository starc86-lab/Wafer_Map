"""
pyqtgraph 2D heatmap + 3D surface 샘플.
실행:
  python sample_pyqtgraph.py            → 창 2개 표시 (인터랙티브)
  python sample_pyqtgraph.py --save     → 창 띄우고 PNG 저장 후 자동 종료
PNG: output_pg2d.png, output_pg3d.png
"""
import sys
from pathlib import Path
import numpy as np
from scipy.interpolate import griddata
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtCore
import pyqtgraph.opengl as gl

from sample_data import make_wafer_points, WAFER_RADIUS

_DEBUG = Path(__file__).resolve().parent.parent / "debug"
_DEBUG.mkdir(exist_ok=True)


def build_surface_colors(z: np.ndarray, inside: np.ndarray) -> np.ndarray:
    """Surface 정점마다 컬러(0~1 float RGBA). 원 밖은 투명."""
    vmin = float(np.nanmin(z[inside]))
    vmax = float(np.nanmax(z[inside]))
    z_safe = np.where(np.isnan(z), vmin, z)
    norm = (z_safe - vmin) / (vmax - vmin + 1e-9)

    cmap = pg.colormap.get("CET-L17") or pg.colormap.get("viridis")
    lut = cmap.getLookupTable(0.0, 1.0, 256)  # (256, 4) ubyte

    idx = np.clip((norm * 255).astype(int), 0, 255)
    colors = np.empty(z.shape + (4,), dtype=np.float32)
    colors[..., :3] = lut[idx, :3] / 255.0
    colors[..., 3] = 1.0
    colors[~inside] = (1.0, 1.0, 1.0, 0.0)  # 투명
    return colors


def main():
    X, Y, V = make_wafer_points()

    G = 200
    xg = np.linspace(-WAFER_RADIUS, WAFER_RADIUS, G)
    yg = np.linspace(-WAFER_RADIUS, WAFER_RADIUS, G)
    XG, YG = np.meshgrid(xg, yg)
    ZG = griddata((X, Y), V, (XG, YG), method="cubic")
    inside = XG**2 + YG**2 <= WAFER_RADIUS**2

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    # ── 2D Heatmap ─────────────────────────────────────────────
    win2d = pg.PlotWidget(title="2D Heatmap (pyqtgraph)")
    win2d.setBackground("w")
    win2d.setAspectLocked(True)
    win2d.setLabel("bottom", "X (mm)")
    win2d.setLabel("left", "Y (mm)")

    ZG_masked = np.where(inside, ZG, np.nan)
    img = pg.ImageItem(ZG_masked)
    img.setRect(QtCore.QRectF(-WAFER_RADIUS, -WAFER_RADIUS,
                              2 * WAFER_RADIUS, 2 * WAFER_RADIUS))
    img.setLookupTable(pg.colormap.get("CET-L17").getLookupTable())
    win2d.addItem(img)

    theta = np.linspace(0, 2 * np.pi, 360)
    win2d.plot(WAFER_RADIUS * np.cos(theta), WAFER_RADIUS * np.sin(theta),
               pen=pg.mkPen("k", width=2))
    win2d.addItem(pg.ScatterPlotItem(
        X, Y, pen=None, brush=pg.mkBrush(0, 0, 0, 200), size=4))
    win2d.resize(640, 640); win2d.show()

    # ── 3D Surface (개선판) ─────────────────────────────────────
    gview = gl.GLViewWidget()
    gview.setWindowTitle("3D Surface (pyqtgraph.opengl)")
    gview.setBackgroundColor("w")
    gview.setCameraPosition(distance=480, elevation=28, azimuth=135)
    gview.resize(760, 640); gview.show()

    # 바닥 그리드 (공간감)
    grid = gl.GLGridItem()
    grid.setSize(x=350, y=350)
    grid.setSpacing(x=50, y=50)
    grid.setColor((140, 140, 140, 200))
    gview.addItem(grid)

    # Z 스케일을 X/Y(±150mm)와 균형 맞춤 → 0~80 범위로 과장
    vmin = float(np.nanmin(ZG[inside]))
    vmax = float(np.nanmax(ZG[inside]))
    z_render = (ZG - vmin) / (vmax - vmin + 1e-9) * 80.0
    z_render = np.where(inside, z_render, np.nan)

    colors = build_surface_colors(ZG, inside)

    surf = gl.GLSurfacePlotItem(
        x=xg, y=yg, z=z_render,
        colors=colors.reshape(-1, 4),
        smooth=True,
        computeNormals=True,          # 법선 계산 → shader='shaded'와 짝
        shader="shaded",              # 조명 → 입체감
        glOptions="opaque",
    )
    gview.addItem(surf)

    # 원 경계선 (3D 바닥)
    circle = gl.GLLinePlotItem(
        pos=np.column_stack([WAFER_RADIUS * np.cos(theta),
                              WAFER_RADIUS * np.sin(theta),
                              np.zeros_like(theta)]),
        color=(0, 0, 0, 1), width=2, antialias=True,
    )
    gview.addItem(circle)

    # Axis
    axis = gl.GLAxisItem()
    axis.setSize(x=150, y=150, z=80)
    gview.addItem(axis)

    # ── --save 플래그: 렌더 안정화 후 PNG 저장 + 종료 ──────────
    if "--save" in sys.argv:
        def save_and_quit():
            win2d.grab().save(str(_DEBUG / "output_pg2d.png"))
            gview.grabFramebuffer().save(str(_DEBUG / "output_pg3d.png"))
            print(f"Saved → {_DEBUG}/output_pg2d.png, output_pg3d.png")
            app.quit()
        QtCore.QTimer.singleShot(400, save_and_quit)
        app.exec()
    else:
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
