# Wafer Map 사용자 가이드

반도체 웨이퍼 측정 데이터(X, Y, VALUE)를 2D / 3D 지도로 시각화하는 데스크톱 앱.

## 빠른 시작

1. `Wafer_Map_0.3.0.zip` 압축 풀기 → 폴더 안의 `Wafer Map.exe` 실행 (무설치).
2. 계측 장비·Excel에서 **long-form CSV** (헤더 포함)를 전체 선택 → Ctrl+C.
3. 앱의 **Input A** 영역에 Ctrl+V.
4. VALUE / X / Y 콤보가 자동 선택됨. 필요 시 수동 변경.
5. **Visualize** 버튼 → 아래 결과 패널에 MAP + Summary 표가 나열됨.

## 주요 워크플로

### 단일 시각화
- Input A 만 입력 → 각 웨이퍼가 한 개 셀로 가로 나열.

### Pre-Post Delta 시각화
- **Input A에 Pre Data**, **Input B에 Post Data** 페이스트.
- WAFERID가 동일한 데이터만 매칭되어 Δ = A − B 로 계산.
- **좌표 합집합 매칭** (tolerance 1mm): 양쪽 매칭 점은 정상 delta, 한쪽만 있는 점도 시각화 (NaN 룰 — A only → dv=va, B only → dv=−vb).
- **Δ-Interp mode** 체크박스 (Control 패널, 양쪽 입력 시 활성): 한쪽만 있는 점에 RBF 보간으로 상대값 채워 정상 delta 표시. 비활성 시 NaN 룰 적용.
- **RECIPE 호환** — `_PRE` / `_POST` 토큰을 끝 또는 중간 어디서든 자동 제외 후 베이스 비교. `Z_TEST_01__PRE` ↔ `Z_TEST_01__POST` ↔ `Z_TEST_01`, `CMP_PRE_THK` ↔ `CMP_POST_THK` ↔ `CMP_THK` 모두 호환. 구분자 `_` 만 인정 (하이픈/구분자 없음은 비호환).
- **DELTA 좌표 fallback**: A 또는 B 한쪽 좌표 누락 시 자동 fallback (옆집 빌리기 / 라이브러리 매칭). 어떤 경로로 해결됐는지 ReasonBar 에 민트색 메시지 표시.

### 다중 웨이퍼
- 같은 페이스트 안에 여러 웨이퍼가 들어 있으면 자동 분리 (WAFERID 그룹핑).

## 입력 검증 + ReasonBar (사유 표시)

페이스트 직후·Visualize 직후 **Input 라벨** 과 **ReasonBar** (Control 와 결과 사이 한 줄) 에 검증 결과가 표시됨. 색으로 의미 구분:

| 색 | 의미 | 동작 |
|---|---|---|
| 🟢 민트 | 정상 / fallback 성공 | Run 가능, 어떻게 성공했는지 안내 |
| ⚪ 회색 | 정보 알림 | Run 가능, 부가 정보 |
| 🟠 주황 | 주의 | Run 가능, 결과 신뢰성 확인 권장 |
| 🔴 빨강 | 차단 사유 | Run 비활성, 사유 해결 필요 |

### Input 라벨 (페이스트 직후)
- 정상: `웨이퍼 N장, Parameter N개, 좌표 N개` (민트)
- 헤더 행 2개+ 발견: `헤더 행 N개 발견 — 첫 헤더만 사용` (회색 info)
- 반복 측정 분리: `반복 측정 N건 발견 — __rep1, __rep2 ...` (회색 info)
- 일부 wafer PARA set 다름: `일부 웨이퍼 PARA 다름 (...) — 시각화 불가` (빨강 error, **Run 차단**)
- 필수 컬럼 누락: `⚠ 필수 컬럼 부족: ...` (빨강 error, **Run 차단**)

### ReasonBar (DELTA 모드 / Run 결과)

**DELTA 좌표 fallback (페이스트 직후)**:
- `B 좌표 없음. A 와 동일 RECIPE 로 A 좌표 사용.` (민트 ok)
- `B 좌표 없음. B RECIPE 라이브러리 좌표 사용.` (민트 ok)
- `양쪽 좌표 없음. 라이브러리 좌표 사용.` (민트 ok)
- `B 좌표 없음. RECIPE 비호환 + 라이브러리 매칭 없음 — 시각화 불가.` (빨강 error)

