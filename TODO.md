# TODO — Wafer Map 후속 작업

이 문서는 v0.1.0 배포 후 남아있는 기술 부채와 미해결 이슈를 정리한다. 큰 항목부터 작은 항목 순.

---

## 1. ~~3D Copy Graph 품질 이슈~~ ✅ 0.2.0 해결

**0.2.0 에서 시나리오 A (직접 FBO 관리) 로 해결**. `wafer_cell._capture_gl_offscreen` 참고.

- ✅ jaggies: FBO format `setSamples(4)` 로 MSAA 4x 강제 (화면 `samples()=0` 환경 무관)
- ✅ Settings 창 포함: FBO 는 화면 독립 → `SettingsDialog(parent=self)` 원복
- ✅ floor/boundary 누락: `gl_view.paint(region, viewport)` 직접 호출로 `drawItemTree()` 그대로 실행
- ✅ 스크롤/창 가림 (P1): widget 표시 상태 무관하게 paintGL 호출 가능
- ✅ GLTextItem 누락: FBO 후처리로 `compute_projection + align_text` 재현 + widget font family 전파
- ✅ 측정점 / 라벨 크기: `scale=1` 전제로 pxMode size 유지

아래 원본 분석은 향후 동일 이슈 재발 시 참고용으로 보존.

## 1-archive. (원본) 3D Copy Graph 품질 이슈

### 1.1 현상 두 가지

**A. Jaggies (계단 모양)**
- 3D surface edge, GLLinePlotItem 경계 원, 바닥 사각형 grid 에서 대각선이 계단식으로 표시됨.
- 화면에서는 선명하다가 Copy Graph → PPT paste 시 확대해 보면 특히 두드러짐.

**B. 프로그램 ↔ paste 이미지 색/구성 불일치**
- 프로그램에서 보이는 3D 렌더와 paste 결과가 다름.
- 변주:
  - **테마 색 leak**: 다크 테마일 때 3D widget 코너(투명 영역)에 테마 배경이 비쳐 검은 삼각형으로 표시됨.
  - **floor / boundary 누락**: supersample·offscreen 방식 시도 시 grid·boundary line 이 렌더 누락됨.
  - **조명/normal 이상**: 특정 shading 경로에서 색감 차이.

---

### 1.2 근본 원인 분석

**OpenGL 렌더링 특성**
- pyqtgraph `GLViewWidget` 은 `QOpenGLWidget` 기반. 화면 표시용 framebuffer 에 렌더.
- Anti-Aliasing 은 두 레이어:
  1. **MSAA (Multi-Sample Anti-Aliasing)**: 하드웨어 레벨 — `QSurfaceFormat.setSamples(4)` 로 요청. 드라이버/GPU 의존. 적용되면 line·edge 모두 smooth.
  2. **`GL_LINE_SMOOTH`**: 구형 OpenGL fixed-pipeline 기능. 최근 드라이버에선 deprecated 되어 무시되는 경우 많음. pyqtgraph `GLLinePlotItem(antialias=True)` 가 이걸 쓰려고 시도.
- Windows + Intel/AMD 내장 GPU 조합에서 MSAA 가 무시되는 사례 다수 보고됨.

**grabFramebuffer의 한계**
- `QOpenGLWidget.grabFramebuffer()` 는 widget 자체 FBO 의 resolve 된 이미지를 반환.
- 알파 채널이 `Format_RGBA8888_Premultiplied` 형식이라 투명 픽셀이 검정으로 나타날 수 있음.
- pyqtgraph `setBackgroundColor("w")` 는 clear alpha=1 로 하지만, 중간 draw 과정에서 alpha 채널을 훼손하는 경우가 있음 (특히 alpha-blended grid 렌더 후).

**Qt의 QWidget.grab() vs GL 특성**
- 일반 widget 은 `grab()` 으로 바로 이미지화 가능.
- `QOpenGLWidget` 자식이 있으면 부모의 `grab()` 은 GL 영역을 검게 남김. 별도로 `grabFramebuffer` 합성해야.

**pyqtgraph `renderToArray` 한계**
- 내부적으로 FBO 를 타일 단위로 순회하며 렌더 (대용량 이미지 출력용).
- GLLinePlotItem / GLGridItem 일부가 특정 타일 경계에서 잘리거나 아예 누락되는 버그 있음.

