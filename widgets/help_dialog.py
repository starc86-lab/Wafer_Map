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
import tempfile
import webbrowser
from pathlib import Path


# ── 도움말 카탈로그 ─────────────────────────────────────────────
# 사용자 (SK hynix 엔지니어) 입장에서 "어떻게 사용하는지" 위주로 작성.
# 내부 구현 디테일 / 코드 모듈명 / 정책 변수명은 노출하지 않음.

HELP_TEXTS: dict[str, tuple[str, str]] = {
    # ─────────────────────────────────────────────────────────
    "input": (
        "입력 방법",
        """
<h2>입력 방법</h2>
<p>측정 데이터를 <b>Ctrl+C → Ctrl+V</b> 로 붙여넣어 사용합니다.</p>

<h3>1. 단일 시각화</h3>
<ol>
  <li>장비/Excel 에서 측정 데이터 전체 선택 → <b>Ctrl+C</b></li>
  <li>앱의 <b>Input A</b> 영역에 <b>Ctrl+V</b></li>
  <li>VALUE / 좌표(X/Y) 콤보가 자동 선택됨 (필요 시 수동 변경)</li>
  <li><b>Run Analysis</b> 클릭 → 결과 패널에 MAP + Summary 표 표시</li>
</ol>

<h3>2. Pre-Post DELTA 시각화</h3>
<p>예: ETCH 전 두께(Pre) − ETCH 후 두께(Post) = ΔTHK</p>
<ol>
  <li><b>Input A</b> 에 Pre 데이터 paste</li>
  <li><b>Input B</b> 에 Post 데이터 paste</li>
  <li>WAFERID 가 같은 wafer 끼리 자동 매칭 → <b>Δ = A − B</b> 계산</li>
  <li>좌표가 정확히 일치하지 않아도 1mm 이내면 같은 점으로 인식</li>
  <li>한쪽에만 있는 측정점도 시각화 표시</li>
</ol>

<h3>3. 입력 데이터 형식</h3>
<p>한 행 = "한 웨이퍼의 한 PARAMETER". 헤더 컬럼명은 대소문자/공백/언더바 구분 안 함.</p>

<p><b>필수 컬럼</b>:</p>
<ul>
  <li><code>WAFERID</code> — 웨이퍼 영구 고유 ID (그룹핑 키)</li>
  <li><code>LOT ID</code> / <code>SLOTID</code> — 현재 위치</li>
  <li><code>PARAMETER</code> — 측정 항목 이름 (T1, T2, X, Y, X_1000 등)</li>
  <li><code>RECIPE</code> — 계측 레시피</li>
  <li><code>DATA1, DATA2, ...</code> — 측정값</li>
</ul>

<h3>4. paste 직후 Input 라벨 색깔</h3>
<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>색</th><th>의미</th><th>Run 버튼</th></tr>
  <tr><td>🟢 민트</td><td>정상</td><td>활성</td></tr>
  <tr><td>⚪ 회색</td><td>알림 (반복 측정 분리, 헤더 행 2개 등)</td><td>활성</td></tr>
  <tr><td>🟠 주황</td><td>주의 — 결과 한번 더 확인</td><td>활성</td></tr>
  <tr><td>🔴 빨강</td><td>오류 — 시각화 불가</td><td>비활성</td></tr>
</table>

<h3>5. 좌표(X/Y) 가 데이터에 없을 때</h3>
<p>같은 RECIPE 의 좌표가 라이브러리에 저장돼 있으면 자동 적용됩니다 (그래프 제목에 📁 표시).</p>
<p>없으면 <b>저장된 좌표 불러오기</b> 버튼 또는 Settings → 좌표 라이브러리 → 수동 추가.</p>

<h3>6. 자주 만나는 문제</h3>
<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>증상</th><th>해결</th></tr>
  <tr><td>"필수 컬럼 부족"</td><td>WAFERID·PARAMETER·DATA1 같은 컬럼명이 첫 행에 있는지 확인</td></tr>
  <tr><td>"일부 웨이퍼 PARA 다름"</td><td>일부 행 누락 paste — 데이터 다시 전체 선택 후 복사</td></tr>
  <tr><td>좌표 콤보 비어있음</td><td>좌표 라이브러리에서 불러오기 또는 수동 추가</td></tr>
</table>
""",
    ),
    # ─────────────────────────────────────────────────────────
    "control": (
        "Control Bar / Copy 기능",
        """
<h2>Control Bar 기능</h2>

<h3>VALUE 콤보</h3>
<p>시각화할 측정 PARAMETER 선택. 변경 시 즉시 재시각화 (Run 안 눌러도 됨).</p>
<ul>
  <li>표시 형식: <code>T1   [55 pt]</code> — [N pt] 는 측정점 개수</li>
  <li>좌표 PARAMETER (X, Y, X_*, Y_*) 는 후보에서 자동 제외</li>
</ul>

<h3>좌표 콤보</h3>
<p>X / Y 좌표 PARAMETER pair 선택. 표시 형식: <code>X / Y   [55 pt]</code>.
suffix 자동 매칭 (X↔Y, X_1000↔Y_1000).</p>

<h3>저장된 좌표 불러오기</h3>
<p>입력에 좌표 PARAMETER 가 없거나 라이브러리의 다른 좌표를 쓰고 싶을 때 사용.
현재 VALUE 의 측정점 개수와 일치하는 좌표만 표시 (RECIPE 일치 우선).</p>

<h3>View: 2D / 3D</h3>
<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>모드</th><th>설명</th></tr>
  <tr><td><b>2D</b></td><td>heatmap. 색으로 VALUE 표현</td></tr>
  <tr><td><b>3D</b></td><td>surface plot. Z 축 높이로 VALUE 표현</td></tr>
</table>

<h3>Z-Scale: 공통 / 개별</h3>
<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>모드</th><th>용도</th></tr>
  <tr><td><b>공통</b></td><td>모든 wafer 동일 Z 범위 — wafer 간 직접 비교</td></tr>
  <tr><td><b>개별</b></td><td>각 wafer 자체 min/max 기반 — 형상·패턴 강조</td></tr>
</table>

<h3>Z-Margin (%) — 공통 모드 전용</h3>
<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>방향</th><th>효과</th></tr>
  <tr><td>증가 (0% → 50% → 100%)</td><td>palette 넓어짐. 색 대비 부드러워짐 (극단값 덜 강조)</td></tr>
  <tr><td>감소</td><td>palette 좁아짐. 작은 차이도 강하게 표현</td></tr>
</table>

<h3>r-symmetry mode</h3>
<p>일반 측정 데이터를 강제로 radial symmetric 처리 (1D fitting → 360° 회전).
1D scan 데이터는 자동 감지되어 항상 radial 처리. 앱 재시작 시 해제.</p>

<h3>Δ-Interp mode (DELTA 모드 전용)</h3>
<p>양쪽 좌표가 부분만 겹칠 때 unmatched 점 처리:</p>
<ul>
  <li><b>비활성</b>: 한쪽에만 있는 점은 0 으로 가정</li>
  <li><b>활성</b>: 빠진 쪽을 보간으로 채워 정상 delta 계산</li>
</ul>
<p>A·B 모두 정상 입력일 때만 활성 가능. 앱 재시작 시 해제.</p>

<h3>Run Analysis</h3>
<p>현재 입력 + 콤보 선택으로 시각화 실행. 같은 입력 재클릭 = 새로 그리기 (reset 효과).</p>

<hr/>

<h2>그래프 우클릭 메뉴 (Copy 기능, PPT 호환)</h2>

<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>메뉴</th><th>동작</th><th>붙여넣기 결과</th></tr>
  <tr>
    <td><b>Reset</b></td>
    <td>3D 회전 / zoom 초기 상태로 복원</td>
    <td>—</td>
  </tr>
  <tr>
    <td><b>Copy Graph</b></td>
    <td>차트 + Summary 표를 하나의 이미지로 복사. 다른 창에 가려져도 깨끗하게 캡처</td>
    <td>PPT 에 <b>사진</b> 으로 paste</td>
  </tr>
  <tr>
    <td><b>Copy Data</b></td>
    <td>측정점 (X, Y, VALUE) 을 표 형식으로 복사</td>
    <td>Excel 셀에 paste 시 표로 펼쳐짐</td>
  </tr>
  <tr>
    <td><b>Copy Table</b></td>
    <td>Summary 표만 복사</td>
    <td>PPT 엔 <b>표</b> 로, Excel 엔 셀로</td>
  </tr>
</table>

<h3>3D 카메라 조작</h3>
<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>조작</th><th>효과</th></tr>
  <tr><td>좌드래그</td><td>선택 그래프만 회전</td></tr>
  <tr><td>Ctrl + 드래그</td><td>선택 그래프만 이동</td></tr>
  <tr><td><b>Shift + 좌클릭/드래그</b></td><td><b>전체 그래프 동시 회전</b></td></tr>
  <tr><td><b>Shift + Ctrl + 드래그</b></td><td><b>전체 그래프 동시 이동</b></td></tr>
  <tr><td>휠</td><td>zoom</td></tr>
</table>

<h3>ReasonBar (Run / paste 결과)</h3>
<p>Control 패널과 결과 패널 사이 한 줄에 안내 표시:</p>
<ul>
  <li>🟢 <b>민트</b>: 좌표 자동 적용 (옆 wafer 에서 / 라이브러리에서)</li>
  <li>🟠 <b>주황</b>: RECIPE 다름, 일부 wafer skip, 측정점 개수 불일치 등</li>
  <li>🔴 <b>빨강</b>: Run 차단 — 좌표 결정 실패, WAFERID 교집합 0 등</li>
</ul>
""",
    ),
    # ─────────────────────────────────────────────────────────
    "settings_chart_common": (
        "MAP 공통 설정",
        """
<h2>MAP 공통 설정</h2>
<p>2D / 3D 양쪽에 공통 적용되는 차트 설정.</p>

<h3>설정 항목</h3>
<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>항목</th><th>증가 / 켜짐 시</th><th>감소 / 꺼짐 시</th><th>기본값</th></tr>
  <tr>
    <td><b>컬러맵</b></td>
    <td colspan="2">28종 (Turbo, Viridis, Plasma, Inferno, Magma, Cividis, 커스텀 White-색 등)</td>
    <td>Turbo</td>
  </tr>
  <tr>
    <td><b>2D 보간 방법</b></td>
    <td colspan="2">RBF 4종 (아래 가이드)</td>
    <td>RBF-ThinPlate</td>
  </tr>
  <tr>
    <td><b>1D Radial 보간</b></td>
    <td colspan="2">7종 (아래 가이드)</td>
    <td>Univariate Spline</td>
  </tr>
  <tr>
    <td><b>격자 해상도</b></td>
    <td>지도 부드러워짐. 렌더 속도 느려짐</td>
    <td>거칠어짐. 빨라짐</td>
    <td>150</td>
  </tr>
  <tr>
    <td><b>그래프 크기</b></td>
    <td>cell 크게. 가독성 ↑, 한 화면에 wafer 수 ↓</td>
    <td>cell 작게. 한 화면에 더 많이</td>
    <td>중</td>
  </tr>
  <tr>
    <td><b>소수점 자릿수</b></td>
    <td>Summary 표 / 컬러바 라벨 정밀도 ↑, 표 폭 넓어짐</td>
    <td>표 간결</td>
    <td>2</td>
  </tr>
  <tr>
    <td><b>Edge Cut (mm)</b></td>
    <td>웨이퍼 외각 잘라냄 — 보간 외삽 노이즈 제거</td>
    <td>0 = 잘라내지 않음</td>
    <td>0</td>
  </tr>
  <tr>
    <td><b>Map Size</b></td>
    <td>3D 카메라 거리 ↑ → 그래프 작게 보임</td>
    <td>거리 ↓ → 크게 보임</td>
    <td>550</td>
  </tr>
  <tr>
    <td><b>1D Scan 폭 (mm)</b></td>
    <td>1D scan 자동 감지 너그러워짐</td>
    <td>엄격해짐 (정확한 라인만 인식)</td>
    <td>45</td>
  </tr>
  <tr>
    <td><b>1D Radial Graph 표시</b></td>
    <td>지도 아래 (r, v) 산점도 + fitting 곡선 추가</td>
    <td>숨김</td>
    <td>off</td>
  </tr>
</table>

<h3>2D 보간 (RBF) 4종 — 사용 가이드</h3>
<p>측정점 사이를 채우는 알고리즘. 측정점에서 멀어질수록 영향이 줄어듭니다.</p>

<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>방법</th><th>특징</th><th>추천 상황</th></tr>
  <tr>
    <td><b>ThinPlate</b><br/>(기본)</td>
    <td>가장 부드럽고 자연스러움</td>
    <td>대부분의 경우. THK / CD 일반 측정값</td>
  </tr>
  <tr>
    <td><b>Multiquadric</b></td>
    <td>ThinPlate 보다 매끄러움. 큰 흐름 강조</td>
    <td>측정 노이즈 많을 때, 매크로 트렌드만 보고 싶을 때</td>
  </tr>
  <tr>
    <td><b>Gaussian</b></td>
    <td>각 점의 영향이 가까이만 미침</td>
    <td>측정점 dense + 국소 변화 강조 (defect, hot-spot 등)</td>
  </tr>
  <tr>
    <td><b>Quintic</b></td>
    <td>곡률 변화 강하게 표현</td>
    <td>골/봉우리 뚜렷한 데이터 (etch depth, step height)</td>
  </tr>
</table>

<p><b>판단 어려우면 ThinPlate 유지</b>.</p>

<h3>1D Radial 보간 7종 — 사용 가이드</h3>
<p>1D scan 데이터 또는 r-symmetry mode 에서 (r, v) 곡선 fitting.</p>

<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>방법</th><th>특징</th><th>추천 상황</th></tr>
  <tr>
    <td><b>Univariate Spline</b><br/>(기본)</td>
    <td>매끄러움 정도 조절 가능. 노이즈 평탄화 + 디테일 보존 균형</td>
    <td>대부분의 경우</td>
  </tr>
  <tr>
    <td><b>Cubic Spline</b></td>
    <td>측정점 정확 통과. 점 사이만 cubic 보간</td>
    <td>측정 노이즈 거의 없을 때 (정밀 측정)</td>
  </tr>
  <tr>
    <td><b>PCHIP</b></td>
    <td>측정점 정확 통과 + 단조성 보존. overshoot 없음</td>
    <td>단조 증감이 의미있는 데이터 (CD trim, ER profile)</td>
  </tr>
  <tr>
    <td><b>Akima</b></td>
    <td>국소 변화에 robust. outlier 영향 국소화</td>
    <td>step / corner 등 국소 이상 패턴</td>
  </tr>
  <tr>
    <td><b>Savitzky-Golay</b></td>
    <td>이동 윈도우 다항식 평탄화. 노이즈 제거 강력</td>
    <td>측정 노이즈 많을 때 (raw plot 시 지글지글)</td>
  </tr>
  <tr>
    <td><b>LOWESS</b></td>
    <td>국소 가중 회귀. outlier weight 자동 감소</td>
    <td>outlier 섞임. 매크로 트렌드만 추출하고 싶을 때</td>
  </tr>
  <tr>
    <td><b>Polynomial</b></td>
    <td>전역 다항식. 매우 매끄러움</td>
    <td>2~5차로 표현 가능한 단순 프로파일 (concave/convex)</td>
  </tr>
</table>

<h3>1D 보간법별 파라미터</h3>
<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>방법</th><th>파라미터</th><th>증가 시</th><th>감소 시</th></tr>
  <tr>
    <td><b>Univariate Spline</b></td>
    <td>Smoothing Factor (0~15)</td>
    <td>곡선 부드러움 ↑, 디테일 손실</td>
    <td>측정점에 가까이 fit, 노이즈도 따라감</td>
  </tr>
  <tr>
    <td rowspan="2"><b>Savitzky-Golay</b></td>
    <td>Window 크기 (홀수)</td>
    <td>평탄화 ↑, 디테일 손실</td>
    <td>평탄화 ↓, 노이즈 잔존</td>
  </tr>
  <tr>
    <td>Polyorder (1~5)</td>
    <td>곡선 복잡도 ↑</td>
    <td>단순 곡선</td>
  </tr>
  <tr>
    <td><b>LOWESS</b></td>
    <td>Frac (0.05~1.0)</td>
    <td>관찰 윈도우 ↑, 부드러움 ↑</td>
    <td>국소 변화에 sensitive</td>
  </tr>
  <tr>
    <td><b>Polynomial</b></td>
    <td>Degree (1~10)</td>
    <td>곡선 굴곡 ↑ (양 끝 oscillation 위험)</td>
    <td>단순 형태 (linear, parabola)</td>
  </tr>
</table>

<p>선택한 보간법의 파라미터만 활성화됩니다.</p>
""",
    ),
    # ─────────────────────────────────────────────────────────
    "settings_chart_2d": (
        "2D MAP 설정",
        """
<h2>2D MAP 설정</h2>
<p>2D heatmap 전용 옵션.</p>

<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>항목</th><th>켜짐 / 증가 시</th><th>꺼짐 / 감소 시</th></tr>
  <tr>
    <td><b>측정점 마커 표시</b></td>
    <td>실제 측정 위치에 점 표시. 보간 결과와 실측 비교 가능</td>
    <td>점 hidden. 매끄러운 heatmap 만 표시</td>
  </tr>
  <tr>
    <td><b>측정점 크기 (px)</b></td>
    <td>마커 크게 — 가독성 ↑, heatmap 가림</td>
    <td>마커 작게 — heatmap 잘 보임</td>
  </tr>
  <tr>
    <td><b>측정값 라벨 표시</b></td>
    <td>각 측정점 옆에 숫자값 표시</td>
    <td>숫자 hidden. 깔끔한 heatmap</td>
  </tr>
</table>

<p><b>참고</b>: 측정점 75 PT 이상에서 라벨 켜면 숫자 겹쳐서 가독성 저하 — 끄는 것 권장.</p>
""",
    ),
    # ─────────────────────────────────────────────────────────
    "settings_chart_3d": (
        "3D MAP 설정",
        """
<h2>3D MAP 설정</h2>
<p>3D surface plot 전용 옵션.</p>

<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>항목</th><th>증가 / 켜짐 시</th><th>감소 / 꺼짐 시</th><th>기본값</th></tr>
  <tr>
    <td><b>부드러운 표면</b></td>
    <td>면이 매끄럽게 이어짐</td>
    <td>각진 면 강조</td>
    <td>on</td>
  </tr>
  <tr>
    <td><b>Z-Height</b></td>
    <td>Z 축 과장 (최대 3.0). 형상 강조</td>
    <td>Z 축 압축 (0.5 = 절반). 평탄화</td>
    <td>1.0</td>
  </tr>
  <tr>
    <td><b>Elevation (°)</b></td>
    <td>위에서 내려다봄. <b>+90°</b> = top-down (2D 모드와 유사)</td>
    <td>옆에서 봄. <b>0°</b> = horizontal, <b>-90°</b> = bottom-up</td>
    <td>28</td>
  </tr>
  <tr>
    <td><b>Azimuth (°)</b></td>
    <td>시계방향 회전</td>
    <td>반시계방향 회전</td>
    <td>-135</td>
  </tr>
</table>

<h3>Azimuth 가이드 (notch 위치)</h3>
<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>각도</th><th>notch 위치</th></tr>
  <tr><td>0°</td><td>3시</td></tr>
  <tr><td>-90°</td><td>6시</td></tr>
  <tr><td><b>-135°</b> (기본)</td><td>4~5시 (radial mesh 시각적 균형)</td></tr>
  <tr><td>180° (= -180°)</td><td>9시</td></tr>
</table>

<p><b>Map Size (카메라 거리)</b> 는 MAP 공통 설정 카드에 있음.</p>

<h3>마우스 조작 (그래프 위에서)</h3>
<ul>
  <li>좌드래그 → 회전</li>
  <li>Ctrl + 드래그 → 이동</li>
  <li>Shift + 좌클릭/드래그 → 전체 cell 동시 회전</li>
  <li>휠 → zoom</li>
  <li>우클릭 → Reset (Settings 값으로 복원)</li>
</ul>

<p>마우스로 돌린 각도는 일시적이고, Settings 값은 새 wafer 셀의 초기 카메라 상태에만 적용됩니다.</p>
""",
    ),
    # ─────────────────────────────────────────────────────────
    "settings_chart_1d": (
        "1D Radial Graph 설정",
        """
<h2>1D Radial Graph</h2>
<p>2D/3D 맵 하단에 (거리, 측정값) 산점도 + fitting 곡선 위젯 표시.
1D scan 또는 r-symmetry mode 에서 fitting 결과 확인용.</p>

<h3>유용한 use case</h3>
<ul>
  <li>웨이퍼 center / edge 값 차이 (radial profile) 분석</li>
  <li>CMP / line-scan 같은 rotation symmetric 공정</li>
  <li>r-symmetry mode 활성 시 fitting 검증 (실측 vs 보간 비교)</li>
</ul>

<h3>설정 항목</h3>
<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>항목</th><th>켜짐 / 증가 시</th><th>꺼짐 / 감소 시</th></tr>
  <tr>
    <td><b>1D Radial Graph 표시</b></td>
    <td>cell 하단에 그래프 추가 (cell 높이 ↑)</td>
    <td>숨김</td>
  </tr>
  <tr>
    <td><b>Moving Avg Window</b></td>
    <td>이동 평균 윈도우 ↑ → 노이즈 감소, 디테일 손실</td>
    <td>0 = 원본 그대로</td>
  </tr>
</table>

<h3>그래프 구성</h3>
<ul>
  <li><b>검은 점</b>: 실측 (거리, 값)</li>
  <li><b>회색 곡선</b>: 보간 fitting 결과</li>
  <li>측정 거리 범위 안에서만 곡선을 그림 (밖은 비워 둠)</li>
</ul>

<h3>fitting 알고리즘 선택</h3>
<p><b>MAP 공통 설정</b> 카드의 <b>1D Radial 보간</b> 콤보에서 선택 (총 7종).
각 알고리즘 특징과 추천 상황은 그쪽 도움말 참고.</p>

<p>요약:</p>
<ul>
  <li><b>Univariate Spline</b> (기본) — 무난</li>
  <li><b>Cubic Spline</b> — 측정 정확, 점들 정확히 통과</li>
  <li><b>PCHIP / Akima</b> — 단조 / 국소 변화 강조</li>
  <li><b>Savitzky-Golay / LOWESS</b> — 노이즈 많을 때</li>
  <li><b>Polynomial</b> — 단순 형태</li>
</ul>
""",
    ),
    # ─────────────────────────────────────────────────────────
    "settings_coord_library": (
        "좌표 라이브러리 설정",
        """
<h2>좌표 라이브러리</h2>
<p>입력에 X/Y 좌표 PARAMETER 가 없는 경우 대비 — 이전 분석에서 사용한 좌표를
RECIPE 별로 저장 / 자동 재사용.</p>

<h3>자동 저장 / 자동 적용</h3>
<ol>
  <li>좌표 있는 데이터로 Run → 좌표가 RECIPE 와 함께 자동 저장</li>
  <li>나중에 좌표 없는 데이터 (같은 RECIPE) 가 들어오면 자동으로 가져와 그림</li>
  <li>자동 적용된 cell 은 그래프 제목에 📁 아이콘</li>
</ol>

<h3>RECIPE 매칭 순서</h3>
<ol>
  <li><b>완전 일치</b> (대소문자 무관)</li>
  <li><b>_PRE / _POST 토큰 무시</b>: 끝 또는 중간의 _PRE / _POST 만 다르면 같은 RECIPE 로 간주
    (예: <code>ABC_PRE</code> ↔ <code>ABC_POST</code> ↔ <code>ABC</code>,
    <code>CMP_PRE_THK</code> ↔ <code>CMP_POST_THK</code> ↔ <code>CMP_THK</code>)</li>
  <li><b>Similarity</b>: 단어 3개 이상 공통 + 측정점 개수 같음</li>
</ol>
<p>구분자 <code>_</code> 만 인정 — <code>ABC-POST</code> (하이픈) / <code>ABCPOST</code> (구분자 X) 는 비호환.</p>

<h3>수동 추가</h3>
<p><b>+ 수동 추가</b> 버튼:</p>
<ol>
  <li>RECIPE 이름 입력</li>
  <li>좌표 paste — 4가지 포맷 자동 감지:
    <ul>
      <li><code>x 0 74 148 / y 148 74 0</code> (행 + X/Y 라벨)</li>
      <li><code>0 74 148 / 148 74 0</code> (행, 위=X)</li>
      <li><code>x y / 0 148 / ...</code> (열 + 헤더)</li>
      <li><code>0 148 / 74 74 / ...</code> (열, 좌=X)</li>
    </ul>
  </li>
  <li>구분자 무관 (공백/탭/콤마/세미콜론)</li>
  <li>미리보기 테이블에서 좌표 확인 후 저장</li>
</ol>

<h3>편집 / 삭제</h3>
<ul>
  <li>헤더 클릭으로 정렬 (RECIPE / X·Y / 점 개수 / 최초 저장 / 마지막 사용)</li>
  <li>레코드 선택 후 <b>삭제</b> (다중 선택 가능)</li>
  <li><b>RECIPE 변경</b> — 이름만 수정 (좌표 수정은 미지원, 새로 저장)</li>
  <li>행 더블클릭 → 좌표 프리뷰 (wafer map + 좌표 표)</li>
</ul>

<h3>자동 정리</h3>
<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr style="background:#f0f0f0;"><th>항목</th><th>증가 시</th><th>0 으로 두면</th><th>기본값</th></tr>
  <tr>
    <td><b>최대 저장 개수</b></td>
    <td>보관 capacity ↑</td>
    <td>제한 없음</td>
    <td>1000</td>
  </tr>
  <tr>
    <td><b>최대 보관일</b></td>
    <td>오래된 좌표도 더 오래 유지</td>
    <td>제한 없음</td>
    <td>0 (무제한)</td>
  </tr>
</table>
<p>한도 초과 시 마지막 사용일이 오래된 순으로 자동 삭제됩니다.</p>
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
    파일은 OS 임시 폴더에 생성 (`wafer_map_help.html`). 같은 이름이라 누적 안 됨.
    """
    html = build_help_html()
    out = Path(tempfile.gettempdir()) / "wafer_map_help.html"
    out.write_text(html, encoding="utf-8")
    webbrowser.open(out.as_uri())
