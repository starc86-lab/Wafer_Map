"""
Run 결과 사유 표시 한 줄 widget.

Control 패널과 Result 패널 사이에 위치. Run 시도 후 시각화 가능 여부 / 차단 사유를
단일 채널로 표시 — 다이얼로그/상태표시줄 분산 대신 여기로 통일.

이번 단계는 디자인 확인용 widget 만 추가. 메시지 카탈로그 + severity 별 색 분기 +
호출자 통합 (`_on_visualize` 등) 은 다음 단계.
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel


class ReasonBar(QFrame):
    """한 줄 사유 표시 바."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("reasonBar")
        self.setFixedHeight(28)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(0)

        self._label = QLabel("[DUMMY] 사유 표시 채널 — Run 결과가 여기 표시됩니다")
        self._label.setStyleSheet("color: #666;")
        lay.addWidget(self._label)
        lay.addStretch(1)

        # control 패널과 result 패널 사이의 시각적 구분
        self.setStyleSheet(
            "#reasonBar { background-color: #fafafa; "
            "border-top: 1px solid #d0d0d0; "
            "border-bottom: 1px solid #d0d0d0; }"
        )

    def set_message(self, text: str, severity: str = "info") -> None:
        """severity: 'info'(회색) / 'ok'(민트) / 'warn'(주황) / 'error'(빨강)."""
        colors = {
            "info": "#666",
            "ok": "#2a9d8f",
            "warn": "#e76f51",
            "error": "#d32f2f",
        }
        self._label.setText(text)
        self._label.setStyleSheet(f"color: {colors.get(severity, '#666')};")

    def set_warnings(self, warnings: list) -> None:
        """ValidationWarning list 받아 가장 높은 severity 색으로 표시.

        빈 list 면 빈 메시지 (라벨 비움). 여러 건이면 ", " 로 join.
        """
        if not warnings:
            self.set_message("", "info")
            return
        text = ", ".join(f"⚠ {w.message}" for w in warnings)
        rank = {"info": 0, "ok": 1, "warn": 2, "error": 3}
        severity = max(
            (w.severity for w in warnings),
            key=lambda s: rank.get(s, 0),
            default="info",
        )
        self.set_message(text, severity)
