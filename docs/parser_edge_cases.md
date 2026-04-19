# 파서 Edge Case 정리

`main.py::parse_wafer_csv()` 와 관련 함수(`_normalize`, `_mode_str`, DATA 수집 등)의 실제 동작을 기준으로, 일반 사용자가 **Excel / 계측 장비에서 Ctrl+V 페이스트** 시 마주칠 가능성 높은 엣지 케이스 정리.

상태 표기:
- ✅ **OK**: 파싱 정상, 사용자 의도대로 동작
- ⚠️ **Silent Error**: 파싱은 되나 결과가 사용자 의도와 다름, 경고 없음 (가장 위험)
- ⚠️ **Warning**: 파싱되지만 경고 메시지 표시
- ❌ **Hard Fail**: `MissingColumnsError` 등 예외 → 컬럼 매핑 다이얼로그 폴백

---

## 1. 헤더(컬럼명) 관련

### 1.1 컬럼 순서 뒤섞임
- **현재**: 정규화 기반 매칭이라 순서 무관
- **결과**: ✅ OK

### 1.2 이름 변형 (LOT ID / Lot_ID / lotid)
- **현재**: `_normalize()` 가 `re.sub(r"[\s_]+", "", name).lower()` 로 공백·언더바·대소문자 무관화
- **결과**:
  - ✅ OK — `LOT ID` / `Lot_ID` / `lotid` / `LOT_ID` 모두 매칭
  - ❌ Hard Fail — **하이픈 포함 시 미매칭** (`Lot-ID` → `lot-id` 는 `lotid` 와 다름)
- **위험도**: 🟡 Medium (외부 제공 CSV 중 대시 쓰는 경우 드묾)
- **권장**: `_normalize` 패턴을 `r"[\s_\-]+"` 로 확장 (대시도 제거)

### 1.3 빈 컬럼 (`,,` 연속)
- **현재**: pandas 가 `Unnamed: N` 으로 자동 명명 → 정규화 미매칭 → 무시
- **결과**: ✅ OK (조용히 무시)

### 1.4 중복 컬럼명 (같은 이름 2개)
- **현재**: `norm_to_orig` 딕셔너리가 **마지막 것만 저장** → 첫 번째 데이터 손실
- **결과**: ⚠️ Silent Error
- **위험도**: 🔴 High (Excel 에서 실수로 복사 확장 시 흔함)
- **권장**: 파싱 전 중복 헤더 감지 → 경고

### 1.5 필수 컬럼 누락
- **현재**: `MissingColumnsError` 발생 → GUI 에서 컬럼 매핑 다이얼로그 팝업
- **결과**: ❌ Hard Fail + fallback UX
- **위험도**: 🟢 Low (사용자가 인지 가능)

### 1.6 MAX_DATA_ID 없음
- **현재**: 선택 컬럼이라 skip. 실제 DATA 셀 수로 대체
- **결과**: ✅ OK

---

## 2. 값(데이터) 관련

### 2.1 숫자 앞뒤 공백
- **현재**: pandas 가 자동 strip
- **결과**: ✅ OK

### 2.2 숫자 내부 공백 (예: `"1 234"`)
- **현재**: `pd.to_numeric(errors='coerce')` → NaN
- **결과**: ⚠️ Silent Error — 경고 없이 NaN
- **위험도**: 🟡 Medium

### 2.3 천단위 쉼표 (`"1,234.56"`)
- **현재**: `to_numeric` 이 쉼표 인식 못 함 → NaN
- **결과**: ⚠️ Silent Error
- **위험도**: 🔴 High (Excel 기본 숫자 포맷에 의도치 않게 포함될 수 있음)
- **권장**: paste 단계에서 `"(\d),(\d)"` → `$1$2` 치환 옵션

### 2.4 과학 표기법 (`1.23e-5`)
- **현재**: `to_numeric` 자동 인식
- **결과**: ✅ OK