**DELTA 기타**:
- `WAFERID 교집합 없음 (A N장, B N장)` (빨강 error)
- `RECIPE 다름 (A=..., B=...)` (주황 warn — 시각화 가능, 의미 해석 주의)
- `A·B 공통 VALUE PARA 없음 — 한쪽만 가진 PARA 도 선택 가능` (주황 warn)
- `A 또는 B 에 WAFERID 중복 N건 — 첫 측정 set 끼리 계산` (주황 warn)

**Run 후 (단일 모드)**:
- `wafer N개 좌표 라이브러리 자동 적용: lot.slot, ...` (민트 ok — 자체 X/Y 없어 라이브러리에서 가져온 wafer 안내)
- `좌표 해결 실패 wafer N개 표시 안 됨: lot.slot, ...` (주황 warn — 시각화는 진행, 일부 wafer 만 빠짐)
- `포인트 개수 불일치 — VALUE T1: 50 pt vs 좌표 X/Y: 55 pt` (주황 warn — 시각화 진행, 결과 신뢰성 확인)

**Run 후 (DELTA 모드 차단)**:
- `DELTA: 양쪽 좌표 결정 실패 — 좌표 라이브러리 매칭 필요` (빨강 error)
- `DELTA: 매칭된 wafer 0 — 시각화할 데이터 없음` (빨강 error)

### 차단 사유 해결 가이드

| 사유 | 해결 |
|---|---|
| WAFERID 교집합 없음 | A·B 입력의 WAFERID 컬럼 확인. 같은 wafer 끼리 매칭 가능한지. |
| 좌표 결정 실패 | Settings → 좌표 라이브러리에 해당 RECIPE 좌표 미리 저장. 또는 입력에 X/Y PARAMETER 행 추가. |
| 일부 웨이퍼 PARA 다름 | 페이스트한 데이터에 일부 행 누락 있는지 확인. 누락된 PARA 행 보충. |
| 필수 컬럼 부족 | 헤더에 `WAFERID`/`LOT ID`/`SLOTID`/`PARAMETER`/`RECIPE`/`DATA1`+ 있는지 확인. |

## 좌표 프리셋 라이브러리

VALUE 파싱은 되지만 X/Y 좌표가 입력에 없는 경우 대비.

### 자동 저장
- Visualize 시 사용한 (RECIPE, X, Y) 조합이 `coord_library.json`에 자동 등록.
- 다음에 같은 RECIPE의 좌표 없는 입력이 들어오면 자동 적용 (타이틀에 📁 아이콘).

### 수동 추가
- Settings → 좌표 라이브러리 탭 → **수동 추가**.
- RECIPE 이름 입력 + 좌표 페이스트.
- 좌표 포맷 4종 자동 감지:
  - `x 0 74 148 / y 148 74 0` (행 + X/Y 라벨)
  - `0 74 148 / 148 74 0` (행, 위=X)
  - `x y / 0 148 / ...` (열 + x/y 헤더)
  - `0 148 / 74 74 / ...` (열, 좌=X)
- 구분자 무관 (공백/탭/콤마/세미콜론). BOM·비데이터 라인 자동 필터.

### 불러오기
- Control 패널의 **저장된 좌표 불러오기** 버튼 → 현재 VALUE 개수에 맞는 프리셋 목록에서 선택.

## Para 조합

서로 다른 PARA + 좌표 페어를 합쳐 하나의 시각화로. 같은 좌표면 element-wise 합 (sum), 다른 좌표면 점 집합 합집합 (concat) — **mode 자동 판정**.

### 사용 흐름
1. Control 패널의 **Para 조합** 버튼 → 다이얼로그
2. PARA 1·2 + 좌표 1·2 선택 (좌표는 PARA 선택 시 자동 매칭)
3. 하단 미리보기에서 최종 형태 확인 → **Apply**
4. 메인 콤보에 `🔗` prefix 붙은 합성 항목으로 추가됨 → **Run** 으로 시각화

### 표기 규칙
| 케이스 | 좌표 | 표기 | 의미 |
|---|---|---|---|
| sum | 같음 | `T1 + T2` | element-wise 덧셈 (예: PRE + POST 두께 합) |
| concat | 다름 | `T1 ∪ T1_A` | 점 집합 합집합 (예: inner + outer 좌표) |

### 누적 / 재조합 (recursive)
- Apply 후 다이얼로그 다시 열면 합성 결과도 PARA 콤보에 노출됨 → 또 다른 합성의 피연산자로 사용 가능
- **같은 mode 끼리는 자동 평탄화**:
  - `(T1+T2) + T3` (모두 같은 좌표) → `T1 + T2 + T3`
  - `(T1 ∪ T1_A) ∪ T1_B` (다른 좌표들) → `T1 ∪ T1_A ∪ T1_B`
