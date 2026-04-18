"""
Auto-select 검증 스크립트.

실행:
    python tests/test_auto_select.py

각 케이스의 (available PARAMETERs, 기대값, 실제값, 매칭 리스트)를 콘솔에 출력.
단위 케이스 7종 + MainWindow 통합 테스트 1종.
실패 케이스가 있으면 exit code 1로 종료.
"""
from __future__ import annotations

import sys
from pathlib import Path

# utf-8 콘솔
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# 프로젝트 루트 import 경로
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from core.auto_select import prioritized_list, select_value, select_y_with_suffix
from main import parse_wafer_csv


# ────────────────────────────────────────────────────────────────
# 테스트 데이터 헬퍼
# ────────────────────────────────────────────────────────────────
def make_df(
    params: dict[str, list[float]],
    *,
    wafer_id: str = "W1.01",
    lot_id: str = "L1",
    slot_id: int = 1,
    recipe: str = "TestRecipe",
    n_data_cols: int = 13,
) -> pd.DataFrame:
    """PARAMETER→값 리스트 dict로 long-form DataFrame 생성."""
    rows = []
    for name, values in params.items():
        row = {
            "WAFERID": wafer_id, "LOT ID": lot_id, "SLOTID": slot_id,
            "PARAMETER": name, "RECIPE": recipe, "MAX_DATA_ID": len(values),
        }
        for i in range(n_data_cols):
            row[f"DATA{i+1}"] = values[i] if i < len(values) else None
        rows.append(row)
    return pd.DataFrame(rows)


def params_to_ns(result) -> dict[str, int]:
    w = next(iter(result.wafers.values()))
    return {name: rec.n for name, rec in w.parameters.items()}


def fmt_list(ordered: list[str], matched: set[str]) -> str:
    return "[" + ", ".join(f"{n}*" if n in matched else n for n in ordered) + "]"


# ────────────────────────────────────────────────────────────────
# 케이스 러너
# ────────────────────────────────────────────────────────────────
results: list[tuple[str, bool]] = []


def run_case(
    name: str,
    params: dict[str, list[float]],
    *,
    n_data_cols: int = 13,
    value_patterns=("T*",),
    x_patterns=("X", "X*"),
    y_patterns=("Y", "Y*"),
    expect_value: str | None = "T1",
    expect_x: str | None = "X",
    expect_y: str | None = "Y",
) -> None:
    df = make_df(params, n_data_cols=n_data_cols)
    result = parse_wafer_csv(df)
    available_ns = params_to_ns(result)

    v_sel, v_ord = select_value(available_ns, value_patterns, n_data_cols)
    x_sel, x_ord = select_value(available_ns, x_patterns, n_data_cols)
    y_sel, y_ord = select_y_with_suffix(x_sel, available_ns, y_patterns, n_data_cols)

    _, v_match = prioritized_list(available_ns, value_patterns, n_data_cols)
    _, x_match = prioritized_list(available_ns, x_patterns, n_data_cols)
    _, y_match = prioritized_list(available_ns, y_patterns, n_data_cols)

    print()
    print("═" * 75)
    print(f" CASE: {name}")
    print("═" * 75)
    ns_str = "  ".join(f"{k}={v}" for k, v in sorted(available_ns.items()))
    print(f" Available (name=n): {ns_str}")
    print(f" Patterns  value={list(value_patterns)}  "
          f"x={list(x_patterns)}  y={list(y_patterns)}  required_n={n_data_cols}")
    print()

    def chk(label, expected, actual, ordered, matched):
        ok = (expected == actual)
        mark = "OK " if ok else "FAIL"
        print(f" [{mark}] {label:6s} expected={expected!s:<10} actual={actual!s:<10}")
        print(f"          list: {fmt_list(ordered, matched)}   (*=매칭)")
        return ok

    ok_v = chk("VALUE", expect_value, v_sel, v_ord, v_match)
    ok_x = chk("X",     expect_x,     x_sel, x_ord, x_match)
    ok_y = chk("Y",     expect_y,     y_sel, y_ord, y_match)

    results.append((name, ok_v and ok_x and ok_y))


# ────────────────────────────────────────────────────────────────
# 케이스 1~7
# ────────────────────────────────────────────────────────────────
run_case(
    "1. Basic — T1, X, Y 모두 존재 + n-mismatch 후보들",
    {
        "T1":     [663.1] * 13,
        "T1_AVG": [638.5],
        "T1_B":   [710.0] * 4,
        "X":      [0] * 13,
        "Y":      [0] * 13,
        "GOF":    [0.99] * 13,
    },
    expect_value="T1", expect_x="X", expect_y="Y",
)

