# 좌표 결정 + 라이브러리 정책

> **유지 정책**: 좌표 결정·DELTA fallback·라이브러리 저장/조회 룰 변경 시 이 파일 동반 갱신. 마지막 업데이트는 하단에.

## 핵심 모델 — "가족 공통 좌표"

**가족 = 한 입력 (A 또는 B) 의 모든 wafer.** 가족은 단일 RECIPE 를 공유 (다르면 ERROR). 가족 내 wafer 들은 **공통 좌표 set 들** 을 공유 — 같은 RECIPE 의 같은 좌표 PARA 이름은 좌표값도 동일이라고 가정.

가족이 보유할 수 있는 좌표 set 은 **여러 개 동시 가능** — 예: `(X, Y)` 13pt + `(X_A, Y_A)` 12pt + `(X_B, Y_B)` 11pt. 각 set 은 별개의 measurement plan.

## Paste 시점 검증 (모든 검증 paste 단계에서 끝)

### 필수
1. **필수 컬럼** 매칭 (`MissingColumnsError` — 기존)
2. **가족 RECIPE 단일성** — 모든 wafer 의 RECIPE 가 PRE/POST 베이스 비교로 같아야 함. 다르면 **ERROR (Run 차단)**.
   - 빈 RECIPE 칼럼은 존재 안 함 (사용자 정책 — 데이터에서 빈 값 발생 X). 일부만 빈 경우 다른 RECIPE 와 불일치로 같이 차단됨.

### 가족 좌표 set list 결정
- 가족 wafer 들의 PARA union 에서 X/Y 페어 추출 (`select_xy_pairs` 동일 룰).
- 결과: `[(X, Y, n), (X_A, Y_A, n_a), (X_B, Y_B, n_b), ...]` — 페어 별 list.
- 각 페어의 n_points 는 가족 내 가장 긴 N 채택 (paste 마지막 cell 누락 edge 대응).

### 가족 좌표 set 의 좌표값
- "RECIPE + 좌표 PARA 이름 같으면 좌표값 동일 보장" — tolerance 비교 폐지.
- 가족 좌표 = 가족 내 그 페어 보유한 wafer 중 **가장 긴 N 의 wafer 좌표** 채택.
- 좌표값 비교 검증 자체 불필요.

## Single mode — 시각화 흐름

라이브러리 좌표는 **가족 좌표 list 의 일반 entry** 로 통합 (사용자 정책
2026-04-30, preset_override 강제 1순위 폐지).

각 wafer 별 priority chain:

| 우선순위 | 출처 | 조건 | 결과 |
|---|---|---|---|
| 1 | wafer 자체 X/Y PARA | wafer.parameters 에 선택된 페어 보유 + N >= 가족 max | 자기 좌표 사용 |
| 2 | 가족 좌표 | 이 페어의 가족 좌표 결정됨 (자체 또는 라이브러리 source) | silent 차용 |
| 3 | RECIPE 라이브러리 fallback | 가족 페어 누락 시 방어 분기 | (paste 시점 자동 매칭이 일반적, 거의 발생 X) |
| 4 | 모두 실패 | — | 시각화 불가 ERROR |

### 가족 좌표 list 의 entry source

- **family**: 가족 wafer 들이 자체 보유한 좌표 페어 (콤보 라벨 prefix X)
- **library**: 라이브러리에서 가족 list 에 추가됨 — 콤보 라벨에 `{id}.` prefix
  - 사용자 명시 추가 (`좌표 추가` 다이얼로그)
  - 자동 RECIPE 매칭 (가족 자체 페어 비어있고 라이브러리 매칭 ✓)

같은 (x_name, y_name) 페어가 가족 자체 + 라이브러리 둘 다 있으면 가족 자체 우선
(콤보 순서 = 자동매칭 우선순위).

## DELTA mode — 시각화 흐름

각 가족 (A, B) 마다 single 정책으로 가족 좌표 결정. 추가:

