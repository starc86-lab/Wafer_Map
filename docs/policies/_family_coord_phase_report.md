# 가족 좌표 정책 도입 — 자율 진행 보고서

작성: 2026-04-30 (overnight 자율 진행 완료)
시작 시점 rollback: `fd780b5` (origin/feature/v0.2.1-rev2 마지막 push)
미푸시 상태로 commit 만 누적. 사용자 검증 후 push 결정.

## Phase 별 commit + 효과

| Phase | Commit | 변경 | Sample diff |
|---|---|---|---|
| 0 (인프라) | `fca15fb` | sample CSV 9개 + capture/compare script + baseline | — |
| 1 docs | `6c5e0ae` | docs/policies/coords.md, reason_bar.md 가족 정책 정의 | 변화 없음 |
| 2 family_coord | `e9b67db` | core/family_coord.py 신규 (RECIPE 검증) + input_validation 통합 | s_family_multi_recipe → ERROR |
| 3 single 시각화 | `5f8d9bc` | family_coord 확장 (좌표 결정/partial 검증) + _visualize_single 가족 정책 | s_family_partial_coord / s_family_short_n / d_partial paste-time info |
| 4 DELTA 시각화 | `100862e` | _resolve_delta_coords 단순화 (옆집/라이브러리 chain), DELTA preset 활성화, delta_partial 폐지 | d_partial 의 stale warn 제거 |
| 5 마이너 정리 | `7cc0315` | preset 버튼 텍스트 단순화, ReasonBar info ⚠ 제거, 라이브러리 가족 단위 저장 | info 메시지 ⚠ prefix 사라짐 |

## 핵심 정책 변경 요약

1. **가족 = 한 입력 (A/B)의 모든 wafer**, 단일 RECIPE 공유 강제 (PRE/POST 호환).
2. **paste 시점 RECIPE 단일성 검증** — 다르면 `single_recipe_mismatch` ERROR (Run 차단).
3. **paste 시점 partial 검증** — wafer 별 좌표 누락 / N 부족 detect → `family_coord_missing` / `family_coord_short` info (LOT.SLOT 라벨).
4. **시각화 시 좌표 결정** — 자기 좌표 → 가족 좌표 차용 → 라이브러리 chain.
5. **DELTA matrix 단순화** — 옆집 borrow + 라이브러리 fallback chain (가족 정책 일관 적용).
6. **DELTA preset_override 활성화** — 양 가족 동일 적용.
7. **라이브러리 가족 단위 저장** — wafer 마다 시도 폐지, 가족당 1번.
8. **info 메시지 ⚠ 제거** — 정보 톤은 plain 표시.

## 사용자 검증 시나리오 (회사 PC)

### 회귀 detector (현재와 동일 동작 기대)
- `s_family_normal` — 3 wafer 정상 렌더
- `s_family_multi_coord_set` — X/Y + X_A/Y_A 정상 노출
- `s_combine_data` — PARA 조합 회귀 X
- `d_normal` — DELTA 정상 (PRE/POST RECIPE 호환)
- `d_recipe_diff` — DELTA RECIPE warn

### 정책 변화 검증
- `s_family_multi_recipe` → **paste 즉시 RECIPE 다름 ERROR** (Run 차단)
- `s_family_partial_coord` → paste 시 `LX002.03 좌표 누락: X_A/Y_A` info, Run 정상
- `s_family_short_n` → paste 시 `LX003.03 좌표 Point 부족` info, Run 시 W3 cell 13pt 렌더 (이전 12pt)
- `d_partial` → paste 시 `A: LX11A.03 좌표 누락: X/Y` info 만 (이전 warn 함께였음). Run 시 가족 정책으로 처리

### 실데이터 검증 권장
- 회사 PC 실 paste 입력으로 단일/DELTA 시각화 정상 동작 확인.
- 특히 paste 마지막 cell 누락된 wafer 가 가족 max N 으로 채워지는지.
- `저장된 좌표 불러오기` DELTA 모드에서 작동하는지 (preset 양 가족 적용).

## 미푸시 commit

```
7cc0315 feat(family-coord) Phase 5
100862e feat(family-coord) Phase 4
5f8d9bc feat(family-coord) Phase 3
e9b67db feat(family-coord) Phase 2
6c5e0ae docs(policies): Phase 1
fca15fb test: 회귀 검증 인프라
```

회귀 발견 시 rollback: `git reset --hard fd780b5` (origin 과 동일).

## 잠재 이슈 / 사용자 결정 필요

1. **`A:` prefix 가 single mode 에서도 표시됨** — `_update_delta_validation` 이 single 입력 결과에도 `A:` 자동 prefix. UI 자연성 떨어질 수 있음. single mode 에선 prefix 제거할지 결정 필요.

2. **메시지 길이** — RECIPE 다름 메시지가 길음 (`A: RECIPE 다름 — LX001.03: RECIPE_B vs 가족: RECIPE_A`). ReasonBar 한 줄 잘림 가능 — tooltip / wrap 필요시 추가.

3. **Phase 4 의 단순화 효과는 sample 캡처에 안 보임** — 자기 좌표 wafer 가 옆집 좌표로 덮이지 않는 개선. 실데이터 (RECIPE 같으면 좌표 동일) 에선 시각적 차이 없음. 차이가 보이는 케이스는 RECIPE 같으면서 좌표가 다른 인위적 케이스 (사실상 발생 X).

4. **라이브러리 가족 단위 저장의 검증** — sample 캡처는 라이브러리 상태 직접 비교 안 함. coord_library.json 의 entry 누적 패턴 변화 — wafer 수 비례 → 가족 수 비례. 사용자 검증 시 라이브러리 폭주 줄어드는지 관찰.

## 권장 push 명령

검증 OK 면:
```
git push origin feature/v0.2.1-rev2
```