### 2.5 NaN / Null / 빈 셀
- **현재**: 대부분 NaN 으로 변환. 행 말미 NaN 은 자르기, 중간 NaN 은 보존
- **결과**: ✅ OK (의도한 동작)

### 2.6 극단값 / 음수 / 0
- **현재**: 특별 처리 없음
- **결과**: ✅ OK (시각화 단계에서 colormap/Z-Scale 이 알아서 처리)

### 2.7 따옴표로 감싼 숫자 (`"123.45"`)
- **현재**: `pd.read_csv(quoting=QUOTE_MINIMAL)` 기본 동작으로 제거됨 (Excel CSV 표준)
- **결과**: ✅ OK
- **단서**: `quoting` 옵션이 기본값이 아니면 실패 가능 — 현재 코드는 기본값 사용

---

## 3. 구조 관련

### 3.1 빈 행
- **현재**: WAFERID 가 NaN → `"nan"` 그룹 생성 → PARAMETER 체크로 skip
- **결과**: ✅ OK (조용히 무시)

### 3.2 행마다 DATA 개수 다름
- **현재**: 각 행의 말미 NaN 을 자름 → `WaferRecord.n` 이 행마다 다를 수 있음
- **결과**: ✅ OK (의도한 동작 — `T1` 은 49 개, `GOF` 는 4 개 같은 패턴 지원)

### 3.3 MAX_DATA_ID ≠ 실제 개수
- **현재**: 경고 추가 후 **실제 개수 사용** (`ParseResult.warnings`)
- **결과**: ⚠️ Warning
- **위험도**: 🟢 Low (경고로 알림)

### 3.4 DATA 컬럼 0 개
- **현재**: `MissingColumnsError`
- **결과**: ❌ Hard Fail

### 3.5 트레일링 빈 컬럼 (`...,DATA20,,,`)
- **현재**: pandas 가 Unnamed 로 처리 후 정규화 미매칭 → 무시
- **결과**: ✅ OK

---

## 4. 붙여넣기 노이즈

### 4.1 헤더 중복 (한 복사본에 헤더 행 2개 이상)
- **현재**: `pd.read_csv` 는 첫 행만 헤더로 인식. 두 번째 헤더는 데이터 행으로 취급 → `to_numeric` 에서 NaN
- **결과**: ⚠️ Silent Error — 중복 헤더 행의 DATA 손실
- **위험도**: 🔴 High (여러 웨이퍼 분할 복사 시 흔함)
- **권장**: 첫 50 행에서 헤더 재등장 감지 → 해당 행 자동 스킵

### 4.2 상단 메타 텍스트 (제목, 조회 조건 등)
- **현재**: 첫 행을 헤더로 취급 → 컬럼 대부분 매칭 실패 → `MissingColumnsError`
- **결과**: ❌ Hard Fail
- **위험도**: 🟡 Medium
- **권장**: paste 텍스트에서 `"WAFERID"` 가 포함된 행을 찾아 그 위를 제거하는 전처리

### 4.3 하단 꼬리글 (footer, 통계 요약)
- **현재**: 데이터 행 뒤 non-numeric 행은 `to_numeric` 에서 NaN → DATA 없음 → 그 웨이퍼 파라미터는 누락
- **결과**: ⚠️ Silent Error 또는 Warning

### 4.4 탭/쉼표 혼재
- **현재**: `pd.read_csv` 는 **첫 줄 separator 만** 자동 감지 → 혼재 시 일부 행 파싱 실패
- **결과**: ⚠️ Partial Fail
- **위험도**: 🔴 High (Excel 과 일반 텍스트 편집기 혼용 시 발생)
- **권장**: paste 전 `\t` / `,` 자동 감지 + 균일화

---

## 5. 인코딩 / 특수 문자

### 5.1 UTF-8 BOM (`\ufeff`)
- **현재**: pandas `read_csv` 는 `utf-8-sig` 엔진이 기본이라 BOM 자동 제거. 클립보드 페이스트 경로는 QClipboard 가 UTF-16 반환이라 BOM 없음
- **결과**: ✅ OK

