# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 개발자 정보
- 한국인, 코딩 중급 수준
- 직접 코딩하지 않고 Claude에 코드 수정 권한 위임 — 제안·논의·리뷰 중심 협업
- 한국어로 친구처럼 반말로 소통
- **코드 변경 전 반드시 협의 후 진행** — 바로 수정 금지

## 관련 프로젝트 / 참고 기준
Wafer Map은 회사 업무의 반도체 측정 데이터 시각화 프로젝트. **자매 프로젝트 Profile Vision**의 스택·코어 구조·UI 규약을 1차 참고 기준으로 한다.

| 프로젝트 | 위치 | 역할 |
|---|---|---|
| **Profile Vision** | `C:/Users/JHPark/Profile Vision/` | 자매 프로젝트. 스택·core·widgets·차트 규약 **참고 기준** |
| Wafer Map (본 프로젝트) | `C:/Users/JHPark/Wafer Map/` | 신규 |

`C:/Users/JHPark/Profile Vision/CLAUDE.md` 에 차트 인터랙션·테마 시스템·해상도 티어·settings.json 규약이 정리되어 있음. Wafer Map의 UI·설정 패턴은 이를 먼저 참고하고 재사용.

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

### 확정 기능 요구사항 — 클립보드 출력 (PPT 워크플로우)
입력이 클립보드라면 **출력도 클립보드**. 모든 시각화 산출물은 PPT에 바로 Paste 가능해야 함. Profile Vision의 구현 패턴을 그대로 재사용한다.

| 기능 | 동작 | Profile Vision 참고 구현 |
|---|---|---|
| **Copy Graph** | 차트(2D/3D) → 클립보드 **이미지**. PPT에 그대로 Paste | `result/result_window.py::_copy_chart` — `plot_widget.grab()` → `clipboard.setPixmap()` |
| **Copy Table** | 측정값 Summary 표 → **PPT 표**로 Paste (Excel에선 셀로) | `result/result_window.py::_copy_table` — `QMimeData`에 `setText(tsv)` + `setHtml(html_table)` **듀얼 MIME** |
| **Copy Data** | 차트의 raw 측정값 → TSV (Excel 붙여넣기용) | `result/result_window.py::_copy_chart_data` — `clipboard.setText()` |

**핵심**: Copy Table은 **TSV 단독으로는 PPT 표가 안 된다.** `QMimeData`에 HTML을 함께 넣어야 PPT가 `<table>`로 인식하고 셀로 붙여넣음. 단일 MIME(TSV만)이면 PPT는 텍스트박스 + 탭 문자열로만 붙임.

차트 우클릭 메뉴 표준: `Reset Zoom` / `Copy Graph` / `Copy Data` — Profile Vision 규약 일치.

### 확정 기능 요구사항 — Summary 표

**메트릭 6종 (계산 정의)**
| 메트릭 | 정의 |
|---|---|
| **AVG (Mean)** | 측정점 VALUE의 산술 평균 |
| **MAX** | 최댓값 |
| **MIN** | 최솟값 |
| **RANGE** | MAX − MIN |
| **3SIG** | 3 × 표준편차 (표본 기준, ddof=1) |
| **NU%** | `(MAX − MIN) / (2 × Mean) × 100` (반도체 half-range 방식) |

**표 레이아웃 (한 웨이퍼 단위, 4행 × 2열)**
| Label | Value (예시) |
|---|---|
| `LOT ID / SLOT` | `RK2A001 / 10` |
| `AVG / NU` | `663.7 / 1.69%` |
| `MIN ~ MAX` | `640 ~ 680` |
| `RANGE / 3SIG` | `40 / 38.3` |

- 다중 웨이퍼: 각 웨이퍼마다 (MAP + 이 표) 한 쌍을 **가로로 나열**
- 소수점 자릿수는 `settings.json`으로 조정 (기본값 구현 시 확정)
- DELTA 시각화도 동일 레이아웃 (LOT/SLOT 칸에 `A_LOT / A_SLOT ← B_LOT / B_SLOT`로 양쪽 병기)

### 확정 기능 요구사항 — 메인 윈도우 레이아웃 (3-패널 세로 스택)

