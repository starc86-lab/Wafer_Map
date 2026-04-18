"""
matplotlib 2D contour + 3D surface 샘플.
실행: python sample_matplotlib.py
PNG 저장: output_mpl_2d.png, output_mpl_3d.png
"""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.tri import Triangulation
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

from sample_data import make_wafer_points, WAFER_RADIUS


def main():
    X, Y, V = make_wafer_points()

    # 2D contour
    fig2d, ax = plt.subplots(figsize=(6.5, 6))
    tri = Triangulation(X, Y)
    cs = ax.tricontourf(tri, V, levels=20, cmap="jet")
    theta = np.linspace(0, 2 * np.pi, 360)
    ax.plot(WAFER_RADIUS * np.cos(theta), WAFER_RADIUS * np.sin(theta),
            "k-", lw=2)
    ax.scatter(X, Y, c="k", s=6)
    ax.set_aspect("equal")
    ax.set_title(f"2D Contour (matplotlib) — N={len(X)}")
    ax.set_xlabel("X (mm)"); ax.set_ylabel("Y (mm)")
    plt.colorbar(cs, ax=ax, label="Thickness (Å)")
    fig2d.tight_layout()
    fig2d.savefig("output_mpl_2d.png", dpi=120)
    print("Saved: output_mpl_2d.png")

    # 3D surface
    fig3d = plt.figure(figsize=(7.5, 6))
    ax3 = fig3d.add_subplot(111, projection="3d")
    ax3.plot_trisurf(X, Y, V, cmap="jet", edgecolor="none", linewidth=0)
    ax3.set_title(f"3D Surface (matplotlib) — N={len(X)}")
    ax3.set_xlabel("X (mm)"); ax3.set_ylabel("Y (mm)"); ax3.set_zlabel("Thickness (Å)")
    fig3d.tight_layout()
    fig3d.savefig("output_mpl_3d.png", dpi=120)
    print("Saved: output_mpl_3d.png")

    plt.show()


if __name__ == "__main__":
    main()