**화면 캡처의 한계 (현재 v0.1.0 방식)**
- `QScreen.grabWindow(0)` + crop — WYSIWYG 보장.
- 단점:
  - widget 이 화면에 실제로 보여야 하고, 다른 창이 위에 있으면 그 내용이 찍힘.
  - 이 한계 때문에 SettingsDialog 를 `parent=None` + `Qt.Window` 플래그로 우회 처리 (tech debt).

---

### 1.3 실패한 접근들 (반복 금지)

| # | 시도 | 결과 | 실패 이유 |
|---|---|---|---|
| 1 | `QSurfaceFormat.setDefaultFormat(samples=4)` at app start | 적용 안 됨 | pyqtgraph 의 ShareWidget / 드라이버 조합에서 무시 |
| 2 | `_LockedGLView.setFormat(samples=4)` per widget | 적용 안 됨 | ShareWidget 이 먼저 생성되어 format 전파 안 됨 |
| 3 | 위젯 temp resize(2x) → grabFramebuffer → 다운스케일 | 일부 item 누락 + 색 이상 | resize 중 grid/boundary 재렌더 타이밍 문제, alpha 채널 이상 |
| 4 | `chart.renderToArray((w*2, h*2))` | floor/boundary 완전 누락 | 타일 기반 렌더 버그 |
| 5 | `grabFramebuffer` + `convertToFormat(RGB32)` | 투명 영역 검정 | premultiplied 알파를 drop alpha 로 처리 → 검정 고정 |
| 6 | `convertToFormat(ARGB32)` + fillRect(white) | 전체 투명으로 보임 | grid/boundary 의 alpha 가 정상 write 되지 않아 바닥 전체 알파 0 |

**교훈**: GL framebuffer 기반 접근은 pyqtgraph 의 alpha blending 동작과 맞물려 계속 함정. 현재 v0.1.0 은 **화면 캡처 방식**으로 회피.

---

### 1.4 제안 해결 방향 (시나리오별)

#### 시나리오 A — 직접 FBO 관리 (추천, 장기)

**접근**: `QOpenGLFramebufferObject` 를 2x 크기로 직접 만들어 pyqtgraph 의 paintGL 을 binding 된 상태에서 호출 → resolve → QImage 변환 → 다운스케일.

```python
# 개략 pseudocode
from PySide6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat

def capture_3d_hires(gl_view, scale=2):
    gl_view.makeCurrent()
    fmt = QOpenGLFramebufferObjectFormat()
    fmt.setSamples(4)  # MSAA
    fmt.setAttachment(QOpenGLFramebufferObject.Attachment.CombinedDepthStencil)
    size = gl_view.size() * scale
    fbo = QOpenGLFramebufferObject(size, fmt)
    fbo.bind()
    # viewport 조정
    gl.glViewport(0, 0, size.width(), size.height())
    # pyqtgraph 의 paintGL 로직을 여기서 직접 호출
    gl_view.paintGL()
    fbo.release()
    qimg = fbo.toImage()  # MSAA resolve 포함
    gl_view.doneCurrent()
    return qimg.scaled(..., SmoothTransformation)
```

**장점**
- 화면 상태와 완전 독립 → Settings 창이 위에 있어도 OK
- MSAA 4x 강제 적용 (FBO format 에서 보장)
- resolution 자유 (2x, 4x 원하는 대로)
- 모든 GL item (surface/boundary/grid) 정상 렌더

**단점**
- pyqtgraph 의 `paintGL` 은 viewport/projection 설정에 widget.size() 의존 → 직접 호출 시 viewport를 FBO 사이즈로 오버라이드 필요
- pyqtgraph 내부 코드 의존성 (버전에 따라 paintGL 시그니처 변할 수 있음)
- 약 30-80ms 추가 비용 예상

**검증 필요 사항**
- pyqtgraph 0.13.x / 0.14.x 에서 `paintGL` 호출 시 `opts` 의 `viewport` 를 임시 override 가능한지
- MSAA FBO 의 resolve 자동 처리 되는지 (`toImage()` 가 multi-sample 를 single-sample 로 blit)

