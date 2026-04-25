"""
Wafer Map 엔트리포인트.

실행:
    python app.py            # 일반 실행
    python app.py --selftest # 창을 잠깐 띄우고 자동 종료 (import·QSS 검증용)
"""
from __future__ import annotations

import sys
import warnings

VERSION = "0.2.0"

# pyqtgraph MeshData.py 의 vertex normal 계산에서 degenerate face (zero-length
# normal) 로 인한 divide-by-zero RuntimeWarning 억제. radial mesh 의 센터 근처
# triangle 이 거의 평평하거나 공선일 때 발생. 렌더 결과엔 영향 없음.
warnings.filterwarnings(
    "ignore",
    message="invalid value encountered in divide",
    category=RuntimeWarning,
    module=r"pyqtgraph\.opengl\.MeshData",
)

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


def _prefetch_lazy_modules() -> None:
    """창 표시 후 백그라운드로 무거운 모듈을 미리 import.

    `widgets.main_window` 가 module-level import 하지 않아 창 표시는 빨라지되,
    사용자가 첫 사용 (Run / Settings / Preset Dialog) 까지 보통 3초+ 걸리는
    틈에 미리 로드해 첫 사용 시 지연 0 보장.
    """
    try:
        import core.interp  # noqa  — scipy.interpolate / scipy.signal 끌어옴 (가장 무거움)
        import core.delta   # noqa
        import widgets.preset_dialog        # noqa
        import widgets.settings_dialog      # noqa
        import widgets.coord_preview_dialog # noqa
        import widgets.preset_add_dialog    # noqa
    except Exception:
        pass


def main() -> int:
    # Windows 작업표시줄 아이콘 표시 — AppUserModelID 명시 설정.
    # 미설정 시 dev 에서는 python.exe 의 AUMID 가 사용되어 Python 로고가 작업표시줄에
    # 표시됨. frozen exe 도 명시하면 동일 그룹 (다중 인스턴스 묶임) 보장.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "WaferMap.App"
            )
        except Exception:
            pass

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

    win = MainWindow()
    win.show()
    # Splash 가 닫히면서 메인 창이 다른 활성 창 뒤로 가려지는 문제 방지 —
    # 강제 foreground / focus.
    win.raise_()
    win.activateWindow()

    # Splash screen 닫기 (PyInstaller bundle 만 효과; dev 환경엔 pyi_splash 없음)
    try:
        import pyi_splash  # type: ignore[import-not-found]
        pyi_splash.close()
    except ImportError:
        pass

    # 창 표시 후 비동기로:
    # 1) GL/render warmup (lazy 초기화 비용 흡수)
    # 2) lazy 모듈 prefetch (사용자 첫 사용 시 지연 0)
    # 사용자 첫 사용까지 보통 2-3초+ 걸리니 그 안에 모두 완료.
    def _async_warmups() -> None:
        _gl_warmup()
        _render_warmup()
        _prefetch_lazy_modules()
    QTimer.singleShot(0, _async_warmups)

    if "--selftest" in sys.argv:
        # 1.5초 후 자동 종료 — 뼈대 import/QSS/창 빌드 검증용
        QTimer.singleShot(1500, app.quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