```
┌─ Wafer Map ────────────────────────────── [⚙ Settings] ─┐
│  [ Panel 1: Input ]   A | B  (QSplitter, Ctrl+V 타겟)   │
├─────────────────────────────────────────────────────────┤
│  [ Panel 2: Control ]                                   │
│    VALUE ▼  X ▼  Y ▼  [저장된 좌표 불러오기]            │
│    View: 2D/3D ▼   Z 스케일: 공통/개별                   │
│                                           [Visualize]   │
├─────────────────────────────────────────────────────────┤
│  [ Panel 3: Result ]   MAP + Summary 표 쌍을 가로 나열  │
│    (QScrollArea, 다중 웨이퍼 대비)                      │
└─────────────────────────────────────────────────────────┘
```

- 세로 분할: `QSplitter(Vertical)` — 사용자가 핸들 드래그로 높이 조정
- 우상단 **`⚙ Settings` 버튼 하나만** (`QToolBar`). 메뉴바·Help 없음 — 최대한 직관적
- `Settings` 다이얼로그: `Appearance` 탭 (테마·폰트) + `Coord Library` 탭 (프리셋 목록 + 삭제)
- **2D / 3D는 탭이 아니라 Control 패널의 콤보/토글로 즉시 전환** (결과 영역은 하나, 내용만 바뀜)
- 차트 상호작용: 우클릭 `Reset Zoom` / `Copy Graph` / `Copy Data` (툴바 아님)

### 확정 기능 요구사항 — 입력 창 & DELTA 시각화

**메인 윈도우는 2-pane 입력 구조.** 좌/우(또는 A/B)에 각각 독립 Ctrl+V 타겟을 둔다.

| 입력 상태 | 동작 |
|---|---|
| 한쪽만 입력 | **단일 시각화** — 해당 입력 파싱 → VALUE/X/Y 사용자 선택 → MAP + Summary 출력. 표시 메타는 해당 입력의 **현재** `LOT ID` / `SLOTID` |
| 양쪽 모두 입력 | **DELTA 시각화** — VALUE/X/Y 선택은 공통. 두 입력을 `WAFERID`로 매칭해 VALUE 차이 계산 |

**DELTA 매칭 규칙**
1. **웨이퍼 매칭: `WAFERID`(영구 불변 키) 일치**. `LOT ID` / `SLOTID` 불일치는 허용 (상태값이라 재할당·이동 가능)
2. **웨이퍼 수 불일치 허용**: A에 10장, B에 4장이 들어와도 `WAFERID` 교집합 웨이퍼만 DELTA 계산·출력. 교집합에 없는 웨이퍼는 **조용히 미출력** (경고 팝업 X). 상단에 `"매칭 4 / A 10 vs B 4"` 요약 한 줄로 개수 안내
3. **점 매칭: 같은 WAFERID 내에서 선택된 `(X, Y)` 좌표가 완전 일치**하는 측정점만 사용. 보간 없음. 좌표 부분 일치도 교집합만
4. **DELTA 부호**: **`A − B` 고정** (UI 토글 없음)
5. 완전 불일치(웨이퍼 교집합 0 or 좌표 교집합 0): 경고 팝업 + DELTA 차트 비활성화
6. 좌표 비교 tolerance (부동소수 오차 대비): 구현 시 확정 (예: 1e-6 mm)

**DELTA 출력 표시 규칙**
- `WAFERID`는 영구 매칭 키이므로 **출력 정체성의 중심**
- 현재 `LOT ID` / `SLOTID`는 두 입력이 다를 수 있음 → **양쪽 다 병기** (예: `RK2A001AC / slot 11  ←  RK2A001 / slot 7`, 화살표는 `A − B` 방향)
- MAP: DELTA 값의 웨이퍼 heatmap
- Summary: DELTA 값에 대한 6종 메트릭(AVG/MAX/MIN/RANGE/3SIG/NU%)

### 확정 기능 요구사항 — 다중 웨이퍼 레이아웃 & 출력 합성 이미지

**다중 웨이퍼 배치**: (MAP + Summary 표) 한 쌍을 한 열로 묶어 **가로로 나열**.