#### 시나리오 B — pyqtgraph 의 `QOpenGLContext` 에 hook

**접근**: `GLViewWidget.paintGL` 내부에서 GL 명령 실행 전에 FBO 를 binding 하도록 monkey-patch. 렌더 후 resolve.

```python
orig_paintGL = gl_view.paintGL

def patched():
    if self._capture_target_fbo:
        self._capture_target_fbo.bind()
    orig_paintGL()
    if self._capture_target_fbo:
        self._capture_target_fbo.release()

gl_view.paintGL = patched
```

**장점**: pyqtgraph 내부 동작 그대로 활용, paintGL 호출 타이밍·상태 동일.

**단점**: monkey-patch → pyqtgraph 내부 구조 변경에 취약.

#### 시나리오 C — Windows WM_PRINT 메시지 활용

**접근**: Windows 네이티브 `WM_PRINT` 메시지로 창 내용을 비트맵으로 받아옴. 가려져 있어도 작동하는 경우 있음 (DWM composition 상태에 따라 다름).

**장점**: 플랫폼 네이티브, 안정적.

**단점**: Windows-only, DWM 에 의존. 한국 사내 환경에서만 테스트 가능.

#### 시나리오 D — matplotlib 3D 로 별도 렌더

**접근**: Copy Graph 시 **별도로** matplotlib Axes3D 로 같은 데이터를 다시 렌더 → 이미지 반환.

**장점**: 완전히 독립된 렌더 파이프라인, 품질 최고 (벡터 포함 가능).

**단점**
- Copy 1회당 수백 ms 추가 (matplotlib 렌더 무거움)
- 시각적으로 pyqtgraph 결과와 미묘하게 다를 수 있음 — "WYSIWYG" 깨짐
- 이미 배포에서 matplotlib 13MB 만큼 용량 증가

#### 시나리오 E — 화면 캡처 유지 + Settings 독립성 개선 (현 상태)

**접근**: 현재 v0.1.0 방식 유지하되, Settings 창 외에도 **가려질 가능성 있는 모든 창**을 독립 윈도우로.

**장점**: 최소 변경, 동작 보증.

**단점**: 근본 해결 아님. 윈도우 해상도·배율에 따라 품질 제한.

---

### 1.5 권장 경로

**단기** (v0.2.0): 시나리오 A (직접 FBO) 검증 후 적용. 실패 시 시나리오 E 유지.

**검증 플랜**
1. Qt OpenGL 예제로 `QOpenGLFramebufferObject` + MSAA + pyqtgraph 호출 가능한지 최소 PoC
2. PoC 성공 시 `WaferCell._copy_graph` 경로에 통합
3. 테마 leak / floor 누락 / jaggies 모두 해결되면 `SettingsDialog(parent=self)` 로 **원복** (tech debt 소거)

**긴급 patch 필요 시**: 시나리오 B (monkey-patch) — pyqtgraph 버전 고정하고 사용.

---

## 1b. 3D 경계 카디널 스트라이프 / 톱니 아티팩트

### 현상
3D MAP 렌더 시 웨이퍼 경계(r=150) 근처에서 두 종류 아티팩트:
- **카디널 스트라이프**: 동/서/남/북 4 방향 측벽이 격자축과 정렬되어 **수직 계단 줄무늬**처럼 보임. 45° 대각 방향은 부드러움.
- **상면 테두리 톱니**: mask 경계(`r<=R`)가 격자 이산화라 상면 윤곽선이 지그재그로 끊김.

두 가지 모두 원본 v0.1.0 이후로 존재. 2026-04-20 확인.

### 시도한 접근과 실패 이유

| # | 시도 | 결과 |
|---|---|---|
| 1 | `GRID_MARGIN_MM=5` (격자를 R+5 까지 확장) | 카디널 스트라이프 그대로. 오히려 surface mesh 가 R 밖으로 삐져나와 smooth wall 방법에서 악영향 |
| 2 | 격자 해상도 G=100 → G=500 | 스트라이프 폭만 좁아질 뿐 존재. 근본 해결 아님. G=500 은 렌더 비용 증가 |
| 3 | `_build_cut_wall_mesh` 로 r=R 원통 wall 추가 (180 segments) | wall top 위치 부정확(probe 위치 r=R-1.5dx 에서 dome 중심 쪽 값 가져옴 → rim 효과). 격자 wall 의 바깥쪽이 smooth wall 뚫고 나와 톱니 재발 |
| 4 | `z=0 drop` 제거 (exterior RBF 외삽 유지) + `glOptions="translucent"` | 카디널 스트라이프 사라지지만 **측벽 자체 소실** → 웨이퍼가 공중에 떠 보임. translucent 는 depth ordering 이슈로 뒷면 비침/어두움 (특히 낮은 카메라 각도) |

