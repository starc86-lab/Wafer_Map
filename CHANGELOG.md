# Changelog

Wafer Map 버전 이력. SemVer(Major.Minor.Patch) 기준.
- **Major**: settings.json 스키마·입력 포맷 등 breaking 변경
- **Minor**: 기능 추가 / UI 변경
- **Patch**: 버그 수정

## [0.2.0] — 2026-04-25

사내 베타 0.1.0 이후 ~87 커밋. 주요 축은 (1) 1D Radial Graph + fitting 고도화, (2) 3D radial mesh 전환, (3) Copy Graph FBO 전환, (4) 좌표 라이브러리 pair-단위 개편, (5) VALUE/좌표 자동 선택 고도화.

### Copy Graph — Offscreen FBO 렌더링 (P1/P2 해결)
- **QScreen.grabWindow 방식 폐기** → `QOpenGLFramebufferObject(MSAA=4)` 로 `GLViewWidget.paint(region, viewport)` 직접 호출. 화면 픽셀 독립.
- 그래프가 **스크롤/윈도우 크기에 가려져도 완전한 이미지** 캡처 (P1).
- Settings / 다른 창이 위에 떠 있어도 캡처 무관 (P2).
- **SettingsDialog `parent=None` + `Qt.Window` 우회 제거** → 표준 `parent=self` + QDialog 기본 플래그로 복원 (tech debt 해소).
- Overlay 재합성 — `_capture_container.grab()` 바탕 위에 FBO 이미지를 chart 위치에 덮고 title / colorbar / r-symmetry 배지 drawPixmap 으로 z-order 복원.
- `GLTextItem` 후처리 — pyqtgraph 가 `QPainter(self.view())` 로 widget 에 직접 그리는 특성으로 FBO 반영 안 됨 → `compute_projection + align_text` 재현 + QSS-resolved widget font family 전파.

### 1D Radial Graph 위젯 (대규모 신규)
- 2D/3D 맵 하단에 `(r, v)` 산점도 + 스플라인 실선 위젯 추가 (Settings 토글).
- **1D 라인 스캔 자동 감지** (`is_radial_scan`) — 원점 중심 직사각형에 fit 되는 점 → Radial Symmetric 변환, 같은 r 평균으로 ±대칭 통합.
- **Radial fitting 6종 선택** (Settings 콤보): Univariate Spline / Cubic Spline / PCHIP / Akima / Savitzky-Golay / LOWESS + Polynomial.
- **Moving Avg Window** (구 Bin Average) — 모든 fitting 방법과 공통 조합되는 전처리.
- **r-symmetry mode** 강제 토글 (체크박스) — 자동 감지 실패해도 수동으로 radial 로 그리게. 세션 휘발 (저장 안 함).
- 스플라인은 측정 r 범위 안에서만 그림 (flat 외삽 / 왜곡된 미러 배제, 과학 시각화 관례).

### 3D MAP — Radial Mesh 전환 (rect 경로 제거)
- rect `(XG, YG)` 격자 기반 3D 렌더 완전 제거. `(r, θ)` radial fan mesh 로 통일.
- 바닥 그리드 320×320 + 간격 40 (원점 대칭 + 0 통과 라인 확보).
- `edge_cut_mm` 옵션 — 측정 외각 톱니 제거. 자동 측벽 생성 (서피스 외각 → Z=0 연결).
- 경계 원 R 설정 가능 (150~160mm), notch V 자 홈 옵션.
- Camera 기본값 조정: distance 620 / elevation 28° / azimuth -135° (notch 가 4~5 시 방향).
- 카디널 스트라이프 아티팩트 해결 (rect 격자 축 정렬 이슈 → radial 로 원천 제거).
- **Chart-Title-Colorbar overlap 구조** — title 영역을 그래프가 침범 가능하되 title 은 항상 위 (raise_).

### 공통 Z-Scale / Z-Margin
- 공통 모드 3D: **형상 개별 stretch + avg 위치 offset 하이브리드** — 납작한 dome 문제 해결.
- **Z-Margin 스핀박스** (구 Z-Span, Z-range) — 공통 스케일 범위 확장 비율 조정. 공통 모드 전용, 개별 모드에선 disable. 세션 휘발.
- 1D radial 도 `display.z_range_1d` 로 공통/개별 토글 공유.

