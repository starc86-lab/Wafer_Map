# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

현재 버전: **0.4.0** (PARA 조합 sum/concat recursive + CombinedState 단일 진실원 + UI 마이너, 2026-04-29). 버전 이력은 [CHANGELOG.md](CHANGELOG.md) 참고, 사용자 가이드는 [USER_GUIDE.md](USER_GUIDE.md).

## 정책 카탈로그 (필수 동반 갱신)

3대 정책은 별도 md 파일로 관리 — 관련 코드 변경 시 **반드시** 동반 갱신:

- [docs/policies/input_parsing.md](docs/policies/input_parsing.md) — 입력 / 파싱 정책 (헤더 매칭·DATA 수집·메타 컬럼·반복 측정 분리·자동 선택·단위 환산)
- [docs/policies/coords.md](docs/policies/coords.md) — 좌표 결정 + 라이브러리 (single 4단계 fallback / DELTA 매트릭스 / 자동 저장·조회·정리)
- [docs/policies/reason_bar.md](docs/policies/reason_bar.md) — 메시지·검증·표시 (severity 4단계 / baseline 보존 / 메시지 카탈로그)

## 개발자 정보
- 한국인, 코딩 중급 수준
- 직접 코딩하지 않고 Claude에 코드 수정 권한 위임 — 제안·논의·리뷰 중심 협업
- 한국어로 친구처럼 반말로 소통
- **코드 변경 전 반드시 협의 후 진행** — 바로 수정 금지

## 관련 프로젝트 / 참고 기준
Wafer Map은 회사 업무의 반도체 측정 데이터 시각화 프로젝트. **자매 프로젝트 Profile Vision** 의 스택·코어 구조·UI 규약을 1차 참고 기준으로 한다.

> **외부 검토자 안내**: Profile Vision 은 **비공개 internal sister project** 라 GitHub 에 공개되지 않음. 본 문서의 `C:/Users/JHPark/Profile Vision/...` 경로 참조는 reviewer-internal — 외부에서 추적 불가. 본 repo 는 sister project 의 패턴 (PySide6 + pyqtgraph 스택 / FONT_SIZES / THEMES / 해상도 티어 / Copy Image 듀얼 MIME) 을 차용했으며, 의존하는 핵심 정책은 본 CLAUDE.md 와 코드에 inline 으로 모두 포함.

| 프로젝트 | 위치 | 역할 |
|---|---|---|
| **Profile Vision** (비공개) | `C:/Users/JHPark/Profile Vision/` (reviewer-internal) | 자매 프로젝트. 스택·core·widgets·차트 규약 **참고 기준** |
| Wafer Map (본 프로젝트) | `C:/Users/JHPark/Wafer Map/` | 신규 |

## 프로젝트 개요
반도체 웨이퍼 측정 데이터 시각화 프로그램.

### 핵심 목표 — 사용자 입력 편의성 최우선
- 파일 로드 없이, **화면에서 Ctrl+C → 프로그램에 Ctrl+V**로 바로 붙여넣는 워크플로우가 제1원칙
- 입력에 부가 정보(Wafer ID, STEP, 측정날짜, LOT ID, RECIPE, 장비 등)가 섞여 있어도 X / Y / VALUE만 선별해 사용

### 시각화 대상
- 300mm 원형 웨이퍼(직경 고정) 내 측정점: (X, Y, VALUE)
- VALUE 종류: 필름 두께(Thickness) 또는 CD(Critical Dimension)
- 출력: 2D Map / 3D Map

### 주요 시나리오
1. **단일 시각화**: 한 번의 입력을 그대로 표시
2. **DELTA 시각화**: 비슷한 입력 두 개를 받아 차이값을 표시
   - 예: (ETCH 전 두께) − (ETCH 후 두께) = DELTA
3. **다중 웨이퍼**: 입력은 1장일 수도, 여러 장일 수도 있음

### 확정 기능 요구사항 (개발자 invariant)

> 사용자 시점 절차·UI 동작·메시지 카탈로그·단축키는 [`USER_GUIDE.md`](USER_GUIDE.md). 본 섹션은 **변경 시 반드시 협의** 영역.

**클립보드 출력 (Copy 패턴)**
- Cell 우클릭 메뉴 4종 (`Reset` / `Copy Image` / `Copy Data` / `Copy Table`). 통합 핸들러 `_show_cell_menu` 가 자식 widget 별 `customContextMenuRequested` 받음 (`GLViewWidget` / `PlotWidget` 이 우클릭 propagate 차단 → 자식별 connect 필요).
- **듀얼 MIME 패턴 (불변)**:
  - Copy Image: alpha 제거 RGB32 + `setImageData(CF_DIB)` + `setData("image/png")` — Excel 좌우 비대칭 quirk 우회 ([memory](C:/Users/JHPark/.claude/projects/c--Users-JHPark-Wafer-Map/memory/project_clipboard_excel_alpha_pitfall.md))
  - Copy Table: `setText(tsv)` + `setHtml(html_table)` — TSV 단독 시 PPT 가 텍스트박스로만 받음
  - Copy Data: `setText(tsv)` 단독
- **Copy Image FBO 합성**: `_capture_container.grab()` (non-GL) + `_capture_gl_offscreen()` (GL, MSAA 4x) 합성 → 듀얼 MIME. 화면 표시 상태 독립 (스크롤·다른 창 가림 무관).

**Summary 표 정책**
- 6 메트릭 정의는 USER_GUIDE 참조. 자릿수 = `chart_common.decimals` (전역).
- DELTA 양쪽 병기: LOT/SLOT 칸 `A_LOT.A_SLOT ← B_LOT.B_SLOT` 화살표는 `A − B` 방향.
- 다중 wafer: (MAP + 표) 한 쌍 가로 나열 (`QScrollArea`).

**메인 윈도우 정책**
- 우상단 **`⚙ Settings` 버튼 하나만** (`QToolBar`). 메뉴바·Help 없음 — 최대한 직관적
- **2D / 3D 는 탭이 아니라** Control 패널 콤보/토글로 즉시 전환 (결과 영역 하나)

**DELTA 매칭 룰 (불변)**

| 항목 | 규칙 |
|---|---|
| Wafer 매칭 키 | `WAFERID` 만 (LOT/SLOT 변동 무관 — 영구 불변 ID) |
| 점 매칭 | 좌표 합집합 + tolerance 1mm. 양쪽 매칭 → dv=va−vb / A only → dv=va / B only → dv=−vb |
| 부호 | **`A − B` 고정** (UI 토글 없음) |
| 차단 사유 | WAFERID 교집합 0 또는 좌표 결정 실패 → ReasonBar error + Run 비활성 |
| Δ-Interp | 체크 시 한쪽 only 점에 RBF 보간 → 정상 delta. 비활성 시 NaN 룰 |
| 다중 wafer | A 10 / B 4 허용. 교집합만 처리, 미매칭 wafer 조용히 skip + ReasonBar 개수 안내 |

**다중 Wafer Z 스케일**
- `z_scale_mode`: `common` (기본) / `individual` 토글, 즉시 전환
- **Z-Margin** (공통 모드 전용): `range × (1 + pct/100)`, midpoint 고정. matplotlib `ax.margins()` 관례. 개별 모드에선 disable + 값 0 회색.

**좌표 프리셋 라이브러리 정책**
- **저장 위치**: `coord_library.json` — 앱 실행 폴더 (포터블)
- **저장 스키마**:
  ```json
  {"presets": [{"name": "...", "recipe": "...", "n_points": 49,
                "x_mm": [...], "y_mm": [...],
                "created_at": "...", "last_used": "..."}]}
  ```
- **자동 저장 (▶ Run 시점)**:
  - 각 wafer 의 `(recipe, x_mm, y_mm)` 조합을 라이브러리와 비교 (tolerance 1e-3 mm)
  - 일치 시 `last_used` 만 갱신, 없으면 신규 추가 (이름 `{recipe}_{n_points}P`)
  - **recipe 같아도 좌표 다르면 별도** / **좌표 같아도 recipe 다르면 별도**
  - 다중 wafer / DELTA → wafer 별 독립 저장
- **자동 적용 (입력에 X/Y PARAMETER 없을 때)**: 해당 wafer 의 RECIPE 일치 프리셋 → `last_used` 최신 레코드 좌표 주입. 매칭 없으면 wafer skip. 자동 적용 셀 → 📁 아이콘
- **불러오기 다이얼로그**: 현재 VALUE 의 N 과 `n_points` 일치 프리셋만 필터. 좌표 동일 (tolerance 1e-3 mm) 프리셋은 대표 1개 + "외 N" 병합. 정렬: RECIPE 일치 우선 → `last_used` 최근순
- **DELTA 모드**: A/B 양쪽 공통 적용 (pane 별 개별 미지원). 좌표 동일이 invariant
- **편집/삭제**: Settings → 좌표 라이브러리 탭. 이름/좌표 수정 미지원 (새로 저장)
- **자동 정리**: `coord_library.max_count` / `max_days` (0=무제한, 기본 1000). 기준 = `last_used` 오래된 순

