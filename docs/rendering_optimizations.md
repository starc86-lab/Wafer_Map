# 렌더링 최적화 이력 & 가이드

이 문서는 Wafer Map의 3D/2D 렌더링 성능 최적화 작업 이력이다.
**새 최적화 시도 전에 반드시 이 문서의 "실패·롤백 이력"을 확인할 것** — 이미 시도해서 문제 있었던 패턴을 반복하지 않기 위함.

## 측정 원칙

**체감 시간으로 측정**한다 (Python code time만 재면 GPU 비동기 렌더를 놓쳐서 실제보다 낙관적 숫자 나옴):

```python
t0 = time.perf_counter()
panel.refresh_all()
QApplication.processEvents()     # Qt 이벤트 + GL swap 포함
dt = (time.perf_counter() - t0) * 1000
```

벤치마크 조건: `case10_delta_A_preEtch_6wafers.csv` (6 wafer × 70 pt × RBF), `grid_resolution=250`.

---

## 적용된 최적화 (효과 큰 순)

### 1. 3D GL item 재사용 + `z_sig` + `meshDataChanged` 명시 호출

**문제**: `_render_3d`가 매 refresh마다 `GLSurfacePlotItem`을 `removeItem` → 새로 생성 → `addItem` → GPU VBO 재할당. cell당 500ms, 6 cell × colormap 변경 = **3300ms**.

**해결**:
- `_gl_surface` / `_gl_boundary` / `_gl_grid` slot에 보관, `setVisible(False)`로만 hide (GPU buffer 유지)
- shader / smooth 변경 시에만 재생성 (`_surface_key` 비교)
- z signature `(interp_key, mask_key, vmin, vmax, factor)` 비교 → z 동일하면 `setData(colors=only)`로 교체 (smooth=True에서 z 업데이트는 매우 비쌈: 250² vertex normals 재계산)

**⚠️ pyqtgraph 버그 회피**: `GLSurfacePlotItem.setData(colors=only)`는 내부에서 `meshDataChanged()` 호출이 **빠져있음** → GPU 반영 안 됨. 명시적으로 `self._gl_surface.meshDataChanged()` 호출해야 한다. 안 부르면 "시간 엄청 빠른데 화면이 안 바뀌는" 버그 발생.

**효과**: colormap 변경 3300ms → **110ms** (~30×).

### 2. Vectorized vertex normals 주입

**문제**: pyqtgraph `MeshData.vertexNormals()`가 Python `for` 루프로 vertex마다 normal 계산. 62,500 vertex 기준 cell당 500ms.

**해결**: numpy vectorized `_compute_smooth_vertex_normals(vertexes, faces)` 계산 후 `self._gl_surface._meshdata._vertexNormals`에 직접 주입 + `_vertexNormalsIndexedByFaces = None` 리셋. pyqtgraph의 lazy 경로 우회.

**효과**: z 변경 항목(shading/smooth/z_exag/notch_depth/show_notch) 3300ms → **200ms** (~15×).

### 3. 병렬 RBF 보간 (`ThreadPoolExecutor`)

**문제**: 6 cell의 RBF 보간이 순차 (cell당 130ms × 6 = 780ms).

**해결**: `WaferCell.prefetch_interp()` (GUI 미접근, 보간 캐시만 채움) + `ResultPanel.refresh_all()`에서 `ThreadPoolExecutor(max_workers=6)`로 병렬 호출. scipy RBF가 GIL 해제하는 C 코드라 효과 극대.

**효과**: grid=250 RBF 781ms → **160ms** (~5×).

### 4. 2단 캐시 (`_interp_cache` / `_mask_cache`)

**문제**: `notch_depth` 변경 시에도 RBF 재계산 발생 (90ms).

**해결**: 캐시를 2층으로 분리.
- `_interp_cache` + `_interp_key=(method, G)`: RBF 결과
- `_mask_cache` + `_mask_key=(G, show_notch, depth)`: inside mask

`notch_depth`만 바뀌면 RBF 건너뛰고 mask만 재계산.

**효과**: notch_depth 변경 90ms → **4ms** (~20×).

### 5. 보간 캐시 분리 (`refresh_graph` vs `revisualize`)

