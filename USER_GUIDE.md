# Wafer Map 사용자 가이드

반도체 웨이퍼 측정 데이터(X, Y, VALUE)를 2D / 3D 지도로 시각화하는 데스크톱 앱.

> 이 문서는 **사내 사용자 매뉴얼**. 외부 인상 / 실행 명령은 [`README.md`](README.md), 개발자 정책은 [`CLAUDE.md`](CLAUDE.md) 참고.

---

## 빠른 시작

1. `Wafer_Map_<버전>.zip` 압축 풀기 → 폴더 안의 `Wafer Map.exe` 실행 (무설치).
2. **MES-DCOL Data** (사내 MES 시스템의 계측 결과 long-form CSV) 전체 선택 → **Ctrl+C**.
3. 앱의 **Input A** 영역에 **Ctrl+V**.
4. VALUE / X / Y 콤보 자동 선택됨. 필요 시 수동 변경.
5. **▶ Run** → 결과 패널에 MAP + Summary 표가 가로 나열.
6. 각 cell 우클릭 → **Copy Image** → PPT / Excel 에 **Ctrl+V** 사진 paste.

> 입력이 클립보드면 **출력도 클립보드**. 파일 I/O 최소화가 핵심 철학.

---

## 메인 윈도우 레이아웃

```
┌─ Wafer Map ────────────────────────── [⚙ Settings] ─┐
│  [ Input ]   A | B  (QSplitter, Ctrl+V 타겟)         │
├──────────────────────────────────────────────────────┤
│  [ Control ]                                         │
│    VALUE ▼  X ▼  Y ▼  [저장된 좌표 불러오기]          │
│    View: 2D/3D ▼  Z 스케일: 공통/개별  Z-Margin %    │
│                                          [▶ Run]    │
├──────────────────────────────────────────────────────┤
│  [ ReasonBar ]  사유/검증 메시지 한 줄                │
├──────────────────────────────────────────────────────┤
│  [ Result ]   MAP + Summary 표 쌍을 가로 나열         │
└──────────────────────────────────────────────────────┘
```

- 세로 분할 핸들 드래그로 패널 높이 조정 가능
- **2D / 3D 는 탭이 아니라 Control 패널 토글** — 결과 영역은 하나, 내용만 바뀜

---

## 단축키

| 키 | 동작 |
|---|---|
| **Ctrl+V** | 클립보드 → 활성 Input (A 또는 B) |
| **Ctrl+Shift+T** | Stress test 모드 (개발자 검증용 — N회 자동 Run) |
| **Esc** | Stress test 정지 |
| **휠** | 차트 zoom (2D / 3D 모두) |
| **Shift + 좌클릭/드래그** | 모든 cell 의 3D 카메라 앵글 동기 |
| **Shift + Ctrl + 드래그** | 모든 cell 의 3D 카메라 위치 동기 |
| **Ctrl + 드래그** | 선택한 cell 만 3D 이동 |
| **우클릭** (cell 어디서든) | Reset / Copy Image / Copy Data / Copy Table |

---

## 주요 워크플로

### 단일 시각화
- Input A 만 입력 → 각 wafer 가 한 cell 로 가로 나열.

### Pre-Post Delta 시각화
- **Input A 에 Pre Data**, **Input B 에 Post Data** paste.
- WAFERID 동일한 wafer 끼리 매칭, **Δ = A − B** 부호 고정 (UI 토글 없음).
- **좌표 합집합 매칭** (tolerance 1mm):
  - 양쪽 매칭된 점: 정상 delta
  - A only: dv = va (B = 0 가정)
  - B only: dv = −vb (A = 0 가정)
- **Δ-Interp mode** 체크박스 (Control 패널, 양쪽 입력 시 활성):
  - 켜면 한쪽만 있는 점에 RBF 보간으로 상대값 채워 정상 delta
  - 끄면 NaN 룰 (위 조항)
- **다중 wafer 지원** — A 10장 / B 4장이어도 WAFERID 교집합만 자동 처리. ReasonBar 에 `매칭 N / A vs B` 안내.

### 다중 Wafer
- 같은 paste 안에 여러 wafer 가 있으면 자동 분리 (WAFERID 그룹핑).
- **출력 순서 = 입력 역순** (시간순). MES 의 wafer 데이터가 위쪽 = 최신, 아래쪽 = 시간순 첫번째 가정. 그래프는 시간순 (오래된 → 최신) 가로 나열.
- DELTA 매칭 시 WAFERID 중복 케이스 (`__rep` 분리) 는 paste 위쪽 (최신) wafer 가 매칭 대상 — 표시 순서만 역순, 매칭 자체는 변동 없음.