## 입력 명세

### 개요
| 항목 | 설명 |
|---|---|
| 입력 방식 | 클립보드 붙여넣기 (Ctrl+V) — 파일 I/O 최소화 |
| 기대 포맷 | Excel / 계측 장비 출력을 바로 복사한 탭 구분 텍스트 |

### 실제 데이터 구조 (회사 광학 계측 CSV, long-form)

**핵심: CSV는 long-form 테이블.** 각 행 = "한 웨이퍼 × 한 PARAMETER 레코드". 참고 샘플: [samples/sample_data.csv](samples/sample_data.csv).

**파싱 원칙 (중요)**
- **컬럼 순서는 가변** — 위치 기반 파싱 절대 금지
- 컬럼 식별은 **헤더 이름(값)으로만** 매칭
- 헤더 매칭은 **대소문자·공백·언더바 무관**하게 정규화 후 비교 (`"LOT ID"` = `"Lot ID"` = `"LOT_ID"` = `"lotid"`)
- 샘플에 없는 추가 컬럼이 실제 입력에 포함될 수 있음 → **모르는 컬럼은 무시**
- DATA 컬럼은 `^DATA[ _]?\d+$` (case-insensitive) 정규식으로 식별, 숫자 suffix 기준 정렬 (`DATA1`, `DATA_1`, `DATA 1` 모두 동일 취급)
- **필수 컬럼**: `WAFERID`, `LOT ID`, `SLOTID`, `PARAMETER`, `RECIPE`, `DATA\d+` 1개 이상
- **선택 컬럼** (있으면 검증용, 없으면 실제 DATA 셀 수로 대체): `MAX_DATA_ID`
- 필수 컬럼 자동 매칭 실패 시 → **컬럼 매핑 다이얼로그** 팝업으로 사용자가 직접 각 논리 역할에 컬럼 지정 (fallback UX)
- 기본 컬럼 이름·alias는 `settings.json`에서 확장 가능

**메타 컬럼 (알려진 주요 항목, 각 행에 반복)**
| 컬럼 | 설명 | 예시 |
|---|---|---|
| `ETC1` / `DATE` / `MACHINE` / `OPERATINID` / `ETC2` / `ETC3` | 계측 로그 메타 (시각화엔 직접 불사용) | `2026-04-17 12:02`, `MTMF01` |
| `STEPDESC` | 계측 공정명 | `BG HM SION DEP THK` |
| `RECIPE` | 계측 레시피. **한 웨이퍼(`WAFERID`)의 모든 PARAMETER 행은 동일 RECIPE** — 한 번의 계측 세션이므로. 파서는 웨이퍼 단위로 하나의 RECIPE 값을 채택(예: 첫 행 or 최빈값) | `RK2A_BGSION_THK` |
| `LOT ID` | **현재 소속** 로트 ID (변경 가능, mutable) | `RK2A007` |
| `WAFERID` | **웨이퍼 영구 고유 ID.** 최초 생성 시의 `LOT.SLOT` 값이 그대로 박혀 불변. 이후 LOT reassign / Slot move 되어도 변하지 않음. **그룹핑·식별 기본 키**. 파싱해서 분해하지 말 것 — 현재 `LOT ID`와 일치하지 않을 수 있음 | `RK2A007.08` |
| `SLOTID` | **현재** 로트 내 슬롯 번호 (변경 가능) | `8`, `11` |
| `PARAMETER` | 측정 항목 이름. **자유 가변** (`T1`, `T2`, `T3_A`, `T4_C`, `GOF`, `X`, `Y`, `X_1000`, `Y_1000`, `T1_AVG`, `T1_B` 등). 자동 분류 불가 | 가변 |
| `MAX_DATA_ID` | 이 행에 **명시된** DATA 개수. 실제 DATA 값 개수와 다를 수 있음 — 불일치 시 **에러 팝업 후 실제 DATA 개수를 신뢰** (중단 X) | `13`, `49`, `1`, `4` |
| `DATA1` ~ `DATAN` | 실제 수치. 유효 값 뒤는 빈칸. 전체 열 개수는 파일마다 가변 | `663.125, 664.25, ...` |

**WAFERID 처리 주의 (중요)**
- 한 웨이퍼가 라이프사이클 중에 LOT reassign / Slot move 되면 `LOT ID`·`SLOTID`는 바뀌지만 `WAFERID`는 **불변**
- 예: 최초 `(LOT=RK2A001, WAFERID=RK2A001.07, SLOTID=7)` → 이후 `(LOT=RK2A001AC, WAFERID=RK2A001.07, SLOTID=11)`
- **그룹핑·비교는 `WAFERID` 문자열 그대로만** 사용. `LOT ID`·`SLOTID`는 **표시용 현재 상태값**

**관찰된 규약**
- PARAMETER 이름은 장비·레시피 따라 자유 — 고정 suffix 규약 없음
- `X`와 `X_1000`은 **같은 좌표를 다른 자릿수로 표기** (혼용됨). 앱이 자동 추정하여 최종 표시 단위는 **mm로 통일**
- 다중 웨이퍼: 메타 행이 웨이퍼별로 **수직 반복**되며 `WAFERID`로 group by

### 파싱 & 시각화 워크플로우 (3단계, 확정)

**Step 1 — 파싱 & 분류**
1. `pd.read_csv` / `pd.read_clipboard`로 long-form DataFrame 로드 (헤더 포함)
2. **헤더 정규화** (lower + 공백·언더바 제거) 후 필수 컬럼 매칭: `WAFERID`, `LOT ID`, `SLOTID`, `PARAMETER`, `RECIPE`, `DATA\d+`(1개 이상). `MAX_DATA_ID`는 있으면 추출
3. 매칭 실패(필수 컬럼 누락) 시 → **컬럼 매핑 다이얼로그** 팝업으로 사용자가 각 논리 역할에 실제 컬럼 선택
4. DATA 컬럼은 `^DATA[ _]?\d+$` (case-insensitive) 매칭으로 수집, 숫자 suffix 오름차순 정렬
5. `WAFERID`로 group by → 웨이퍼별 서브셋 (LOT/Slot 값 변동에 영향 받지 않음)
6. 각 웨이퍼의 `PARAMETER` 행 목록을 리스트로 수집 (UI 표시용)
7. 각 PARAMETER 행에서 **실제 DATA 값 개수**를 N으로 채택 (비어있지 않은 DATA 셀 수, 정렬된 순서 기준). `MAX_DATA_ID`가 있고 값이 다르면 **에러 팝업 후 실제 개수 사용**
8. 다중 웨이퍼일 때 UI에 보여줄 PARAMETER 리스트는 **모든 웨이퍼가 공유하는 공통 집합**

**Step 2 — 사용자 선택 UI (한 번 선택 → 모든 웨이퍼 공통 적용)**

페이스트 직후 VALUE/X/Y는 `settings.json`의 `auto_select` 규칙으로 **자동 채택** (사용자가 콤보에서 수동 변경 가능).
- **VALUE**: `value_patterns` (기본 `["T*"]`) fnmatch 매칭 + **값 개수 = DATA 컬럼 총 개수** 인 이름 우선
- **X**: `x_patterns` (기본 `["X", "X*"]`) — 완전 일치 → 접두사 매칭 순
- **Y**: X의 suffix를 물려받아 `Y{suffix}` 1순위. 없으면 `y_patterns` fallback
- 우선순위: 패턴 목록 순서 → 같은 패턴 내 알파벳 → 매칭 안 된 나머지(알파벳). 콤보 리스트도 동일 정렬
- **폴백**: 패턴 매칭 실패 시 `n == data_columns 총 개수` 인 이름 중 **알파벳 첫**을 자동 선택. 그마저도 없으면 `None` (사용자 수동 선택)
- **X 수동 변경 시 Y 자동 재선택** (suffix 동기화). **Y 수동 변경 시 X는 유지** — 사용자가 `X=X_1000`, `Y=Y_B` 같이 suffix 다른 조합을 의도적으로 고를 수 있게 비대칭 설계