**문제**: Settings 변경 시 `revisualize()` → `_on_visualize()` → cell 통째 재생성. 모든 것 날아감.

**해결**: Settings graph_changed는 `ResultPanel.refresh_all()` 호출 → 각 cell은 렌더 캐시만 reset, **보간 캐시는 유지**. `WaferCell.refresh()` API.

**효과**: 컬러맵 등 대부분 항목에서 RBF 생략.

### 6. `prefetch_inactive_view` + `grabFramebuffer` (첫 2D→3D 전환 깜빡임 제거)

**문제**: Run Analysis 후 첫 3D 클릭 시 `GLViewWidget`이 그제야 GL context 초기화 → GPU 업로드 → 첫 paint. cell당 ~80ms, 6 cell × grid=250 = **451ms**.

**해결**:
- `ResultPanel.set_displays` 후 `QTimer.singleShot(50, prefetch_inactive_views)` 예약
- `WaferCell.prefetch_inactive_view()`: 비활성 view를 미리 렌더 + **hidden 상태에서 `_gl_3d.grabFramebuffer()` 호출**로 GL context 초기화 + 첫 paint 강제
- 사용자가 2D 확인하는 사이 3D 준비 완료 → 토글 시 `setCurrentIndex`만

**효과**: 2D→3D 전환 451ms → **~75ms** (격자 무관, 깜빡임 없음).

### 7. `set_displays`의 defer_render + 병렬 prefetch_interp

**문제**: Run Analysis 시 cell이 순차 생성되며 각자 RBF 실행.

**해결**: `WaferCell(defer_render=True)`로 Qt 아이템 생성 스킵 → 모든 cell의 `prefetch_interp`를 병렬 실행 → 각 cell `render_initial()` 호출.

**효과**: grid=250 · 6 cell 2D 표시 872ms → **~265ms** (~3.3×).

### 8. App 시작 시 GL warm-up + result_panel hidden anchor

**해결** (b0.0.0~, 기존):
- `Qt.AA_ShareOpenGLContexts` + dummy `GLViewWidget` show→hide→deleteLater
- `ResultPanel`에 영구 hidden `GLViewWidget` 1개 → ancestor native window 승격을 startup에 처리

**효과**: 첫 Run Analysis 시점 깜빡임 제거.

### 9. `cb_zscale` ground truth + `invalidate_3d`

**해결**: Z scale 콤보 변경 시 cell 재생성 없이 displays의 z_range만 갱신 + `invalidate_3d()` → 3D 캐시만 무효화 (2D 유지). 현재 view가 3D면 즉시 재렌더.

---

## 실패·롤백한 시도 (같은 함정 반복 금지)

### ❌ scipy `RBFInterpolator(neighbors=K)` (local RBF)

- **기대**: 각 query 점마다 가장 가까운 K개만 사용 → 큰 N에서 빠름
- **결과**: N=70 작은 케이스에서 각 query마다 kd-tree lookup + local RBF setup 오버헤드가 누적 → **5배 느려짐**
- **교훈**: N < 100 정도면 전역 RBF가 더 빠름. `neighbors`는 N > 수백 경우에만.

### ❌ Edge fade-out + `translucent` surface

- **목적**: 3D 바닥 경계선이 surface에 가려지는 문제 해결
- **시도**: surface 경계 근처 vertex의 alpha를 낮추고 `glOptions="translucent"` 전환
- **결과**: 사용자 피드백 "엉망". translucent가 뒤쪽 삼각형과 앞쪽을 blend하여 유리처럼 보이는 시각 artifact
- **교훈**: surface는 `opaque` 유지. 경계 표시는 별도 방법 (현재는 `opaque` line, 앞쪽만 보이는 것 감수).

### ❌ `GLLinePlotItem` width 증가 + bottom ring mesh

- **목적**: 3D 바닥 경계선 굵게
- **시도 1**: `width=4` → OpenGL 드라이버 제한으로 거의 효과 없음
- **시도 2**: `antialias=False` → 미세 차이만
- **시도 3**: `GLMeshItem`으로 두꺼운 링 (6mm 폭) → 바닥에 뚜렷하지만 surface 뒤쪽은 여전히 가려짐
- **결론**: 사용자가 현재 `GLLinePlotItem(width=2, opaque)` 상태로 롤백 유지