| 케이스 | 처리 |
|---|---|
| 양 가족 모두 정상 (자체 또는 가족 좌표 보유) | 각자 사용 |
| 한 가족 전체 좌표 누락 + 옆집 RECIPE 호환 (PRE/POST) + 옆집 좌표 보유 | **옆집 borrow** |
| 한 가족 전체 누락 + 옆집 비호환 / 옆집도 누락 | 라이브러리 lookup |
| 양 가족 모두 누락 + 라이브러리 매칭 X | ERROR |

### DELTA 부호
- **A − B 고정**. 토글 X.

### DELTA 매칭 룰
- **wafer 매칭** = `WAFERID` 일치만. `LOT ID` / `SLOTID` 불일치 허용.
- **점 매칭** = 같은 `WAFERID` 의 (X, Y) tolerance 1mm 이내 합집합.
  - 양쪽 매칭 점: `dv = va − vb`
  - A only / B only: `dv = va` 또는 `−vb` (NaN 룰).
  - **Δ-Interp mode** 활성 시 a_only/b_only 점 RBF 보간으로 채움.

### DELTA 라이브러리 좌표 추가
- "좌표 추가" 다이얼로그 — single + DELTA 모두 활성. 양 가족 list 에 동일 entry
  추가됨 (preset_override 강제 1순위 폐지 후 일반 entry 화).

### RECIPE 호환 룰 (`core/recipe_util.recipes_compatible`)
- 구분자 `_` 만 인정 + `_PRE` / `_POST` 토큰 끝/중간 어디서든 제외 후 베이스 비교 + 대소문자 무관.
- 예: `Z_TEST_01_PRE` ↔ `Z_TEST_01_POST` 호환.

## 콤보 표시

### 가족 좌표 set list 콤보
- 좌표 콤보: 가족 좌표 페어 list — `X / Y [13 pt]`, `X_A / Y_A [12 pt]`, ...
- 라이브러리 source 페어는 라이브러리 entry id prefix `{N}.` 표기 (예:
  `7. X / Y [13 pt]`). 가족 자체 페어는 prefix X.
- 가족 자체 페어 비어있을 때 자동 RECIPE 매칭 → `_added_presets` 에 silent 추가
  → 콤보에 라이브러리 entry 로 노출 (`{id}. X / Y [N pt]`).

### VALUE PARA 콤보
- 가족 VALUE PARA union — 일부 wafer 만 가진 PARA 도 노출. 누락 wafer 는 `(no data)` cell 자동.

### 콤보 자동 매칭
- VALUE 변경 시 같은 n_points / suffix 의 좌표 페어 자동 선택 (현재 동작 유지).
- VALUE 와 좌표 페어 N 불일치 조합 가능 — 사용자 자유. n_mismatch warn 표시.

## 라이브러리 (CoordLibrary)

저장 위치: 앱 실행 폴더 `coord_library.json`.

### Entry 구조 + 키
- entry 키: `(RECIPE, x_name, y_name, n_points)` 4-tuple.
- 좌표값 비교 폐지 — 같은 4-tuple 이면 dedup (last_used 갱신).
- entry: `id`, `recipe`, `x_name`, `y_name`, `n_points`, `x_mm`, `y_mm`, `created_at`, `last_used`.

### 영구 고유 번호 (`id`)
- 1부터 시작, entry 별 영구 고유 (사용자 정책 2026-04-30).
- 신규 add 시 **smallest-unused** 부여. 삭제 후 빈 번호 → 다음 add 가 채움
  (예: 1, 2, 4, 5 보유 → 다음 add 시 id=3 채움).
- 콤보 라벨 prefix 용 (`{id}. X/Y`).
- 기존 라이브러리 마이그레이션: load 시 id=0 entry 들에 created_at 순으로
  smallest-unused 자동 부여.

### 저장 (Visualize 시)
- **가족 단위 1회 저장** — 가족이 보유한 좌표 페어 set 별로 entry 1개.
- 저장 조건:
  - 가족 RECIPE 비어있지 않음
  - 가족 wafer 중 그 페어 보유 wafer 존재 (좌표값 추출 가능)
  - 합성 친화 키 (`+`, `∪` 포함) 는 저장 X
