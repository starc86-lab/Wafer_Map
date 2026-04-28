"""
Wafer Map 엔트리포인트.

실행:
    python app.py            # 일반 실행
    python app.py --selftest # 창을 잠깐 띄우고 자동 종료 (import·QSS 검증용)
"""
from __future__ import annotations

import sys
import warnings

VERSION = "0.3.0"

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
    """OpenGL 컨텍스트 사전 초기화 — 첫 3D 깜빡임 제거용 (GUI 스레드 필수)."""
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


def _pg_widget_warmup() -> None:
    """pyqtgraph widget 류 첫 호출 비용 흡수 (GUI 스레드 필수).

    PlotWidget / ImageItem / ColorMap 의 lazy 초기화. show + processEvents 로
    첫 paint 까지 강제 → 첫 Run Analysis 의 cell 별 lazy init 누적 흡수.
    """
    try:
        import numpy as np
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


def _bg_warmup() -> None:
    """백그라운드 스레드 — Qt widget 무관 부분만.

    scipy RBF dummy 호출 + 무거운 모듈 prefetch. 둘 다 numpy/scipy/lapack 같은
    C 확장 사용량 大 → GIL 풀려서 GUI 스레드 영향 거의 0. Qt widget 은 GUI
    스레드 전용이므로 절대 만지지 않음.
    """
    try:
        import numpy as np
        from scipy.interpolate import RBFInterpolator
        pts = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        vals = np.array([1.0, 2.0, 3.0, 4.0])
        rbf = RBFInterpolator(pts, vals, kernel="thin_plate_spline")
        rbf(np.array([[0.5, 0.5]]))
    except Exception:
        pass
    try:
        import core.interp  # noqa  — scipy.interpolate / scipy.signal 끌어옴 (가장 무거움)
        import core.delta   # noqa
        import widgets.preset_dialog        # noqa
        import widgets.settings_dialog      # noqa
        import widgets.coord_preview_dialog # noqa
        import widgets.preset_add_dialog    # noqa
    except Exception:
        pass


def _install_dialog_tracer() -> None:
    """모든 QDialog show()/exec() 호출 시 stderr 에 traceback 출력 (디버그).

    DELTA Run 시 정체불명 팝업 추적용 (사용자 보고 2026-04-28).
    원인 파악 후 제거.
    """
    import traceback
    from PySide6.QtWidgets import QDialog

    _orig_exec = QDialog.exec
    _orig_show = QDialog.show

    def _traced_exec(self):
        sys.stderr.write(
            f"\n[DIALOG-TRACE] exec({type(self).__name__}, "
            f"title={self.windowTitle()!r})\n"
        )
        traceback.print_stack(file=sys.stderr)
        sys.stderr.write("[DIALOG-TRACE] /end\n")
        return _orig_exec(self)

    def _traced_show(self):
        sys.stderr.write(
            f"\n[DIALOG-TRACE] show({type(self).__name__}, "
            f"title={self.windowTitle()!r})\n"
        )
        traceback.print_stack(file=sys.stderr)
        sys.stderr.write("[DIALOG-TRACE] /end\n")
        return _orig_show(self)

    QDialog.exec = _traced_exec
    QDialog.show = _traced_show


def _install_window_tracer(app) -> None:
    """모든 top-level QWidget 의 ShowEvent 추적 — "Python" 제목 미설정 창 잡기.

    QDialog 아닌 QWidget (예: GLViewWidget) 이 직접 native window 로 표시되는
    경우 추적. application-level event filter — 노이즈 적음 (top-level only).
    """
    import traceback
    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtWidgets import QWidget

    class _Tracer(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.Show and isinstance(obj, QWidget):
                if obj.isWindow():
                    # WA_DontShowOnScreen 인 경우는 노이즈라 제외
                    from PySide6.QtCore import Qt
                    if not obj.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen):
                        sys.stderr.write(
                            f"\n[WIN-TRACE] show({type(obj).__name__}, "
                            f"title={obj.windowTitle()!r}, "
                            f"size={obj.width()}x{obj.height()})\n"
                        )
                        traceback.print_stack(file=sys.stderr)
                        sys.stderr.write("[WIN-TRACE] /end\n")
            return False

    # app 자체에 보관 (GC 방지)
    app._win_tracer = _Tracer()
    app.installEventFilter(app._win_tracer)


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

    # 디버그: 모든 QDialog show/exec + top-level QWidget show 추적
    _install_dialog_tracer()
    _install_window_tracer(app)

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

    # 창 표시 후 warmup —
    #   - GUI 스레드: GL warmup → 다음 틱에 pyqtgraph widget warmup (단계 분할)
    #   - 백그라운드 스레드: scipy RBF + lazy 모듈 prefetch (Qt 무관 부분)
    # 이전 (단일 콜백 직렬 실행) 은 GUI 스레드 0.5~2s 점유 → 윈도우 응답성 저하.
    # 분할 + 병렬화로 GUI 스레드 점유 ~300ms 이하로 축소.
    # 환경변수 `WAFERMAP_BENCH=1` 설정 시 단계별 시간 stdout 출력.
    import os
    import threading
    import time
    bench = bool(os.environ.get("WAFERMAP_BENCH"))
    t_main = time.perf_counter()

    def _log(stage: str, t0: float) -> None:
        if bench:
            print(f"[startup] {stage}: {(time.perf_counter() - t0) * 1000:.0f}ms")

    def _step_pg() -> None:
        t0 = time.perf_counter()
        _pg_widget_warmup()
        _log("pg widget warmup (gui)", t0)

    def _step_gl() -> None:
        t0 = time.perf_counter()
        _gl_warmup()
        _log("gl warmup (gui)", t0)
        QTimer.singleShot(0, _step_pg)

    def _bg_thread() -> None:
        t0 = time.perf_counter()
        _bg_warmup()
        _log("bg warmup (thread)", t0)

    threading.Thread(target=_bg_thread, daemon=True).start()
    QTimer.singleShot(0, _step_gl)
    _log("main → exec (gui blocking)", t_main)

    if "--selftest" in sys.argv:
        # 1.5초 후 자동 종료 — 뼈대 import/QSS/창 빌드 검증용
        QTimer.singleShot(1500, app.quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
