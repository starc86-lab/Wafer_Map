# 개발자 상수 카탈로그

settings.json 에 노출되지 않거나, 노출은 됐어도 Settings UI 에서 제외된 값들의 정리 카탈로그. **향후 사용자 노출 검토 시 참고용**.

작성: 2026-05-03 (F103 시점). 새 상수 추가 / 기존 상수 노출 변경 시 본 문서 동반 갱신.

---

## 1. 제품 / 알고리즘 invariant (변경 금지)

| 위치 | 상수 | 값 | 의미 |
|---|---|---|---|
| `core/coords.py` | `WAFER_RADIUS_MM` | `150.0` | 300mm wafer 반경 — 제품 invariant |
| `core/coords.py` | `MM_UPPER_BOUND` | `200.0` | 단위 자동 환산 — mm 판정 임계 |
| `core/coords.py` | `UM_UPPER_BOUND` | `200_000.0` | 단위 자동 환산 — μm 판정 임계 |
| `core/delta.py` | `DELTA_COORD_TOLERANCE_MM` | `1.0` | DELTA 좌표 매칭 tolerance |
| `core/coord_library.py` | `COORD_TOLERANCE_MM` | `5e-3` (5μm) | 좌표 중복 판정 tolerance |
| `core/coord_library.py` | `MIN_SHARED_TOKENS` | `3` | RECIPE similarity 최소 공통 토큰 |
| `core/coord_library.py` | `_EXACT_MATCH_BONUS` | `10_000` | RECIPE 매칭 점수 bonus |
| `widgets/wafer_cell.py` | `_NOTCH_ANGLE` | `3π/2` | wafer notch 6시 방향 |
| `widgets/wafer_cell.py` | `_NOTCH_HALF_RAD` | `3°` | notch V자 폭 ±3° |
| `widgets/wafer_cell.py` | `_NOTCH_DEFAULT_DEPTH_MM` | `5.0` | notch fallback (settings.notch_depth_mm 우선) |
| `main.py` | `REQUIRED_KEYS` | 5종 | 파싱 필수 컬럼 (waferid/lot_id/slot_id/parameter/recipe) |
| `main.py` | `OPTIONAL_KEYS` | (`max_data_id`,) | 파싱 선택 컬럼 |
| `main.py` | `DATA_COL_PATTERN` | regex | DATA 컬럼 인식 |

> 노출 검토 영역 아님. 변경 시 알고리즘 / 데이터 호환성 깨짐.

---

## 2. UI layout 상수 (시각 일관성용)

| 위치 | 상수 | 값 | 의미 |
|---|---|---|---|
| `widgets/paste_area.py` | `HEADER_BUTTON_WIDTH` | `88` | Text/Table/Clear 버튼 폭 |
| `widgets/paste_area.py` | `HEADER_BUTTON_SPACING` | `6` | 버튼 간 간격 |
| `widgets/paste_area.py` | `_UNDO_MAX` | `100` | cell edit undo stack 한도 |
| `widgets/settings_dialog.py` | `LABEL_WIDTH` | `140` | Settings 라벨 폭 |
| `widgets/settings_dialog.py` | `FIELD_WIDTH` | `135` | Settings 입력 위젯 폭 |
| `widgets/settings_dialog.py` | `FIELD_HEIGHT` | `30` | Settings 행 높이 |
| `widgets/settings_dialog.py` | `FONT_SCALE_CHOICES` | 0.85 / 1.0 / 1.15 | font_scale 콤보 옵션 |
| `widgets/wafer_cell.py` | `BOUNDARY_SEGMENTS` | `361` | 경계 원 polygon 세그먼트 수 |
| `widgets/wafer_cell.py` | `_ColorBar._BAR_W` | `17` | 컬러바 폭 |
| `widgets/wafer_cell.py` | `_ColorBar._BAR_RIGHT` | `5` | 컬러바 우측 margin |
| `widgets/wafer_cell.py` | `_ColorBar._LABEL_GAP` | `4` | 컬러바 라벨 간격 |
| `widgets/wafer_cell.py` | `_ColorBar._MARGIN_V` | `12` | 컬러바 상하 여유 |
| `widgets/wafer_cell.py` | `_ColorBar._N_STOPS` | `20` | gradient stop 수 |
| `widgets/wafer_cell.py` | `_ColorBar._N_TICKS` | `5` | 컬러바 라벨 수 |
| `widgets/wafer_cell.py` | `_ColorBar._MIN_WIDTH` | `60` | 컬러바 최소 폭 |
| `widgets/wafer_cell.py` | Copy Table `_CELL_PX` | `80` | PPT cell 폭 (px) |
| `widgets/wafer_cell.py` | Copy Table 폰트 | `11pt Arial` | PPT 표 글자 |
| `core/themes.py` | `FONT_SIZES` | 8 키 | body=14, section=15, caption=12, run_btn=19 등 |
| `core/themes.py` | `BASE_FONT_SIZES` | dict copy | font_scale 적용 기준값 (immutable) |
| `core/themes.py` | `UI_MODE_SCALE` | FHD=0.75, QHD=1.0, UHD=1.3 | 해상도 티어 배율 |
| `core/themes.py` | `UI_MODES` | `["auto", "FHD", "QHD", "UHD"]` | 콤보 옵션 |

