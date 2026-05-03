"""
도움말 카탈로그 + 브라우저 오픈 헬퍼.

방식 — `HELP_TEXTS` 7 토픽을 통합 HTML 한 페이지로 빌드 → 임시 파일 →
기본 브라우저로 오픈. 앱 내부 모달 다이얼로그 X.

규약 (사용자 정책 2026-04-27):
- `HELP_TEXTS` — 카탈로그. key → (title, html_body)
- `open_help_in_browser()` — Settings 의 [도움말] 버튼이 호출. 하나의 HTML 페이지에
  좌측 목차 + 우측 본문 (간단한 anchor 기반)
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import webbrowser
from pathlib import Path


def _help_assets_dir() -> Path:
    """`assets/help/` 절대 경로 — PyInstaller `_MEIPASS` 환경도 자동 인식.

    이 폴더에 PNG/JPG/SVG 등을 두고 HTML 본문에서
    `<img src="파일명.png">` 형식으로 참조 가능.
    """
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "help"
    return Path(__file__).resolve().parent.parent / "assets" / "help"


# ── 도움말 카탈로그 ─────────────────────────────────────────────
# 사용자 (SK hynix 엔지니어) 입장에서 "어떻게 사용하는지" 위주로 작성.
# 내부 구현 디테일 / 코드 모듈명 / 정책 변수명은 노출하지 않음.

HELP_TEXTS: dict[str, tuple[str, str]] = {
    # ─────────────────────────────────────────────────────────
    "intro": (
        "프로그램 소개",
        """
<h2>Wafer Map</h2>
<p><b>Film thickness</b> 측정 결과의 <b>MES Dcol Data</b> 를 <b>2D / 3D Map</b> 으로 시각화하는 프로그램.</p>


<h3>주요 특징</h3>
<ul>
  <li><b>초간단 입력</b> — <b>MES Dcol Data</b> 전체 선택 → <b>Ctrl+C</b>, 입력창에 <b>Ctrl+V</b>.</li>
  <li><b>초간단 출력</b> — Graph 우클릭 → <b>Copy Image</b>, PPT나 Excel 에 <b>Ctrl+V</b>.</li>
  <li><b>빠른 렌더링 속도</b> — 격자 Grid → Radial Mesh로 Wafer 영역만 Mesh 계산.</li>
  <li><b>높은 품질의 Graph</b> — MSAA 4x AA + 보간 알고리즘 4종 + Fitting 7종.</li>
</ul>
""",
    ),
    # ─────────────────────────────────────────────────────────
    "quickstart": (
        "Quick Guide",
        """
<h2>Quick Guide</h2>

<h3>1. 단일 시각화</h3>
<div style="display:flex; gap:12px; margin-bottom:12px;">
  <figure style="flex:1; margin:0; min-width:0;">
    <img src="1_mes_dcol_copy.png" alt="MES Dcol Copy"
         style="width:100%; height:240px; object-fit:contain; max-width:none;">
    <figcaption>Dcol Data 전체 Copy</figcaption>
  </figure>
  <figure style="flex:1; margin:0; min-width:0;">
    <img src="1_input_a_paste.png" alt="Input A Paste"
         style="width:100%; height:240px; object-fit:contain; max-width:none;">
    <figcaption>Input A 영역에 Paste</figcaption>
  </figure>
  <figure style="flex:1; margin:0; min-width:0;">
    <img src="1_result_main.png" alt="Run Result"
         style="width:100%; height:240px; object-fit:contain; max-width:none;">
    <figcaption>Run 버튼 클릭</figcaption>
  </figure>
</div>
<ol>
  <li><b>MES Dcol</b> 에서 측정 데이터 전체 선택 → <b>Ctrl+C</b>.</li>
  <li>앱의 <b>Input A</b> 영역에 <b>Ctrl+V</b>.</li>
  <li><b>Run</b> 클릭 → 결과 영역에 <b>Graph + Table</b> 표시.</li>
</ol>

<h3>2. Delta 시각화 (Pre - Post)</h3>
<ol>
  <li><b>Input A</b> 에 <b>Pre</b> 데이터 Paste.</li>
  <li><b>Input B</b> 에 <b>Post</b> 데이터 Paste.</li>
  <li><b>Run</b> 클릭 → <b>WAFERID</b> 가 같은 Wafer 끼리 자동 매칭 → <b>Δ = A − B</b> 계산.</li>
</ol>