- 좌표값은 가족 내 가장 긴 N wafer 의 것 사용.

### 자동 조회 (가족 전체 좌표 누락 시)
- (RECIPE, x_name, y_name, n_points) 매칭 → `last_used` 최신 사용.
- 매칭 우선순위: 정확 일치 → PRE/POST 베이스 일치 → similarity (3+ 토큰).

### 좌표 추가 (가족 list 에 라이브러리 entry 추가)
- "좌표 불러오기" 버튼 → "좌표 추가" 다이얼로그 (single + DELTA 모두 활성).
- 다이얼로그 — n_points 일치 필터 + recipe 유사도 정렬, **다중 행 선택** 가능.
- 더블클릭 → 즉시 추가 (Add). 우클릭 → 좌표 미리보기 컨텍스트 메뉴.
- "추가" 버튼 — 선택된 모든 entries 를 `_added_presets` list 에 append → 가족
  좌표 list 에 통합되어 콤보에 `{id}. X/Y` prefix 로 노출.
- paste 변경 시 자동 해제 (`_clear_added_presets`).
- 사용자 정책 2026-04-30: 강제 priority 1 적용 폐지, 콤보 일반 entry 동작.

### 자동 정리
- `coord_library.max_count` (기본 1000) / `max_days` (기본 0=무제한).
- `last_used` 오래된 순 삭제.

### 편집 / 삭제
- Settings → 좌표 라이브러리 탭. 헤더 클릭 정렬, 개별 삭제.

## ReasonBar 알림

### Paste 시점 (`validate` / `validate_delta`)
- `single_recipe_mismatch` (error) — 가족 RECIPE 다름. 메시지에 다른 RECIPE wafer 의 LOT.SLOT 명시.
- `family_coord_missing` (info) — 가족 일부 wafer 가 좌표 페어 누락. `LOT.SLOT 좌표 누락: X_A/Y_A` 형식. wafer 별 1건씩.
- `family_coord_short` (info) — 가족 일부 wafer 가 좌표 N 부족. `LOT.SLOT 좌표 Point 부족: X (12pt, 1점 부족)` 형식.
- `delta_no_intersect` (error) — `WAFERID 교집합 없음`.
- `delta_recipe_mismatch` (warn) — `RECIPE 다름` (이웃 가족 비교).
- `delta_coord_unresolved` (error) — 양 가족 좌표 결정 실패.

### Run 시점
- `n_mismatch` (warn) — VALUE n vs 좌표 n 불일치 (콤보 선택 결과).

## 글로벌 정책 — 사용자 알림에 LOT.SLOT 명시

wafer 단위 이슈 메시지는 모두 `{lot_id}.{pad2(slot_id)}{rep_suffix}` 라벨 포함. 가족/이웃 단위 이슈 (RECIPE 다름, 교집합 없음) 는 라벨 무관.

## 코드 참조

- 가족 좌표 결정: [core/family_coord.py](../../core/family_coord.py) (Phase 2 신설 예정)
- Single 시각화: [widgets/main_window.py::_visualize_single](../../widgets/main_window.py)
- DELTA 시각화: [widgets/main_window.py::_visualize_delta](../../widgets/main_window.py)
- DELTA 매트릭스: [widgets/main_window.py::_resolve_delta_coords](../../widgets/main_window.py)
- RECIPE 호환: [core/recipe_util.py::recipes_compatible](../../core/recipe_util.py)
- 라이브러리: [core/coord_library.py](../../core/coord_library.py)
- 라이브러리 저장 가드: [widgets/main_window.py::_save_used_pair_to_library](../../widgets/main_window.py)

---

**마지막 업데이트**: 2026-04-30 (preset_override 강제 1순위 폐지 → 라이브러리
좌표 = 가족 list 일반 entry, id 영구 고유 번호 도입 — F1~F6)