```
┌──────────┬──────────┬──────────┐
│  MAP 1   │  MAP 2   │  MAP 3   │
├──────────┼──────────┼──────────┤
│ Table 1  │ Table 2  │ Table 3  │
└──────────┴──────────┴──────────┘
```

**3D Z 스케일 모드 (다중 웨이퍼)**
- **기본**: 값 범위 기반 자동 + 사용자 수동 오버라이드
- **공통 스케일 모드** (`z_common`): 모든 웨이퍼가 동일 Z 범위 → 직관적 비교용 (기본 권장)
- **개별 스케일 모드** (`z_individual`): 각 웨이퍼 자체 최적 → 서로 비교하지 않는 독립 데이터용
- UI 토글로 즉시 전환

**Copy Graph — MAP + 표 합성 이미지 (기술적으로 가능, PySide6 표준 패턴)**
- 결과 패널은 `QWidget` 컨테이너 안에 (MAP 위젯 + Summary 테이블 위젯)을 `QVBoxLayout`으로 수직 배치
- 다중 웨이퍼: (MAP+Table 열)을 가로로 나열한 전체 컨테이너 하나
- **Copy Graph 액션**: `container.grab()` → `QPixmap` → `clipboard.setPixmap(pixmap)` → PPT에 **하나의 사진으로** Paste
- **3D 시 주의**: `GLViewWidget.grab()`은 OpenGL 프레임버퍼라 일반 widget과 다름 → `QPainter` + `drawImage(glview.grabFramebuffer())` + table widget `render()` 결합 필요. 구현 시 검증 항목
- **Copy Table** (표만 PPT 표로 = HTML+TSV 듀얼 MIME)과 **Copy Graph** (합성 이미지)는 **별개 액션**으로 유지

### 확정 기능 요구사항 — 좌표 프리셋 라이브러리

입력 데이터의 PARAMETER 리스트에 **X/Y 좌표 행이 없이 측정값(`T1`, `THK`, `THK_PRE-POST` 등)만** 있는 경우가 있다. 이를 위해 이전 분석에서 사용한 X/Y 좌표를 저장·재사용하는 기능.

**저장 위치**: `coord_library.json` — **앱 실행 폴더(exe 옆)**. 무설치 포터블 배포 방식이라 앱 전체가 폴더 단위로 이동 가능. settings.json도 동일 폴더.

**저장 스키마**
```json
{
  "presets": [
    {
      "name": "49P Polar 5mm",
      "recipe": "HT_SOC_POLAR_49PT_5mm",
      "n_points": 49,
      "x_mm": [0, 10, -10, ...],
      "y_mm": [0, 0, 0, ...],
      "created_at": "2026-04-18T14:00:00",
      "last_used": "2026-04-18T14:00:00"
    }
  ]
}
```

**저장 시점** — **자동** (사용자 조작 없음)
- Visualize 클릭 시, 입력된 **각 웨이퍼별로** `(recipe, x_mm, y_mm)` 조합을 라이브러리와 비교
- 셋 다 tolerance(≈1e-3 mm) 내 일치하는 기존 레코드가 있으면 → `last_used`만 갱신
- 없으면 새 레코드 추가. 이름 자동 생성: `{recipe}_{n_points}P` (중복 허용)
- **recipe 같아도 좌표 다르면 별도 레코드** (레시피 수정 / 장비별 미세 좌표 차이 케이스)
- **좌표 같아도 recipe 다르면 별도 레코드** (같은 좌표를 다른 레시피로 재사용)
- 다중 웨이퍼 입력(헤더 반복 페이스트 포함) → 웨이퍼별 고유 `(recipe, 좌표)` 조합마다 저장
- DELTA 모드: A/B 각 웨이퍼 모두 독립 저장 (장비 간 좌표 차이 허용)
- 용량: 1개 ≈ 1~2KB, 1,000개 ≈ 1~2MB — 성능 문제 없음
- 누적 정리는 **Settings → Coord Library 탭에서 수동 삭제**