1. **시각화할 VALUE PARAMETER** 선택 (예: `T1`, `T1_B`, `T2`, `T3_A`)
2. 좌표 결정 — 두 경로 중 택1:
   - **(A) 입력에서 좌표 PARAMETER 선택**:
     - X 좌표 PARAMETER (예: `X`, `X_1000`, `X_A`)
     - Y 좌표 PARAMETER (예: `Y`, `Y_1000`, `Y_A`)
     - 좌표 행은 보통 서로 인접 → X 선택 시 인접 행을 Y 후보로 우선 제안
   - **(B) 좌표 프리셋 라이브러리에서 불러오기**:
     - 버튼 항상 제공. 클릭 시 `n_points == 현재 VALUE 실제 DATA 개수`인 프리셋만 필터해서 목록 표시
     - 선택 시 좌표 PARAMETER 선택 UI는 스킵
3. ▶ Run 시 **좌표가 자동 프리셋 저장됨** (중복 없으면 추가, 있으면 `last_used` 갱신)
4. VALUE/X/Y 선택은 **기억하지 않음** (매 페이스트마다 다시 선택). 프리셋은 영구 저장소

**Step 3 — 시각화**
- 각 웨이퍼마다 선택된 (VALUE, X, Y) 삼중으로 `(X[i], Y[i], VALUE[i])` 점 집합 구성
- **좌표 단위 자동 mm 환산** (대부분은 mm이지만 `_1000`류 대비):
  - `|max| ≤ 200` → 이미 mm, 그대로 사용
  - `200 < |max| ≤ 200000` → μm 또는 ×1000 표기로 판정 → `/1000` 환산하여 mm
  - 그 외 → 사용자 수동 오버라이드 요청
- (VALUE/X/Y) 실제 DATA 개수가 서로 다르면 경고 팝업 + 시각화 차단
- 출력: 2D heatmap / 3D surface, cell 어디든 우클릭 → `Reset` / `Copy Image` / `Copy Data` / `Copy Table`, Summary 6종

## 설계 원칙
- 웨이퍼 직경 300mm 고정 — 반경 150mm **밖**의 측정점은 경고 팝업 후 제외 (실제 데이터엔 드물지만 안전장치)
- 파일 기반 I/O보다 클립보드 기반 UX 우선
- PARAMETER 이름·컬럼은 가변 — X/Y/VALUE를 자동 추론하지 말고 **사용자 선택 UI**로 해결 (Step 2 워크플로우)
- Profile Vision의 core·widgets 패턴(테마·설정·해상도 티어·차트 인터랙션)을 가능한 한 그대로 재사용

## 기술 스택 (확정)
**배포 형태**: PySide6 기반 **데스크톱 앱** (Profile Vision 방식). 브라우저·웹 방식 아님.

- Python 3.14.3
- **PySide6** — Profile Vision과 일치
- **pyqtgraph** — 2D heatmap + `pyqtgraph.opengl` 3D 주력
- numpy / scipy — 보간(`scipy.interpolate.griddata`) 포함
- pandas — 클립보드 / CSV 파싱
- chardet — 파일 인코딩 감지 (Profile Vision 참고)
- Qt style: `app.setStyle("Fusion")` — Profile Vision 규약

## 환경 / 배포
**배포 방식**: **무설치 포터블 폴더** (PyInstaller `--onedir`). 설치 과정 없이 폴더 전체를 복사·실행. 모든 런타임 파일(`settings.json`, `coord_library.json`, 로그 등)은 **앱 실행 폴더 내부**에 저장.

- 개발용 가상환경: `venv/`
  - Windows 활성화: `venv\Scripts\activate`
- 의존성 설치: `pip install -r requirements.txt`

## 실행
```
python app.py
```

샘플·테스트 산출물 (PNG/HTML 등)은 모두 **`debug/` 폴더**에 생성된다. `samples/`·`tests/` 안에는 산출물을 두지 않는다 (스크립트가 `_DEBUG = .../debug` 경로로 강제 저장). `debug/`는 `.gitignore`에서 통째로 무시.

## settings.json 스키마 (계획)

Profile Vision 관례 참고해 다음 키 운영. `core/settings.py`로 로드·저장.

| 키 | 설명 |
|---|---|
| `theme` | 차트 테마 (색상 팔레트, grid 색 등) |
| `window` | 메인·결과 창 크기 (해상도 티어로 auto 보조) |
| `font` | 폰트 family + 글자 크기 (title / section / body / caption) |
| `chart_common` | 2D/3D 공통 설정. 주요 키: colormap, interp_method, radial_rings, radial_seg, chart_width/height, decimals, edge_cut_mm, show_1d_radial, camera_distance, z_range_expand_pct. Radial 1D 보간 (`core.interp.RADIAL_METHODS`) 은 `radial_method` 콤보(Univariate Spline/Cubic Spline/PCHIP/Akima/Savitzky-Golay/LOWESS) + 각 알고리즘 파라: `radial_smoothing_factor`(Univariate, 0~15 step 0.1), `savgol_window`/`savgol_polyorder`(SavGol), `lowess_frac`(LOWESS 0.05~1.0). Settings 에서 선택 method 에 따라 관련 파라만 활성화. **Settings UI 제거·개발자값 고정**: `show_circle`/`show_notch`/`show_scale_bar`는 항상 True, `notch_depth_mm=3.0`, `boundary_r_mm=153.0`, `radial_line_width_mm=45.0` 고정. |
| `chart_2d` | 2D MAP 전용 (show_points, point_size, show_value_labels) |
| `chart_3d` | 3D MAP 전용 (smooth, z_exaggeration, show_grid, elevation, azimuth) — shading은 `shaded` 하드코딩, FOV=45·x_stretch=1.0 고정. `elevation`(-90~90°, 기본 40) / `azimuth`(-180~180°, 기본 -90) 는 Settings UI 노출. `camera_distance`는 `chart_common`으로 이동. |
| `z_scale_mode` | 다중 웨이퍼 3D Z 스케일 모드 (`common` / `individual`) — 메인 윈도우 컨트롤에서 토글 |
| `table` | `style` (Table Style 콤보 — 11종 중 선택, default `ppt_basic`) + `nu_percent_suffix`. 값 자릿수는 `chart_common.decimals` 로 이관 |
| `ui_mode` | UI 해상도 (Qt scale_factor) — `auto` (default, primary monitor 가로 자동 판정) / `FHD` (×0.75) / `QHD` (×1.0) / `UHD` (×1.3). 변경 시 재시작 필요 (`QT_SCALE_FACTOR` 환경변수). 사용자 정책 2026-05-01 — UHD 1.5 → 1.3 (FHD 모니터 control bar deadlock 회피). |
| `coord_library` | 자동 정리(`max_count` / `max_days` — 0=무제한, 기본 1000). 삭제 기준은 `last_used` 오래된 순 |
| `window` | `main`/`maximized`/`splitter_sizes`. `maximized=true`면 복원 시 `WindowMaximized` state + 복원 크기로 normalGeometry 저장 |
| `column_aliases` | 파싱 컬럼 이름 alias (`WAFERID`/`LOT ID`/... 확장) |
| `coord_library_path` | 좌표 프리셋 라이브러리(`coord_library.json`) 경로. 좌표 없는 입력 대비 저장·재사용 |

키는 필요 시 추가. 모든 기본값은 `core/themes.py` 또는 `core/settings.py`의 `DEFAULT_SETTINGS`에 중앙 관리.

