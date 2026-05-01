"""
No Table style — 표 영역 완전 제거. 사용자 정책 2026-04-30.

선택 시 cell 의 표 영역이 사라지면서 cell 전체 세로 길이가 표 사라진 만큼
감소함. 대신 cell 의 chart 좌상단에 Mean / NU 만 작은 overlay 로 표시
(간단 출력 모드).

SummaryWidget 자체는 빈 위젯 (height 0). overlay 표시는 wafer_cell 이
이 widget 의 is_chart_overlay_only() True 보고 chart 위 QLabel 갱신.
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget

from widgets.summary.base import SummaryWidget, format_metrics


class SummaryNoTable(SummaryWidget):
    """빈 위젯 — 표 그리지 않음. metrics 는 wafer_cell 의 chart overlay 가 표시."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # 차지 공간 0 — wafer_cell 의 SUMMARY_RESERVED_H 0 결합으로 cell 전체
        # 세로 길이가 표 영역만큼 감소.
        self.setFixedHeight(0)
        # update_metrics 는 cell 이 직접 호출하지만 여기 보관해 cell 이 last_metrics
        # 조회 가능하게 함.
        self._last_avg: str = "—"
        self._last_range: str = "—"
        self._last_nu: str = "—"

    def update_metrics(self, metrics, decimals, percent_suffix=True):
        avg_s, range_s, nu_s = format_metrics(metrics, decimals, percent_suffix)
        self._last_avg = avg_s
        self._last_range = range_s
        self._last_nu = nu_s

    def set_target_width(self, w: int) -> None:
        self.setFixedWidth(w)
        self.setFixedHeight(0)

    def get_natural_height(self) -> int:
        return 0

    def is_chart_overlay_only(self) -> bool:
        """wafer_cell 이 chart 좌상단 overlay 표시 / SUMMARY_RESERVED_H=0 결정용."""
        return True

    def overlay_texts(self) -> tuple[str, str, str]:
        """현재 (Mean, Range, NU) 표시 문자열 — wafer_cell 이 overlay 라벨 갱신."""
        return self._last_avg, self._last_range, self._last_nu
