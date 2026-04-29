# 좌표 결정 + 라이브러리 정책

> **유지 정책**: 좌표 결정 우선순위·DELTA fallback 매트릭스·라이브러리 저장/조회/정리 룰을 변경할 때 이 파일을 동반 갱신. 마지막 업데이트는 하단에.

## Single mode — per-wafer 4단계 fallback

각 wafer 의 좌표를 **개별** 결정. 한 wafer 실패가 다른 wafer 에 영향 X.

| 순위 | 출처 | 조건 | 결과 표시 |
|---|---|---|---|
| 1 | **사용자 명시 프리셋** | "저장된 좌표 불러오기" 다이얼로그에서 선택 (`_preset_override`) | 정상, silent |
| 2 | **wafer 자체 X/Y PARA** | `wafer.parameters` 에 X, Y 둘 다 존재 | 정상, silent |
| 3 | **RECIPE 기반 라이브러리** | `wafer.recipe` 일치 프리셋 존재. `n_points` 일치 우선 | 📁 아이콘, silent |
| 4 | **모두 실패** | — | cell skip + ReasonBar warn `좌표 해결 실패 wafer N개` |

### 라이브러리 source 두 종류

- **같은 Run 안의 다른 wafer** — 먼저 처리된 wafer 가 `_save_used_pair_to_library` 로 저장한 entry. 같은 RECIPE → 자동 매칭.
- **이전 Run 들의 누적** — `coord_library.json` 에 영구 저장.

### Single mode edge case

- **순서 의존성** — 좌표 없는 wafer 가 첫 iteration 이면 라이브러리 비어있어 priority 3 실패 가능. 후순위 처리 시엔 자동 fallback.
- **stale library** — 이전 Run 의 좌표가 RECIPE 매칭으로 silent 사용될 수 있음.

## DELTA mode — all-or-nothing per side 매트릭스

**양쪽 좌표를 side (A 전체 / B 전체) 기준으로 결정**. 일부만 누락된 경우는 별도 warn (아래).

| A 좌표 | B 좌표 | RECIPE 호환 | 처리 |
|---|---|---|---|
| 있음 | 있음 | any | A·B 각자 (compute_delta 합집합 매칭) |
| 있음 | 없음 | 호환 | B 가 A 좌표 빌림 (양쪽 동일) |
| 있음 | 없음 | 비호환 | B 라이브러리 매칭 → 합집합 / 매칭 X 비활성 |
| 없음 | 있음 | 호환 | A 가 B 좌표 빌림 |
| 없음 | 있음 | 비호환 | A 라이브러리 매칭 → 합집합 / 매칭 X 비활성 |
| 양쪽 없음 | — | 호환 | A 라이브러리 → 없으면 B 라이브러리 (양쪽 동일) |
| 양쪽 없음 | — | 비호환 | 양쪽 라이브러리 모두 필요 |

### DELTA 부호

- **A − B 고정**. 토글 옵션 없음.

### DELTA 매칭 룰

- **wafer 매칭** — `WAFERID` 일치만. `LOT ID` / `SLOTID` 불일치 허용 (mutable 상태값).
- **점 매칭** — 같은 `WAFERID` 안 (X, Y) tolerance 1mm 직선거리 내 일치. 합집합 룰:
  - 양쪽 매칭 점: `dv = va − vb`
  - A only 점: `dv = va` (B = 0 가정)
  - B only 점: `dv = −vb` (A = 0 가정)
  - **Δ-Interp mode** 활성 시 a_only/b_only 점에 RBF 보간으로 채움 (NaN 룰 대신)
- **wafer 수 불일치 허용** — `WAFERID` 교집합만 출력. 비공통 wafer 는 silent skip.

### DELTA 부분 좌표 누락 처리

- **현재 정책 (정정 필요 가능성)**: `_resolve_delta_coords` 가 all-or-nothing per side. 한 wafer 라도 좌표 없으면 그 side 전체 누락으로 처리 → 옆집/라이브러리 빌려옴.
- **부작용**: 자기 좌표 있는 wafer 까지 옆집 좌표로 덮임. RECIPE 같으면 시각적 차이 거의 없지만 silent 데이터 override.
- **paste 시점 surface**: `validate_delta` 가 `delta_a_partial_coord` / `delta_b_partial_coord` warn 발행 (`A 일부 wafer 좌표 누락 (N/M)` 형식).
- **TODO** (사용자 정책 미확정): single 처럼 per-wafer fallback 으로 재작성하면 warn 자체 불필요해짐.

