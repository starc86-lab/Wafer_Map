"""
v0.1.0 렌더링 관련 사용자 액션별 체감 딜레이 측정.

입력: case10 6 wafer (70 pt each).
실행: python docs/perf_measure.py
결과: 콘솔 출력 + docs/v0.1.0_perf.md 로 저장.

각 액션마다 `QApplication.processEvents()` 후 elapsed 측정 — GUI에 실제 반영되는
시간까지 포함 (단순 함수 호출 시간 아님).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

# Windows cp949 콘솔에서 em-dash / 유니코드 텍스트 쓰기 위해
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PySide6.QtCore import QPoint, QSize, Qt, QEvent
from PySide6.QtGui import (
    QGuiApplication, QMouseEvent, QSurfaceFormat,
)
from PySide6.QtWidgets import QApplication

from app import _gl_warmup, _render_warmup
from core import runtime
from core import settings as settings_io
from widgets.main_window import MainWindow
from widgets.settings_dialog import apply_global_style


CASE_A = _ROOT / "samples" / "cases" / "case10_delta_A_preEtch_6wafers.csv"
OUT_MD = _ROOT / "docs" / "v0.1.0_perf.md"


def _t(label: str, fn) -> float:
    t0 = time.perf_counter()
    fn()
    QApplication.processEvents()
    dt_ms = (time.perf_counter() - t0) * 1000.0
    print(f"  {label:<48} {dt_ms:8.1f} ms")
    return dt_ms


def _run() -> dict:
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    screen = QGuiApplication.primaryScreen().availableGeometry()
    runtime.update_screen_max(screen.width(), screen.height())

    s = settings_io.load_settings()
    apply_global_style(app, s)
    _gl_warmup()
    _render_warmup()

    win = MainWindow()
    win.show()
    app.processEvents()

    results: dict[str, float] = {}

    # ── 1. Paste + parse ──
    print("\n[1] Paste 입력 + 파싱")
    data = CASE_A.read_text(encoding="utf-8")
    results["paste_parse"] = _t("Input A 에 paste (파싱까지)", lambda: win.paste_a._editor.setPlainText(data))

    # ── 2. First Run Analysis (6 cell 동시 생성·렌더) ──
    print("\n[2] 첫 Run Analysis (2D 렌더)")
    # 보장: VALUE 가 T1 로 선택됐는지
    idx = win.cb_value.findText("T1")
    if idx >= 0:
        win.cb_value.setCurrentIndex(idx)
    app.processEvents()
    results["first_run_2d"] = _t("Visualize → 6 cell 2D 렌더 완료", win._on_visualize)

    # ── 3. View toggle 2D→3D (첫 3D 전환) ──
    print("\n[3] View 토글 (첫 3D 전환)")
    results["view_2d_to_3d_first"] = _t("cb_view → 3D (첫 전환)", lambda: win.cb_view.setCurrentText("3D"))

    # ── 4. View toggle 3D→2D (캐시) ──
    print("\n[4] View 토글 3D → 2D (캐시)")
    results["view_3d_to_2d_cached"] = _t("cb_view → 2D (캐시 적중)", lambda: win.cb_view.setCurrentText("2D"))

    # ── 5. View toggle 2D→3D (캐시) ──
    results["view_2d_to_3d_cached"] = _t("cb_view → 3D (두번째)", lambda: win.cb_view.setCurrentText("3D"))

    # ── 6. VALUE 변경 재-Run (GOF) ──
    print("\n[5] VALUE 콤보 변경 → 자동 재-Run")
    gof_idx = win.cb_value.findText("GOF")
    if gof_idx >= 0:
        results["value_change_gof"] = _t("VALUE → GOF", lambda: win.cb_value.setCurrentIndex(gof_idx))

    t1_idx = win.cb_value.findText("T1")
    if t1_idx >= 0:
        results["value_change_t1_back"] = _t("VALUE → T1 (복귀)", lambda: win.cb_value.setCurrentIndex(t1_idx))

    # ── 7. Z-Scale 토글 ──
    print("\n[6] Z-Scale 토글")
    results["zscale_common"] = _t("Z-Scale 개별 → 공통", lambda: win.cb_zscale.setCurrentText("공통"))
    results["zscale_individual"] = _t("Z-Scale 공통 → 개별", lambda: win.cb_zscale.setCurrentText("개별"))

    # ── 8. Settings 변경이 유발하는 refresh_graph ──
    print("\n[7] Settings graph_changed (refresh_all)")

    def _patch_setting(key_path: list[str], val):
        cfg = settings_io.load_settings()
        node = cfg
        for k in key_path[:-1]:
            node = node.setdefault(k, {})
        node[key_path[-1]] = val
        settings_io.set_runtime(cfg)
        win.refresh_graph()

    # 컬러맵 (cheap — z_sig skip path)
    results["colormap_change"] = _t("컬러맵 Turbo → Plasma", lambda: _patch_setting(["chart_common", "colormap"], "Plasma"))
    results["colormap_back"] = _t("컬러맵 Plasma → Turbo (복귀)", lambda: _patch_setting(["chart_common", "colormap"], "Turbo"))

    # 보간 방법 (expensive — RBF 재실행)
    results["interp_multiquadric"] = _t("보간 ThinPlate → Multiquadric", lambda: _patch_setting(["chart_common", "interp_method"], "RBF-Multiquadric"))
    results["interp_back"] = _t("보간 → ThinPlate (복귀)", lambda: _patch_setting(["chart_common", "interp_method"], "RBF-ThinPlate"))

    # 격자 해상도 (expensive — RBF + mesh 재생성)
    results["grid_200"] = _t("격자 150 → 200", lambda: _patch_setting(["chart_common", "grid_resolution"], 200))
    results["grid_150_back"] = _t("격자 200 → 150 (복귀)", lambda: _patch_setting(["chart_common", "grid_resolution"], 150))

    # show_notch (mask cache 재계산)
    results["notch_off"] = _t("Notch 표시 해제", lambda: _patch_setting(["chart_common", "show_notch"], False))
    results["notch_on"] = _t("Notch 표시 복원", lambda: _patch_setting(["chart_common", "show_notch"], True))

    # show_circle (가벼움)
    results["circle_off"] = _t("경계 원 해제", lambda: _patch_setting(["chart_common", "show_circle"], False))
    results["circle_on"] = _t("경계 원 복원", lambda: _patch_setting(["chart_common", "show_circle"], True))

    # Chart size (no render, resize만)
    results["chart_size_large"] = _t("그래프 크기 360 → 432", lambda: _patch_setting(["chart_common", "chart_width"], 432) or _patch_setting(["chart_common", "chart_height"], 336))
    results["chart_size_back"] = _t("그래프 크기 복귀 360×280", lambda: _patch_setting(["chart_common", "chart_width"], 360) or _patch_setting(["chart_common", "chart_height"], 280))

    # Z exaggeration (GL transform only)
    results["z_exaggeration_2x"] = _t("Z-Height 1.0 → 2.0", lambda: _patch_setting(["chart_3d", "z_exaggeration"], 2.0))
    results["z_exaggeration_back"] = _t("Z-Height 2.0 → 1.0", lambda: _patch_setting(["chart_3d", "z_exaggeration"], 1.0))

    # Smooth toggle (meshdata rebuild)
    results["smooth_off"] = _t("3D smooth off", lambda: _patch_setting(["chart_3d", "smooth"], False))
    results["smooth_on"] = _t("3D smooth on", lambda: _patch_setting(["chart_3d", "smooth"], True))

    # Decimals (Summary 표만 갱신)
    results["decimals_3"] = _t("소수점 2 → 3", lambda: _patch_setting(["chart_common", "decimals"], 3))
    results["decimals_2"] = _t("소수점 3 → 2", lambda: _patch_setting(["chart_common", "decimals"], 2))

    # ── 9. Copy Graph (화면 캡처 + 클립보드) ──
    print("\n[8] Copy Graph (2D·3D)")
    # 첫 셀 가져오기
    cells = win._result_panel.cells
    if cells:
        # 2D로 복귀 후 측정
        win.cb_view.setCurrentText("2D"); app.processEvents()
        results["copy_graph_2d"] = _t("Copy Graph (2D)", cells[0]._copy_graph)
        win.cb_view.setCurrentText("3D"); app.processEvents()
        results["copy_graph_3d"] = _t("Copy Graph (3D)", cells[0]._copy_graph)

    # ── 10. 두 번째 Run (캐시 효과 확인) ──
    print("\n[9] 두 번째 Run Analysis (캐시 재사용 없음 — 셀 재생성)")
    win.cb_view.setCurrentText("2D"); app.processEvents()
    results["second_run_2d"] = _t("Run Analysis 다시 (2D)", win._on_visualize)

    # ── 11. Shift+drag 6 cell sync rotate (시뮬레이션) ──
    # _LockedGLView._broadcast_camera를 직접 호출
    print("\n[10] Shift+drag broadcast (카메라 동기 — 1 호출당)")
    try:
        # 3D로 전환
        win.cb_view.setCurrentText("3D")
        app.processEvents()
        cell0 = cells[0]
        gl0 = cell0._gl_3d
        # 카메라 약간 변경
        gl0.opts["azimuth"] = gl0.opts.get("azimuth", -135) + 15
        results["shift_drag_broadcast"] = _t("broadcast → 5개 셀 update", gl0._broadcast_camera)
    except Exception as e:
        print(f"  shift_drag_broadcast skipped: {e}")

    app.quit()
    return results


def _write_report(results: dict) -> None:
    lines: list[str] = []
    lines.append("# v0.1.0 렌더링 성능 측정")
    lines.append("")
    lines.append(f"입력: `case10_delta_A_preEtch_6wafers.csv` — 6 웨이퍼 × 70 pt")
    lines.append(f"측정 시각: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"환경: Python {sys.version.split()[0]}, Windows")
    lines.append("")
    lines.append("각 액션은 Qt event loop에서 `processEvents()` 까지 포함한 end-to-end 체감 시간.")
    lines.append("")
    lines.append("| 액션 | 시간 (ms) | 비고 |")
    lines.append("|---|---:|---|")
    # 순서 있는 dict라 기록 순서 유지됨
    notes = {
        "paste_parse": "텍스트 set → `parse_wafer_csv` 자동 호출까지",
        "first_run_2d": "6 cell 생성 + 보간 (병렬 RBF) + 2D render + layout",
        "view_2d_to_3d_first": "GL 컨텍스트 init + meshdata 생성 (cell당) + 6 cell paint",
        "view_3d_to_2d_cached": "QStackedLayout setCurrentIndex — 캐시 활용",
        "view_2d_to_3d_cached": "캐시 적중 — setCurrentIndex만",
        "value_change_gof": "재-Run (셀 재생성, 새 보간)",
        "value_change_t1_back": "동일 — VALUE 캐시 없음",
        "zscale_common": "display.z_range 주입 + refresh_all (2D/3D 둘 다)",
        "zscale_individual": "z_range None reset + refresh_all",
        "colormap_change": "z_sig skip path — setData(colors=only) + meshDataChanged 명시",
        "interp_multiquadric": "RBF 재실행 (cell당 ~80-130ms, 병렬)",
        "grid_200": "격자 150² → 200² (1.78x 증가) — RBF + mesh 전면 재생성",
        "notch_off": "mask cache 재생성 (G×G bool)",
        "circle_off": "boundary line setVisible toggle",
        "chart_size_large": "`_apply_chart_size` — setFixedSize만, 재렌더 없음",
        "z_exaggeration_2x": "GL mesh transform scale 업데이트",
        "smooth_off": "MeshData flat/smooth 재계산 (normals 바뀜)",
        "decimals_3": "Summary 표 문자열만 재생성 — 그래프 영향 없음",
        "copy_graph_2d": "`QScreen.grabWindow` + crop",
        "copy_graph_3d": "동일 — 화면 캡처 방식이라 2D/3D 동일 비용",
        "second_run_2d": "첫 Run과 동일 경로 — 셀 재생성 (이전 셀 deleteLater)",
        "shift_drag_broadcast": "5 개 셀 `opts.update` + `update()` 호출만",
    }
    for key, dt in results.items():
        note = notes.get(key, "")
        lines.append(f"| `{key}` | {dt:.1f} | {note} |")
    lines.append("")
    lines.append("## 관찰 사항")
    lines.append("")
    lines.append("- **값이 작을수록 좋은 액션**: colormap 변경, view 토글(캐시), circle/decimals toggle — 50ms 이하 목표.")
    lines.append("- **값이 클 수밖에 없는 액션**: 첫 Run, 보간/격자 변경, VALUE 변경 — 병렬 RBF + mesh 생성 불가피.")
    lines.append("- **캐시 효과 확인**: view 토글의 first vs cached 격차가 크면 첫 3D 전환 비용이 큼 → prefetch 검토.")
    lines.append("")
    lines.append("## 주의")
    lines.append("")
    lines.append("- 각 수치는 1회 측정이라 ±20% 노이즈 포함. 안정치 필요하면 N회 평균 필요.")
    lines.append("- OpenGL 드라이버·GPU에 따라 3D 관련 수치는 유의미하게 바뀔 수 있음.")
    lines.append("- Windows 백그라운드 프로세스 영향 있음.")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n결과 저장: {OUT_MD}")


if __name__ == "__main__":
    results = _run()
    _write_report(results)