---

## WAFERID 처리 (중요)

웨이퍼는 라이프사이클 중에 **재할당 가능**:
- `LOT ID` / `SLOTID` — **현재 상태값** (변경됨)
- `WAFERID` — **영구 불변 ID**, 최초 생성 시 `LOT.SLOT` 이 그대로 박힘

### 예시
```
최초:    LOT=RK2A001     WAFERID=RK2A001.07   SLOTID=7
이동 후: LOT=RK2A001AC   WAFERID=RK2A001.07   SLOTID=11
```

→ DELTA 매칭은 **WAFERID 만**. `LOT ID` / `SLOTID` 가 다르더라도 같은 wafer 면 매칭됨. 출력 cell 타이틀은 양쪽 현재 값 병기 (예: `RK2A001AC.11 ← RK2A001.07`).

---

## 입력 검증 + ReasonBar

paste 직후·Run 직후 **Input 라벨** 과 **ReasonBar** (Control 와 결과 사이 한 줄) 에 검증 결과 표시. 색으로 의미 구분.

### Severity 4 단계

| 색 | 의미 | Run 동작 |
|---|---|---|
| 🟢 민트 | 정상 / fallback 성공 | 활성 |
| ⚪ 회색 | 정보 알림 | 활성 |
| 🟠 주황 | 주의 (결과 신뢰성 확인) | 활성 |
| 🔴 빨강 | 차단 사유 | 비활성 (사유 해결 필요) |

### Input 라벨 (paste 직후)
- 정상: `웨이퍼 N장, Parameter N개, 좌표 N개` (민트)
- 헤더 행 2개+ 발견: `헤더 행 N개 발견 — 첫 헤더만 사용` (회색 info)
- 반복 측정 분리: `반복 측정 N건 발견 — __rep1, __rep2 ...` (회색 info)
- 일부 wafer PARA set 다름: 빨강 error, **Run 차단**
- 필수 컬럼 누락: `⚠ 필수 컬럼 부족: ...` 빨강 error, **Run 차단**
- **가족 RECIPE 모두 비어있음**: `가족 RECIPE 모두 비어있음 — 입력 데이터 확인` 빨강 error, **Run 차단**
- **가족 RECIPE 다름** (PRE/POST 호환 X): `RECIPE 다름 — lot.slot: X vs 가족: Y` 빨강 error, **Run 차단**. 일부 wafer 만 RECIPE 비어있어도 동일 (정상 vs 빈값 = 다름)

### ReasonBar — DELTA 좌표 fallback (paste 직후)
- `B 좌표 없음. A 와 동일 RECIPE 로 A 좌표 사용.` (민트 ok)
- `B 좌표 없음. B RECIPE 라이브러리 좌표 사용.` (민트 ok)
- `양쪽 좌표 없음. 라이브러리 좌표 사용.` (민트 ok)
- `WAFERID 교집합 없음 (A N장, B N장)` (빨강 error)
- `RECIPE 다름 (A=..., B=...)` (주황 warn — 시각화 가능, 의미 해석 주의)
- `A·B 공통 VALUE PARA 없음` (주황 warn — 한쪽만 가진 PARA 도 선택 가능)
- `A 또는 B 에 WAFERID 중복 N건` (주황 warn — 첫 측정 set 끼리 계산)

### ReasonBar — Run 후
- `wafer N개 좌표 라이브러리 자동 적용: lot.slot, ...` (민트 — 자체 X/Y 없는 wafer 자동 fallback)
- `좌표 해결 실패 wafer N개 표시 안 됨: lot.slot, ...` (주황 — 일부 wafer 만 빠짐)
- `포인트 개수 불일치 — VALUE T1: 50pt vs 좌표 X/Y: 55pt` (주황)

### 차단 사유 해결 가이드

| 사유 | 해결 |
|---|---|
| WAFERID 교집합 없음 | A·B 입력의 WAFERID 컬럼 확인. 같은 wafer 매칭 가능 여부. |
| 좌표 결정 실패 | Settings → 좌표 라이브러리에 해당 RECIPE 좌표 미리 저장. 또는 입력에 X/Y PARAMETER 행 추가. |
| 일부 웨이퍼 PARA 다름 | 페이스트한 데이터 일부 행 누락 확인. 누락 PARA 행 보충. |
| 필수 컬럼 부족 | 헤더에 `WAFERID`/`LOT ID`/`SLOTID`/`PARAMETER`/`RECIPE`/`DATA1`+ 있는지 확인. |

