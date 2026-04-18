"""
pyvista 3D wafer surface 샘플. off_screen 렌더로 PNG 저장.
"""
from pathlib import Path
import numpy as np
from scipy.interpolate import griddata
import pyvista as pv

from sample_data import make_wafer_points, WAFER_RADIUS

_DEBUG = Path(__file__).resolve().parent.parent / "debug"
_DEBUG.mkdir(exist_ok=True)


def main():
    X, Y, V = make_wafer_points()

    G = 200
    xg = np.linspace(-WAFER_RADIUS, WAFER_RADIUS, G)
    yg = np.linspace(-WAFER_RADIUS, WAFER_RADIUS, G)
    XG, YG = np.meshgrid(xg, yg)
    ZG = griddata((X, Y), V, (XG, YG), method="cubic")
    inside = XG**2 + YG**2 <= WAFER_RADIUS**2

    vmin = float(np.nanmin(ZG[inside]))
    vmax = float(np.nanmax(ZG[inside]))
    Z_disp = (ZG - vmin) / (vmax - vmin + 1e-9) * 80.0
    Z_disp = np.where(inside, Z_disp, 0.0)

    # StructuredGrid — 원 밖은 0 높이 + 투명 처리 대신 clip
    grid = pv.StructuredGrid(XG, YG, Z_disp)
    grid["thickness"] = ZG.T.ravel()
    # 원 내부만 추출
    r2 = (XG**2 + YG**2).T.ravel()
    ids = np.where(r2 <= WAFER_RADIUS**2)[0]
    grid_in = grid.extract_points(ids, adjacent_cells=False)

    p = pv.Plotter(off_screen=True, window_size=(760, 640))
    p.set_background("white")
    p.add_mesh(
        grid_in,
        scalars="thickness",
        cmap="viridis",
        smooth_shading=True,
        show_scalar_bar=True,
        scalar_bar_args={"title": "Thickness (A)"},
    )

    # 원 경계
    theta = np.linspace(0, 2 * np.pi, 361)
    circ = np.column_stack([
        WAFER_RADIUS * np.cos(theta),
        WAFER_RADIUS * np.sin(theta),
        np.zeros(361),
    ])
    p.add_mesh(pv.lines_from_points(circ), color="black", line_width=2)

    # 카메라
    p.camera_position = [(450, -450, 260), (0, 0, 40), (0, 0, 1)]
    p.screenshot(str(_DEBUG / "output_pyvista_3d.png"))
    p.close()
    print(f"Saved → {_DEBUG}/output_pyvista_3d.png")


if __name__ == "__main__":
    main()
