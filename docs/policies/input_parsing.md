# 입력 / 파싱 정책

> **유지 정책**: 파싱 동작·헤더 매칭·DATA 수집·메타 컬럼 처리·반복 측정/헤더 분리 룰을 변경할 때 이 파일을 동반 갱신. 마지막 업데이트는 하단에.
>
> 코드 동작 디테일은 [parser_edge_cases.md](../parser_edge_cases.md) 참조. 이 문서는 **확정 정책**만.

## 워크플로 원칙

- **클립보드 우선** — Ctrl+V 가 제1 입력 방법. 파일 I/O 최소화.
- **출력도 클립보드** — Copy Image (RGB32 + PNG/DIB 듀얼) / Copy Table (HTML+TSV 듀얼) / Copy Data (TSV) PPT/Excel paste 호환.

## 파싱 원칙

- **컬럼 순서 가변** — 위치 기반 파싱 절대 금지.
- **헤더 이름 정규화 매칭** — `_normalize()` 가 lower + 공백·언더바 제거 후 매칭. `LOT ID` = `Lot_ID` = `lotid` 등 동치.
- **모르는 컬럼은 무시** — 샘플에 없는 추가 컬럼이 있어도 파싱 진행.
- **DATA 컬럼 식별** — `^DATA[ _]?\d+$` (case-insensitive) 정규식. 숫자 suffix 정렬 (`DATA1`, `DATA_1`, `DATA 1` 동일 취급).

## 필수 컬럼

| 컬럼 | 역할 |
|---|---|
| `WAFERID` | 영구 고유 ID. 그룹핑·DELTA 매칭의 기본 키 |
| `LOT ID` | 현재 소속 로트 (mutable) |
| `SLOTID` | 현재 슬롯 번호 (mutable) |
| `PARAMETER` | 측정 항목 이름 (자유 가변) |
| `RECIPE` | 계측 레시피 (라이브러리 매칭 키) |
| `DATA1` ~ `DATAN` | 실제 수치, 1개 이상 |

필수 컬럼 매칭 실패 시 → **컬럼 매핑 다이얼로그** 폴백 (사용자가 직접 매핑).

## 선택 컬럼

| 컬럼 | 동작 |
|---|---|
| `MAX_DATA_ID` | 명시된 DATA 개수. 실제 셀 개수와 다르면 **에러 팝업 후 실제 개수 신뢰** (중단 X) |
| `STEPDESC` / `DATE` / `MACHINE` / `OPERATINID` / `ETC1~3` | 시각화 미사용. 있어도 무시 |

## WAFERID 처리 (중요)

- 한 wafer 가 라이프사이클 중 LOT reassign / Slot move 되면 `LOT ID`·`SLOTID` 는 변하지만 **`WAFERID` 는 불변**.
- **그룹핑·비교는 `WAFERID` 문자열 그대로만**. `LOT ID`·`SLOTID` 는 표시용 현재 상태값.
- `WAFERID` 분해 금지 — 형식이 `RK2A007.08` 처럼 보여도 LOT/SLOT 으로 파싱하지 않음.

## 헤더 / 반복 측정 분리

- **헤더 행 2개+ 발견** — 첫 헤더만 사용. info 알림 (현재 simplified 로 메시지 출력 X).
- **(WAFERID, PARAMETER) 재등장** — `__rep1`, `__rep2` suffix 로 분리. 첫 set 이 **시간상 가장 최신 측정** (사내 시스템 정책). cell 타이틀에 `(rep1)` 형태 표시.

## 좌표 단위 자동 환산

| 측정값 max | 단위 추정 | 처리 |
|---|---|---|
| `\|max\| ≤ 200` | 이미 mm | 그대로 사용 |
| `200 < \|max\| ≤ 200000` | μm 또는 ×1000 표기 | `/1000` 환산하여 mm |
| 그 외 | 불명 | 사용자 수동 오버라이드 요청 |

## 반경 외 점

- 웨이퍼 직경 **300mm 고정** — 반경 150mm 밖 측정점은 경고 후 제외.

## VALUE / X / Y 자동 선택

- **VALUE**: `value_patterns` (기본 `["T*"]`) fnmatch + n=DATA 컬럼 총 개수 우선
- **X**: `x_patterns` (기본 `["X", "X*"]`) — 완전 일치 → 접두사 매칭 순
- **Y**: X 의 suffix 를 물려받아 `Y{suffix}` 1순위. 없으면 `y_patterns` fallback
- **VALUE 자동 선택 휴리스틱** — `|3σ/AVG|` 최댓값 (변동성 큰 PARA 우선)
- **X 변경 시 Y 자동 재선택**, **Y 변경 시 X 유지** — 비대칭. 사용자가 `X=X_1000`, `Y=Y_B` 같은 의도적 조합 가능

## 단일 입력 검증 (`core/input_validation`)

0.3.0 이후 메시지 출력 거의 없음 — 호환성을 위해 인터페이스 유지. 향후 추가 시 ReasonBar baseline 에 표시.

## 코드 참조

- 파서: [main.py](../../main.py) `parse_wafer_csv`, `_normalize`, `_drop_leading_empty_columns`, `_preclean`
- 자동 선택: [core/auto_select.py](../../core/auto_select.py)
- 단위 환산: [core/coords.py](../../core/coords.py) `normalize_to_mm`, `WAFER_RADIUS_MM`
- 검증: [core/input_validation.py](../../core/input_validation.py)

---

**마지막 업데이트**: 2026-04-30 (정책 카탈로그 분리)
