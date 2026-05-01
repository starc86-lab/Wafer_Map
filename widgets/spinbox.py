"""자유 입력 SpinBox — Qt 기본의 range 검사로 자릿수 막힘 회피.

Qt 의 `QAbstractSpinBox.validate()` 기본 동작은 입력 텍스트 → 값 변환 후 range
비교 → range 외면 `Invalid` 반환 → 키 입력 거부. 결과: range 0~200 spinbox 에
"300" 타이핑 시 "30" 까지만 받고 막힘 (사용자 보고 2026-05-02).

본 모듈의 `FlexSpinBox` / `FlexDoubleSpinBox` 는 `validate()` override 로
**range 검사 우회** — 숫자 파싱만 통과하면 항상 `Acceptable`. 최대 999_999_999
까지 자유 입력 허용. 확정 시점 (Enter / focus out / spin button) 에 Qt 의
`setMinimum`/`setMaximum` 가 자동 clamp + `setCorrectionMode(CorrectToNearestValue)`
가 표시 텍스트도 boundary 로 정정.

prefix / suffix 보존 — `"%"` suffix 등 spinbox 도 입력 도중 프리픽스/서픽스
포함된 텍스트로 들어와 strip 후 숫자 파싱.
"""
from __future__ import annotations

from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox


def _strip_fix(text: str, prefix: str, suffix: str) -> str:
    """spinbox display 텍스트에서 prefix / suffix 제거 후 strip."""
    s = text
    if prefix and s.startswith(prefix):
        s = s[len(prefix):]
    if suffix and s.endswith(suffix):
        s = s[:-len(suffix)]
    return s.strip()


class FlexSpinBox(QSpinBox):
    """정수 spinbox — range 외 입력도 자유 허용. 확정 시 clamp."""

    def validate(self, text, pos):  # noqa: D401
        s = _strip_fix(text, self.prefix(), self.suffix())
        if not s or s in ("-", "+"):
            return QValidator.State.Intermediate, text, pos
        try:
            int(s)
            return QValidator.State.Acceptable, text, pos
        except ValueError:
            return QValidator.State.Invalid, text, pos


class FlexDoubleSpinBox(QDoubleSpinBox):
    """소수 spinbox — range 외 입력도 자유 허용. 확정 시 clamp."""

    def validate(self, text, pos):  # noqa: D401
        s = _strip_fix(text, self.prefix(), self.suffix())
        if not s or s in ("-", "+", ".", "-.", "+."):
            return QValidator.State.Intermediate, text, pos
        try:
            float(s)
            return QValidator.State.Acceptable, text, pos
        except ValueError:
            return QValidator.State.Invalid, text, pos
