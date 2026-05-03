"""
Qt 글로벌 스타일시트 빌더.

`build_stylesheet(theme_dict, font_name)` 한 번 호출로 전역 QSS 문자열을 생성.
`QApplication.setStyleSheet(qss)` 로 전 위젯 일괄 적용.

Profile Vision stylesheet와 동일 규격 — 테마 dict의 키 구조가 같으면 호환.
"""
from __future__ import annotations

import os


def _generate_arrow_svg(direction: str, color: str, filename: str) -> None:
    """QScrollBar 양 끝 화살표 SVG (8×8) 를 assets/ 에 생성.

    Qt QSS 의 sub-control (`up-arrow` 등) 은 image 만 받음 — border 트릭 안 됨.
    Fusion 스타일의 native arrow 는 sub-line 을 QSS 로 스타일링하면 사라져서
    명시적 image url 이 필요.
    """
    if direction == "up":
        points = "4,1.5 7,6.5 1,6.5"
    elif direction == "down":
        points = "1,1.5 7,1.5 4,6.5"
    elif direction == "left":
        points = "1.5,4 6.5,1 6.5,7"
    elif direction == "right":
        points = "1.5,1 6.5,4 1.5,7"
    else:
        return
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8" '
        'viewBox="0 0 8 8">'
        f'<polygon points="{points}" fill="{color}"/></svg>'
    )
    os.makedirs("assets", exist_ok=True)
    path = os.path.join("assets", filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                if f.read() == svg:
                    return
        except Exception:
            pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)


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

    # 스크롤바 화살표 SVG 4종 — text 색 사용 (다크/라이트 자동 적응)
    arrow_color_hex = t["text"].replace("#", "")
    arrow_files = {}
    for direction in ("up", "down", "left", "right"):
        fn = f"arrow_{direction}_{arrow_color_hex}.svg"
        _generate_arrow_svg(direction, t["text"], fn)
        arrow_files[direction] = f"assets/{fn}"

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
QLabel:disabled {{ color: {t['text_sub']}; }}
/* QSpinBox / QDoubleSpinBox 기본 규칙 — `:disabled` 만 있으면 Qt 가 이 위젯을
   stylesheet-style 로 전환하며 Fusion native border 가 사라져 활성 상태에서도
   테두리가 안 보이는 버그. 기본 규칙을 명시해 전 상태 일관성 확보. */
QSpinBox, QDoubleSpinBox {{
    background-color: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 0px 6px;
    font-size: {F['small']}px;
    min-height: 26px;
    max-height: 26px;
}}
QSpinBox:disabled, QDoubleSpinBox:disabled,
QComboBox:disabled, QLineEdit:disabled {{
    background-color: {t['surface_alt']};
    color: {t['text_sub']};
    border: 1px solid {t['border']};
}}
QCheckBox:disabled {{ color: {t['text_sub']}; }}
QCheckBox::indicator:disabled {{
    background: {t['surface_alt']};
    border-color: {t['border']};
}}
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
    min-height: 28px;
    max-height: 28px;
}}
QPushButton:pressed {{
    border: 4px solid rgba(128,128,128,0.3);
    border-style: inset;
    padding-top: 4px;
}}
QPushButton[class="danger"]    {{ background-color: {t['danger']}; }}
QPushButton[class="secondary"] {{ background-color: {t['success']}; }}
QPushButton[class="primary"] {{
    background-color: {t.get('primary_btn', t['success'])};
    color: {t['bg']};
    padding: 0px 24px;
    font-size: {F['section']}px;
    letter-spacing: 0.5px;
}}
/* disabled state — Qt 가 stylesheet 적용 시 native palette disable 효과를
   무력화 → 명시 :disabled rule 필수. Run 처리 중 회색 표시 (사용자 정책 2026-05-02). */
QPushButton:disabled {{
    background-color: {t['surface_alt']};
    color: {t['text_sub']};
}}
QPushButton[class="primary"]:disabled,
QPushButton[class="secondary"]:disabled,
QPushButton[class="danger"]:disabled {{
    background-color: {t['surface_alt']};
    color: {t['text_sub']};
}}
/* QToolButton[class="icon"] — toolbar 의 정사각형 이모지 버튼 (도움말 / Settings).
   테마 변수 기반 — Light/Dark 자동 추종. enabled/disabled 무관 동일 외곽. */
QToolButton[class="icon"] {{
    padding: 0px;
    border: 1px solid {t['border']};
    border-radius: 4px;
    background: {t['surface']};
    color: {t['text']};
    font-size: 22px;
}}
QToolButton[class="icon"]:hover    {{ background: {t['surface_alt']}; }}
QToolButton[class="icon"]:pressed  {{ background: {t['header_bg']}; }}
QToolButton[class="icon"]:disabled {{ background: {t['surface']}; color: {t['text_sub']}; }}
QSplitter::handle {{ background-color: {t['border']}; }}
QScrollArea {{ background: transparent; border: none; }}
QDialog {{ background-color: {t['bg']}; color: {t['text']}; }}
/* ReasonBar — Control 패널과 Result 패널 사이의 메시지 한 줄 위젯.
   배경은 Control 패널과 동일 (theme bg). 사용자 정책 2026-05-04 —
   Control 사이 border-top 제거 (배경 통일로 시각 흐름 자연). 결과 영역과의
   border-bottom 만 유지. */