run_case(
    "2. Scale _1000 — X 없음, X_1000만 존재",
    {
        "T1":     [663.1] * 13,
        "X_1000": [0] * 13,
        "Y_1000": [0] * 13,
    },
    expect_value="T1", expect_x="X_1000", expect_y="Y_1000",
)

run_case(
    "3. Multiple T — 알파벳 순 가장 앞 채택",
    {
        "T3": [10] * 13, "T2": [20] * 13, "T1": [30] * 13,
        "X":  [0] * 13,  "Y":  [0] * 13,
    },
    expect_value="T1", expect_x="X", expect_y="Y",
)

run_case(
    "4. REV* fallback — T 계열 없고 REV만 (사용자 정의 패턴)",
    {
        "REV1": [1] * 13, "REV2": [2] * 13,
        "X":    [0] * 13, "Y":    [0] * 13,
    },
    value_patterns=("T*", "REV*"),
    expect_value="REV1", expect_x="X", expect_y="Y",
)

run_case(
    "5. Suffix _A — X_A/Y_A 쌍만 존재",
    {
        "T1":  [1] * 13,
        "X_A": [0] * 13,
        "Y_A": [0] * 13,
    },
    expect_value="T1", expect_x="X_A", expect_y="Y_A",
)

run_case(
    "6. T* 패턴에 THK도 포함 — T로 시작하는 모든 이름 매칭",
    {
        "THK": [1] * 13,
        "X":   [0] * 13,
        "Y":   [0] * 13,
    },
    expect_value="THK", expect_x="X", expect_y="Y",
)

run_case(
    "6b. 패턴 매칭 실패 → n 일치 알파벳 첫 폴백",
    {
        "FILMTHK": [1] * 13,  # T*·REV* 아님 → 패턴 매칭 실패 → FILMTHK(알파벳 첫)로 폴백
        "X":       [0] * 13,
        "Y":       [0] * 13,
    },
    expect_value="FILMTHK", expect_x="X", expect_y="Y",
)

run_case(
    "6c. n 일치 후보도 아예 없음 — 모든 이름 = None",
    {
        "FILMTHK": [1] * 4,   # required_n=13 인데 모두 n=4
        "X":       [0] * 4,
        "Y":       [0] * 4,
    },
    expect_value=None, expect_x=None, expect_y=None,
)

run_case(
    "7. X 완전 일치 없고 여러 X_* 후보 — 알파벳 첫 선택",
    {
        "T1":     [1] * 13,
        "X_1000": [0] * 13,
        "X_A":    [0] * 13,
        "X_B":    [0] * 13,
        "Y_1000": [0] * 13,
        "Y_A":    [0] * 13,
        "Y_B":    [0] * 13,
    },
    expect_value="T1", expect_x="X_1000", expect_y="Y_1000",
)


# ────────────────────────────────────────────────────────────────
# 통합 테스트: MainWindow 런타임 X→Y 동기화
# ────────────────────────────────────────────────────────────────
print()
print("═" * 75)
print(" INTEGRATION: MainWindow — 페이스트 + X 수동 변경 → Y 자동 동기화")
print("═" * 75)

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from widgets.main_window import MainWindow
win = MainWindow()

csv_text = open("samples/sample_data.csv", encoding="utf-8").read()
win.paste_a._editor.setPlainText(csv_text)

init = (win.cb_value.currentText(), win.cb_x.currentText(), win.cb_y.currentText())
print(f" [초기]  VALUE={init[0]:<8} X={init[1]:<8} Y={init[2]:<8}  expected (T1, X, Y)")
ok_init = init == ("T1", "X", "Y")

win.cb_x.setCurrentText("X_1000")
y_after_1000 = win.cb_y.currentText()
print(f" [X=X_1000]                       Y={y_after_1000:<8}  expected Y_1000")
ok_1000 = (y_after_1000 == "Y_1000")

win.cb_x.setCurrentText("X")
y_back = win.cb_y.currentText()
print(f" [X=X (복귀)]                      Y={y_back:<8}  expected Y")
ok_back = (y_back == "Y")

integration_ok = ok_init and ok_1000 and ok_back
print(f" → {'OK' if integration_ok else 'FAIL'}")
results.append(("INTEGRATION  MainWindow X→Y sync", integration_ok))


# ────────────────────────────────────────────────────────────────
# 최종 요약
# ────────────────────────────────────────────────────────────────
print()
print("═" * 75)
print(" SUMMARY")
print("═" * 75)
all_ok = True
for name, ok in results:
    mark = "OK  " if ok else "FAIL"
    print(f"  [{mark}] {name}")
    all_ok &= ok

print()
print(" → 전체 통과" if all_ok else " → 실패 케이스 있음 ⚠")
sys.exit(0 if all_ok else 1)