### 미시도 / 검토 가능한 방향

- **smooth wall 재시도**: `GRID_MARGIN_MM=0` (grid 가 정확히 ±R) + wall 을 r=R+0.5mm (격자 밖) + wall top probe 를 r=R-dx (boundary 에 가장 가까운 interior) 로. z-fighting 피하면서 wall 이 격자 jagged wall 을 앞에서 덮음.
- **radial (polar) 격자**: 현재 rect 격자 대신 `(r, θ)` 격자로 mesh 구성. 경계가 정확히 원. 구현량 큼 — `GLSurfacePlotItem` 은 rect 전용이라 `GLMeshItem` 수동 구성 필요.
- **top 경계 alpha soft fade**: r>R-1mm 부터 r=R 까지 alpha 선형 감소 + translucent. 톱니 완화. 단 translucent 의 depth 이슈 남음.
- **surface mesh 를 inscribed-square (r=R/√2) 까지만** 렌더 + 외곽 고리를 원통/콘 mesh 로. 복잡.

### 현재 상태
옵션 1 (GRID_MARGIN_MM=5) 만 코드에 남음. 카디널 스트라이프 visible. 사용자는 인지 상태.

### 우선순위
중간. 첫 사용 가능 배포(v0.1.0)에 포함됐고 기능 동작엔 지장 없음. 품질 개선 과제.

### 참고
- 디버그 스크립트: [debug/debug_cardinal_wall.py](debug/debug_cardinal_wall.py), [debug/debug_verify_real.py](debug/debug_verify_real.py) — 여러 옵션 비교 PNG 생성
- 결과 PNG: `debug/cardinal/*.png`, `debug/verify/*.png`

---

## 2. 용량 최적화 (125MB → 목표 70-80MB)

### 현재 구성 (dist/Wafer Map/ — 271MB, zipped 125MB)
| 모듈 | 크기 | 필수 여부 |
|---|---|---|
| PySide6 (Qt) | 104MB | 필수 — 일부 plugin 제외 가능 |
| scipy | 50MB | RBF 만 씀 — 대부분 submodule 불필요 |
| matplotlib | 13MB | **완전 불필요** — transitively 포함 |
| pandas | 14MB | CSV 파싱용 — 필수 |
| numpy | 5.9MB | 필수 |
| OpenGL | 1.8MB | 필수 |
| pyqtgraph | 1.6MB | 필수 |

### 작업 항목
- [ ] `--exclude-module matplotlib` 추가 → -13MB
- [ ] scipy submodule 정리 (`signal`, `stats`, `sparse`, `optimize` 등 제외) → -20~30MB
- [ ] PySide6 Qt plugins 정리 (WebEngine, Multimedia 등) → -20MB
- [ ] UPX 압축 시도 (실패 시 삭제) → -20~30%
- [ ] PyInstaller spec 파일 작성 (명령어 길어지므로)

목표: zipped 70-80MB, unpacked <150MB.

---

## 3. 3D MSAA 작동 확인

현재 `app.py::setDefaultFormat(samples=4)` + `_LockedGLView.setFormat(samples=4)` 로 설정해도 일부 환경에서 적용 안 됨. 진단 필요:

- [ ] Windows + Intel UHD/Iris / AMD Vega / NVIDIA GeForce 각 환경 실제 `format().samples()` 값 확인
- [ ] 안 먹히면 pyqtgraph ShareWidget 을 먼저 setFormat 한 뒤 생성하는 방법 검토
- [ ] 드라이버 레벨 강제 (NVIDIA Control Panel 의 AA Override) 로 차이 있는지 확인

---

## 4. 기타 수집된 아이디어

