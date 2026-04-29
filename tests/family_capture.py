"""
가족 좌표 정책 회귀 검증 — 샘플 CSV 들 일괄 실행 후 결과 dump.

실행:
    venv/Scripts/python tests/family_capture.py [out_dir]

각 sample 별로 ReasonBar 메시지, 시각화된 cell list, Run 활성 여부 등을 dict 로
caputre 후 JSON 으로 저장. 코드 변경 후 재실행 → diff 비교.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SAMPLES_DIR = ROOT / "samples" / "cases" / "family_test"

# Single mode samples — single CSV file
SINGLE_SAMPLES = [
    "s_family_normal",
    "s_family_partial_coord",
    "s_family_short_n",
    "s_family_multi_recipe",
    "s_family_multi_coord_set",
    "s_combine_data",
]

# DELTA samples — pair of (A, B) CSV files
DELTA_SAMPLES = [
    "d_normal",
    "d_partial",
    "d_recipe_diff",
]


def read_csv(name: str) -> str:
    path = SAMPLES_DIR / f"{name}.csv"
    return path.read_text(encoding="utf-8")


def setup_app():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


def make_main_window():
    from widgets.main_window import MainWindow
    return MainWindow()


def reset(mw):
    """모든 입력 / 콤보 / preset / 합성 상태 + result_panel cell 초기화."""
    mw.paste_a._editor.clear()
    mw.paste_b._editor.clear()
    # paste_area._on_text_changed 가 빈 텍스트 시 _result 를 None 으로 안 만들어서
    # 명시적으로 강제 초기화 (이전 sample 잔재 방지)
    mw.paste_a._result = None
    mw.paste_b._result = None
    mw._result_a = None
    mw._result_b = None
    mw._reset_preset_override()
    mw._clear_combined()
    mw._result_panel.clear()
    mw._update_delta_validation()
    mw._refresh_controls()


def paste(paste_widget, text: str) -> None:
    paste_widget._editor.setPlainText(text)


def capture_state(mw) -> dict:
    """현재 main window 상태 dict 추출."""
    cells = []
    for c in mw._result_panel.cells:
        d = c.display
        n = len(d.x_mm) if d.x_mm is not None else 0
        try:
            v_min = float(d.values[~_isnan(d.values)].min()) if n > 0 else None
            v_max = float(d.values[~_isnan(d.values)].max()) if n > 0 else None
        except Exception:
            v_min = v_max = None
        cells.append({
            "title": d.title,
            "n_points": n,
            "x_first": float(d.x_mm[0]) if n > 0 else None,
            "y_first": float(d.y_mm[0]) if n > 0 else None,
            "values_min": _round(v_min),
            "values_max": _round(v_max),
            "is_radial": bool(getattr(d, "is_radial", False)),
            "is_delta": bool(getattr(d, "is_delta", False)),
        })
    return {
        "reason_bar_text": mw._reason_bar._label.text(),
        "reason_bar_severity": mw._reason_bar._label.property("severity") or "",
        "n_cells": len(cells),
        "cells": cells,
        "btn_run_enabled": bool(mw.btn_visualize.isEnabled()),
        "value_combo": mw.cb_value.currentText(),
        "coord_combo": mw.cb_coord.currentText(),
        "delta_warnings": [
            {"code": w.code, "severity": w.severity, "message": w.message}
            for w in mw._delta_warnings
        ],
    }


def _isnan(arr):
    import numpy as np
    return np.isnan(arr) if arr is not None else False


def _round(v):
    if v is None:
        return None
    return round(v, 3)


def run_single(mw, name: str) -> dict:
    """단일 sample 실행 — A 에 paste 후 Run."""
    reset(mw)
    text = read_csv(name)
    paste(mw.paste_a, text)
    _process()
    # paste 후 검증 결과 capture
    paste_state = {
        "after_paste_reason_bar": mw._reason_bar._label.text(),
        "after_paste_severity": mw._reason_bar._label.property("severity") or "",
        "after_paste_run_enabled": bool(mw.btn_visualize.isEnabled()),
    }
    # Run (가능하면)
    if mw.btn_visualize.isEnabled():
        mw._on_visualize()
        _process()
    state = capture_state(mw)
    state.update(paste_state)
    return state


def run_delta(mw, name: str) -> dict:
    """DELTA sample 실행 — A 와 B 에 paste 후 Run."""
    reset(mw)
    paste(mw.paste_a, read_csv(f"{name}_A"))
    _process()
    paste(mw.paste_b, read_csv(f"{name}_B"))
    _process()
    paste_state = {
        "after_paste_reason_bar": mw._reason_bar._label.text(),
        "after_paste_severity": mw._reason_bar._label.property("severity") or "",
        "after_paste_run_enabled": bool(mw.btn_visualize.isEnabled()),
    }
    if mw.btn_visualize.isEnabled():
        mw._on_visualize()
        _process()
    state = capture_state(mw)
    state.update(paste_state)
    return state


def _process():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        app.processEvents()


def main():
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else (ROOT / "tests" / "baseline")
    out_dir.mkdir(parents=True, exist_ok=True)
    setup_app()
    mw = make_main_window()

    results = {}
    for name in SINGLE_SAMPLES:
        try:
            print(f"  capturing {name}...", flush=True)
            results[name] = run_single(mw, name)
        except Exception as e:
            import traceback
            traceback.print_exc()
            results[name] = {"_error": str(e)}

    for name in DELTA_SAMPLES:
        try:
            print(f"  capturing {name} (delta)...", flush=True)
            results[name] = run_delta(mw, name)
        except Exception as e:
            import traceback
            traceback.print_exc()
            results[name] = {"_error": str(e)}

    out_file = out_dir / "results.json"
    out_file.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nWrote {out_file}")
    print(f"Total samples: {len(results)}")


if __name__ == "__main__":
    main()
