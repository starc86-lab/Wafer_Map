"""
vispy 3D wafer surface 샘플. Mesh visual에 vertex_colors를 직접 주는 방식.
"""
import numpy as np
from scipy.interpolate import griddata
from PIL import Image

from vispy import app as vp_app, scene
from vispy.scene import visuals
from vispy.color import get_colormap

from sample_data import make_wafer_points, WAFER_RADIUS

vp_app.use_app("pyside6")


def main():
    X, Y, V = make_wafer_points()

    G = 200
    xg = np.linspace(-WAFER_RADIUS, WAFER_RADIUS, G)
    yg = np.linspace(-WAFER_RADIUS, WAFER_RADIUS, G)
    XG, YG = np.meshgrid(xg, yg, indexing="ij")
    ZG = griddata((X, Y), V, (XG, YG), method="cubic")
    inside = XG**2 + YG**2 <= WAFER_RADIUS**2

    vmin = float(np.nanmin(ZG[inside]))
    vmax = float(np.nanmax(ZG[inside]))
    Z_disp = np.where(inside, (ZG - vmin) / (vmax - vmin + 1e-9) * 80.0, 0.0)

    cmap = get_colormap("viridis")
    norm = np.where(inside, (ZG - vmin) / (vmax - vmin + 1e-9), 0.0)
    vertex_colors = cmap.map(norm.ravel()).astype(np.float32)

    # 정점 & faces (격자 → 삼각형 2개씩)
    vertices = np.column_stack([XG.ravel(), YG.ravel(), Z_disp.ravel()])
    i, j = np.meshgrid(np.arange(G - 1), np.arange(G - 1), indexing="ij")
    idx0 = (i * G + j).ravel()
    idx1 = (i * G + j + 1).ravel()
    idx2 = ((i + 1) * G + j).ravel()
    idx3 = ((i + 1) * G + j + 1).ravel()
    faces = np.vstack([
        np.column_stack([idx0, idx1, idx2]),
        np.column_stack([idx1, idx3, idx2]),
    ]).astype(np.uint32)

    # 원 내부 faces만
    inside_flat = inside.ravel()
    face_mask = (inside_flat[faces[:, 0]]
                 & inside_flat[faces[:, 1]]
                 & inside_flat[faces[:, 2]])
    faces = faces[face_mask]

    canvas = scene.SceneCanvas(keys="interactive", bgcolor="white",
                               size=(760, 640), show=True)
    view = canvas.central_widget.add_view()
    view.camera = scene.TurntableCamera(elevation=28, azimuth=135,
                                        distance=500, fov=45)

    mesh = visuals.Mesh(
        vertices=vertices, faces=faces,
        vertex_colors=vertex_colors,
        shading="smooth",
    )
    view.add(mesh)

    theta = np.linspace(0, 2 * np.pi, 361)
    circle = visuals.Line(
        pos=np.column_stack([WAFER_RADIUS * np.cos(theta),
                              WAFER_RADIUS * np.sin(theta),
                              np.zeros(361)]),
        color="black", width=2, antialias=True,
    )
    view.add(circle)

    canvas.update()
    vp_app.process_events()
    img = canvas.render(alpha=False)
    Image.fromarray(img).save("output_vispy_3d.png")
    print("Saved: output_vispy_3d.png")


if __name__ == "__main__":
    main()
