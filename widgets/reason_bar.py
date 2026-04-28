"""
Run 결과 사유 표시 한 줄 widget.

Control 패널과 Result 패널 사이에 위치. Run 시도 후 시각화 가능 여부 / 차단 사유를
단일 채널로 표시 — 다이얼로그/상태표시줄 분산 대신 여기로 통일.

이번 단계는 디자인 확인용 widget 만 추가. 메시지 카탈로그 + severity 별 색 분기 +
호출자 통합 (`_on_visualize` 등) 은 다음 단계.
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

# 폰트 크기 — 사용자 정책 2026-04-28: 눈에 덜 띄도록 작게.
_FONT_PX = 11


class ReasonBar(QFrame):
    """한 줄 사유 표시 바."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("reasonBar")
        self.setFixedHeight(24)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(0)

        self._label = QLabel("")
        self._label.setStyleSheet(f"color: #111; font-size: {_FONT_PX}px;")
        lay.addWidget(self._label)
        lay.addStretch(1)

        # control 패널과 result 패널 사이의 시각적 구분
        self.setStyleSheet(
            "#reasonBar { background-color: #fafafa; "
            "border-top: 1px solid #d0d0d0; "
            "border-bottom: 1px solid #d0d0d0; }"
        )

    def set_message(self, text: str, severity: str = "info") -> None:
        """severity: 'info' / 'ok' / 'warn' (모두 검정) / 'error' (빨강).

        warn 도 검정으로 — 강렬한 주황은 눈에 너무 띔. 정말 시급한 차단 사유 (error)
        만 빨강. ⚠ 마크로 시각적 구분.
        """
        colors = {
            "info": "#111",
            "ok": "#111",
            "warn": "#111",
            "error": "#d32f2f",
        }
        self._label.setText(text)
        self._label.setStyleSheet(
            f"color: {colors.get(severity, '#111')}; font-size: {_FONT_PX}px;"
        )

    def set_warnings(self, warnings: list) -> None:
        """ValidationWarning list 받아 가장 높은 severity 색으로 표시.

        빈 list 면 빈 메시지 (라벨 비움). 여러 건이면 ", " 로 join.
        ok severity 는 정상 동작 알림이라 ⚠ prefix 안 붙임 — 경고 마크와 톤 충돌.
        """
        if not warnings:
            self.set_message("", "info")
            return

        def _fmt(w) -> str:
            return w.message if w.severity == "ok" else f"⚠ {w.message}"

        text = ", ".join(_fmt(w) for w in warnings)
        rank = {"info": 0, "ok": 1, "warn": 2, "error": 3}
        severity = max(
            (w.severity for w in warnings),
            key=lambda s: rank.get(s, 0),
            default="info",
        )
        self.set_message(text, severity)
