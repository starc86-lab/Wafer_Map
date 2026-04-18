"""
Wafer Map 엔트리포인트.

실행:
    python app.py            # 일반 실행
    python app.py --selftest # 창을 잠깐 띄우고 자동 종료 (import·QSS 검증용)
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from core import runtime
from core import settings as settings_io
from widgets.main_window import MainWindow
from widgets.settings_dialog import apply_global_style


def main() -> int:
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

    if "--selftest" in sys.argv:
        # 1.5초 후 자동 종료 — 뼈대 import/QSS/창 빌드 검증용
        QTimer.singleShot(1500, app.quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