> 변경 시 layout 깨짐 위험. 노출은 비추 — 디자인 영역.

---

## 3. Clipboard / Capture 동작

| 위치 | 상수 | 값 | 의미 |
|---|---|---|---|
| `widgets/wafer_cell.py` | `_safe_clipboard_set` retries | `2` | clipboard race 재시도 회수 |
| `widgets/wafer_cell.py` | `_safe_clipboard_set` delay_ms | `50` | 재시도 대기 시간 |
| `widgets/wafer_cell.py` | `_capture_gl_offscreen` MSAA | `4x` | FBO anti-alias |
| `widgets/wafer_cell.py` | `_capture_gl_offscreen` scale | `1` | FBO 해상도 배율 (2x 시 GLScatter pxMode 깨짐) |

---

## 4. settings.json 키지만 Settings UI 미노출 (개발자 고정값)

> CLAUDE.md "확정 기능 요구사항" 영역. 변경 시 협의 필요.

| 키 | 현재값 | 위치 | UI 상태 / 메모 |
|---|---|---|---|
| `chart_common.show_circle` | `True` | `core/themes.py` | UI 제거됨 — 항상 True |
| `chart_common.show_notch` | `True` | `core/themes.py` | UI 제거됨 — 항상 True |
| `chart_common.show_scale_bar` | `True` | `core/themes.py` | UI 제거됨 — 항상 True |
| `chart_common.notch_depth_mm` | `3.0` | `core/themes.py` | UI 제거됨 |
| `chart_common.boundary_r_mm` | `153.0` | `core/themes.py` | UI 제거됨 (150~160 권장) |
| `chart_common.radial_line_width_mm` | `45.0` | `core/themes.py` | UI 제거됨 (1D scan 감지 직사각형 폭) |
| `chart_3d` shading | `"shaded"` | `widgets/wafer_cell.py` 하드코딩 | normalColor / heightColor 콤보 제거됨 |
| `chart_3d` FOV | `45` | `widgets/wafer_cell.py` 하드코딩 | 카메라 시야각 |
| `chart_3d` x_stretch | `1.0` | `widgets/wafer_cell.py` 하드코딩 | x축 stretch (제거됨) |
| `chart_2d.label_font_scale` | `0.85` | `core/themes.py` | UI 미노출 — 측정점 라벨 폰트 배율 |
| `chart_2d.point_size` | `4` | `core/themes.py` | UI 미노출 (코드 확인 필요) |
| `chart_2d.show_value_labels` | `False` | `core/themes.py` | UI 미노출 (코드 확인 필요) |
| `auto_select.value_patterns` | `["T*"]` | `core/themes.py` | UI 미노출 — settings.json 직접 편집만 |
| `auto_select.x_patterns` | `["X", "X*"]` | `core/themes.py` | UI 미노출 |
| `auto_select.y_patterns` | `["Y", "Y*"]` | `core/themes.py` | UI 미노출 |
| `column_aliases` | `{}` | `core/themes.py` | UI 미노출 — 사용자 정의 alias |
| `coord_library_path` | `"coord_library.json"` | `core/themes.py` | UI 미노출 — 보통 변경 X |

---

## 5. 사용자 결정 영역 (실데이터 본 뒤 default 업데이트 예정)