- **다른 mode 가 섞이면 자동 괄호** (우선순위 명시):
  - `(T1 + T2) ∪ T_A`
  - `(((T1 ∪ T2) + T3 + T4) ∪ (T5 + T6)) ∪ T7` 임의 깊이 가능

### 주의
- 같은 PARA 두 번 선택 (예: T1 + T1) — 다이얼로그에서 차단
- 좌표 매칭 안 되는 wafer 는 Apply 시 "조합 대상 데이터 없음" 사유 표시 후 추가 안 됨
- 입력 (페이스트) 변경하면 합성 항목 자동 해제

## Copy 기능 (PPT 호환)

**그래프 우클릭 메뉴**:
- **Copy Graph** — 그래프 + Summary 표 전체를 이미지로 Copy. PPT에 Ctrl+V로 사진 붙여넣기.
  - **0.2.0 부터 offscreen 렌더 방식**: 그래프가 다른 창에 가려지거나 스크롤에 숨어 있어도 완전한 이미지가 복사됨. MSAA 4x 로 가장자리도 부드럽게.
- **Copy Data** — 측정점 raw 값 (X / Y / VALUE) → TSV. Excel 셀에 바로 붙여넣기.
- **Copy Table** — Summary 표 → PPT 표로. HTML+TSV dual MIME.

## 3D 조작

| 조작 | 효과 |
|---|---|
| 좌드래그 | 선택 그래프만 회전 |
| Ctrl + 드래그 | 선택 그래프만 이동 |
| **Shift + 좌클릭/드래그** | **전체 그래프 앵글 동기** |
| **Shift + Ctrl + 드래그** | **전체 그래프 위치 동기** |
| 휠 | 비활성 (크기 고정) |
| 우클릭 → Reset | 카메라 초기 상태 복원 |

## Settings

우상단 **⚙ Settings** 버튼.

### 디자인 설정 탭
- **테마·폰트·글자 크기** — 14가지 테마.
- **MAP 공통** — 컬러맵(28종) · 보간 방법(RBF 4종) · 격자 해상도 · 경계 원 / Notch / 스케일바 · **그래프 크기(5종)** · **소수점 자릿수(0~3)**.
- **2D MAP** — 측정점 마커 표시·크기, 측정점 값 라벨.
- **3D MAP** — 부드러운 표면, Z-Height 과장, 카메라 거리.

### 좌표 라이브러리 탭
- 저장된 프리셋 목록. 헤더 클릭으로 정렬. 편집/삭제.
- **자동 정리** — 최대 저장 개수·최대 보관일 초과 시 last_used 오래된 순으로 삭제 (0 = 무제한).

### Default
- 디자인 설정 탭 좌측 하단 **Default** 버튼 — 그래프 4개 카드 (Chart Common · 2D · 3D · 1D Radial) 만 기본값으로 리셋.
- **UI 카드 (테마·글꼴·윈도우 크기 저장·글자 크기) 는 Default 영향 없음** — 디자인 취향 영역이라 사용자 마지막 값 보존. 처음 실행 시엔 `Light (기본)` 테마, `Segoe UI (기본)` 글꼴, 글자 크기 보통 적용.

### Save
- **Save** — settings.json에 저장 (창은 안 닫힘, 연속 조정 가능).
- **Close** — 저장 없이 닫기.

## 입력 데이터 포맷

계측 장비의 long-form CSV. 한 행 = "한 웨이퍼의 한 PARAMETER".

**필수 컬럼** (헤더 대소문자/공백/언더바 무관):
- `WAFERID` / `LOT ID` / `SLOTID` / `PARAMETER` / `RECIPE`
- `DATA1`, `DATA2`, ... (1개 이상)

**선택 컬럼**:
- `MAX_DATA_ID` · `STEPDESC` · `DATE` · `MACHINE` 등 (시각화엔 불사용, 있어도 무시).

**PARAMETER 이름** (예):
- 측정값: `T1`, `T2`, `T3_A`, `GOF`, `T1_AVG` 등 자유.
- 좌표: `X`, `Y`, `X_1000`, `Y_A` 등. `|max| > 200`면 μm로 간주하여 `/1000` mm 환산.

## 파일 위치

실행 폴더 내부 (무설치 포터블):
- `settings.json` — 사용자 설정
- `coord_library.json` — 좌표 프리셋

## 버전 / 피드백

현재 버전은 창 우상단에 표시 (`v0.4.0 | © 2026 SK hynix | Jihwan Park`). 이슈·요청은 GitHub Issues 또는 사내 채널로.
