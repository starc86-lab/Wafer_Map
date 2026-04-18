"""
Wafer Map 엔트리포인트.

실행:
    python app.py            # 일반 실행
    python app.py --selftest # 창을 잠깐 띄우고 자동 종료 (import·QSS 검증용)
"""
from __future__ import annotations

import sys

VERSION = "b0.0.0"

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from core import runtime
from core import settings as settings_io
from widgets.main_window import MainWindow
from widgets.settings_dialog import apply_global_style


def _gl_warmup() -> None:
    """앱 시작 시 OpenGL 컨텍스트/드라이버 초기화 비용을 미리 지불.

    첫 GLViewWidget이 생성되는 시점(= 사용자가 처음 3D 선택)에 발생하는
    화면 깜빡임을 제거. show 없이 setVisible(False)로 만들고 즉시 폐기.
    """
    try:
        import pyqtgraph.opengl as gl
        w = gl.GLViewWidget()
        w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        w.resize(8, 8)
        w.show()                # 컨텍스트 생성 트리거
        QApplication.processEvents()
        w.hide()
        w.deleteLater()
    except Exception:
        pass


def main() -> int:
    # GL 컨텍스트 공유 (warm-up 컨텍스트와 실제 셀들이 같은 자원 공유)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

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

    _gl_warmup()  # 첫 3D 깜빡임 제거: 윈도우 show 전에 OpenGL 컨텍스트 정착

    win = MainWindow()
    win.show()

    if "--selftest" in sys.argv:
        # 1.5초 후 자동 종료 — 뼈대 import/QSS/창 빌드 검증용
        QTimer.singleShot(1500, app.quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
