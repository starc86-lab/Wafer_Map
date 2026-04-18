"""
plotly 2D heatmap + 3D surface 샘플.
실행: python sample_plotly.py
HTML 저장: output_plotly_2d.html, output_plotly_3d.html
저장된 HTML을 브라우저로 열면 hover/회전/줌 인터랙션이 가능하다.
"""
import numpy as np
import plotly.graph_objects as go
from scipy.interpolate import griddata

from sample_data import make_wafer_points, WAFER_RADIUS


def main():
    X, Y, V = make_wafer_points()

    G = 150
    xg = np.linspace(-WAFER_RADIUS, WAFER_RADIUS, G)
    yg = np.linspace(-WAFER_RADIUS, WAFER_RADIUS, G)
    XG, YG = np.meshgrid(xg, yg)
    ZG = griddata((X, Y), V, (XG, YG), method="cubic")
    outside = XG**2 + YG**2 > WAFER_RADIUS**2
    ZG[outside] = np.nan

    # 2D
    fig2d = go.Figure()
    fig2d.add_trace(go.Heatmap(x=xg, y=yg, z=ZG, colorscale="Jet",
                               colorbar=dict(title="Thickness (Å)")))
    fig2d.add_trace(go.Scatter(x=X, y=Y, mode="markers",
                               marker=dict(size=4, color="black"),
                               showlegend=False, name="measured"))
    theta = np.linspace(0, 2 * np.pi, 360)
    fig2d.add_trace(go.Scatter(
        x=WAFER_RADIUS * np.cos(theta), y=WAFER_RADIUS * np.sin(theta),
        mode="lines", line=dict(color="black", width=2), showlegend=False,
    ))
    fig2d.update_layout(
        title=f"2D Heatmap (plotly) — N={len(X)}",
        width=720, height=720,
        xaxis_title="X (mm)", yaxis_title="Y (mm)",
    )
    fig2d.update_yaxes(scaleanchor="x", scaleratio=1)
    fig2d.write_html("output_plotly_2d.html", auto_open=False)
    print("Saved: output_plotly_2d.html")

    # 3D
    fig3d = go.Figure(data=[go.Surface(x=xg, y=yg, z=ZG, colorscale="Jet")])
    fig3d.update_layout(
        title=f"3D Surface (plotly) — N={len(X)}",
        width=820, height=720,
        scene=dict(xaxis_title="X (mm)", yaxis_title="Y (mm)",
                   zaxis_title="Thickness (Å)"),
    )
    fig3d.write_html("output_plotly_3d.html", auto_open=False)
    print("Saved: output_plotly_3d.html")
    try:
        fig2d.write_image("output_plotly_2d.png", width=720, height=720)
        fig3d.write_image("output_plotly_3d.png", width=820, height=720)
        print("Saved: output_plotly_2d.png, output_plotly_3d.png")
    except Exception as e:
        print(f"PNG export failed: {e}")


if __name__ == "__main__":
    main()