---

## Summary 표 — 6 메트릭

| 메트릭 | 정의 |
|---|---|
| **AVG** | 측정값의 산술 평균 |
| **MAX** | 최댓값 |
| **MIN** | 최솟값 |
| **RANGE** | MAX − MIN |
| **3SIG** | 3 × 표준편차 (표본 기준, ddof=1) |
| **NU%** | `(MAX − MIN) / (2 × Mean) × 100` (반도체 half-range) |

소수점 자릿수는 Settings → 디자인 설정 → MAP 공통 → **소수점 자릿수** (0~3).

### Table Style 11종
Settings → 디자인 설정 → **Table Style** 콤보로 즉시 swap.
- 표 형식: `ppt_basic` (기본) / `dark_neon` / `vertical_stack`
- 자유 layout: `big_number` / `highlight_lead` / `stat_tiles` / `minimal_underline` / `pill_badge` / `color_footer` / `layered_depth`
- Overlay 전용: `no_table` (표 없이 chart 좌상단에 Mean / Range / NU%)

---

## 좌표 프리셋 라이브러리

VALUE 파싱은 되지만 X/Y 좌표가 입력에 없는 경우 대비.

### 자동 저장
- ▶ Run 시 사용한 `(RECIPE, X, Y)` 조합이 `coord_library.json` 에 자동 등록.
- 다음에 같은 RECIPE 의 좌표 없는 입력이 들어오면 **자동 적용** (cell 타이틀에 📁 아이콘).

### 수동 추가
- Settings → 좌표 라이브러리 탭 → **수동 추가**
- RECIPE 이름 입력 + 좌표 paste
- 좌표 포맷 4종 자동 감지:
  - `x 0 74 148 / y 148 74 0` (행 + X/Y 라벨)
  - `0 74 148 / 148 74 0` (행, 위=X)
  - `x y / 0 148 / ...` (열 + x/y 헤더)
  - `0 148 / 74 74 / ...` (열, 좌=X)
- 구분자 무관 (공백/탭/콤마/세미콜론). BOM·비데이터 라인 자동 필터.

### 불러오기
- Control 패널의 **저장된 좌표 불러오기** 버튼 → 현재 VALUE 개수에 맞는 프리셋 목록.

### RECIPE 호환 (PRE / POST)
`_PRE` / `_POST` 토큰을 끝 또는 중간 어디서든 자동 제외 후 베이스 비교:
- `Z_TEST_01__PRE` ↔ `Z_TEST_01__POST` ↔ `Z_TEST_01` (호환)
- `CMP_PRE_THK` ↔ `CMP_POST_THK` ↔ `CMP_THK` (호환)
- `Z_TEST_01-POST` (하이픈) / `Z_TEST_01POST` (구분자 없음) — 비호환

---

## PARA 조합 (sum / concat recursive)

서로 다른 PARA + 좌표 페어를 합쳐 하나의 시각화로. **mode 자동 판정**.

### 사용 흐름
1. Control 패널의 **Para 조합** 버튼 → 다이얼로그
2. PARA 1·2 + 좌표 1·2 선택 (좌표는 PARA 선택 시 자동 매칭)
3. 미리보기에서 최종 형태 확인 → **Apply**
4. 메인 콤보에 `🔗` prefix 합성 항목 추가됨 → **Run** 으로 시각화

### 표기 규칙
| 케이스 | 좌표 | 표기 | 의미 |
|---|---|---|---|
| sum | 같음 | `T1 + T2` | element-wise 덧셈 (예: PRE + POST 두께) |
| concat | 다름 | `T1 ∪ T1_A` | 점 집합 합집합 (예: inner + outer) |

### Recursive (재조합)
- Apply 후 다이얼로그 다시 열면 합성 결과도 PARA 콤보에 노출 → 또 다른 합성의 피연산자
- **같은 mode 끼리는 자동 평탄화**:
  - `(T1+T2) + T3` → `T1 + T2 + T3`
  - `(T1 ∪ T1_A) ∪ T1_B` → `T1 ∪ T1_A ∪ T1_B`
