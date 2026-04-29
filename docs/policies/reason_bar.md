# ReasonBar — 메시지 / 검증 / 표시 정책

> **유지 정책**: severity 추가·메시지 카탈로그 변경·검증 분기 추가·baseline/덮어쓰기 정책 변경 시 이 파일을 동반 갱신. 마지막 업데이트는 하단에.

## 단일 채널 원칙

- **모든 검증 결과 / Run 차단 사유 / 자동 fallback 알림 = ReasonBar 한 곳**.
- 다이얼로그 (QMessageBox) 사용 금지. 분산 X.
- silent 분기 0 — skip / fallback / 차단 모두 ReasonBar 에 표시.
- "Run 클릭 = 결과 영역이 현재 입력 상태와 동기화" — 잔재 없음.

## Severity 4단계

| Severity | 색 (theme 기반) | Run | 의미 | 메시지 prefix |
|---|---|---|---|---|
| `error` | `t['danger']` (예: 빨강) | **차단** | 시각화 불가능, 사용자 조치 필요 | — |
| `warn` | `t['text']` (검정 톤) | 활성 | 시각화 가능, 결과 신뢰성 확인 권장 | `⚠` |
| `ok` | `t['success']` (녹색, bold) | 활성 | fallback 성공 등 정상 동작 알림 | — (⚠ 안 붙임) |
| `info` | `t['text']` | 활성 | 부가 정보 | — |

- 여러 건 동시 표시 시 max severity 색 채택, 메시지는 `, ` join
- 정상 상태 (warning 0건) → 좌측 `Message:` 라벨 + `✓` (theme `success` 색, bold)

## 표시 시점

| 시점 | 동작 |
|---|---|
| **Paste 직후** | `_update_delta_validation` 호출 → `_delta_warnings` baseline 갱신 → `set_warnings(baseline)` 표시 |
| **Run 시작** | `_on_visualize` 가 `set_warnings(baseline)` 으로 복원 (이전 Run 잔재 제거) |
| **Run 후** | single/delta 별 추가 warn 만 baseline + extras 형태로 추가 (override 금지) |
| **Settings 변경 / 콤보 변경** | 자동 재시각화 (`_on_visualize` 거치므로 baseline 복원 자동) |

## baseline 보존 룰

- **단독 `set_message` 사용 금지** — `set_warnings(baseline + extras)` 패턴 강제.
- baseline (`_delta_warnings`) 은 paste 시점 검증 결과 cache.
- Run 후 추가되는 warn (좌표 해결 실패 wafer N개, n 불일치 등) 은 ValidationWarning 으로 wrap 후 baseline 리스트와 합쳐 표시.
- `_show_blocking_reason(code, severity, message)` 헬퍼 — 차단 사유 표준 진입점. 자동으로 baseline + 차단 메시지 합쳐 표시 + result_panel.clear() 동시 호출.

## 메시지 카탈로그

### Paste 시점 검증 — `core/input_validation` (단일 입력)

| code | severity | 메시지 | 비고 |
|---|---|---|---|
| (현재 simplified — 메시지 출력 거의 없음) | — | — | 0.3.0 에서 `extra_header` / `repeat_measurement` / `para_set_mismatch` warn 메시지 제거. 인터페이스 유지 |

### Paste 시점 검증 — `core/delta_validation` (DELTA 입력)

| code | severity | 메시지 (예) | 분기 |
|---|---|---|---|
| `delta_no_intersect` | error | `WAFERID 교집합 없음` | A·B `WAFERID` 교집합 0 |
| `delta_repeats_in_input` | warn | `A에 웨이퍼 중복 N건, 최신 측정 데이터 사용` | A 또는 B 에 `__rep` 분리 wafer 존재 |
| `delta_coord_unresolved` | error | `A 좌표 없음` / `B 좌표 없음` / `A, B 좌표 없음` | 좌표 fallback 실패 (자세한 매트릭스는 [coords.md](coords.md) 참조) |
| `delta_a_partial_coord` | warn | `A 일부 wafer 좌표 누락 (N/M)` | A 일부 wafer 만 좌표 PARA 누락 (`_resolve_delta_coords` 의 silent 옆집/라이브러리 fallback 인지 surface) |
| `delta_b_partial_coord` | warn | `B 일부 wafer 좌표 누락 (N/M)` | B 대칭 |
| `delta_no_common_value_para` | warn | `공통 PARA 없음` | A∩B VALUE PARA = ∅ (union 으로 콤보 노출되지만 알림) |
| `delta_recipe_mismatch` | warn | `RECIPE 다름` | A·B RECIPE 비호환 (PRE/POST 룰 적용 후) |

### Run 시점 추가 — single mode

| code | severity | 메시지 (예) | 분기 |
|---|---|---|---|
| `single_skipped_wafers` | warn | `좌표 해결 실패 wafer N개` | 일부 wafer 의 좌표 해결 실패 (4단계 fallback 모두 실패) |
| `single_no_coord_all` | error | `좌표 없음` | 모든 wafer 좌표 해결 실패 → 시각화 불가 |
| `n_mismatch` | warn | `측정점 개수 불일치` | VALUE / X / Y 의 n 이 모두 같지 않음 |

### Run 시점 추가 — DELTA mode

| code | severity | 메시지 (예) | 분기 |
|---|---|---|---|
| `delta_coord_unresolved_runtime` | error | `A, B 좌표 없음` | paste 시점 검증 통과했지만 runtime 외부 라이브러리 변경 등 edge case |
| `delta_compute_failed` | error | `매칭 wafer 없음` | `compute_delta` 의 `matched == 0` (WAFERID 교집합 통과 후에도 좌표 합집합 0) |
| `n_mismatch` | warn | `측정점 개수 불일치` | VALUE / X / Y n 불일치 |

### Run 시점 — 공통

| code | severity | 메시지 (예) | 분기 |
|---|---|---|---|
| `no_input` | error | `입력 없음` | A·B 둘 다 빈 paste |
| `no_value_para` | error | `측정값 없음` | VALUE 콤보 비어있음 |
| `no_coord` | error | `좌표 없음` | 좌표 콤보 비어있음 |
| `combined_no_data` | error | `조합 대상 데이터 없음 (operand 누락)` | PARA 조합 Apply 시 매칭 wafer 0 |

## 코드 참조

- ReasonBar widget: [widgets/reason_bar.py](../../widgets/reason_bar.py)
- baseline 복원: [widgets/main_window.py::_on_visualize](../../widgets/main_window.py)
- 차단 사유 헬퍼: [widgets/main_window.py::_show_blocking_reason](../../widgets/main_window.py)
- baseline 갱신: [widgets/main_window.py::_update_delta_validation](../../widgets/main_window.py)
- 단일 입력 검증: [core/input_validation.py](../../core/input_validation.py)
- DELTA 검증: [core/delta_validation.py](../../core/delta_validation.py)
- 전역 QSS 색 매핑: [core/stylesheet.py](../../core/stylesheet.py) (`#reasonBar`, `#reasonBarLabel[severity="..."]`)

## 안티패턴 (금지)

- ❌ `self._reason_bar.set_message(text, severity)` 단독 호출 — baseline 덮어쓰임
- ❌ `QMessageBox.warning(...)` / `QMessageBox.critical(...)` — 다이얼로그 분산
- ❌ silent skip — 일부 wafer 가 표시 안 되면 반드시 ReasonBar 에 사유 표시
- ❌ 시그니처 skip — 같은 입력 재 Run 시에도 항상 새로 시각화

---

**마지막 업데이트**: 2026-04-30 (정책 카탈로그 분리)