<h3>3. Graph 구성</h3>
<div style="display:flex; gap:16px; align-items:flex-start; margin-bottom:12px;">
  <figure style="margin:0; flex-shrink:0;">
    <img src="2_graph.png" alt="Graph 영역"
         style="height:360px; width:auto; max-width:none;">
  </figure>
  <div style="flex:1;">
    <p>출력된 Graph는 다음 영역으로 구성:</p>
    <ul>
      <li><b>제목</b> — Lot.Slot – Parameter 이름.</li>
      <li><b>2D/3D Map</b> — 측정값을 색 또는 높이로 표현.</li>
      <li><b>컬러 스케일바</b> — 측정 결과의 스케일 표시.</li>
      <li><b>1D Radial Graph</b> — (옵션) 2D (x, y, v) 데이터를 <b>1D (r, v)</b> 로 변환한 Graph.</li>
      <li><b>Summary 표</b> — Mean / Range / Non Unif% 표시.</li>
    </ul>
    <p style="margin-top:12px;">Graph 우클릭 — Copy / Paste 메뉴:</p>
    <ul>
      <li><b>Reset</b> — Graph 크기, 위치 등을 초기 상태로 복원.</li>
      <li><b>Copy Image</b> — 출력 전체 이미지 Copy.</li>
      <li><b>Copy Data</b> — 측정값을 (X, Y, VALUE) 칼럼 형식의 표로 Copy.</li>
      <li><b>Copy Table</b> — Summary 표 Copy.</li>
    </ul>
  </div>
</div>

<h3>4. Graph 자유 조작 기능</h3>
<table border="1" cellpadding="6" cellspacing="0" width="70%">
  <tr style="background:#f0f0f0;"><th>조작</th><th>효과</th></tr>
  <tr><td>좌드래그</td><td>선택 Graph 만 회전</td></tr>
  <tr><td>Ctrl + 드래그</td><td>선택 Graph 만 이동</td></tr>
  <tr><td><b>Shift + 좌클릭 / 드래그</b></td><td><b>전체 Graph 동시 회전</b></td></tr>
  <tr><td><b>Shift + Ctrl + 드래그</b></td><td><b>전체 Graph 동시 이동</b></td></tr>
  <tr><td>휠</td><td>Zoom</td></tr>
</table>
""",
    ),
    # ─────────────────────────────────────────────────────────
    "features": (
        "주요 기능",
        """
<h2>주요 기능</h2>

<h3>1. 1D Radial Graph</h3>
<p>Wafer 중심으로부터의 거리 (r) 와 측정값 (v) 의 산점도 + Fitting 곡선 Graph.</p>
<ul>
  <li><b>산점도</b> — 실측 (r, v).</li>
  <li><b>라인</b> — 보간 Fitting 결과.</li>
</ul>

<h3>2. Etch Rate Map 변환 기능</h3>
<p>Delta 모드 Graph 상단의 <b>Time: [ ] sec</b> 입력란에 Time 입력 시,
<b>ΔTHK / Time</b> 으로 변환 → <b>ER Map</b> 으로 시각화.</p>
<ul>
  <li>각 Graph 별 개별 입력 또는 ☑ <b>전체 적용</b> 체크로 모든 Graph 동기화.</li>
  <li>공란 입력 → ER 모드 해제 (원본 표시).</li>
</ul>

<h3>3. r-symmetry mode</h3>
<p>일반 2D 측정 데이터를 <b>Radial Symmetry</b> 로 가정하여 처리 (같은 반경의 측정값을 동일하게 가정).</p>
<ul>
  <li>(r, v) 추출 → 1D Fitting → 원점 360° 회전 → 2D / 3D Map.</li>
  <li>CMP Map 처럼 Radial Symmetry 가 강한 측정 결과 시각화에 사용.</li>
</ul>

<h3>4. Δ-Interp mode</h3>
<p>Pre - Post 계산 시 양쪽 데이터의 좌표가 다른 경우 한쪽에만 있는 좌표점을 보간 처리하여 시각화.</p>
<ul>
  <li><b>비활성</b>: 한쪽에만 있는 점은 0 으로 가정.</li>
  <li><b>활성</b>: 빠진 쪽을 보간으로 채워 정상 Delta 계산.</li>
  <li>활성 시 Pre 측정점 55 개, Post 측정점 13 개인 경우도 Delta 정상 계산 가능.</li>
</ul>

<h3>5. 좌표 저장 기능</h3>
<p>매 분석마다 유효 좌표를 계측 <b>RECIPE</b> 와 함께 저장. 이후 <b>Dcol Data</b> 에
좌표가 누락된 경우 저장된 좌표를 사용.</p>
<ul>
  <li>좌표 직접 생성, 편집 및 삭제 가능.</li>
  <li>장기 미사용 좌표 자동 정리 기능.</li>