**RECIPE 기반 자동 좌표 적용 (좌표 PARAMETER 없는 입력)**
- 입력에 X/Y PARAMETER 행이 없어 `auto_select` 폴백으로 X/Y 콤보가 VALUE와 같은 이름이 되는 경우 → 좌표 선택 무효
- 이때 라이브러리에서 **해당 웨이퍼의 RECIPE 와 일치하는 프리셋** 을 조회, `last_used` 최신 레코드의 좌표를 자동 주입
- 사용자 조작 없음. 불러오기 다이얼로그 생략. 같은 RECIPE의 좌표가 여러 개면 최신 사용 기준
- 라이브러리에 매칭 레코드 없으면 해당 웨이퍼 시각화 스킵 (또는 사용자가 수동 "저장된 좌표 불러오기")
- 자동 적용된 셀은 타이틀에 📁 아이콘 표시

**불러오기 UI (Step 2 좌표 경로 B)**
- Step 2에 항상 `"저장된 좌표 불러오기"` 버튼 제공
- 클릭 시 프리셋 목록 다이얼로그:
  - **필터**: 현재 VALUE PARAMETER의 **실제 DATA 개수 N**과 `n_points`가 일치하는 프리셋만
  - **중복 좌표 병합 표시**: `x_mm`·`y_mm` 배열이 tolerance(예: 1e-3mm) 내 동일한 프리셋들은 **대표 1개 + "외 N"** 으로 묶어 표시 (예: `HT_SOC_POLAR_49PT_5mm 외 3`). 대표는 `last_used` 최신 레코드
  - **정렬**: RECIPE 일치 우선 (있으면 상단), 그 다음 `last_used` 최근순
- 프리셋 선택 시 해당 X/Y 배열을 좌표로 주입 → 좌표 PARAMETER 선택 UI는 스킵
- 선택 후 해당 레코드의 `last_used` 갱신

**편집/삭제 UI**
- `Settings` 다이얼로그의 `Coord Library` 탭에서 진입 (별도 메인 메뉴 없음)
- 모든 프리셋을 **병합 없이 전체 목록**으로 표시 (이름·RECIPE·n_points·최근 사용일)
- 개별 선택 후 **삭제** 가능. 이름·좌표 수정은 미지원 (새로 저장하는 방식)

**DELTA 모드에서의 적용**
- 양쪽 입력의 좌표는 **무조건 동일**해야 하므로, 프리셋 불러오기 시 **양쪽 pane에 공통 적용**
- pane별 개별 프리셋 선택 미지원

**좌표 PARAMETER 자동 감지 안 함** — 사용자가 "불러오기" 버튼으로 명시적 진입

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
3. Visualize 시 **좌표가 자동 프리셋 저장됨** (중복 없으면 추가, 있으면 `last_used` 갱신)
4. VALUE/X/Y 선택은 **기억하지 않음** (매 페이스트마다 다시 선택). 프리셋은 영구 저장소

**Step 3 — 시각화**
- 각 웨이퍼마다 선택된 (VALUE, X, Y) 삼중으로 `(X[i], Y[i], VALUE[i])` 점 집합 구성
- **좌표 단위 자동 mm 환산** (대부분은 mm이지만 `_1000`류 대비):
  - `|max| ≤ 200` → 이미 mm, 그대로 사용
  - `200 < |max| ≤ 200000` → μm 또는 ×1000 표기로 판정 → `/1000` 환산하여 mm
  - 그 외 → 사용자 수동 오버라이드 요청
