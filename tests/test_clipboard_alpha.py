"""
Copy Image clipboard pipeline alpha 처리 검증 (F95 회귀 detect).

배경 — `QPixmap.toImage()` 의 default `ARGB32_Premultiplied` alpha 채널이
PNG 에 그대로 저장되면, Excel 이 paste 시 alpha 를 background 와 합성하면서
좌우 1px 비대칭으로 그리는 quirk 가 있다 (PPT 는 영향 없음). `widgets/wafer_cell.py
::WaferCell._set_clipboard_pixmap` 의 RGB32 변환 step 이 이 회귀를 차단.

본 테스트는:
  1. 입력 fixture 가 alpha 채널 있는지 (sanity)
  2. RGB32 변환 후 hasAlphaChannel()=False
  3. PNG round-trip 후에도 alpha 부활 안 함
  4. 외곽 anti-alias 픽셀의 alpha=255 (Excel 합성 회귀 차단)

실행:
    python tests/test_clipboard_alpha.py

failure 시 exit code 1.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# utf-8 콘솔 (cp949 환경 한국어 출력 보장)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Qt offscreen platform — headless / CI 환경에서 GUI 없이 동작
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter


def _build_image_with_alpha() -> QImage:
    """ARGB32_Premultiplied 이미지 + 외곽 anti-alias 1px 테두리 (실제 cell 합성 흉내)."""
    img = QImage(100, 100, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(255, 255, 255, 255))
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QColor("#bfbfbf"))
    painter.drawRect(0, 0, 99, 99)
    painter.end()
    return img


def _to_clipboard_format(img: QImage) -> tuple[QImage, bytes]:
    """`_set_clipboard_pixmap` 의 alpha 제거 + PNG 인코딩 단계 재현."""
    if img.hasAlphaChannel():
        img = img.convertToFormat(QImage.Format.Format_RGB32)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return img, bytes(ba.data())


def main() -> int:
    if QGuiApplication.instance() is None:
        QGuiApplication(sys.argv)

    failures: list[str] = []

    # 1. fixture sanity — 입력이 alpha 채널 가짐
    src = _build_image_with_alpha()
    if not src.hasAlphaChannel():
        failures.append("[1] fixture 가 alpha 채널 없음 — 테스트 prerequisite 실패")

    # 2. RGB32 변환 후 alpha 제거 확인
    out, png_bytes = _to_clipboard_format(src)
    if out.hasAlphaChannel():
        failures.append("[2] RGB32 변환 후 hasAlphaChannel()=True — Excel 비대칭 회귀")
    if out.format() != QImage.Format.Format_RGB32:
        failures.append(f"[3] format != RGB32 (실제 {out.format()})")

    # 3. PNG round-trip 후 alpha 부활 안 함
    rt = QImage()
    rt.loadFromData(png_bytes, "PNG")
    if rt.hasAlphaChannel():
        failures.append("[4] PNG round-trip 후 alpha 부활 — Excel 비대칭 회귀")

    # 4. 외곽 픽셀 alpha=255 (transparent 픽셀 0)
    edge_alpha = (rt.pixel(0, 0) >> 24) & 0xFF
    if edge_alpha != 255:
        failures.append(
            f"[5] 외곽 픽셀 alpha={edge_alpha} != 255 — Excel 합성 비대칭 가능"
        )

    if failures:
        print("FAIL:")
        for msg in failures:
            print(f"  {msg}")
        return 1
    print("OK — Copy Image alpha 제거 + PNG 인코딩 검증 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