## 아키텍처 (현행)
```
Wafer Map/
├── app.py                       ← QApplication 진입점 (Fusion 스타일 + MainWindow)
├── main.py                      ← long-form CSV/클립보드 파서 (parse_wafer_csv, WaferData/WaferRecord/ParseResult, MissingColumnsError)
├── core/
│   ├── themes.py                ← DEFAULT_SETTINGS / THEMES(14종) / FONT_SIZES / HEATMAP_COLORMAPS
│   ├── settings.py              ← settings.json 로드·저장 + 런타임 캐시 (load/save/set_runtime/invalidate_cache)
│   ├── stylesheet.py            ← 테마 캐스케이딩 글로벌 QSS (QTableWidget 가독성 포함)
│   ├── runtime.py               ← 해상도 티어 판정
│   ├── auto_select.py           ← VALUE/X/Y 자동 선택 + Y suffix 동기화 (X→Y만, Y→X 비동기)
│   ├── coords.py                ← normalize_to_mm / filter_in_wafer / match_points / WAFER_RADIUS_MM=150
│   ├── interp.py                ← RBF 4종(ThinPlate/Multiquadric/Gaussian/Quintic) + `RadialInterp` 1D spline + `is_radial_scan` 자동 감지 + `make_interp` 팩토리
│   ├── metrics.py               ← summary_metrics (AVG/MAX/MIN/RANGE/3SIG/NU%)
│   ├── delta.py                 ← compute_delta (WAFERID 매칭 → 좌표 합집합 + NaN 룰 + A−B + Δ-Interp 옵션)
│   ├── coord_library.py         ← CoordLibrary + CoordPreset (해시 버켓 O(N) 중복 검출, recipe_similarity, PRE/POST 베이스 매칭)
│   ├── input_summary.py         ← 단일 ParseResult 요약 (n_wafers / n_parameter / n_coord_pairs)
│   ├── input_validation.py      ← 단일 입력 정합성 (extra_header/repeat_measurement info, para_set_mismatch error)
│   ├── delta_validation.py      ← 양쪽 입력 정합성 (no_intersect/coord_unresolved error, coord_fallback ok, recipe_mismatch/no_common_value_para/repeats_in_input warn)
│   ├── recipe_util.py           ← RECIPE 호환 판정 단일 진실 원천 (`_+(PRE|POST)$` 베이스 비교, 구분자 `_` 만)
│   └── combine.py               ← CombinedItem / CombinedState (PARA 조합 단일 진실원, sum/concat recursive flatten)
├── widgets/
│   ├── main_window.py           ← 3-패널 QSplitter + view_mode 분기, closeEvent 윈도우 저장 + cache invalidate (combine 은 core/combine.py 사용)
│   ├── reason_bar.py            ← Message 라벨 + 사유 한 줄 표시. severity dynamic property 기반 QSS selector (테마 자동 반영). 빈 상태 ✓ 표시
│   ├── para_combine_dialog.py   ← Para 조합 다이얼로그 — mode 자동 판정 (좌표 동일 → sum) + recursive flatten + composites 콤보 노출 (state 기반)
│   ├── paste_area.py            ← Ctrl+V 타겟 (Text/Table 토글 + Clear). 단일 입력 검증 라벨 (severity 색)
│   ├── wafer_cell.py            ← WaferDisplay/WaferCell — 2D pyqtgraph + 3D GLSurfacePlotItem 동적 swap
│   ├── result_panel.py          ← (MAP+Summary) 쌍을 가로 나열, 합성 Copy Image용 컨테이너
│   ├── settings_dialog.py       ← non-modal Save/Close/Default. Save는 저장만 (close 안 함) — 사용자가 연속 조정 가능. Close 누르면 미저장
│   ├── preset_dialog.py         ← 좌표 프리셋 선택 (n_points 필터 + recipe_similarity 정렬 + group_by_coords 병합)
│   └── preset_add_dialog.py     ← 수동 프리셋 추가
├── samples/
│   ├── sample_data.csv          ← 실제 포맷 테스트 CSV (2 웨이퍼)
│   ├── sample_data.py           ← 샘플 점 생성기
│   ├── sample_*.py              ← 라이브러리 비교 샘플 7종 (matplotlib/plotly/pyqtgraph/pyvista/vispy/wfmap/cap1tan)
│   └── cases/                   ← 케이스 CSV (case01..case12, case_no_coords, case_inner_outer_combined — sum/concat 시연용)
├── tests/
│   ├── test_auto_select.py      ← auto_select 통합 테스트 10케이스
│   └── compare_interp.py        ← 4 보간 방법 한 화면 비교 (debug/output_compare_interp.png)
├── debug/                       ← 모든 샘플·테스트 산출물 (PNG/HTML) 통합 폴더 (.gitignore)
├── assets/                      ← 아이콘 등 정적 자원
├── requirements.txt
├── settings.json                ← 런타임 설정 (.gitignore)
└── coord_library.json           ← 좌표 프리셋 영구 저장소 (.gitignore)
```

**PARA 조합 — sum / concat recursive (0.4.0~)**

서로 다른 PARA + 좌표 페어를 합쳐 하나의 시각화로. Apply 후 main 콤보에 합성 항목으로 누적 등록 → Run 으로 시각화. recursive 가능 (합성 결과를 또 합성).

- **데이터 모델 단일 진실원**: `core/combine.py::CombinedItem` (N-ary dataclass) + `CombinedState` (누적 list). 기존 `_combined dict + _combined_pairs mapping + sentinel 문자열` 산재 → 7번 사용자 검증 사이클 발생 → 단일 진실원으로 리팩토링 (2026-04-29). `widgets/main_window.py` 가 import 만.
- **mode 자동 판정** (다이얼로그):
  - 두 좌표 페어 동일 → `sum` (element-wise 덧셈, 좌표 단일)
  - 다름 → `concat` (점 집합 합집합, 좌표 union)
- **친화 키 표기 (`v_key`/`x_key`/`y_key`)**:
  - sum: ` + ` (예 `T1 + T2 + T3`, 좌표 단일 `X` / `Y`)
  - concat: ` ∪ ` (예 `T1 ∪ T1_A`, 좌표 `X ∪ X_A` / `Y ∪ Y_A`)
- **recursive 자동 flatten** (`_flatten_same_mode`): 같은 mode 끼리는 평탄화. 다른 mode 면 그대로.
- **합성 operand 자동 괄호** (`_wrap_if_composite`): operand 가 ` + ` 또는 ` ∪ ` 포함 시 괄호. 한 줄 규칙으로 임의 깊이 처리:
  - `(T1 + T2) ∪ T_A`
  - `(((T1 ∪ T2) + T3 + T4) ∪ (T5 + T6)) ∪ T7`
- **Apply 시점 inject** (`_inject_combined_temp_paras`): 친화 키를 즉시 `wafer.parameters` 에 등록. 다음 다이얼로그 열 때 합성 PARA 가 `_gather_paras` 통과해 콤보에 노출되어 recursive 가능. paste 변경 시 `_clear_combined` 가 `state.temp_keys()` 기준 정확 제거.
- **다이얼로그 콤보 노출** (`para_combine_dialog`):
  - `_gather_paras` 는 ` + ` / ` ∪ ` 모두 필터 (plain PARA 만 반환)
  - composite 항목은 `combined_state` 에서 직접 빌드해 콤보에 추가 (🔗 prefix)
  - composite operand 선택 시 `_auto_pick_coord` 가 state 의 매핑으로 즉시 결정 (suffix 매칭 우회)
- **콤보 라벨**:
  - sum: `🔗 T1 + T2  [13 pt]` / `X/Y  [13 pt]` (좌표 plain)
  - concat: `🔗 T1 ∪ T1_A  [13+11 pt]` / `🔗 X/Y ∪ X_A/Y_A  [13+11 pt]` (operand 별 n breakdown)
- **이모지 통일** `🔗` (sum/concat 동일).

**입력 검증 + ReasonBar 단일 채널 정책 (0.3.0~)**

배경 — silent 분기로 인한 디버깅·UX 혼란 해결. 어제까지 `_on_visualize` 가 검증·skip·다이얼로그·clear 5가지를 다 떠안아 결과 영역과 입력 상태가 동기화 안 되는 문제. 분리 + 단일 채널화로 해결.

- **검증 분리** (단일 책임):
  - `core/input_summary` — 카운트 (n_wafers / n_parameter / n_coord_pairs)
  - `core/input_validation` — 단일 입력 정합성 (extra_header info / repeat_measurement info / para_set_mismatch error)
  - `core/delta_validation` — 양쪽 입력 정합성 (no_intersect/coord_unresolved error / coord_fallback ok / recipe_mismatch/no_common_value_para/repeats_in_input warn)
  - paste 직후 호출 → 결과 cache (`_delta_warnings`) → `_refresh_controls` (Run 활성/비활성 결정) + ReasonBar (사유 표시) 양쪽에서 재사용. 검증 한 번 → 두 채널 갱신.