### 5.2 한글 PARAMETER (`"두께"`, `"막두께"`)
- **현재**: PARAMETER 이름은 자유 문자열이라 그대로 보존
- **결과**: ✅ OK
- **단서**: `auto_select.py` 의 VALUE/X/Y 패턴 매칭(`"T*"`, `"X"`, `"Y"`)과 안 맞으므로 수동 선택 필요

### 5.3 Non-breaking space / zero-width (Word 복사)
- **현재**: 파서 단계에서 `_normalize` 에만 적용, 데이터 값은 그대로 → NaN 유발
- **결과**: ⚠️ Silent Error
- **위험도**: 🟡 Medium

### 5.4 유니코드 minus (`−`, U+2212)
- **현재**: `to_numeric` 이 ASCII `-` 만 숫자로 인식 → NaN
- **결과**: ⚠️ Silent Error
- **위험도**: 🟡 Medium (PDF / Word 복사 시 흔함)
- **권장**: paste 전 `\u2212` → `-` 치환

---

## 6. 좌표 특수 케이스

### 6.1 mm / μm 혼재
- **현재**: 파서는 수치 그대로 보존. 시각화 단계 `normalize_to_mm` 이 `|max|` 기준 휴리스틱 환산 (200~200000 → `/1000`)
- **결과**: ✅ OK (대부분 케이스), ⚠️ 경계 케이스에서 오판 가능
- **위험도**: 🟢 Low

### 6.2 `X` / `X_1000` 동시 존재
- **현재**: 서로 다른 PARAMETER 로 저장. 자동 선택은 `X` 우선
- **결과**: ✅ OK. 사용자가 수동으로 `X_1000` 선택 가능

### 6.3 X 만 있고 Y 누락
- **현재**: X 만 저장됨
- **결과**: ✅ 파싱 OK + ❌ 시각화에서 좌표 부재 → RECIPE 자동 조회로 fallback

---

## 7. WAFERID 변형

### 7.1 앞뒤 공백 (`" RK2A007.01"`)
- **현재**: `str(wid)` 그대로 저장 → `" RK2A007.01"` ≠ `"RK2A007.01"`
- **결과**: ⚠️ Silent Error — 같은 웨이퍼가 두 그룹으로 분산
- **위험도**: 🔴 High (Excel 셀 포맷 문제로 흔함)
- **권장**: `wid = str(wid).strip()` 추가 (main.py 의 group by 직전)

### 7.2 서로 다른 표기 형식 (`RK2A007.07` vs `RK2A007_07` vs `RK2A007.7`)
- **현재**: 문자열 그대로 비교 → 각각 별개 그룹
- **결과**: ⚠️ Silent Error (의도적으로 보존할 수도, 실수일 수도 있음)
- **위험도**: 🟡 Medium

### 7.3 숫자형 WAFERID (`1`, `2`, ...)
- **현재**: `str(wid)` 로 문자열화 → `"1"`, `"2"` 등
- **결과**: ✅ OK

---

## 8. DELTA 매칭 관련

### 8.1 교집합 WAFERID 0 개
- **현재**: `compute_delta` 가 `matched == 0` 감지 → `main_window::_visualize_delta` 에서 `QMessageBox.warning` + 결과 클리어
- **결과**: ⚠️ Warning (사용자에게 명시적 안내)
- **위험도**: 🟢 Low

### 8.2 양측 RECIPE 다름
- **현재**: 각 입력 내에서 최빈값 RECIPE 채택. 두 입력의 RECIPE 일치 여부는 검증 안 함
- **결과**: ⚠️ Silent Error (Pre / Post 서로 다른 레시피여도 DELTA 계산됨)
- **위험도**: 🟡 Medium (사용자가 의도적으로 할 수도 있음)
- **권장**: RECIPE 불일치 시 안내 배너 (차단 말고 알림만)

