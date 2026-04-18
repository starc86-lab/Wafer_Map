"""
Qt 글로벌 스타일시트 빌더.

`build_stylesheet(theme_dict, font_name)` 한 번 호출로 전역 QSS 문자열을 생성.
`QApplication.setStyleSheet(qss)` 로 전 위젯 일괄 적용.

Profile Vision stylesheet와 동일 규격 — 테마 dict의 키 구조가 같으면 호환.
"""
from __future__ import annotations

import os


def _generate_check_svg(color: str, filename: str) -> None:
    """QCheckBox::indicator:checked 에 쓸 체크마크 SVG를 assets/에 생성."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 18 18">'
        f'<polyline points="4,9 8,13 14,5" fill="none" stroke="{color}" '
        f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )
    os.makedirs("assets", exist_ok=True)
    path = os.path.join("assets", filename)
    # 이미 있고 내용이 같으면 재작성 생략
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                if f.read() == svg:
                    return
        except Exception:
            pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)


def build_stylesheet(t: dict, font: str) -> str:
    """테마 팔레트 dict + 폰트명 → 전역 Qt QSS 문자열."""
    from core.themes import FONT_SIZES as F

    check_filename = f"check_{t['accent'].replace('#','')}.svg"
    _generate_check_svg(t["accent"], check_filename)

    # accent hex → rgba (QSS 반투명 배경용)
    ac = t["accent"].lstrip("#")
    r, g, b = int(ac[:2], 16), int(ac[2:4], 16), int(ac[4:6], 16)

    return f"""
QMainWindow {{ background-color: {t['bg']}; }}
QWidget {{
    background-color: {t['bg']};
    color: {t['text']};
    font-family: '{font}', sans-serif;
    font-size: {F['body']}px;
}}
QLabel {{ background: transparent; }}
QListWidget {{
    background-color: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    font-size: {F['subtitle']}px;
    padding: 4px;
}}
QListWidget::item {{ padding: 4px 8px; border-radius: 4px; min-height: 24px; }}
QListWidget::item:selected {{ background-color: rgba({r},{g},{b},80); color: {t['text']}; }}
QLineEdit, QPlainTextEdit, QTextEdit {{
    background-color: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 4px 8px;
}}
QPushButton {{
    background-color: {t['accent']};
    color: {t['bg']};
    border: none;
    border-radius: 6px;
    padding: 0px 16px;
    font-size: {F['body']}px;
    font-weight: bold;
    min-height: 32px;
    max-height: 32px;
}}
QPushButton:pressed {{
    border: 4px solid rgba(128,128,128,0.3);
    border-style: inset;
    padding-top: 4px;
}}
QPushButton[class="danger"]    {{ background-color: {t['danger']}; }}
QPushButton[class="secondary"] {{ background-color: {t['success']}; }}
QSplitter::handle {{ background-color: {t['border']}; }}
QScrollArea {{ background: transparent; border: none; }}
QDialog {{ background-color: {t['bg']}; color: {t['text']}; }}
QCheckBox {{ background: transparent; spacing: 8px; font-size: {F['small']}px; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 4px;
    border: 2px solid {t['border']}; background: {t['surface']};
}}
QCheckBox::indicator:checked {{
    background: {t['surface']};
    border-color: {t['accent']};
    image: url(assets/{check_filename});
}}
QComboBox {{
    background-color: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 4px 8px;
    font-size: {F['small']}px;
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background-color: {t['surface']};
    color: {t['text']};
    selection-background-color: {t['surface_alt']};
}}
QMenu {{
    background-color: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['border']};
    padding: 4px 0px;
}}
QMenu::item         {{ padding: 6px 18px; background: transparent; }}
QMenu::item:selected{{ background-color: {t['accent']}; color: {t['bg']}; }}
QMenu::item:disabled{{ color: {t['text_sub']}; }}
QTableWidget {{
    background-color: {t['surface']};
    color: {t['text']};
    alternate-background-color: {t['surface_alt']};
    selection-background-color: rgba({r},{g},{b},90);
    selection-color: {t['text']};
    border: 1px solid {t['border']};
    gridline-color: {t['border']};
    font-size: {F['body']}px;
}}
QTableWidget::item {{
    padding: 4px;
    color: {t['text']};
    background: transparent;
}}
QTableWidget::item:selected {{
    background-color: rgba({r},{g},{b},90);
    color: {t['text']};
}}
QTableCornerButton::section {{
    background-color: {t['header_bg']};
    border: 1px solid {t['border']};
}}
QHeaderView::section {{
    background-color: {t['header_bg']};
    border: 1px solid {t['border']};
    padding: 4px 8px;
    font-size: {F['body']}px;
    font-weight: bold;
}}
QScrollBar:horizontal {{ background-color: {t['surface']}; height: 10px; }}
QScrollBar::handle:horizontal {{ background-color: {t['border']}; border-radius: 5px; }}
QScrollBar:vertical   {{ background-color: {t['surface']}; width: 10px; }}
QScrollBar::handle:vertical   {{ background-color: {t['border']}; border-radius: 5px; }}
QStatusBar {{ background-color: {t['surface_alt']}; color: {t['text_sub']}; }}
QToolTip {{
    background-color: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['border']};
    padding: 4px 8px;
}}
"""
