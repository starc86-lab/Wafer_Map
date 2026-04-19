"""
Wafer Map 엔트리포인트.

실행:
    python app.py            # 일반 실행
    python app.py --selftest # 창을 잠깐 띄우고 자동 종료 (import·QSS 검증용)
"""
from __future__ import annotations

import sys

VERSION = "0.1.0"

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QSurfaceFormat
from PySide6.QtWidgets import QApplication

from core import runtime
from core import settings as settings_io
from widgets.main_window import MainWindow
from widgets.settings_dialog import apply_global_style


def _gl_warmup() -> None:
    """OpenGL 컨텍스트 사전 초기화 — 첫 3D 깜빡임 제거용."""
    try:
        import pyqtgraph.opengl as gl
        w = gl.GLViewWidget()
        w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        w.resize(8, 8)
        w.show()
        QApplication.processEvents()
        w.hide()
        w.deleteLater()
    except Exception:
        pass


def _render_warmup() -> None:
    """pyqtgraph / scipy 의 lazy 초기화 비용을 앱 시작 시점에 흡수.

    첫 Run Analysis에서 발생하던 cell 순차 생성 느낌(cell 하나씩 나타남)은
    이 lib들의 첫 호출 cost가 cell마다 누적되어 발생. 여기서 미리 한 번 돌려
    이후 Run Analysis는 두 번째 실행부터와 동일한 속도로 시작.
    """
    import numpy as np
    try:
        # pyqtgraph — PlotWidget / ImageItem / ColorMap 첫 사용 준비
        import pyqtgraph as pg
        pw = pg.PlotWidget()
        pw.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        pw.resize(8, 8)
        img = pg.ImageItem(np.zeros((8, 8), dtype=np.float32))
        pw.addItem(img)
        cm = pg.colormap.get("turbo")
        img.setLookupTable(cm.getLookupTable(0.0, 1.0, 32))
        pw.show()
        QApplication.processEvents()
        pw.hide()
        pw.deleteLater()
    except Exception:
        pass
    try:
        # scipy RBF — 첫 호출 JIT/초기화 비용 흡수
        from scipy.interpolate import RBFInterpolator
        pts = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        vals = np.array([1.0, 2.0, 3.0, 4.0])
        rbf = RBFInterpolator(pts, vals, kernel="thin_plate_spline")
        rbf(np.array([[0.5, 0.5]]))
    except Exception:
        pass


def main() -> int:
    # GL 컨텍스트 공유 (warm-up 컨텍스트와 실제 셀들이 같은 자원 공유)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    # 3D GLViewWidget 전역 4x MSAA — 경계선·surface edge·grid line 계단 제거
    # (표시 + grabFramebuffer 둘 다 효과). 반드시 첫 GL 위젯 생성 전에 호출
    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 해상도 기반 기본 창 크기 준비
    screen = QGuiApplication.primaryScreen().availableGeometry()
    runtime.update_screen_max(screen.width(), screen.height())

    # 설정 로드 + QSS 적용 (theme / font / font_scale 반영)
    s = settings_io.load_settings()
    apply_global_style(app, s)

    # QColorDialog custom colors 복원 (실패해도 앱 진행)
    try:
        settings_io.apply_custom_colors_to_dialog(settings_io.load_custom_colors())
    except Exception:
        pass

    _gl_warmup()      # OpenGL 컨텍스트 정착
    _render_warmup()  # pyqtgraph/scipy lazy 초기화 → 첫 Run Analysis가 2번째와 동속

    win = MainWindow()
    win.show()

    if "--selftest" in sys.argv:
        # 1.5초 후 자동 종료 — 뼈대 import/QSS/창 빌드 검증용
        QTimer.singleShot(1500, app.quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
