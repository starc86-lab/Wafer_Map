"""
Wafer Map 엔트리포인트.

실행:
    python app.py            # 일반 실행
    python app.py --selftest # 창을 잠깐 띄우고 자동 종료 (import·QSS 검증용)
"""
from __future__ import annotations

import os
import sys
import threading
import warnings

VERSION = "0.6.0"

# pyqtgraph MeshData.py 의 vertex normal 계산에서 degenerate face (zero-length
# normal) 로 인한 divide-by-zero RuntimeWarning 억제. radial mesh 의 센터 근처
# triangle 이 거의 평평하거나 공선일 때 발생. 렌더 결과엔 영향 없음.
warnings.filterwarnings(
    "ignore",
    message="invalid value encountered in divide",
    category=RuntimeWarning,
    module=r"pyqtgraph\.opengl\.MeshData",
)

# ────────────────────────────────────────────────────────────────
# UI scale (QHD/FHD/UHD) — QApplication 인스턴스 전 적용 필수.
# QT_SCALE_FACTOR 환경변수로 모든 widget / 폰트 / pixmap 일괄 비례.
# 사용자 정책 2026-05-01.
# ────────────────────────────────────────────────────────────────
def _apply_ui_scale() -> None:
    from core import settings as _settings_io
    from core.themes import UI_MODE_SCALE
    s = _settings_io.load_settings()
    mode = str(s.get("ui_mode", "auto") or "auto")
    if mode == "auto":
        # tkinter 로 primary monitor 가로 측정 (QApplication 와 독립)
        sw = 2560  # default = QHD
        try:
            import tkinter
            r = tkinter.Tk()
            r.withdraw()
            sw = int(r.winfo_screenwidth())
            r.destroy()
        except Exception:
            pass
        if sw < 2400:
            scale = UI_MODE_SCALE["FHD"]
        elif sw < 3200:
            scale = UI_MODE_SCALE["QHD"]
        else:
            scale = UI_MODE_SCALE["UHD"]
    elif mode in UI_MODE_SCALE:
        scale = UI_MODE_SCALE[mode]
    else:
        scale = 1.0
    # 내부 ui_mode 가 ground truth — scale==1.0 일 때 외부 env 가 잔존하면
    # 사용자 설정과 다른 scale 이 적용됨 (사용자 정책 2026-05-01).
    if scale != 1.0:
        os.environ["QT_SCALE_FACTOR"] = str(scale)
    else:
        os.environ.pop("QT_SCALE_FACTOR", None)


_apply_ui_scale()


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

    # 해상도 기반 기본 창 크기 준비 — RDP 재접속 등 edge case 에서 None 가능
    primary = QGuiApplication.primaryScreen()
    if primary is not None:
        screen = primary.availableGeometry()
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

    # Splash screen 닫기 (PyInstaller bundle 만 효과; dev 환경엔 pyi_splash 없음).
    # close() 가 multi-call / detach 후 호출 시 RuntimeError/AttributeError 가능 →
    # 광범위 except 로 앱 죽음 방지 (사용자 정책 2026-05-01).
    # 닫기 직전 우상단에 version + 저작권 텍스트 표시 (사용자 정책 2026-05-04).
    try:
        import pyi_splash  # type: ignore[import-not-found]
        pyi_splash.update_text(f"v{VERSION} © SK hynix")
        pyi_splash.close()
    except Exception:
        pass

    # 창 표시 후 warmup —
    #   - GUI 스레드: GL warmup → 다음 틱에 pyqtgraph widget warmup (단계 분할)
    #   - 백그라운드 스레드: scipy RBF + lazy 모듈 prefetch (Qt 무관 부분)
    def _step_gl() -> None:
        _gl_warmup()
        QTimer.singleShot(0, _pg_widget_warmup)

    threading.Thread(target=_bg_warmup, daemon=True).start()
    QTimer.singleShot(0, _step_gl)

    if "--selftest" in sys.argv:
        # 1.5초 후 자동 종료 — 뼈대 import/QSS/창 빌드 검증용
        QTimer.singleShot(1500, app.quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