### ❌ 3D에서 notch 위치에 수직 tick 마커

- **목적**: 카메라 각도 무관 notch 위치 식별
- **시도**: 6시 경계에서 z 방향으로 솟은 짧은 검은 선
- **결과**: 사용자 피드백 "엉망"
- **교훈**: 과한 시각 표시는 역효과. notch는 경계의 V자 + 적절한 기본 카메라 각도(`azimuth=-135`)로 충분.

### ❌ z_sig / color_sig 분리 (A안)

- **목적**: z_exag 변경 시 colors 재전송 skip
- **결과**: z_exag 200ms → 190ms (~5% 개선). 상태 2개 관리 + branch 4개로 복잡도 증가
- **롤백 이유**: 효과 < 복잡도. z/colors 계산 자체가 cell당 몇 ms라 skip 효과 작음. 진짜 병목은 normals + GPU upload + Qt paint
- **교훈**: 5~10% 개선은 복잡도 감수할 가치 없음.

### ❌ B안 — Run Analysis 시 2D+3D 동시 렌더

- **목적**: 첫 2D→3D 전환 즉시화
- **문제**: 둘 다 렌더 후 paint 1회 → **2D 표시 자체가 늦어짐** (~400ms → ~700ms)
- **대안**: A안(`prefetch_inactive_view` + `QTimer.singleShot(50, ...)`)으로 2D 표시 지연 없이 3D 백그라운드 준비. **이게 채택된 방식**.

---

## 구조적 한계

측정 결과 **200ms대에 하한선 존재** — 더 쥐어짜기 어려움:

- 6 cell의 GL 업데이트는 Qt 이벤트 루프로 **순차 처리** (Qt restriction)
- 각 cell: `setData(z,colors)` GPU 업로드 ~10ms + Qt paint + vsync 대기 ~15~20ms
- 6 cell × ~30ms = ~180~200ms (이게 한계)
- 병렬화 가능한 건 CPU-side 계산(normals, colors)뿐 → 현실적 20~30ms 절감

**shader 변경 (`shading`)은 surface 재생성 필수** — pyqtgraph가 shader를 생성자에서만 받음.

---

## 측정 결과 (현재, grid=250 · 6 cells × 3D · 체감 시간)

| 카테고리 | 항목 | ms |
|---|---|---|
| 🟢 즉시 | show_circle/grid/points/point_size/value_labels 토글 | 30~40 |
| 🟢 즉시 | colormap 변경 | 33~85 |
| 🟢 빠름 | grid=100 | 70 |
| 🟡 중간 | grid=150 | 131 |
| 🟡 중간 | show_notch/notch_depth | 190~195 |
| 🟡 중간 | z_exag | 200 |
| 🟡 중간 | shading/smooth | 200~217 |
| 🟡 중간 | grid=200 | 210 |
| 🟡 중간 | interp=cubic | 230 |
| 🟠 약간 느림 | grid=250 | 334 |
| 🟠 약간 느림 | interp=rbf | 340 |
| Run Analysis 2D 표시 | 265 | |
| 2D→3D 전환 (prefetch 완료 후) | 75 | |

---

## 미래 수정 시 가이드라인

1. **측정 먼저** — 체감 시간(Python + `processEvents`) 기준. Python time만으로 판단 금지.
2. **2D vs 3D** — 2D는 pyqtgraph Qt-based라 빠름, 3D는 OpenGL + GPU upload + vsync가 비용.
3. **새 최적화 전 이 문서의 "실패·롤백" 섹션 확인** — 같은 실수 반복 금지.
4. **복잡도 대비 효과 판단** — 5~10% 개선은 롤백이 안전. 2× 이상일 때 도입.
5. **pyqtgraph 내부 직접 접근은 최후 수단** — 버전 업데이트 시 깨질 수 있음. 현재 의존:
   - `GLSurfacePlotItem._vertexes`, `._faces`, `._meshdata`
   - `MeshData._vertexNormals`, `._vertexNormalsIndexedByFaces`
   - `GLSurfacePlotItem.setData(colors=only)` + 명시 `meshDataChanged()`
6. **`translucent` glOption은 artifact 많음** — surface는 `opaque` 유지.
