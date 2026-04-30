"""
Summary 위젯 카탈로그 — wafer_cell 의 표 영역 추상화 (사용자 정책 2026-04-30).

각 style 은 별도 모듈에 SummaryWidget 상속 클래스 1개. lazy import 로
선택된 style 모듈만 로드. wafer_cell 은 build_summary(style, ...) factory
한 번 호출 + 공통 인터페이스 (`update_metrics`, `set_target_size`) 만 사용.

추가/제거는 STYLES dict 와 단일 모듈 파일만 건드림. 다른 style 영향 0,
ppt_basic 절대 수정 X (회귀 보장).
"""
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from widgets.summary.base import SummaryWidget


# (module_path, class_name) — lazy import 하므로 여기 import 않음
STYLES: dict[str, tuple[str, str]] = {
    "ppt_basic":         ("widgets.summary.ppt_basic", "SummaryPPTBasic"),
    # Group 1 — QTableWidget 변형 (phase 2)
    "dark_neon":         ("widgets.summary.dark_neon", "SummaryDarkNeon"),
    "vertical_stack":    ("widgets.summary.vertical_stack", "SummaryVerticalStack"),
    "big_number":        ("widgets.summary.big_number", "SummaryBigNumber"),
    # Group 2 — 자유 layout (phase 3)
    "stat_tiles":        ("widgets.summary.stat_tiles", "SummaryStatTiles"),
    "highlight_lead":    ("widgets.summary.highlight_lead", "SummaryHighlightLead"),
    "minimal_underline": ("widgets.summary.minimal_underline", "SummaryMinimalUnderline"),
    "pill_badge":        ("widgets.summary.pill_badge", "SummaryPillBadge"),
    "color_footer":      ("widgets.summary.color_footer", "SummaryColorFooter"),
    # Group 3 — paintEvent (phase 4)
    "layered_depth":     ("widgets.summary.layered_depth", "SummaryLayeredDepth"),
    # Group 4 — overlay only (phase 5, 표 영역 제거 + chart 좌상단 표시)
    "no_table":          ("widgets.summary.no_table", "SummaryNoTable"),
}

DEFAULT_STYLE = "ppt_basic"


def available_styles() -> list[tuple[str, str]]:
    """(key, display_name) list — Settings 콤보 빌드용."""
    from widgets.summary.base import STYLE_DISPLAY_NAMES
    return [(k, STYLE_DISPLAY_NAMES.get(k, k)) for k in STYLES]


def build_summary(
    style: str | None = None,
    parent: "QWidget | None" = None,
) -> "SummaryWidget":
    """선택된 style 의 SummaryWidget 인스턴스 반환.

    잘못된 style 명 / 모듈 로드 실패 → ppt_basic fallback (안정성 보장).
    """
    key = style if style in STYLES else DEFAULT_STYLE
    mod_path, cls_name = STYLES[key]
    try:
        mod = importlib.import_module(mod_path)
        cls = getattr(mod, cls_name)
    except Exception:
        # safe fallback — ppt_basic 도 fail 하면 raise 그대로
        mod = importlib.import_module(STYLES[DEFAULT_STYLE][0])
        cls = getattr(mod, STYLES[DEFAULT_STYLE][1])
    return cls(parent=parent)