</ul>

<h3>6. Parameter 조합 기능</h3>
<p>서로 다른 Parameter 를 조합하여 하나로 시각화 가능.</p>
<ul>
  <li><b>T1 + T2 + T3</b> — 하부 Stack Layer 합산하여 Graph 출력 (<b>sum</b> 모드).</li>
  <li><b>T1 ∪ T1_A</b> — Wafer Inner, Wafer Edge 합쳐서 시각화 (<b>concat</b> 모드).</li>
</ul>
<p>좌표가 동일하면 <b>sum</b> (값 합산), 다르면 <b>concat</b> (점 집합 합집합) 자동 판정.</p>
""",
    ),
}


# ── 통합 HTML 페이지 빌드 + 브라우저 오픈 ──────────────────────

_PAGE_CSS = """
body { font-family: 'Segoe UI', sans-serif; max-width: 960px; margin: 0 auto;
       padding: 24px; color: #222; background: #fafafa; line-height: 1.55; }
h1 { color: #1a4d6e; border-bottom: 2px solid #1a4d6e; padding-bottom: 8px; }
h2 { color: #1a4d6e; margin-top: 36px; padding-top: 8px;
     border-top: 1px solid #d0d0d0; }
h3 { color: #2e5a7a; margin-top: 24px; }
table { border-collapse: collapse; margin: 8px 0 16px 0; width: 100%; }
table, th, td { border: 1px solid #aaa; }
th, td { padding: 8px 12px; text-align: left; vertical-align: top; }
th { background: #e8eef3; }
code { background: #eef2f5; padding: 2px 5px; border-radius: 3px;
       font-family: 'Consolas', 'Courier New', monospace; font-size: 0.92em; }
ul, ol { margin: 6px 0 14px 0; }
li { margin-bottom: 4px; }
.toc { background: #fff; border: 1px solid #d0d0d0; padding: 12px 24px;
       border-radius: 4px; margin-bottom: 24px; }
.toc ul { list-style: none; padding-left: 8px; }
.toc a { color: #1a4d6e; text-decoration: none; font-weight: bold; }
.toc a:hover { text-decoration: underline; }
img { max-width: 100%; height: auto; border: 1px solid #ccc;
      border-radius: 4px; margin: 8px 0; display: block; }
figure { margin: 12px 0; }
figcaption { font-size: 0.9em; color: #666; text-align: center;
             margin-top: 4px; font-style: italic; }
"""


def build_help_html() -> str:
    """모든 토픽을 하나의 HTML 페이지로 통합 — 목차 + 본문."""
    parts: list[str] = [
        "<!DOCTYPE html>",
        "<html lang='ko'><head><meta charset='utf-8'>",
        "<title>Wafer Map 도움말</title>",
        f"<style>{_PAGE_CSS}</style>",
        "</head><body>",
        "<h1>Wafer Map 도움말</h1>",
    ]

    # 목차
    parts.append("<div class='toc'><h3 style='margin-top:0'>목차</h3><ul>")
    for key, (title, _) in HELP_TEXTS.items():
        parts.append(f"<li><a href='#{key}'>{title}</a></li>")
    parts.append("</ul></div>")

    # 본문 — 각 토픽을 anchor 와 함께
    for key, (_title, body) in HELP_TEXTS.items():
        parts.append(f"<section id='{key}'>{body}</section>")

    parts.append("</body></html>")
    return "\n".join(parts)


def open_help_in_browser() -> None:
    """통합 도움말 HTML 을 임시 파일에 쓰고 기본 브라우저로 오픈.

    매 호출마다 새로 빌드 — `HELP_TEXTS` 변경 즉시 반영.

    이미지 처리: `assets/help/` 의 모든 파일을 같은 임시 폴더로 자동 복사 →
    HTML 본문에서 `<img src="파일명.png">` 형식으로 참조 가능 (상대 경로).
    PyInstaller 배포 시에도 동일하게 동작.
    """
    out_dir = Path(tempfile.gettempdir())
    src_dir = _help_assets_dir()
    if src_dir.exists():
        for f in src_dir.iterdir():
            if f.is_file():
                try:
                    shutil.copy2(f, out_dir / f.name)
                except OSError:
                    pass

    html = build_help_html()
    out = out_dir / "wafer_map_help.html"
    out.write_text(html, encoding="utf-8")
    webbrowser.open(out.as_uri())