### DELTA preset_override

- **수동 프리셋 불러오기 — 비활성**. DELTA 진입 시 버튼 회색 처리.
- 자동 fallback 매트릭스가 좌표 결정 담당. 수동 override 불필요.

### RECIPE 호환 룰 (`core/recipe_util.recipes_compatible`)

- 구분자 `_` 만 인정 + `_PRE` / `_POST` 토큰 끝/중간 어디서든 제외 후 베이스 비교 + 대소문자 무관
- 예: `Z_TEST_01__PRE` ↔ `Z_TEST_01__POST` 호환. `Z_PRE_TEST_01` 도 처리 (중간 토큰).
- 부분 일치 보호: `Z_PRESET_01` (PRE+SET), `Z_POSTBAKE_01` 등은 lookahead 로 매치 회피.
- 맨 앞 (`PRE_TEST_01`) 은 처리 안 함 (사내 데이터에 존재 안 함).

## 좌표 라이브러리 (CoordLibrary)

저장 위치: 앱 실행 폴더 `coord_library.json` (포터블, .gitignore).

### 저장 스키마

```json
{
  "presets": [{
    "name": "49P Polar 5mm",
    "recipe": "HT_SOC_POLAR_49PT_5mm",
    "n_points": 49,
    "x_mm": [...], "y_mm": [...],
    "created_at": "...",
    "last_used": "..."
  }]
}
```

### 자동 저장 (Visualize 시)

- 입력된 wafer 별로 `(recipe, x_mm, y_mm)` 조합을 라이브러리와 비교
- tolerance (≈1e-3 mm) 내 일치 레코드 있으면 → `last_used` 갱신만
- 없으면 새 레코드 추가. 자동 이름: `{recipe}_{n_points}P` (중복 시 `(2)`, `(3)` suffix)
- **저장 조건** (single + DELTA 동일):
  - wafer 자체에 v / x / y PARA 모두 존재
  - 좌표/값 길이 일치 (`n_x == n_y == n_v`)
  - `wafer.recipe` 비어있지 않음
  - **합성 친화 키 차단** — 이름에 ` + ` (sum) 또는 ` ∪ ` (concat) 포함 시 저장 X
  - **Fallback 좌표 round-trip 차단** — 라이브러리/preset/옆집에서 가져온 좌표는 다시 저장 X (single: `from_preset` / `from_lib` 검사. DELTA: `wafer.parameters` 자체 X/Y 존재 검사)

### 자동 조회 (좌표 없는 입력)

- 입력에 X/Y PARA 없거나 `auto_select` 폴백 실패 시 → `wafer.recipe` 매칭 프리셋 자동 사용
- 매칭 우선순위: 정확 일치 → PRE/POST 베이스 일치 → similarity (3+ 토큰)
- `last_used` 최신 레코드 사용
- cell 타이틀에 📁 아이콘 표시

### 수동 불러오기 (Step 2 path B)

- "저장된 좌표 불러오기" 버튼 (single mode 만)
- n_points 일치 필터 + recipe 우선 정렬
- 중복 좌표 (1e-3mm tolerance) 묶어서 표시 (`{recipe} 외 N`)
- 선택 시 `_preset_override` 셋. paste 변경 시 자동 해제.

### DELTA 모드

- **수동 불러오기 비활성** — 자동 fallback 매트릭스가 처리.

### 자동 정리

- `coord_library.max_count` (기본 1000) / `max_days` (기본 0=무제한)
- 초과 시 `last_used` 오래된 순 삭제
- `_visualize_single` / `_visualize_delta` 끝 + Settings Save 시점에 호출

### 편집 / 삭제

- Settings → 좌표 라이브러리 탭
- 헤더 클릭 정렬, 개별 삭제 가능
- 이름·좌표 수정 미지원 (새로 저장하는 방식)

## 코드 참조

- Single 결정: [widgets/main_window.py::_visualize_single](../../widgets/main_window.py)
- DELTA 결정: [widgets/main_window.py::_resolve_delta_coords](../../widgets/main_window.py)
- 부분 누락 검출: [core/delta_validation.py::_wafer_has_xy](../../core/delta_validation.py)
- RECIPE 호환: [core/recipe_util.py::recipes_compatible](../../core/recipe_util.py)
- 라이브러리: [core/coord_library.py](../../core/coord_library.py)
- 라이브러리 저장 가드: [widgets/main_window.py::_save_used_pair_to_library](../../widgets/main_window.py)

---

**마지막 업데이트**: 2026-04-30 (정책 카탈로그 분리)