### ER Map (Etch Rate) 변환
- DELTA 셀 하단 Time 입력란 추가. Time 값으로 DELTA 값을 자동 나누어 Etch Rate 로 변환.
- Master/slave — 첫 셀 값이 체크박스로 전 셀 전파. 개별 입력도 가능.

### 좌표 라이브러리 (Pair-단위 개편)
- **좌표 X/Y 콤보 통합** — 단일 "좌표" 콤보로 pair 단위 선택 (이전: X 콤보 + Y 콤보 분리).
- **Per-pair overwrite** — 같은 RECIPE 여러 좌표 pair 를 각자 독립 저장.
- **좌표 프리셋 프리뷰 다이얼로그** — 웨이퍼 맵 + 좌표 표로 시각 확인. 수동 추가 다이얼로그 재활용.
- Library 탭 UI — 개별 레코드 행 표시 (recipe 그룹 병합 제거), n 필터 유지.
- preset 자동 선택 시 Run "좌표 없음" 경고 오진 수정.
- `name` 필드 제거 + UI X/Y 컬럼 추가.
- 라이브러리 save 버그 수정 (신규 레코드 파일 반영 안 되던 문제).

### VALUE / X / Y 자동 선택 고도화
- **VALUE 자동 선택 `|3σ/AVG|` 최대** — 공간적 변동 큰 측정이 맵 시각화 가치 높음. GOF / K[633] 등 변동 작은 파라 자동 후순위.
- **선택 순서 X/Y → VALUE** 로 변경 — X 의 n (좌표 개수) 기준으로 VALUE required_n 확정.
- VALUE 콤보에서 **좌표 (X, Y, X_*, Y_*) 완전 제외** + 단일값 파라 (`_AVG`) 제외.
- **X/Y pair 매칭 (suffix 기반)** — `X` ↔ `Y`, `X_1000` ↔ `Y_1000`, 한쪽만 있는 이름 제외.
- **보조(suffix) 그룹 콤보 유지** — `T1_A`, `T1_B` 같은 그룹 suffix 파라도 콤보에 노출.
- **정수값 파라 (DIE_ROW/DIE_COL)** 필터 완화 — 콤보엔 유지, 자동 선택만 후순위 demote.
- VALUE union + NaN 셀 — 일부 wafer 에만 있는 PARAMETER 도 후보에 노출, 누락 wafer 는 NaN 셀 + `(no data)` 타이틀.
- DELTA VALUE optional — 한쪽에만 VALUE 있어도 NaN delta 셀 생성 (좌표는 필수).
- `[N pt]` 콤보 표시 (pair / VALUE 각자).
- X 변경 시 Y suffix 동기화, Y 변경 시 X 유지 (비대칭).

### Settings UI
- **디자인 설정 탭 구조 개편** — 카드별 분리 (UI / MAP 공통 / 2D / 3D / 1D Radial / 좌표 라이브러리).
- 개발자값 고정 (boundary / notch / scale bar 등) + 사용자 설정만 노출.
- Map Size / View Angle 컨트롤 개편.
- QSpinBox / QDoubleSpinBox / QCheckBox 마우스 휠 차단 (값 의도치 않은 변경 방지).
- Default 버튼 디자인 설정 탭 좌측 하단 sticky.
- 세션 휘발 설정 (r-symmetry, Z-Margin) 명시적 분리.

### UI / Chart 디테일
- 2D MAP 값 라벨 폰트 base 8pt → 9pt (scale 0.85/1.0/1.15 → 8/9/10pt).
- Colorbar 길이 축소 + right pad 4px + r-symmetry 배지 좌측 하단.
- Summary 표 헤더 회색 배경 (`#f7f7f7`) — QSS override 문제 item delegate 로 우회.
- 1D 그래프 / 표 레이아웃 컴팩트 얼라인 + font_scale 연동.
- X/Y 좌표 콤보 비어있을 때 Run 클릭 시 경고 팝업.
- Run 동일 입력 no-op — cell 상태 (카메라/휠 zoom/ER 입력) 보존.