- (VALUE/X/Y) 실제 DATA 개수가 서로 다르면 경고 팝업 + 시각화 차단
- 출력: 2D heatmap / 3D surface, 우클릭 메뉴 `Reset Zoom` / `Copy Graph` / `Copy Data`, Summary 6종, Copy Table

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
| `chart_common` | 2D/3D 공통 (colormap, interp_method, grid_resolution, show_circle, show_notch, notch_depth_mm) |
| `chart_2d` | 2D MAP 전용 (show_points, point_size, show_value_labels) |
| `chart_3d` | 3D MAP 전용 (shading, smooth, z_exaggeration, show_grid) |
| `z_scale_mode` | 다중 웨이퍼 3D Z 스케일 모드 (`common` / `individual`) |
| `table` | Summary 표 소수점 자릿수, NU% 표시 방식 등 |
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
│   ├── interp.py                ← rbf / cubic / cubic_nearest / phantom_ring 보간
│   ├── metrics.py               ← summary_metrics (AVG/MAX/MIN/RANGE/3SIG/NU%)
│   ├── delta.py                 ← compute_delta (WAFERID 매칭 → 좌표 매칭 → A−B)
│   └── coord_library.py         ← CoordLibrary + CoordPreset (해시 버켓 O(N) 중복 검출, recipe_similarity)
├── widgets/
│   ├── main_window.py           ← 3-패널 QSplitter, 컨트롤 패널 fixed-height, view_mode 분기, closeEvent 윈도우 저장
│   ├── paste_area.py            ← Ctrl+V 타겟 (Text/Table 토글 + Clear)
│   ├── wafer_cell.py            ← WaferDisplay/WaferCell — 2D pyqtgraph + 3D GLSurfacePlotItem 동적 swap
│   ├── result_panel.py          ← (MAP+Summary) 쌍을 가로 나열, 합성 Copy Graph용 컨테이너
│   ├── settings_dialog.py       ← non-modal Save/Close/Default, Design 탭(2열, UI/Common/2D/3D 카드 4개)
│   ├── preset_dialog.py         ← 좌표 프리셋 선택 (n_points 필터 + recipe_similarity 정렬 + group_by_coords 병합)
│   └── preset_add_dialog.py     ← 수동 프리셋 추가
├── samples/
│   ├── sample_data.csv          ← 실제 포맷 테스트 CSV (2 웨이퍼)
│   ├── sample_data.py           ← 샘플 점 생성기
│   ├── sample_*.py              ← 라이브러리 비교 샘플 7종 (matplotlib/plotly/pyqtgraph/pyvista/vispy/wfmap/cap1tan)
│   └── cases/                   ← 9 케이스 CSV (case01_basic..case07_x_multi, case_no_coords)
├── tests/
│   ├── test_auto_select.py      ← auto_select 통합 테스트 10케이스
│   └── compare_interp.py        ← 4 보간 방법 한 화면 비교 (debug/output_compare_interp.png)
├── debug/                       ← 모든 샘플·테스트 산출물 (PNG/HTML) 통합 폴더 (.gitignore)
├── assets/                      ← 아이콘 등 정적 자원
├── requirements.txt
├── settings.json                ← 런타임 설정 (.gitignore)
└── coord_library.json           ← 좌표 프리셋 영구 저장소 (.gitignore)
```

**3D 렌더링 메모**
- 셰이더는 `shaded` / `normalColor` / `heightColor` 3종만 지원 (pyqtgraph가 `flat` 미지원)
- 경계 원 `GLLinePlotItem`은 `glOptions='opaque'`로 둬야 뒤쪽이 가려짐 (기본 `translucent`는 depth-write off라 항상 보임)
- 3D Copy Graph: `GLViewWidget.grabFramebuffer()` + table `render()`를 `QPainter`로 합성

**좌표 프리셋 라이브러리 성능**
- `group_by_coords`는 첫/중간/마지막 점을 양자화한 해시 버킷으로 O(N) 처리 (2,000개 기준 9ms — naive O(N²)는 44초)

**Y → X 자동 동기화는 의도적으로 비대칭**
- X 변경 시 Y는 suffix 일치로 재선택 / Y 변경 시 X는 그대로 유지
- `X=X_1000`, `Y=Y_B` 처럼 사용자가 다른 suffix 조합을 의도적으로 고를 수 있게 함

**렌더링 캐시 — view_mode / z_scale / Settings 토글 시 재계산 방지 (b0.0.0~)**
- `WaferCell`이 `_chart_box`를 `QStackedLayout`으로 보유. 셀 생성 시 `_plot_2d`(idx 0) + `_gl_3d`(idx 1) 둘 다 미리 인스턴스화. 토글은 `setCurrentIndex` 한 줄, 0ms.
- 모드별 캐시 플래그 `_rendered_2d` / `_rendered_3d`. 첫 진입에만 그리고 캐시. `set_view_mode(mode)` API.
- `invalidate_3d()` — z_range 변경 등 3D만 영향받을 때 사용. 2D 캐시는 유지. 현재 view가 3D면 즉시 재렌더, 2D면 다음 진입 시.
- **2단 캐시**: `_interp_cache`(method, G) + `_mask_cache`(G, show_notch, depth) 분리. notch_depth만 바꿔도 RBF 재계산 없이 mask만 새로 (RBF 90ms → 4ms).
- `refresh()` 는 렌더 캐시 reset + 현재 view 재렌더 (보간 캐시는 유지). Settings graph_changed가 `revisualize`(cell 재생성) 대신 `ResultPanel.refresh_all()` → 각 cell.refresh() 호출.
- **ResultPanel.refresh_all()의 병렬 RBF**: `prefetch_interp()`를 `ThreadPoolExecutor`로 cell당 병렬 호출. scipy RBF가 GIL 해제하는 C 코드라 6-cell 병렬이 ~5× 향상 (grid=250 기준 791ms → 160ms). 보간 완료 후 렌더는 메인 스레드에서 순차. scipy `neighbors` 옵션은 N=70 작은 케이스에서 오히려 악효과라 미사용.
- `_apply_z_scale_mode`는 메인 윈도우의 `cb_zscale`을 ground truth로 (settings 무시), view_mode 분기 제거. 토글 시 cell 재생성 없이 displays z_range만 갈아끼우고 `invalidate_3d()`.

**3D 첫 렌더링 깜빡임 제거 (b0.0.0~)**
- `app.py`에서 `Qt.AA_ShareOpenGLContexts` set + 시작 시 dummy `GLViewWidget` show→hide→deleteLater (`_gl_warmup`).
- `result_panel`에 hidden `GLViewWidget` 1개 영구 자식. startup show 시점에 ancestor가 native window로 일괄 승격되어, 이후 cell의 GL widget 추가 시 깜빡임 없음.

**페이스트 응답성 (b0.0.0~)**
- `_fill_table` 동안 `ResizeToContents` 일시 해제(`Interactive` 모드) — 매 setItem마다 컬럼 측정 트리거 방지 (991ms → 6ms)
- Table 뷰가 비활성이면 dirty 플래그만 set, Table 토글 시점에 채움 (lazy fill) — paste 직후 0ms

**버튼 폭 정합 규약**
- `paste_area.HEADER_BUTTON_WIDTH = 88` 모듈 상수.
- Text/Table/Clear, Settings 다이얼로그의 Save/Close/Default 모두 같은 폭.
- 메인 Run Analysis는 `HEADER_BUTTON_WIDTH * 3 + HEADER_BUTTON_SPACING * 2 = 276` 폭 + control panel과 paste_area의 좌우 margin이 동일(8) → 시작/끝 X가 Input B의 Text/Clear와 자동 일치.

**메인 액션 강조 색**
- `class="primary"` (글로벌 QSS) — `t.get('primary_btn', t['success'])` fallback. 두 테마(Mint Cream / Everforest Light)는 `success`가 `accent`와 같아 강조가 안 보였기에 `primary_btn` 키 명시 추가.

**컬러맵 확장**
- `HEATMAP_COLORMAPS` (core/themes.py)에 pyqtgraph 기본 16종 + 커스텀 2-stop gradient 7종(`Red/Blue/Black/Navy/Pink/Brown/Charcoal-White`) = 23종.
- 실제 `pg.ColorMap` 인스턴스는 `wafer_cell._CUSTOM_CMAPS`. `resolve_colormap(name)` 헬퍼가 커스텀→pg→viridis fallback 순서로 resolve.
- 기본값은 `turbo` / 격자 해상도 `100`.

**웨이퍼 notch 표시**
- `chart_common.show_notch` (default on) + `notch_depth_mm` (3~6mm, default 5mm). 방향은 6시(3π/2) 고정, V자 폭 ±3°.
- `_boundary_xy(show_notch, depth)`: 2D plot과 3D GLLinePlotItem 공유 경계 좌표.
- `_points_inside_wafer(XG, YG, show_notch, depth)`: 격자점 inside mask. V자 내부 + cell 반지름(0.5 픽셀) margin까지 투명 처리 → 해상도 무관 V자 영역 크기 동일.
- 3D 기본 카메라 `azimuth=-135` — notch가 오른쪽 하단(4~5시)에 위치하는 앵글.