- **severity 4단계 + 색 팔레트** (paste_area + ReasonBar 공통):
  - `error` (#d32f2f, 빨강) — Run 차단. `_SEVERITY_RANK = 3`
  - `warn`  (#e76f51, 주황) — Run 활성, 주의. `RANK = 2`
  - `ok`    (#2a9d8f, 민트) — Run 활성, **fallback 성공 알림**. `⚠` prefix 안 붙임 (정상 동작 톤). `RANK = 1`
  - `info`  (#666,    회색) — 정보. `RANK = 0`
  - 여러 건 동시 표시 시 max severity 색 채택, 메시지는 `, ` join

- **Run 단일 약속 + silent 분기 0** (사용자 정책 2026-04-27):
  - "Run 클릭 = 결과 영역이 현재 입력 상태와 동기화" — 잔재 없음
  - 차단 사유는 모두 `_show_blocking_reason(code, severity, message)` 헬퍼로 표시 (result_panel.clear + ReasonBar.set_warnings 한 번에)
  - paste 시점 `_delta_warnings` 보존 + 차단 사유 합쳐 표시 (ValidationWarning 리스트 합집합)
  - QMessageBox 사용 0 — 다이얼로그 차단 UX 제거. 모든 사유는 ReasonBar 단일 채널
  - 일부 wafer 좌표 실패 (skip) 와 라이브러리 자동 fallback (성공) 도 ReasonBar 알림 — silent 동작 0

- **DELTA 좌표 fallback 매트릭스** (`_resolve_delta_coords` + `delta_validation`):
  - 양쪽 좌표 O → 각자 사용 (compute_delta 합집합 매칭)
  - A 좌표 O + B 좌표 X + RECIPE 호환 → 옆집 (B 가 A 좌표 빌림) → ok
  - A 좌표 O + B 좌표 X + RECIPE 비호환 + B 라이브러리 매칭 ✓ → ok
  - A 좌표 O + B 좌표 X + RECIPE 비호환 + B 라이브러리 매칭 X → error (Run 차단)
  - A 좌표 X + B 좌표 O 도 대칭
  - 양쪽 좌표 X + 호환 + 라이브러리 매칭 ✓ → ok
  - 양쪽 좌표 X + 비호환 + A·B 라이브러리 모두 매칭 ✓ → ok (각자 사용)
  - 그 외 → error
  - 자세한 docstring: `widgets/main_window.py::_resolve_delta_coords`

- **RECIPE 호환 룰** (`core/recipe_util` — 단일 진실 원천):
  - 구분자 `_` 만 인정 + `_PRE` / `_POST` 토큰 끝/중간 어디서든 제외 후 베이스 비교 + 대소문자 무관
  - 끝: `Z_TEST_01__PRE` / 중간: `Z_PRE_TEST_01`, `CMP_PRE_THK` 모두 처리
  - 맨 앞 (`PRE_TEST_01`) 은 처리 안 함 (사내 데이터에 존재 안 함)
  - 부분 일치 보호: `Z_PRESET_01` (PRE+SET), `Z_POSTBAKE_01` 등은 lookahead `(?=_|$)` 로 매치 회피
  - `Z_TEST_01-POST` (하이픈) / `Z_TEST_01POST` (구분자 X) 는 비호환
  - DELTA 호환 판정 + `coord_library.find_by_recipe` (3-stage fallback: 정확 일치 → PRE/POST 베이스 일치 → similarity 3+ 토큰 매칭) 에서 사용

- **DELTA 합집합 매칭 + NaN 룰** (`core/delta::compute_delta`):
  - 양쪽 매칭 점: dv = va − vb (정상)
  - A only 점: dv = va (B = 0 가정)
  - B only 점: dv = −vb (A = 0 가정)
  - 한쪽만 가진 PARA 도 union 으로 콤보 노출 — DELTA 가능
  - tolerance: 1mm 직선거리

- **Δ-Interp mode** (체크박스, Control 패널, A·B 모두 유효 시 활성):
  - 활성 시 a_only / b_only 점에 RBF 보간으로 상대값 채움 → 정상 delta
  - 비활성 시 NaN 룰 (위 조항)
  - `compute_delta(..., interp_factory=...)` 로 Settings 의 보간법 사용
  - `DeltaWafer.interp_indices` 에 보간 점 인덱스 기록 (시각화 마커용, 현재 미사용 deferred)

- **signature skip 폐기** (2026-04-27): 같은 입력 재클릭 = reset 의미. 매번 새로 시각화. cell 재생성 비용 무시 가능. `_applied_cam_dist` 등 별도 추적기로 카메라 상태만 보존

**3D 렌더링 메모**
- 셰이더는 `shaded` 하드코딩. (normalColor/heightColor는 콤보 변경해도 시각적 효과 의미 없거나 컬러맵 무시되어 제거)
- 카메라: FOV=45 고정, x_stretch=1.0 고정 (Settings에서 제거). `camera_distance`(= Map Size, chart_common, 400~800 step 10, 기본 620) · `elevation`(chart_3d, -90~90°, 기본 40) · `azimuth`(chart_3d, -180~180°, 기본 -90) Settings UI 노출
- Z-Height(`z_exaggeration`): 0.5~3.0, 0.1 step, 기본 1.0 (자동 옵션은 1.0과 동치라 제거)
- 2D/3D 휠 zoom 활성 — pyqtgraph 기본 `wheelEvent` (distance 변경). 예전엔 `_LockedGLView.wheelEvent.ignore()` 로 3D 차단했었는데 `_applied_cam_dist` 트래커 도입 후 불필요해져 제거. `_render_*` 에서 Settings Map Size 와 `_applied_cam_dist` 비교 — 값 바뀔 때만 `setCameraPosition(distance=...)` 호출, 그 외엔 사용자 휠 zoom 상태 유지. Reset 메뉴로 카메라 초기화
- 경계 원 `GLLinePlotItem`은 `glOptions='opaque'`로 둬야 뒤쪽이 가려짐 (기본 `translucent`는 depth-write off라 항상 보임)
- **Copy Graph 는 offscreen FBO 렌더 방식** (0.2.0). `wafer_cell._capture_gl_offscreen(gl_view, scale=1)` 가 `QOpenGLFramebufferObject(MSAA=4)` 로 `gl_view.paint(region, viewport)` 호출 → `toImage()`. widget 이 스크롤에 가리거나 다른 창이 덮어도 완전 렌더. MSAA 4x 는 FBO format 에서 강제라 화면 `samples()=0` 환경도 캡처는 AA 적용. 합성: `_capture_container.grab()` 바탕 위에 FBO 이미지를 `chart.mapTo(cap)` 위치에 drawImage, 그 후 overlay (title / _colorbar / _badge_2d/3d) 를 각자 `.grab()` 해 drawPixmap 해 z-order 복원. `GLTextItem` 은 pyqtgraph 가 `QPainter(self.view())` 로 widget 에 직접 그려 FBO 에 반영 안 됨 → FBO 후처리에서 `compute_projection + align_text` 재현해 QImage 위에 `drawText`, QSS-resolved widget font family 를 `QFont.setFamily` 로 전파. `scale=1` 전제 (pxMode scatter/label 크기 보존 + widget.rect == FBO size). FBO 실패 시 기존 `QScreen.grabWindow(0)` crop 방식 폴백.
- **Shift+좌클릭 다중 셀 동기**: press 순간 클릭 셀의 카메라(`elevation/azimuth/distance/center/fov`)를 전 셀에 복사 → 이어서 Shift 유지 드래그하면 실시간 전파. WeakSet 레지스트리로 인스턴스 자동 추적, `update()`만 재호출해 캐시 영향 없음
- 2D `PlotWidget`: `setMouseEnabled(False, False)` + `setMenuEnabled(False)` + **`hideButtons()`로 좌하단 auto-range [A] 버튼 숨김** (누르면 크기 변화)
- 렌더 AA: `app.py`에서 `QSurfaceFormat.setDefaultFormat(samples=4)` + `_LockedGLView.setFormat(samples=4)` — 드라이버/pyqtgraph 조합에 따라 안 먹을 수 있음

**1D radial scan 자동 감지 (CMP 등 rotation symmetric 공정)**
- `core/interp.py::is_radial_scan(x, y, line_width_mm=45)` — 원점 중심 (길이 300 × 폭 `line_width_mm`) 직사각형에 모든 점 fit 되면 True
  - SVD of raw points (centering 없이) → 원점 통과 best-fit 방향. 최대 수직편차 ≤ line_width_mm/2 판정
  - 각도/오프셋 무관 (수평/수직/45°/임의 각도 모두 동일)
- `core/interp.py::RadialInterp` — `RBFInterpolator` 와 동일 인터페이스. `(x,y,v) → (r,v) → UnivariateSpline(r_u, v_u, k=3, s=n·noise²·factor, ext=3)`. `smoothing_factor=10.0` 하드코딩 (factor ≥ 3 부터 시각 차이 없음, 10은 나이테 방지 safe 값). 1μm 양자화 + 같은 r 평균으로 ±대칭 / zigzag perp 편차 통합
- `core/interp.py::make_interp(..., radial_line_width_mm)` — 팩토리. 자동 감지해서 `RadialInterp` 또는 `make_rbf` 반환. render 경로 (wafer_cell.py, main_window.py) 는 `make_rbf` 대신 이 팩토리를 호출
- Settings `1D Scan 폭` 스핀박스 (10~150mm, 기본 45mm, step 5mm). 내부에서 /2 로 half_width 사용

**3D pinwheel artifact (알려진 tech debt)**
- CMP 같은 radial symmetric 3D 렌더 중심부에 희미한 비대칭 "그림자" 패턴. radial mesh triangulation 의 vertex normal 이 회전 대칭 아님 + `shader="shaded"` lighting 이 이 편향 증폭. 2D 는 shader 없어 영향 무
- 현재 수용 ("자연스러운 그림자"). 해결 옵션: (A) analytic radial normal 주입 (RadialInterp 전용, 완벽) (B) bowtie triangulation — quad diagonal 번갈아 (범용 개선) (C) flat shading 또는 shader=None (3D 깊이감 저하)
- 메모리: [project_3d_pinwheel_artifact.md](memory)

**1D Radial Graph 위젯 (0.1.0~)**
- Settings `1D Radial Graph` 체크 → WaferCell 의 chart_box 와 Summary 표 사이에 `pg.PlotWidget` 삽입 (기본 hidden)
- 구성: 실측 `(r_i, v_i)` 산점도 (검정 4px) + 1D 스플라인 실선 (`#777`, 2px). `RadialInterp` 재사용 — 메인 맵이 RBF/Radial 어느 경로든 무관
- **스플라인 그리기 범위 = 측정 r 범위 [r_min, r_max] 만** (0~150 전체가 아님). `r<r_min` (센터 측정 없을 때) 구간은 공백 — 정석 과학 시각화 관례 (flat 외삽 / 왜곡된 미러 모두 부적절). 센터 포함된 CMP 1D 스캔에선 자연스럽게 0 부터 그려짐
- 축: 좌/하만 visible (Y/X 라벨). 상/우 축은 visible 이지만 **pen 투명 + tickLength=0 + ticks 비움** 으로 보이지 않는 padding 역할
  - 우축 폭 48 (좌축 48 과 대칭) — 플롯 영역이 widget 내부에서 **중앙 배치** (위젯은 cell 꽉 채움, 플롯만 좁게)
  - 상축 높이 16 — 2D/3D 맵과 1D 플롯 사이 수직 여백 확보
- X = `-10~160` (0~150 대칭 10mm 여유), 하단 주눈금 0/50/100/150. Y = 3 tick (min / midpoint / max), 자릿수는 colorbar 공식 `max(0, -log10((vmax-vmin)/4))` 과 동일
- 축 숫자 색 `#111111` (표 글자색과 동일), 폰트 12px **하드코딩** (font_scale 무관 — 축 폭 고정이라 큰 폰트 시 잘림 방지)
- 위젯 width = `w + bar_w` (cell content 꽉 채움). height 135px
- Y 범위 = `display.z_range_1d` (개별/공통 토글 + Z-Margin 공유, 실측 v min/max 기반). 2D/3D 의 rendered range 와 **독립**. 뷰 padding 추가 8%
- visibility / size: `_apply_chart_size` 가 `show_1d_radial` 에 맞춰 설정. data plot 은 `_update_radial_graph` (render_2d/render_3d 끝에서 호출)

**Summary 표 카탈로그 (0.3.0~, F82-F86 refactor)**

`widgets/summary/` 패키지 — 11 style + base + factory 구조. `Settings → Table Style` 콤보로 cell 별 표 디자인 변경.

- **Base** (`widgets/summary/base.py`):
  - `SummaryWidget(QWidget)` — 추상 base. 인터페이스: `update_metrics(m, decimals, percent_suffix)` / `set_target_width(w)` / `apply_fonts()` / `copy_table_data() → list[list[str]]` / `is_chart_overlay_only()` / `overlay_texts() → (Mean, Range, NU)` (no_table 만)
  - `_TableSummary(SummaryWidget)` — `QTableWidget(rows=2, cols=3)` 베이스. `ROWS / COLS / HEADERS` override 가능. `_make_delegate()` / `_populate_headers()` / `_fill_values()` 만 자식에서 구현 — boilerplate 80 라인 제거 (F83).
  - 공용 helper: `format_metrics(metrics, decimals, percent_suffix) → (avg_s, range_s, nu_s)`, `dynamic_decimals(vmin, vmax)`, `STYLE_DISPLAY_NAMES`
- **Factory**: `widgets/summary/__init__.py::build_summary(style_key, parent) → SummaryWidget` + `available_styles() → [(key, display)]`. `STYLES` dict 등록만 하면 콤보에 자동 노출.
- **11 style**:
  - **`_TableSummary` 상속 (3종, delegate paint 매번 `FONT_SIZES` re-read)**: `ppt_basic` (기본), `dark_neon`, `vertical_stack`
  - **자유 layout (7종, `__init__` 끝 `apply_fonts()` 로 stylesheet 박제)**: `big_number`, `highlight_lead`, `stat_tiles`, `minimal_underline`, `pill_badge`, `color_footer`, `layered_depth` (Rounded Card)
  - **overlay-only (1종)**: `no_table` — 표 영역 0 (`SUMMARY_RESERVED_H=0`), wafer_cell 의 `_chart_overlay_2d/3d` (=`_OutlineLabel`) 가 chart 좌상단 Mean/Range/N.U % 표시. 흰색 외곽선 + #666666 fill, 글로벌 폰트 follow.
- **font_scale 변경 정책 (F85)**: cell 의 `_summary` 위젯 swap 안 하고 `apply_fonts_all` (가벼운 reflow) — set_table_style swap 의 ~5ms × N 비용 회피. delegate 기반 3종은 paint 마다 re-read 라 자동 반영.
- **Copy Table 정책 (F86)**: 자유 layout style 도 `copy_table_data()` override 로 자체 row/col 반환. base default 는 `_last_metrics` 기반 3 col × 2 row.
- **(레거시) ppt_basic 의 표 자체 디자인** — 위젯 폭 `setFixedWidth(w + bar_w - 16)` (cell 보다 좌/우 8px), `setShowGrid(False)` + item border 로 4변 1px 균일, 테두리 `#888888` / 글자 `#111111` / `FONT_SIZES['body']`.

**UI 해상도 (`ui_mode`) — Qt `QT_SCALE_FACTOR` 기반 (F81, F96)**
- `core/themes.py::UI_MODE_SCALE = {"FHD": 0.75, "QHD": 1.0, "UHD": 1.3}`. `auto` 는 tkinter 로 primary monitor 가로 측정 후 임계값 (2400 / 3200) 으로 FHD/QHD/UHD 분기. 변경 시 **앱 재시작 필요** — `QT_SCALE_FACTOR` 는 QApplication 인스턴스 생성 전에만 set 가능.
- `app.py::_apply_ui_scale()` 이 모듈 top-level (line 61) 에서 호출 — `QApplication` 생성 (line 162) 보다 먼저. `scale==1.0` 분기에선 외부 env 잔존 방지 위해 `os.environ.pop("QT_SCALE_FACTOR", None)` (F96 H).
- **deadlock 회피 (F96)**: 작은 모니터 + 큰 scale 조합 (예 FHD 모니터 + UHD 1.5) 에서 윈도우가 화면 밖으로 나가 Settings 버튼 클릭 불가. 두 단계 fix:
  1. `widgets/__init__.py::clamp_to_screen(widget)` helper — 모든 dialog 와 main_window 에서 size 를 `availableGeometry` 안으로 clamp.
  2. UHD scale 1.5 → 1.3 — control bar 의 logical minimum width (~1280) 가 FHD 모니터 logical avail (1.5 시 1280) 와 정확히 fit 되어 frame border 가 화면 밖으로 나가던 문제. 1.3 으로 logical avail 1477 확보 → 197px 여유.
- `Qt.AA_ShareOpenGLContexts` set 도 QApplication 생성 전 (line 154) 에 호출 필요 — `_apply_ui_scale` import 체인이 `QApplication`/`QGuiApplication` 을 instantiate 하면 안 되는 묵시적 invariant.

**font_scale 동작 (settings UI 폰트 크기 콤보 연동)**
- `core/themes.py`: `FONT_SIZES` (가변) + `BASE_FONT_SIZES` (base backup, `dict(FONT_SIZES)` 로 생성)
- `settings_dialog.apply_global_style`: `BASE_FONT_SIZES` 에서 `scale` 곱해 `FONT_SIZES` 영구 갱신 → 이후 FONT_SIZES 읽는 모든 코드 (차트 제목 / 컬러바 / 1D 축 / 표) 가 scale 반영된 값 얻음
- 이전 버그: `try/finally` 로 QSS 빌드 직후 FONT_SIZES 원복 → 차트 내부 텍스트가 scale 무시. 지금은 영구 갱신이라 해결
- `SettingsDialog.ui_changed` → `_apply_ui_runtime` (QSS 재빌드) + `_apply_graph_runtime` (cell.refresh) 양쪽 emit → cell 내부 폰트도 즉시 반영
- cell.refresh 에서 제목 인라인 stylesheet 재작성 (`FONT_SIZES['body'] + 3` → 17px 기본)
- 컬러바: `paintEvent` 에서 매번 FONT_SIZES 조회 / 1D 축: `_update_radial_graph` 에서 `setStyle(tickFont=…)` 재적용

**폰트 크기 계층 (font_scale=1.0 기본):**
- 차트 제목: `FONT_SIZES['body'] + 3` = 17px
- 표 텍스트: `FONT_SIZES['body']` = 14px
- 컬러바 / 1D 축 숫자: `FONT_SIZES['caption']` = 12px
- 모든 텍스트 색 `#111111` 통일, 테두리 `#888888` 통일

**카메라 zoom 상태 보존 (Settings 변경 시 사이즈 유지)**
- `WaferCell._applied_cam_dist` 인스턴스 속성 — 마지막으로 settings 에서 적용한 `camera_distance` 추적
- `_render_2d`/`_render_3d` 에서 `opts['distance']` (현재 위젯 상태, 사용자 휠 zoom 반영됨) 와 비교하지 않고, `_applied_cam_dist` 와 비교. settings 값이 **실제로 바뀔 때만** `setCameraPosition(distance=…)`
- 비교 대상이 위젯 opts 이면 사용자 zoom 마다 "차이 감지" 로 리셋되는 버그 있었음 → 이 속성 도입으로 해결
- Reset 메뉴 action 에서도 `_applied_cam_dist` 동기 (이후 render 가 또 리셋 트리거 않도록)

**좌표 프리셋 라이브러리 성능**
- `group_by_coords`는 첫/중간/마지막 점을 양자화한 해시 버킷으로 O(N) 처리 (2,000개 기준 9ms — naive O(N²)는 44초)

**Y → X 자동 동기화는 의도적으로 비대칭**
- X 변경 시 Y는 suffix 일치로 재선택 / Y 변경 시 X는 그대로 유지
- `X=X_1000`, `Y=Y_B` 처럼 사용자가 다른 suffix 조합을 의도적으로 고를 수 있게 함

**VALUE 콤보 동작 규약**
- VALUE 리스트에서 **현재 선택된 X/Y** 파라미터는 자동 제외 (좌표 PARAMETER는 VALUE 후보 아님)
- `_refresh_controls` / `_on_x_changed` / `_on_y_changed` 모두 `_refilter_value_combo`로 재필터
- VALUE 콤보 변경 시 기존 셀이 있으면 **즉시 재시각화** (Run Analysis 버튼 안 눌러도 됨)

**Summary 표 (3행, 테마 무관 흰색)**
- `Average` / `Non Unif.` / `Range, 3Sig` 3행으로 단순화 (LOT/SLOT은 타이틀과 중복이라 제거, MIN~MAX도 제거)
- 소수점 `chart_common.decimals` 전역. 컬러바는 별도 tick_step 동적 (적용 안 함)
- **배경 흰색 · 글자 #222 고정 stylesheet** — 다크 테마에서도 PPT paste용 고정. `QHeaderView::section` 도 같이 고정
- 스크롤바 ScrollBarAlwaysOff + `_update_table` 끝에서 `resizeRowsToContents()` + 합산으로 `setFixedHeight` → Copy 캡처에 스크롤바 안 따라옴

**셀 타이틀**
- 포맷: `{lot_id}.{pad2(slot_id)} – {PARA}` (en-dash) / DELTA는 `... – Δ {PARA}`
- Slot ID는 출력만 zero-pad 2자리 (`_pad_slot`). 내부 파서 값은 원본 유지
- 폰트: `FONT_SIZES['body'] + 4` px, bold, `#444` (전역 QSS의 QLabel font-size를 인라인 stylesheet로 override)

**좌표 프리셋 라이브러리 — 자동 정리 정책**
- `coord_library.max_count` / `max_days` (0=무제한, 기본 1000) — `enforce_limits`
- **max_days 기준은 `last_used`** (created_at 아님) — 최근 쓴 레코드는 생성 오래돼도 유지
- `_visualize_single` / `_visualize_delta` 끝에서 `_enforce_library_limits` 호출 (Settings Save도 동일 경로)
- 자동 이름 충돌 시 `(2)`, `(3)` suffix — 동일 recipe·n에 좌표만 살짝 다른 레코드 구분

**좌표 라이브러리 탭**
- 헤더 클릭 정렬 (QTableWidget `setSortingEnabled`). `n`은 `setData(DisplayRole, int)` 숫자 정렬, 날짜는 ISO 사전순 = 시간순
- populate 시 `setSortingEnabled(False)→True` 토글 (setItem 마다 재정렬 방지)
- `gather()`가 `enforce_limits` 결과 `removed` 있을 때만 refresh — 없으면 사용자 정렬 상태 유지
- 컬럼: Interactive + content 기준 natural 폭 계산 후 여유분 균등 분배. `resizeEvent`에서 재분배

**프리셋 수동 추가 다이얼로그**
- 4 포맷 자동 감지: 행+X/Y라벨 / 행 라벨없음 / 열+xy헤더 / 열 헤더없음. y-first도 허용 (순서 무관)
- 노이즈 허용: BOM/NBSP/ZWSP, 유니코드 minus, 토큰 양끝 따옴표, leading/trailing 비데이터 행 자동 스킵
- 페이스트 직후 미리보기 테이블(2행 X/Y × N열 DATA1..N) 라이브 표시

**Settings 다이얼로그 구조**
- 디자인 설정 탭: `Default` 버튼 **탭 내부 좌측 하단 sticky** (다른 탭엔 안 보임)
- 좌표 라이브러리 탭: 정렬 콤보 삭제 (헤더 클릭 정렬). `Default` 없음
- 공통 하단 버튼: Save / Close만. Save는 저장만 (close 안 함)
- **SettingsDialog(parent=self)** — 0.2.0 FBO Copy Image 전환으로 tech debt 해결. 이전엔 Settings 창이 위에 뜨면 화면 캡처에 포함되어 `parent=None + Qt.Window` 로 transient owner 끊었었으나, FBO 는 화면 독립이라 원복. `_main_window`/`setMainWindow` 호환성 fallback 도 dead 라 제거됨 (2026-05-01) — `self.parent()` 직접 사용.

**렌더링 최적화 전반**
상세 이력·측정 결과·실패·롤백 사례·pyqtgraph 내부 의존성은 **[docs/rendering_optimizations.md](docs/rendering_optimizations.md)** 참고 필수. 새 최적화 시도 전 "실패·롤백" 섹션부터 확인 — 같은 실수 반복 금지.

핵심 구조만 요약:
- `WaferCell._chart_box` = `QStackedLayout` (2D/3D 위젯 둘 다 미리 생성, `setCurrentIndex`로 즉시 토글)
- **3단 캐시**: 렌더(`_rendered_2d/3d`) · 보간(`_interp_cache`, key `(method, G)`) · mask(`_mask_cache`, key `(G, show_notch, depth)`)
- **3D GL item 재사용**: `_gl_surface`/`_gl_boundary`/`_gl_grid` slot 보관, `setData`로 데이터만 교체. shader/smooth 변경 시에만 재생성
- **z signature skip**: `_surface_z_sig`가 같으면 `setData(colors=only)` + **명시 `meshDataChanged()`** (pyqtgraph setData(colors-only)가 meshDataChanged 호출 누락하는 버그 우회)
- **Vectorized vertex normals 주입**: `_meshdata._vertexNormals` 직접 set (pyqtgraph 기본 Python loop 우회)
- **병렬 RBF**: `ResultPanel.refresh_all`·`set_displays`에서 `ThreadPoolExecutor`로 cell별 `prefetch_interp` 병렬
- **첫 3D 전환 prefetch**: `set_displays` 후 `QTimer.singleShot(50, prefetch_inactive_views)` → hidden `_gl_3d.grabFramebuffer()`로 GL init 강제 (깜빡임 없음)
- **Settings graph_changed** → `refresh_graph` = `ResultPanel.refresh_all` (cell 재생성 없이 각 cell.refresh())
- `_apply_z_scale_mode`는 `cb_zscale`을 ground truth로, view_mode 분기 없음. 토글 시 `refresh_all()` (2D `img.setLevels(z_range)`도 영향 받기 때문 — `invalidate_3d`만으론 2D 컬러 스케일 안 바뀜)
- **Z-Margin 스핀박스 (메인 컨트롤 패널, cb_zscale 옆)**: 공통 모드 전용. 개별 모드에선 disable + 값 0 회색 (저장값은 별도 보관). matplotlib `ax.margins()` 관례 — `midpoint` 고정, `range × (1 + pct/100)` 로 확장. pct=0 원본, 50% → 1.5배, 100% → 2.0배. 각 wafer 가 palette 더 좁게 써서 시각 대비 부드러워짐. `_apply_z_scale_mode` 끝에서 적용. 즉시 settings.json 저장 + 전 셀 재렌더
- **첫 Run Analysis 시퀀셜 표시 제거**: `ResultPanel.set_displays`가 `container.hide() → cells 생성·렌더·addWidget → layout.activate() + adjustSize() → container.show()` 순서. activate/adjustSize 빠지면 show() 직후 (0,0) 중첩 → HBoxLayout 펼침이 1프레임 보임
- **첫 Run lazy init 흡수**: `app.py::_pg_widget_warmup` 이 시작 시 dummy `pg.PlotWidget` + `_bg_warmup` 이 dummy `RBFInterpolator` 1회 호출 — 첫 Run Analysis 가 두번째와 동속
- **WaferCell.cleanup() — GL VBO/FBO 명시 release (F100, 2026-05-02)**: cell `deleteLater` 직전 `ResultPanel._clear_layout` 이 호출. 각 `_gl_2d`/`_gl_3d` 에 `makeCurrent → clear() → _cached_capture_fbo=None → doneCurrent` + GL slot/큰 array None. cell 자체는 GC 잘 되지만 (`alive=0` 검증), pyqtgraph 가 GLMeshItem destructor 에서 `glDeleteBuffers` 안 호출해 driver memory 잔존 → 명시 cleanup 으로 cycle 잔재 18MB → 9MB 절반.

**Run 연타 차단 + Progress bar + Stress test (F100, 2026-05-02)**

- **`_on_visualize` 직렬화**: `_visualize_in_progress` flag + `btn_visualize.hide()` + `progress_run.show()` + `processEvents(ExcludeUserInputEvents)` (paint 만) + `QTimer.singleShot(0, _do_visualize_and_defer_restore)`. 전체 cycle = button hide → defer work → defer restore. button 이 hidden 이라 OS 큐의 click event 가 button 으로 dispatch 안 됨 (Qt 가 hidden widget 의 mouse event 무시) → 연타 reentrancy 차단.
- **`progress_run` swap (Run 자리)**: `QProgressBar(0, 100)` `setFormat("처리 중... %p%")`. `_do_visualize` 가 동기 CPU bound 라 paint 안 들어와 indeterminate (0,0) 모드는 멈춤 → determinate 단계별 `_set_progress(5/20/40/60/85/95/100)` + `processEvents(ExcludeUserInputEvents)` 로 paint 강제. mousePressEvent/mouseReleaseEvent `accept()` swallow + `_restore_run_button` 에서 button show 전 `processEvents()` flush 로 progress 클릭이 다음 Run trigger 회귀 방지.
- **Stress test mode (Ctrl+Shift+T 시작 / Esc 정지)**: `MainWindow._show_stress_dialog → _start_stress(N)` — 입력 다이얼로그로 cycle 수 입력, paste 한 데이터로 자동 N 회 Run. `_restore_run_button` 끝에서 `_stress_log_cycle` chain → `gc.collect()` ×2 + `WaferCell._alive_instances` len + `psutil` RSS 측정 → `debug/stress_log_YYYYMMDD_HHMMSS.csv` append (cycle/timestamp/n_wafers/t_ms/alive/total_created/rss_mb). ReasonBar 우측에 `Stop (N/Total)` 버튼 카운트 실시간. 매 1000 cycle 마다 `gc.collect(2)` full GC.
- **누적 leak 검증 (1800 wafer 누적, 2026-05-02)**: 100 cycle × 18 WF stress test 결과 — `t_ms` 변동 ±2% (누적 0), `alive=18` 고정 (cell GC 완벽), RSS 가 cycle 60 까지 +85MB 증가 후 cycle 62/72/88 에 OS 가 자체 회수해 cycle 100 에서 시작 +27MB. 단조 증가 아니라 **plateau + oscillation**. 한 달 무중단 사용 시나리오 안전성 검증됨.

**Startup warmup 구조 (0.2.1~)**
- 이전 `_async_warmups` 단일 콜백이 GUI 스레드 0.5~2s 점유 → 윈도우 응답성 저하
- 분리 구조: GUI 스레드 단계 분할 (`_gl_warmup` → 다음 틱 `_pg_widget_warmup`) + 백그라운드 `threading.Thread` 로 `_bg_warmup` (scipy RBF dummy + lazy import). Qt widget 은 GUI 스레드 전용이므로 백그라운드는 절대 만지지 않음
- 측정 (벤치): GUI 스레드 ~167ms (gl 132ms + pg 35ms), bg 스레드 ~1.1s (병렬). 이전 대비 GUI 점유 89% 감소
- 진단용 startup bench 출력은 F94 (2026-05-01) 에서 제거됨

**3D 첫 렌더링 깜빡임 제거 (0.1.0~)**
- `app.py`에서 `Qt.AA_ShareOpenGLContexts` set + 시작 시 dummy `GLViewWidget` show→hide→deleteLater (`_gl_warmup`).
- `result_panel`에 hidden `GLViewWidget` 1개 영구 자식. startup show 시점에 ancestor가 native window로 일괄 승격되어, 이후 cell의 GL widget 추가 시 깜빡임 없음.

**페이스트 응답성 (0.1.0~)**
- `_fill_table` 동안 `ResizeToContents` 일시 해제(`Interactive` 모드) — 매 setItem마다 컬럼 측정 트리거 방지 (991ms → 6ms)
- Table 뷰가 비활성이면 dirty 플래그만 set, Table 토글 시점에 채움 (lazy fill) — paste 직후 0ms

**버튼 폭 정합 규약**
- `paste_area.HEADER_BUTTON_WIDTH = 88` 모듈 상수.
- Text/Table/Clear, Settings 다이얼로그의 Save/Close/Default 모두 같은 폭.
- 메인 Run Analysis는 `HEADER_BUTTON_WIDTH * 3 + HEADER_BUTTON_SPACING * 2 = 276` 폭 + control panel과 paste_area의 좌우 margin이 동일(8) → 시작/끝 X가 Input B의 Text/Clear와 자동 일치.

**메인 액션 강조 색**
- `class="primary"` (글로벌 QSS) — `t.get('primary_btn', t['success'])` fallback. 두 테마(Mint Cream / Everforest Light)는 `success`가 `accent`와 같아 강조가 안 보였기에 `primary_btn` 키 명시 추가.

**컬러맵 확장**
- `HEATMAP_COLORMAPS` (core/themes.py): pyqtgraph 기본 16종 + Reverse 5종(Viridis/Plasma/Inferno/Magma/Cividis) + 커스텀 White 2-stop 7종(`Red/Blue/Black/Navy/Pink/Brown/Charcoal-White`) = 28종. 첫글자 대문자 / PascalCase-dash 표기 규칙.
- 실제 `pg.ColorMap` 인스턴스는 `wafer_cell._CUSTOM_CMAPS`. `resolve_colormap(name)` 헬퍼가 커스텀→pg(대소문자 무관)→viridis fallback 순서.
- Reverse는 `pg.colormap.get(base).color[::-1]`을 uint8 변환 후 새 `pg.ColorMap` 생성 (pg 기본은 float64라 변환 필수).
- 기본값 `Turbo` / 격자 해상도 `150`.

**컬러 스케일바 (`_ColorBar` in wafer_cell.py)**
- `QWidget` + `QPainter` 직접 그리기. `pg.PlotWidget` 버전(280ms) 대비 ~0.1ms로 경량.
- 위치: cell 우측. 라벨은 bar 좌측에 우측정렬. 그라데이션 top=max 색 / bottom=min 색.
- 폭 60px 고정, bar 14px, 좌우 5px 마진. 라벨은 5-tick (top/25%/mid/75%/bot).
- 토글(`show_scale_bar`)은 정렬만 변경 (chart_area는 항상 fixed) — 3D GL widget 사이즈 변동 방지.

**차트 사이즈 / 셀 통합**
- `chart_common.chart_width × chart_height` 고정. 비율 360:280 (대 432×336 / 중 360×280 / 소 288×224).
- `WaferCell(QFrame)` 의 `_capture_container` `setObjectName("waferCell")` + `border: 1px solid #bfbfbf` 통합 패널. 제목 + 차트 + 컬러바 + Summary 표를 한 박스로 묶어 Copy Image 가 합성 이미지 한 장.
- `_chart_box = QStackedLayout(2D pyqtgraph / 3D _LockedGLView)` — `setCurrentIndex`로 즉시 토글. 2D/3D 모두 휠 zoom 활성.

**웨이퍼 notch 표시**
- `chart_common.show_notch` (default on) + `notch_depth_mm` (3~6mm, default 5mm). 방향은 6시(3π/2) 고정, V자 폭 ±3°.
- `_boundary_xy(show_notch, depth)`: 2D plot과 3D GLLinePlotItem 공유 경계 좌표.
- `_points_inside_wafer(XG, YG, show_notch, depth)`: 격자점 inside mask. V자 내부 + cell 반지름(0.5 픽셀) margin까지 투명 처리 → 해상도 무관 V자 영역 크기 동일.
- 3D 기본 카메라 `azimuth=-90` — notch가 화면 하단(6시)에 정렬되는 앵글.