### 버그 픽스
- `Chart1DRadialGroup` snapshot stale 값 덮어쓰기 버그.
- `Settings._collect` 가 stale `_initial` 로 `r_symmetry_mode` 덮어쓰는 버그.
- `select_xy_pairs` 콤보 중복 버그.
- View angle 변경 시 `boundary_r_mm=150` 으로 회귀하던 버그 (chart_common UI 미관리 키 보존).
- QSpinBox/QDoubleSpinBox 기본 QSS 테두리 소실 픽스.
- Radial 모드가 `interp_method` 설정 무시하던 버그.
- RBF overshoot clamp / 공통 Z-scale 정합 / 2D radial notch 회전.

### 문서 / 진단
- `docs/v0.1.0_perf.md` — 0.1.0 렌더링 성능 측정.
- `docs/parser_edge_cases.md` — 파서 엣지 케이스 정리.
- `docs/rendering_optimizations.md` — 렌더링 최적화 이력 / 실패 사례.
- RBF 실패 시 stderr 상세 로그 + 성공 경로 x_std/y_std 진단.

### 알려진 제한
- 3D 중심부 pinwheel 아티팩트 (radial mesh triangulation + shaded lighting) — 현재 수용, 향후 analytic normal 주입 또는 bowtie triangulation 검토.

## [0.1.0] — 2026-04-20
첫 사용 가능 배포 (사내 베타).

### 기능
- 클립보드 페이스트 기반 long-form CSV 파서 (헤더 대소문자/공백/언더바 무관).
- 3-패널 세로 스택 UI (Input A/B · Control · Result).
- 2D Heatmap + 3D Surface MAP — `QStackedLayout`으로 즉시 토글.
- VALUE/X/Y 자동 선택 (`auto_select.py`) + X 변경 시 Y suffix 동기화 + VALUE 변경 즉시 재시각화.
- 다중 웨이퍼 가로 나열. DELTA 시각화 (A-B WAFERID 교집합 · 좌표 일치점).
- Summary 표 (Average / Non Unif. / Range, 3Sig) — 테마 무관 흰색 고정.
- Copy Graph (화면 픽셀 캡처, PPT paste 호환) / Copy Data (TSV) / Copy Table (HTML+TSV dual MIME).
- 좌표 프리셋 라이브러리 (`coord_library.json`) — RECIPE 기반 자동 조회 + 수동 추가.
  - 4 포맷 자동 감지 (row+라벨 / row / col+header / col) + y-first 허용.
  - 노이즈 허용 (BOM/NBSP/quote/leading·trailing 비데이터).
- 자동 정리 정책 (max_count / max_days, last_used 기준, 0=무제한, 기본 1000).
- 보간: RBF 4종 (ThinPlate / Multiquadric / Gaussian / Quintic).
- 컬러맵 28종 + 컬러 스케일바 (Turbo 기본). Reverse·Custom White 포함.
- 테마 14종 + font_scale + Segoe UI 기본.
- 무설치 포터블 배포 (PyInstaller `--onedir`) — settings.json·coord_library.json 실행 폴더 기준.

### UI 인터랙션
- 3D 카메라: 좌드래그=회전, Ctrl+드래그=이동, 휠=비활성.
- **Shift+좌클릭**: 전체 3D 셀 카메라 스냅 동기 + 이어 드래그하면 실시간 전파.
- 우클릭 메뉴: Reset / Copy Graph / Copy Data / Copy Table.
- 윈도우 크기·splitter·최대화 상태 자동 복원.

### 제한사항 / 알려진 이슈
- Copy Graph가 화면 픽셀 캡처 방식이라 **다른 창이 위에 있으면 그 내용이 포함됨** — Settings 창을 `parent=None` 처리로 뒤로 갈 수 있게 workaround. 추후 offscreen FBO 방식으로 전환 예정. *(0.2.0 에서 해결)*
- 3D surface edge에 MSAA가 일부 드라이버에서 적용 안 될 수 있음 (jaggies). *(0.2.0 Copy Graph 는 FBO 에서 MSAA 4x 강제라 영향 없음. 화면 표시에만 해당)*
