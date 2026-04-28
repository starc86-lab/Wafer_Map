"""
Run 결과 사유 표시 한 줄 widget.

Control 패널과 Result 패널 사이에 위치. Run 시도 후 시각화 가능 여부 / 차단 사유를
단일 채널로 표시 — 다이얼로그/상태표시줄 분산 대신 여기로 통일.

스타일은 전역 QSS (#reasonBar / #reasonBarTitle / #reasonBarLabel) 가 처리 — 테마
변경 시 자동 반영. severity 별 색은 dynamic property 로 QSS selector 매칭.
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel


class ReasonBar(QFrame):
    """한 줄 메시지 표시 바 — 좌측 'Message:' 라벨 + 사유 / 우측 액션 버튼.

    severity 4단계 — info / ok / warn / error. error 만 빨강, ok (정상 또는 fallback
    성공) 는 녹색 굵게, 그 외 theme text. 빈 warning 일 땐 ✓ 정상 표시
    (사용자 정책 2026-04-29).
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("reasonBar")
        # 높이 44px — Control 패널 버튼 행과 동일 (32px 버튼 + 위·아래 6px 패딩)
        self.setFixedHeight(44)

        self._lay = QHBoxLayout(self)
        # 좌·우 8px — paste_area / Control 패널 contents margin (8) 과 일치.
        # 위·아래 6px — Control 패널 버튼 padding 과 동일 → Run/Clear 위아래 여백.
        self._lay.setContentsMargins(8, 6, 8, 6)
        self._lay.setSpacing(6)

        self._title = QLabel("Message:")
        self._title.setObjectName("reasonBarTitle")
        self._lay.addWidget(self._title)

        self._label = QLabel("")
        self._label.setObjectName("reasonBarLabel")
        self._lay.addWidget(self._label)
        self._lay.addStretch(1)

        # 초기: 정상 (✓)
        self.set_warnings([])

    def add_right_widget(self, widget) -> None:
        """우측에 액션 위젯 추가 (Run / Clear 등)."""
        self._lay.addWidget(widget)

    def set_message(self, text: str, severity: str = "info") -> None:
        """severity → dynamic property 로 QSS color 매칭 (전역 QSS 가 색 결정).

        severity: 'info' / 'ok' / 'warn' / 'error'.
        """
        self._label.setText(text)
        self._label.setProperty("severity", severity)
        # property 변경은 QSS 재평가를 위해 polish() 필요
        st = self._label.style()
        if st is not None:
            st.unpolish(self._label)
            st.polish(self._label)

    def set_warnings(self, warnings: list) -> None:
        """ValidationWarning list 받아 가장 높은 severity 색으로 표시.

        빈 list → '✓' 정상 표시 (ok severity, 녹색 굵게). 여러 건이면 ", " join.
        ok severity 항목은 ⚠ prefix 없음 — 정상 동작 톤.
        """
        if not warnings:
            self.set_message("✓", "ok")
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