#reasonBar {{
    background-color: {t['bg']};
    border-bottom: 1px solid {t['border']};
}}
#reasonBarTitle, #reasonBarLabel {{
    color: {t['text']};
    background: transparent;
    font-size: 11px;
}}
/* DEBUG (사용자 정책 2026-05-04) — message 영역 차지 공간 확인용 흰색 배경.
   확인 후 원복 (transparent). */
#reasonBarLabel {{ background: #ffffff; }}
#reasonBarTitle {{ font-weight: bold; }}
#reasonBarLabel[severity="error"] {{ color: {t['danger']}; }}
#reasonBarLabel[severity="ok"]    {{ color: {t['success']}; font-weight: bold; }}
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
    padding: 0px 8px;
    font-size: {F['small']}px;
    min-height: 26px;
    max-height: 26px;
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
    padding: 1px 4px;
    color: {t['text']};
    background: transparent;
}}
/* cell 더블클릭 / F2 edit mode 시 사용되는 inline QLineEdit editor —
   글로벌 QLineEdit padding (4px 8px) 이 짧은 행 (22px) 에 비해 커서 위/아래
   contents 가 잘리는 회귀 fix (사용자 정책 2026-05-04). */
QTableWidget QLineEdit {{
    padding: 0px 4px;
    border: 1px solid {t['accent']};
    border-radius: 0px;
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
    padding: 2px 8px;
    font-size: {F['body']}px;
    font-weight: bold;
}}
/* 스크롤바 — 양 끝 화살표 버튼 + handle 최소 크기.
   대용량 데이터에서 thumb 가 너무 작아져도 화살표로 클릭 스크롤 가능. */
QScrollBar:horizontal {{
    background-color: {t['surface']};
    height: 14px;
    margin: 0 16px 0 16px;
}}
QScrollBar:vertical {{
    background-color: {t['surface']};
    width: 14px;
    margin: 16px 0 16px 0;
}}
QScrollBar::handle:horizontal {{
    background-color: {t['border']};
    border-radius: 5px;
    min-width: 25px;
}}
QScrollBar::handle:vertical {{
    background-color: {t['border']};
    border-radius: 5px;
    min-height: 25px;
}}
QScrollBar::sub-line:horizontal {{
    background: {t['surface_alt']};
    width: 16px; subcontrol-position: left;  subcontrol-origin: margin;
    border: 1px solid {t['border']};
}}
QScrollBar::add-line:horizontal {{
    background: {t['surface_alt']};
    width: 16px; subcontrol-position: right; subcontrol-origin: margin;
    border: 1px solid {t['border']};
}}
QScrollBar::sub-line:vertical {{
    background: {t['surface_alt']};
    height: 16px; subcontrol-position: top;    subcontrol-origin: margin;
    border: 1px solid {t['border']};
}}
QScrollBar::add-line:vertical {{
    background: {t['surface_alt']};
    height: 16px; subcontrol-position: bottom; subcontrol-origin: margin;
    border: 1px solid {t['border']};
}}
/* 양 끝 화살표 — 명시적 SVG (Fusion native 가 sub-line 스타일 시 사라짐) */
QScrollBar::up-arrow:vertical {{
    image: url({arrow_files['up']});
    width: 8px; height: 8px;
}}
QScrollBar::down-arrow:vertical {{
    image: url({arrow_files['down']});
    width: 8px; height: 8px;
}}
QScrollBar::left-arrow:horizontal {{
    image: url({arrow_files['left']});
    width: 8px; height: 8px;
}}
QScrollBar::right-arrow:horizontal {{
    image: url({arrow_files['right']});
    width: 8px; height: 8px;
}}
/* QSpinBox / QDoubleSpinBox — 화살표 SVG 통일 (스크롤바와 동일 자산).
   사용자 정책 2026-05-01 — 사내 환경 default arrow 안 보이는 회귀 fix. */
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    background: {t['surface_alt']};
    border-left: 1px solid {t['border']};
    border-bottom: 1px solid {t['border']};
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 16px;
    background: {t['surface_alt']};
    border-left: 1px solid {t['border']};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({arrow_files['up']});
    width: 8px; height: 8px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({arrow_files['down']});
    width: 8px; height: 8px;
}}
QStatusBar {{ background-color: {t['surface_alt']}; color: {t['text_sub']}; }}
QToolTip {{
    background-color: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['border']};
    padding: 4px 8px;
}}
QTabBar::tab {{
    padding: 6px 14px;
    font-size: {F['body']}px;
    font-weight: bold;
}}
QGroupBox::title {{
    font-weight: bold;
    subcontrol-origin: margin;
    left: 10px;
    padding: 0px 4px;
}}
"""