### 4.1 보간 품질
- [ ] Kriging 보간 추가 검토 (v0.1.0 에서 보류). 속도 vs 품질 절충이 RBF 보다 나은지.
- [ ] **1D 데이터 Radial Symmetric 변환** — Y 값 변동이 threshold(~2mm) 이하면
  1D 라인 스캔으로 판정 → `|X|` 를 반경 r 로 취급 → 같은 r 값 평균 → `scipy.interp1d`
  로 v(r) 구한 뒤 웨이퍼 격자 각 점 `R=√(X²+Y²)` 에 매핑.
  - 장점: Center/Edge/Mid High 같은 전형적인 반도체 profile 시각화 자연스러움.
    RBF 대비 빠르고 extrapolation 문제 없음.
  - 단점: 실제 비대칭 profile 이면 거짓 대칭 표시. 양측 X 값 차이 큰 경우 평균으로
    정보 손실.
  - UX: 자동 감지 후 적용 + 타이틀에 `(Radial)` 뱃지. Settings 에서 on/off 토글.
  - 구현량: interp.py 에 `interpolate_radial` 함수 추가(~50줄) + wafer_cell 감지 분기.

### 4.2 UX
- [ ] VALUE 변경 시 즉시 재-Run — 다중 VALUE 스위칭 캐싱 (메모리 부담 100-250MB 수준, 현재 미적용)
- [ ] Shift+좌클릭 카메라 sync 의 "rotate 중 sync" 뿐 아니라 "pan/zoom sync" 확인 (이미 `center` 복사해서 될 듯하나 체감 테스트 필요)
- [ ] 2D MAP 회전 (notch 방향 돌리기) — 보류됨. 필요시 재검토
- [ ] **Run Analysis 버튼 always-enabled 로 전환** — 현재 `setEnabled(any_input and bool(available_ns))` 로 조건부 disable. 그런데 `class="primary"` 녹색 스타일은 disabled 여도 회색으로 안 변해서 사용자가 enabled 로 착각 → 클릭 안 되는 버그처럼 느낌 (2026-04-21 사례). 방향:
  1. `btn_visualize.setEnabled(True)` 고정
  2. `_on_visualize` 시작부에서 전제조건 검사 실패 시 `QMessageBox.warning` + early return
  3. 경고 메시지는 구체적 이유 명시 (입력 없음 / VALUE 미선택 / 좌표 미선택 등)

### 4.3 Copy Image 개선
- [ ] 우클릭 메뉴에 "Copy Image (HiRes)" 옵션 추가 — 화면 캡처 대신 2x/3x 렌더 옵션 (시나리오 A 구현 후)

### 4.4 좌표 프리셋
- [ ] 이름 수동 편집 시 자동 생성 suffix `(2)` 충돌 처리
- [ ] 라이브러리 탭에서 좌표 시각화 프리뷰 (선택된 프리셋의 X/Y 산점도)

---

## 4.5 자동 선택 로직

- [ ] **R1: `X_*` / `Y_*` 시작 비좌표 이름 VALUE 콤보에서 제거되는 문제**
  - 예: `X_측정위치`, `X_window_size`, `Y_offset_cal` 등 — `_is_coord_name` 정규식
    `^[xyXY](_.*)?$` 에 매치되어 VALUE 후보에서 완전 제외됨
  - 사용자가 의도적으로 이런 이름을 측정값으로 썼을 때 접근 불가
  - 완화안:
    - 정규식 좁히기 — `^[xyXY]$ | ^[XY]_[0-9]` (숫자/기본 suffix 만)
    - 또는 값 분포 기반 판정 — 실제 좌표처럼 넓은 span / 대칭 값 갖는지 체크
    - 또는 화이트리스트 — settings 에 "VALUE 로 강제 취급할 이름 패턴" 추가
  - 우선순위 낮음 (실사용 드문 네이밍)


## 5. 알려진 작은 버그 / 개선

