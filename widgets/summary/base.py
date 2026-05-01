"""
SummaryWidget 추상 클래스 + 공통 helper (사용자 정책 2026-04-30).

모든 style 은 이 인터페이스만 구현. wafer_cell 은 base 만 알고 dispatch.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtWidgets import QWidget


# 콤보 표시명 — 알파벳 prototype 라벨 그대로 사용 (사용자 정책 2026-04-30)
STYLE_DISPLAY_NAMES: dict[str, str] = {
    "ppt_basic":         "PPT Style (기본)",
    "stat_tiles":        "Stat Tiles",
    "highlight_lead":    "Highlight Lead",
    "minimal_underline": "Minimal Underline",
    "pill_badge":        "Pill Badge",
    "dark_neon":         "Dark Neon",
    "vertical_stack":    "Vertical Stack",
    "color_footer":      "Color Footer",
    "big_number":        "Big Number",
    "layered_depth":     "Rounded Card",
    "no_table":          "No Table",
}


def font_px(role: str) -> int:
    """role 기반 폰트 크기 (px). 현재 font_scale 자동 반영.

    base = FONT_SIZES['body'] (settings_dialog.apply_global_style 가 font_scale
    적용해 영구 갱신). 모든 style 이 hardcode 대신 이 함수 호출 → 한 곳에서
    일괄 조정 + font_scale 연동 (사용자 정책 2026-04-30).

    role 카탈로그:
      label_xs : 매우 작은 라벨 (대시보드 톤)
      label    : 보통 라벨
      value    : 표준 값 (ppt_basic / 일반)
      value_lg : 강조 값
      value_xl : 매우 큰 강조 값 (Big Number 류)
    """
    from core.themes import FONT_SIZES
    base = int(FONT_SIZES.get("body", 14))
    table = {
        "label_xs": max(7, base - 6),
        "label":    max(8, base - 4),
        "value":    base,
        "value_lg": base + 2,
        "value_xl": base + 4,
    }
    return table.get(role, base)


def fmt_value(v, decimals: int) -> str:
    """metric 값 포맷 — NaN/None → '—'."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{decimals}f}"


def dynamic_decimals(vmin: float, vmax: float, n_ticks: int = 5) -> int:
    """tick 간격 + range bucket 기반 자릿수 (cap 3).

    bucket 룰 (사용자 정책 2026-04-30 갱신):
      - range < 1     → 3 (GOF, K)
      - range < 10    → 2 (작은 스케일, NK)
      - range < 1000  → 1 (thickness, 일반 다중 wafer)
      - range >= 1000 → 0
    """
    if vmax <= vmin:
        return 0
    tick_step = (vmax - vmin) / max(n_ticks - 1, 1)
    range_val = vmax - vmin
    if tick_step <= 0 or range_val <= 0:
        return 2
    needed = max(0, -int(math.floor(math.log10(tick_step))))
    if range_val < 1.0:
        bucket = 3
    elif range_val < 10.0:
        bucket = 2
    elif range_val < 1000.0:
        bucket = 1
    else:
        bucket = 0
    return min(max(needed, bucket), 3)


def format_metrics(
    metrics: dict, decimals: int, percent_suffix: bool = True,
) -> tuple[str, str, str]:
    """{avg, range, nu_pct} → (Mean, Range, NU) 표시 문자열.

    각 style 이 동일 입력 처리하도록 base 에서 공통화.
    """
    nu = metrics.get("nu_pct", float("nan"))
    if isinstance(nu, float) and math.isnan(nu):
        nu_s = "—"
    elif percent_suffix:
        nu_s = f"{nu:.{decimals}f}%"
    else:
        nu_s = f"{nu / 100.0:.{decimals + 2}f}"
    return (
        fmt_value(metrics.get("avg"), decimals),
        fmt_value(metrics.get("range"), decimals),
        nu_s,
    )


class SummaryWidget(QWidget):
    """모든 Summary style 의 공통 base.

    크기 정책 (사용자 정책 2026-04-30 — table style 변경 시 cell 전체 크기
    불변 보장): wafer_cell 의 `_apply_chart_size` 가 setFixedWidth/Height
    호출. 각 style 이 자체 fixed size 정책으로 무시하면 안 됨 (target_w 만
    호출하면 강제 폭 적용).

    인터페이스:
      - update_metrics(m, decimals, percent_suffix): 값 갱신
      - set_target_width(w): wafer_cell 이 강제하는 폭. 모든 style 동일 수용.
      - get_natural_height(): wafer_cell 이 cell 전체 높이 계산할 때 참조.
        ppt_basic 의 ~50px 와 동일하면 cell 높이 변동 없음.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def update_metrics(
        self, metrics: dict, decimals: int, percent_suffix: bool = True,
    ) -> None:
        raise NotImplementedError

    def set_target_width(self, w: int) -> None:
        """wafer_cell 의 _apply_chart_size 에서 호출. setFixedWidth 디폴트."""
        self.setFixedWidth(w)

    def get_natural_height(self) -> int:
        """ppt_basic 기준값 — 다른 style 도 가능하면 동일 높이 따름.

        wafer_cell 이 setFixedHeight(get_natural_height()) 호출해 cell 전체
        세로 길이 일관 유지.
        """
        # ppt_basic: 2 row × 24 + frame ≈ 50px. 정확한 값은 _update_table 에서
        # resizeRowsToContents 후 계산되지만, base default 는 공통 추정치.
        return 50

    def fit_to_height(self, h: int) -> None:
        """wafer_cell 이 setFixedHeight(reserved) 후 호출. style 별 내부 layout
        이 reserved 안에 fit 되도록 후처리 — 다행 위젯 (vertical_stack) 의 행
        높이 재배분 등. default no-op (대부분 style 은 자연 sizeHint 로 충분).
        """
        return

    def is_chart_overlay_only(self) -> bool:
        """True 면 표 영역 안 그리고 cell 의 chart 좌상단 overlay 만 표시.

        no_table style 만 True. wafer_cell 이 SUMMARY_RESERVED_H=0 + chart overlay
        활성 (사용자 정책 2026-04-30).
        """
        return False

    def overlay_texts(self) -> tuple[str, str]:
        """is_chart_overlay_only True 인 style 만 의미. (Mean, NU) 문자열."""
        return "—", "—"
