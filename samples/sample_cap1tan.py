"""
cap1tan/wafermap 샘플. die grid + 점 단위 플로팅 (연속 heatmap은 미지원).
HTML 출력 (folium 기반 zoomable map). PNG 저장은 선택 (headless Chrome 필요).
"""
from pathlib import Path
import numpy as np
import wafermap
import pyqtgraph as pg

from sample_data import make_wafer_points, WAFER_RADIUS

_DEBUG = Path(__file__).resolve().parent.parent / "debug"
_DEBUG.mkdir(exist_ok=True)


def value_to_hex(v, vmin, vmax, lut):
    norm = (v - vmin) / (vmax - vmin + 1e-9)
    idx = int(np.clip(norm * 255, 0, 255))
    r, g, b = lut[idx, 0], lut[idx, 1], lut[idx, 2]
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def main():
    X, Y, V = make_wafer_points()
    vmin, vmax = float(V.min()), float(V.max())
    lut = pg.colormap.get("CET-L17").getLookupTable(0.0, 1.0, 256)

    wm = wafermap.WaferMap(
        wafer_radius=WAFER_RADIUS,        # mm
        cell_size=(10.0, 10.0),           # die 크기 가정 (10mm × 10mm)
        edge_exclusion=0.0,
        coverage="full",
        notch_orientation=270.0,
    )

    for x, y, v in zip(X, Y, V):
        color = value_to_hex(v, vmin, vmax, lut)
        wm.add_point(
            cell=(0, 0),
            offset=(float(x), float(y)),
            point_style={
                "color": color,
                "fillColor": color,
                "fillOpacity": 1.0,
                "radius": 4,
                "weight": 1,
            },
        )

    wm.save_html(str(_DEBUG / "output_cap1tan_wafermap.html"))
    print(f"Saved → {_DEBUG}/output_cap1tan_wafermap.html")
    try:
        wm.save_png(str(_DEBUG / "output_cap1tan_wafermap.png"))
        print(f"Saved → {_DEBUG}/output_cap1tan_wafermap.png")
    except Exception as e:
        print(f"PNG save failed (headless Chrome 필요할 수도): {e}")


if __name__ == "__main__":
    main()