- [ ] 페이스트 시 RECIPE 가 공백만 있을 때 `find_by_recipe` 가 빈 문자열 매칭해서 엉뚱한 프리셋 주입할 위험 — 공백 체크 강화
- ~~`SettingsDialog(parent=None)` 로 인해 Settings 창이 실수로 메인 창보다 먼저 닫히면 refresh_graph 콜백이 안 갈 수 있는지 검증~~ ✅ 0.2.0 에서 `parent=self` 원복으로 해결
- [ ] 다크 테마 + PPT paste 에서 title/table 글자 색이 진한 회색(#444)/진한 회색(#222) 으로 괜찮은지 사용자 피드백 수집
- [ ] **"데이터 0개인 파라미터가 1로 표시되는 케이스" 예외처리** — 실제 장비 데이터에서 흔함. `_row_values` 가 빈 셀만 있는 행에서도 한 개로 세거나 `MAX_DATA_ID=1` 등으로 표기되는 경우. 대응:
  - `n_actual == 0` (유효 값 없음) 또는 유효 값이 전부 NaN 이면 해당 PARAMETER 를 스킵하고 경고 누적
  - VALUE 콤보에서도 후보 제외 (선택해도 시각화 실패하니)
  - 구현: `main.py::_group_by_waferid` 에서 `values` 가 전부 NaN/빈 이면 `wafer.parameters[name]` 에 아예 넣지 말고 warning 추가

---

## 6. wafer 별 PARA set 다른 케이스 시각화 허용 (0.3.x — 우선순위 높음)

**현재 동작**: `input_validation::para_set_mismatch` (severity=error) 가 paste
단계에서 Run 차단. 사내 실제 데이터에 wafer 별 PARA 다른 케이스 다수 존재 →
너무 엄격한 차단.

**필요 변경**:
- [ ] `input_validation::para_set_mismatch` severity 를 `error` → `warn` 완화 —
  Run 활성, ReasonBar 알림으로 사용자 인지만
- [ ] VALUE 콤보 union 기준 (이미 `_build_selection_context` 가 union 처리 중 —
  `para_set_mismatch` 차단 풀면 자연 동작)
- [ ] 선택한 VALUE PARA 없는 wafer 도 cell 생성 + NaN 시각화 (이미
  `_visualize_single` 에 `has_value=False` 분기 + `(no data)` 타이틀 + NaN array
  로직 있음 — 차단만 풀면 자연 동작 가능성 큼)
- [ ] 일부 wafer 만 좌표 PARA 갖는 케이스도 같은 패턴 — 좌표 union + 좌표 없는
  wafer 는 라이브러리 fallback 또는 skip + ReasonBar 알림

**검증 시나리오**: 16+장 wafer 입력 + 일부 wafer 에만 T2 / T3 / T_A 같은 케이스
- Run 활성 OK
- VALUE 콤보 = {T1, T2, T3, T_A} union 전부 노출
- T2 선택 시 T2 있는 wafer 만 정상 렌더, 없는 wafer 는 NaN cell + (no data)


## 7. 0.2.0 → 0.2.1 회귀 검증 (낮음)

**배경**: `bc315ff` (input_validation 도입) 에서 `_group_by_waferid` 가
`df.groupby(wid_col).iterrows()` → `df.iterrows() + df.loc[df_idx]` 패턴으로 변경.
이로 인해 leading whitespace / 컬럼명 중복 등 "지저분한 데이터" 케이스가
TypeError 로 노출됨 (0.3.x 에서 robust 처리 완료, `a2a265b` 등).

0.2.0 에선 `groupby` 가 silent 통과시킨 거였는데, 그게 정확한 처리였는지
(일부 wafer 묶이거나 빠뜨린 silent bug 였을 가능성) 검증 필요.

- [ ] 사내 실제 데이터로 0.2.0 build (zip 보관본) vs 0.3.x 결과 비교
- [ ] 차이 있으면 어느 쪽이 정확한지 판정 + 보강

우선순위 낮음 — 현재 0.3.x 가 명시적으로 정의된 robust 동작 (leading/trailing
노이즈 정리 + `row[data_cols]` 1D 강제) 이라 신뢰성 더 높음.

---

## 참고 파일
- `docs/rendering_optimizations.md` — 렌더링 최적화 이력·실패 사례 (반드시 참고)
- `docs/v0.1.0_perf.md` — v0.1.0 성능 측정 기록
- `docs/parser_edge_cases.md` — 파서 엣지 케이스 (v0.1.0 후 작성)
- `CHANGELOG.md` — 버전 이력
- `CLAUDE.md` — 개발자 가이드