### 8.3 좌표는 일치하나 WAFERID 다름
- **현재**: WAFERID 교집합이 키. 좌표 같아도 WAFERID 다르면 매칭 안 됨
- **결과**: ⚠️ WAFERID 0 개 → 위 8.1 경고
- **위험도**: 🟢 Low (의도된 동작)

### 8.4 같은 WAFERID 에서 좌표 집합이 다름
- **현재**: `compute_delta` 가 tolerance 1μm 로 좌표 매칭 → 일치점만 사용
- **결과**: ✅ OK (부분 매칭 지원)

---

## 9. 헬퍼 함수의 숨은 한계

### 9.1 `_normalize()` — 대시 미처리
```python
def _normalize(name: str) -> str:
    return re.sub(r"[\s_]+", "", str(name)).lower()
```
→ `"Lot-ID"` → `"lot-id"` → alias `"lotid"` 와 불일치.
**권장**: `r"[\s_\-]+"` 로 확장.

### 9.2 `_mode_str()` — 동률 처리
```python
Counter(vals).most_common(1)[0][0]
```
- 빈도 동률 시 순서 보장 없음 (파이썬 3.7+ dict 순서는 insertion order 지만 실제로는 첫 출현 유지)
- **위험도**: 🟡 Medium (사용자 혼란 가능)
- **권장**: tie-break 규칙 명시 (예: 첫 등장 우선)

---

## 10. 우선순위 요약

| 엣지 케이스 | 위험도 | 개선 난이도 | 권장 버전 |
|---|---|---|---|
| **WAFERID 앞뒤 공백** (7.1) | 🔴 High | 쉬움 (1 줄) | 0.1.1 patch |
| **천단위 쉼표 숫자** (2.3) | 🔴 High | 중간 | 0.2.0 |
| **탭/쉼표 혼재** (4.4) | 🔴 High | 중간 | 0.2.0 |
| **헤더 중복** (4.1) | 🔴 High | 쉬움 | 0.1.1 patch |
| **중복 컬럼명** (1.4) | 🔴 High | 쉬움 | 0.1.1 patch |
| **NBSP / 유니코드 minus** (5.3, 5.4) | 🟡 Medium | 쉬움 | 0.1.1 patch |
| **WAFERID 형식 다름** (7.2) | 🟡 Medium | 어려움 (판단 모호) | 검토 |
| **대시 헤더** (1.2) | 🟡 Medium | 쉬움 (정규식 1 줄) | 0.1.1 patch |
| **상단 메타 텍스트** (4.2) | 🟡 Medium | 중간 | 0.2.0 |
| **RECIPE 불일치 DELTA** (8.2) | 🟡 Medium | 쉬움 (안내만) | 0.1.1 patch |

---

## 11. 0.1.1 패치에서 제안하는 최소 변경 (합계 ~10줄)

1. `main.py::_normalize` — 정규식에 대시 포함: `r"[\s_\-]+"`
2. `main.py` group by 직전 — `wid = str(wid).strip()` 추가
3. `main.py::parse_wafer_csv` 시작 부분 — text 전처리 헬퍼 추가:
   ```python
   def _preclean(text: str) -> str:
       text = text.replace("\u2212", "-")   # unicode minus → ASCII
       text = text.replace("\u00a0", " ")   # NBSP → space
       text = text.replace("\ufeff", "")    # BOM
       return text
   ```
4. 중복 컬럼 감지 시 `ParseResult.warnings` 추가
5. DELTA 시 A/B RECIPE 불일치면 summary_line 에 경고 문구 포함

천단위 쉼표 / 헤더 중복 / 탭·쉼표 혼재는 UX 영향 크므로 `0.2.0` 에서 paste 단계 전처리기로 통합 대응 권장.

---

## 참고

- 각 케이스는 `main.py` 및 `core/delta.py` 실제 코드 기준으로 검증.
- 현장 CSV 예시: `samples/cases/case10_delta_A_preEtch_6wafers.csv`.
- 테스트 확장: `tests/test_parser_edge_cases.py` 작성 권장 (각 케이스를 assertion 으로 고정).