- **다른 mode 섞이면 자동 괄호** (우선순위 명시):
  - `(T1 + T2) ∪ T_A`
  - `(((T1 ∪ T2) + T3 + T4) ∪ (T5 + T6)) ∪ T7` 임의 깊이

### 주의
- 같은 PARA 두 번 선택 (예: `T1 + T1`) — 다이얼로그에서 차단
- 좌표 매칭 안 되는 wafer 는 Apply 시 "조합 대상 데이터 없음" 사유 표시
- 입력 (paste) 변경 시 합성 항목 자동 해제

---

## ER Map / Deposition Rate (Time 입력)

각 cell 상단 **Time** 입력란에 시간(sec) 입력 → `dTHK / Time` 자동 변환. ER (Etch Rate) / Deposition Rate 등 단위 시간 당 변화율 계산용.
- **Single + DELTA 모두** 사용 가능 (single 은 deposition rate 등)
- 단일 cell 입력 또는 **전체 적용** 체크 (master cell, 첫 cell) 로 모든 cell 일괄 적용
- 빈칸으로 두면 변환 없음 (원본 값)
- Time 입력란은 **cell 상단 (캡처 영역 밖)** — Copy Image 에 포함 안 됨

---

## r-symmetry mode (radial 강제)

CMP 같은 회전 대칭 공정 데이터 — 자동 감지 안 되거나 강제하고 싶을 때.
- cell 우상단 r-symmetry 체크박스 → 1D radial 보간으로 강제
- 자동 감지 룰: `is_radial_scan(x, y)` — SVD 기반 직선 fit (300mm × 폭 N mm 직사각형 안에 모든 점 들어가면 True). Settings 의 `1D Scan 폭` (10~150mm, 기본 45mm) 으로 조정.

---

## Copy 기능 (PPT / Excel 호환)

Cell **우클릭 메뉴** (cell 어디서 우클릭하든 동일):

| 메뉴 | 동작 | Paste 동작 |
|---|---|---|
| **Reset** | 3D 회전·zoom 초기 상태 복원 | — |
| **Copy Image** | Cell 전체 (차트+컬러바+1D+표) 합성 이미지 | PPT/Excel 둘 다 사진 |
| **Copy Data** | 측정점 raw 값 (X/Y/VALUE) | Excel 셀 (TSV) |
| **Copy Table** | Summary 표 | PPT 표 / Excel 셀 (HTML+TSV dual) |

### Copy Image 핵심 (0.2.0+)
- **Offscreen FBO 렌더 (MSAA 4x)** — 그래프가 다른 창에 가려지거나 스크롤에 숨어 있어도 완전한 이미지 복사
- **Excel 호환** (2026-05-01 fix) — alpha 제거 + PNG/DIB 듀얼 MIME 으로 Excel 좌우 비대칭 회귀 차단

---

## Settings (⚙ 우상단 버튼)

### 디자인 설정 탭

#### UI 카드 (Default 영향 없음 — 사용자 마지막 값 보존)
- **테마** — 14종 (Light 기본 / Dark / Solarized / Nord / Mint Cream / Everforest 등)
- **글꼴** — Segoe UI 기본
- **글자 크기** (font_scale) — 작게/보통/크게/매우 크게
- **UI 해상도** — auto / FHD / QHD / UHD (변경 시 **재시작 필요**, `QT_SCALE_FACTOR` 환경변수 적용)
- **윈도우 크기 저장** — 종료 시 현재 크기 보존

#### MAP 공통
- **컬러맵** — 28종 (Turbo 기본 + 커스텀 White 2-stop 7종)
- **보간 방법** — RBF 4종 (ThinPlate / Multiquadric / Gaussian / Quintic)
- **격자 해상도** (grid) — 50~300 (기본 150)
- **그래프 크기** (Map Size) — 5종 (소~대), camera distance 400~800
- **소수점 자릿수** — 0~3
- **경계 원 / Notch / 스케일바** — 표시 토글 (개발자 고정값 fallback)

#### 2D MAP
- 측정점 마커 표시·크기, 측정점 값 라벨

#### 3D MAP
- **부드러운 표면** (smooth shading)
- **Z-Height** (0.5~3.0) — 과장 배율
- **Elevation / Azimuth** — 카메라 앵글 (-90~90° / -180~180°, 기본 40 / -90)