> Settings UI 노출됨. 단 default 값이 임시 — 회사 실데이터 충분히 본 뒤 최적화.

| 키 | 현재값 | 메모 |
|---|---|---|
| `chart_common.radial_smoothing_factor` | `5.0` | 이전 10 → 5 (2026-04-23 사용자 피드백). 데이터마다 적정값 다름 |
| `chart_common.radial_method` default | `"Univariate Spline"` | 1D fitting 7종 중. 사용자 수동 스위치 전제 |
| `chart_common.radial_bin_size_mm` | `3` | Bin Average 전처리. 0=비활성 |
| `coord_library.max_count` | `5000` | 자동 정리 (2026-05-02 변경). 0=무제한 |
| `coord_library.max_days` | `0` (무제한) | 자동 정리 (2026-05-02 변경) |

---

## 6. RadialInterp 코드 default (Settings 우선, 직접 호출 시 fallback)

`core/interp.py::RadialInterp.__init__`:

| 인자 | 코드 default | Settings 키 | 우선 |
|---|---|---|---|
| `smoothing_factor` | `10.0` | `chart_common.radial_smoothing_factor` (5.0) | Settings |
| `savgol_window` | `11` | `chart_common.savgol_window` | Settings |
| `savgol_polyorder` | `3` | `chart_common.savgol_polyorder` | Settings |
| `lowess_frac` | `0.3` | `chart_common.lowess_frac` | Settings |
| `polyfit_degree` | `3` | `chart_common.polyfit_degree` | Settings |

> `make_interp` 팩토리는 settings 값을 명시 전달 → 정상 경로에선 코드 default 발동 안 함. 단위 테스트 / 직접 호출 시에만 fallback.

---

## 7. 노출 검토 후보 (자주 바꾸고 싶은데 settings.json 직접 편집 필요)

향후 사용자 요청 시 Settings UI 추가 검토:

| 항목 | 우선도 | 이유 |
|---|---|---|
| `auto_select.value_patterns` | 상 | 회사 PARAMETER 명명 다양화 시 유용 (T*, THK*, GOF 등) |
| `auto_select.x_patterns` / `y_patterns` | 상 | 좌표 PARAMETER 이름 변동 |
| `column_aliases` | 중 | 다른 계측 장비 헤더 매칭 |
| `chart_common.notch_depth_mm` | 하 | 시각적 디자인 영역 |
| `chart_common.boundary_r_mm` | 하 | 디자인 영역 |
| `chart_2d.label_font_scale` | 하 | 디자인 영역 |
| Copy Table cell 폭 (`_CELL_PX`) | 하 | 슬라이드 폭 customize 시 |
| Copy Table 폰트 크기 | 하 | 사용자 PPT 톤에 따라 |

---

## 8. 제거 / 정리 후보 (의도적 고정인데 코드만 차지)

| 키 | 현재 | 이유 |
|---|---|---|
| `chart_common.show_circle` | True 고정 | 키 자체 제거 가능 — 항상 True |
| `chart_common.show_notch` | True 고정 | 동일 |
| `chart_common.show_scale_bar` | True 고정 | 동일 |

> 제거 시 `core/themes.py::DEFAULT_SETTINGS` + `widgets/wafer_cell.py` 의 사용처 함께 정리.

---

## 9. 노출 가이드라인 (새 항목 노출 시 참고)

**노출 가능**:
- 사용자 워크플로 변경 영향 (예: auto_select pattern, recipe alias)
- 시각 디자인 (단 layout 안 깨지는 범위)
- 정책 default (실데이터 본 뒤 변경 가능 영역)

**노출 비추**:
- 알고리즘 invariant (RBF kernel 선택은 Settings 노출됨, 단 그 안의 epsilon 등은 노출 X)
- 제품 정합성 영향 (WAFER_RADIUS_MM, 컬럼 alias REQUIRED_KEYS)
- 시각 layout 의 정밀 좌표 (`_BAR_W` 등 — 잘못 변경 시 column 어긋남)

**노출 시 추가 작업**:
1. Settings UI 카드 추가 (settings_dialog.py)
2. `DEFAULT_SETTINGS` 등록
3. CLAUDE.md 정책 카탈로그 갱신 (필요 시)
4. 본 문서 (`docs/developer_constants.md`) 갱신 — 노출 후 본 카탈로그에서 제거
