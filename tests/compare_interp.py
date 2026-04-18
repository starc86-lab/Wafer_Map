"""
4가지 보간 방법을 한 윈도우에 나란히 렌더해서 PNG 비교.

실행: python tests/compare_interp.py
저장: tests/output_compare_interp.png
"""
from __future__ import annotations

import sys, time
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8")
    except Exception: pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.coords import WAFER_RADIUS_MM, filter_in_wafer, normalize_to_mm
from core.interp import interpolate_wafer
from main import parse_wafer_csv


METHODS = ["cubic", "cubic_nearest", "phantom_ring", "rbf"]


def render_panel(x_in, y_in, v_in, method: str) -> QWidget:
    panel = QWidget()
    lay = QVBoxLayout(panel); lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(2)

    title = QLabel(f"method = {method}")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-weight: bold;")
    lay.addWidget(title)

    plot = pg.PlotWidget()
    plot.setBackground("w")
    plot.setAspectLocked(True)
    plot.setMinimumSize(360, 360)

    G = 200
    xg = np.linspace(-WAFER_RADIUS_MM, WAFER_RADIUS_MM, G)
    yg = np.linspace(-WAFER_RADIUS_MM, WAFER_RADIUS_MM, G)
    XG, YG = np.meshgrid(xg, yg, indexing="ij")
    ZG = interpolate_wafer(x_in, y_in, v_in, XG, YG, method=method)
    inside = XG * XG + YG * YG <= WAFER_RADIUS_MM * WAFER_RADIUS_MM
    ZG = np.where(inside, ZG, np.nan)

    img = pg.ImageItem(ZG)
    img.setRect(QRectF(-WAFER_RADIUS_MM, -WAFER_RADIUS_MM,
                       2 * WAFER_RADIUS_MM, 2 * WAFER_RADIUS_MM))
    cmap = pg.colormap.get("CET-L17") or pg.colormap.get("viridis")
    img.setLookupTable(cmap.getLookupTable())
    plot.addItem(img)

    theta = np.linspace(0, 2 * np.pi, 361)
    plot.plot(WAFER_RADIUS_MM * np.cos(theta), WAFER_RADIUS_MM * np.sin(theta),
              pen=pg.mkPen("k", width=2))
    plot.addItem(pg.ScatterPlotItem(
        x_in, y_in, pen=None, brush=pg.mkBrush(0, 0, 0, 220), size=4,
    ))
    lay.addWidget(plot, stretch=1)
    return panel


def main() -> int:
    app = QApplication.instance() or QApplication([])

    result = parse_wafer_csv("samples/sample_data.csv")
    wafer = next(iter(result.wafers.values()))  # 첫 웨이퍼 기준
    x_raw = wafer.parameters["X"].values
    y_raw = wafer.parameters["Y"].values
    v_raw = wafer.parameters["T1"].values
    x_mm, _ = normalize_to_mm(x_raw)
    y_mm, _ = normalize_to_mm(y_raw)
    x_in, y_in, v_in, _ = filter_in_wafer(x_mm, y_mm, np.asarray(v_raw, dtype=float))

    root = QWidget()
    root.resize(1600, 500)
    hl = QHBoxLayout(root); hl.setContentsMargins(4, 4, 4, 4); hl.setSpacing(6)
    for method in METHODS:
        hl.addWidget(render_panel(x_in, y_in, v_in, method))
    root.show()

    for _ in range(10):
        app.processEvents()
        time.sleep(0.05)

    out = Path("tests/output_compare_interp.png")
    root.grab().save(str(out))
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