#### 1D Radial Graph
- **표시** 체크 → cell 의 차트와 표 사이에 1D radial 그래프 삽입
- **Fitting 방법 7종** — Univariate Spline / Cubic / PCHIP / Akima / Savitzky-Golay / LOWESS / Polynomial
  - 데이터 종류마다 적합한 방법이 달라서 **수동 스위치 사용 전제** — 풍부함 자체가 의도된 설계
- **Smoothing factor** (Univariate / spline 계열, 1~15)
- **Bin Average** — 같은 r 값 평균 전처리

### 좌표 라이브러리 탭
- 저장 프리셋 목록. 헤더 클릭으로 정렬. 편집/삭제.
- **자동 정리** — 최대 저장 개수·최대 보관일 초과 시 `last_used` 오래된 순 삭제 (0 = 무제한, 기본 1000개).

### Save / Close / Default
- **Save** — `settings.json` 저장 (창 안 닫힘, 연속 조정 가능)
- **Close** — 저장 없이 닫기
- **Default** (디자인 설정 탭 좌측 하단) — 그래프 4개 카드 (Chart Common / 2D / 3D / 1D Radial) 만 기본값으로. **UI 카드는 영향 없음**.

---

## 다중 Wafer Z 스케일

Control 패널의 **Z 스케일** 토글:
- **공통** (기본) — 모든 wafer 동일 Z 범위. 직관적 비교용
- **개별** — 각 wafer 자체 최적. 서로 비교하지 않는 독립 데이터용
- **Z-Margin %** (공통 모드 전용) — palette 더 좁게 써서 시각 대비 부드러워짐 (0=원본, 50% → 1.5배 확장)

---

## Run 진행 표시

▶ Run 클릭 시:
1. Run 버튼 → **Progress bar** 로 swap (`처리 중... %p%`)
2. 단계별 5 → 20 → 40 → 60 → 85 → 95 → 100% progress
3. 100% 도달 후 자동 Run 버튼 복원

> Progress bar 영역 클릭은 무시됨 (다음 Run 우발 trigger 방지). Run 진행 중 Run 클릭 연타도 첫 클릭만 처리.

---

## 입력 데이터 포맷

**MES-DCOL Data** 의 **long-form CSV**. 한 행 = "한 wafer 의 한 PARAMETER". (계측 장비 측정값이 사내 MES 시스템에 업로드된 형식)

### 필수 컬럼
헤더 대소문자/공백/언더바 무관 (예: `LOT ID` = `lot_id` = `lotid`).

| 컬럼 | 설명 |
|---|---|
| `WAFERID` | 영구 불변 ID (LOT/SLOT 변동 무관) |
| `LOT ID` | 현재 LOT (mutable) |
| `SLOTID` | 현재 slot 번호 (mutable) |
| `PARAMETER` | 측정 항목 이름 (자유, 예: `T1`, `GOF`, `X`, `Y`) |
| `RECIPE` | 계측 레시피 |
| `DATA1`, `DATA2`, ... | 측정값 (1개 이상). `DATA 1`, `DATA_1` 도 인식 |

### 선택 컬럼 (있어도 무시 / 검증 보조)
- `MAX_DATA_ID` (실제 DATA 개수와 다르면 에러 팝업 후 실제 수 신뢰)
- `STEPDESC` / `DATE` / `MACHINE` 등 (시각화엔 불사용)

### PARAMETER 이름 (예시)
- 측정값: `T1`, `T2`, `T3_A`, `GOF`, `T1_AVG` 등 자유
- 좌표: `X`, `Y`, `X_1000`, `Y_A` 등

### 좌표 단위 자동 환산
- `|max| ≤ 200` → 이미 mm, 그대로 사용
- `200 < |max| ≤ 200000` → μm 또는 ×1000 표기 → `/1000` 환산
- 그 외 → 사용자 수동 오버라이드

### 더러운 데이터 허용 (F99 J fix)
DATA 셀이 천단위 콤마 (`1,300.5`), 공백 (`1 320.4`), 따옴표 (`"1,360.2"`) 섞여 있어도 자동 cleansing 후 파싱.

---

## 파일 위치 (무설치 포터블)

실행 폴더 내부:
- `settings.json` — 사용자 설정
- `coord_library.json` — 좌표 프리셋

---

## 버전 / 피드백

현재 버전은 창 우상단에 표시 (`v0.5.0 | © 2026 SK hynix | Jihwan Park`).
이슈·요청은 GitHub Issues 또는 사내 채널.
