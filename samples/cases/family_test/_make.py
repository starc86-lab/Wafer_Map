"""
가족 좌표 정책 검증용 샘플 CSV 생성기.

생성 시나리오 (가장 중요한 6 + 회귀 detector 3 = 9개):

Single mode:
  s_family_normal        — 정상 가족 (회귀 detector)
  s_family_partial_coord — 한 wafer 가 X_A/Y_A 페어 누락 (paste 잘림)
  s_family_short_n       — 한 wafer 좌표 N 부족 (paste 마지막 cell 누락)
  s_family_multi_recipe  — 한 wafer RECIPE 다름 (새 정책 ERROR)
  s_family_multi_coord_set — 정상 가족 + X/Y + X_A/Y_A 두 set
  s_combine_data         — PARA 조합 회귀 detector (T1, T2 같은 좌표)

DELTA mode (각 sample 은 _A.csv + _B.csv 페어):
  d_normal_A / d_normal_B — A·B 정상, RECIPE PRE/POST 호환
  d_partial_A / d_partial_B — A 한 wafer 좌표 누락
  d_recipe_diff_A / d_recipe_diff_B — A·B RECIPE 비호환

13 DATA 컬럼 고정. 각 wafer 별 측정값은 무난한 두께값 (660~700 범위).
"""
from __future__ import annotations

import os
import random

random.seed(42)

HEADER = (
    "ETC1,DATE,MACHINE,OPERATINID,ETC2,ETC3,STEPDESC,RECIPE,"
    "LOT ID,WAFERID,Slot ID,PARAMETER,MAX_DATA_ID,"
    + ",".join(f"DATA{i+1}" for i in range(13))
)

# 표준 inner 13pt 좌표 (case03 와 유사한 패턴)
X13 = [0, 50, -50, 0, 0, 100, -100, 0, 0, 130, -130, 0, 0]
Y13 = [0, 0, 0, 50, -50, 0, 0, 100, -100, 0, 0, 130, -130]
# 12pt outer 좌표 (예시)
X12 = [132, 111, 55, -19, -86, -127, -127, -86, -19, 55, 111, 132]
Y12 = [0, 71, 120, 131, 100, 37, -37, -100, -131, -120, -71, 0]

assert len(X13) == 13 and len(Y13) == 13
assert len(X12) == 12 and len(Y12) == 12


def fmt_cells(values):
    return [f"{v:.2f}".rstrip("0").rstrip(".") for v in values]


def row(meta, recipe, lot, wafer, slot, para, n_max, values):
    cells = fmt_cells(values)
    cells += [""] * (13 - len(cells))
    return ",".join([
        meta, recipe, lot, wafer, str(slot), para, str(n_max),
        *cells,
    ])


def gen_t1(seed_offset=0):
    rng = random.Random(seed_offset)
    return [round(rng.gauss(663, 5), 2) for _ in range(13)]


def gen_t2(seed_offset=0):
    rng = random.Random(seed_offset + 100)
    return [round(rng.gauss(120, 2), 2) for _ in range(13)]


def gen_t_a(seed_offset=0):
    """outer T_A — 12pt"""
    rng = random.Random(seed_offset + 200)
    return [round(rng.gauss(400, 5), 2) for _ in range(12)]


META = "XX,2026-04-30 09:00,MTMF01,A001,AAA,B,FAMILY TEST"


def write_csv(name: str, rows: list[str]):
    path = os.path.join(os.path.dirname(__file__), name)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(HEADER + "\n")
        f.write("\n".join(rows) + "\n")
    print(f"wrote {name}: {len(rows)} rows")


# ── s_family_normal ────────────────────────────────────
def make_family_normal():
    recipe = "RECIPE_FAM"
    rows = []
    for i in range(3):
        lot = "LX001"
        wafer = f"LX001.0{i+1}"
        slot = i + 1
        rows.append(row(META, recipe, lot, wafer, slot, "T1", 13, gen_t1(i)))
        rows.append(row(META, recipe, lot, wafer, slot, "X", 13, X13))
        rows.append(row(META, recipe, lot, wafer, slot, "Y", 13, Y13))
    write_csv("s_family_normal.csv", rows)


# ── s_family_partial_coord ────────────────────────────
def make_family_partial_coord():
    """W3 가 X_A 만 보유, Y_A 누락 (paste 잘림 시나리오 — 마지막 행 누락)."""
    recipe = "RECIPE_FAM"
    rows = []
    for i in range(3):
        lot = "LX002"
        wafer = f"LX002.0{i+1}"
        slot = i + 1
        rows.append(row(META, recipe, lot, wafer, slot, "T1", 13, gen_t1(i)))
        rows.append(row(META, recipe, lot, wafer, slot, "X", 13, X13))
        rows.append(row(META, recipe, lot, wafer, slot, "Y", 13, Y13))
        rows.append(row(META, recipe, lot, wafer, slot, "T_A", 12, gen_t_a(i)))
        if i == 2:
            # W3: X_A 만, Y_A 누락
            rows.append(row(META, recipe, lot, wafer, slot, "X_A", 12, X12))
        else:
            rows.append(row(META, recipe, lot, wafer, slot, "X_A", 12, X12))
            rows.append(row(META, recipe, lot, wafer, slot, "Y_A", 12, Y12))
    write_csv("s_family_partial_coord.csv", rows)


# ── s_family_short_n ──────────────────────────────────
def make_family_short_n():
    """W3 의 X 가 12pt 만 (paste 마지막 cell 누락). 다른 wafer 는 13pt."""
    recipe = "RECIPE_FAM"
    rows = []
    for i in range(3):
        lot = "LX003"
        wafer = f"LX003.0{i+1}"
        slot = i + 1
        rows.append(row(META, recipe, lot, wafer, slot, "T1", 13, gen_t1(i)))
        if i == 2:
            # W3: X 12pt 만
            rows.append(row(META, recipe, lot, wafer, slot, "X", 12, X13[:12]))
        else:
            rows.append(row(META, recipe, lot, wafer, slot, "X", 13, X13))
        rows.append(row(META, recipe, lot, wafer, slot, "Y", 13, Y13))
    write_csv("s_family_short_n.csv", rows)


# ── s_family_multi_recipe ──────────────────────────────
def make_family_multi_recipe():
    """W3 만 RECIPE 다름. 새 정책 ERROR 차단 대상."""
    rows = []
    for i in range(3):
        recipe = "RECIPE_A" if i < 2 else "RECIPE_B"
        lot = "LX004"
        wafer = f"LX004.0{i+1}"
        slot = i + 1
        rows.append(row(META, recipe, lot, wafer, slot, "T1", 13, gen_t1(i)))
        rows.append(row(META, recipe, lot, wafer, slot, "X", 13, X13))
        rows.append(row(META, recipe, lot, wafer, slot, "Y", 13, Y13))
    write_csv("s_family_multi_recipe.csv", rows)


# ── s_family_multi_coord_set ──────────────────────────
def make_family_multi_coord_set():
    """가족 모두 X/Y (13pt) + X_A/Y_A (12pt) 두 set 보유. 정상."""
    recipe = "RECIPE_FAM"
    rows = []
    for i in range(3):
        lot = "LX005"
        wafer = f"LX005.0{i+1}"
        slot = i + 1
        rows.append(row(META, recipe, lot, wafer, slot, "T1", 13, gen_t1(i)))
        rows.append(row(META, recipe, lot, wafer, slot, "X", 13, X13))
        rows.append(row(META, recipe, lot, wafer, slot, "Y", 13, Y13))
        rows.append(row(META, recipe, lot, wafer, slot, "T_A", 12, gen_t_a(i)))
        rows.append(row(META, recipe, lot, wafer, slot, "X_A", 12, X12))
        rows.append(row(META, recipe, lot, wafer, slot, "Y_A", 12, Y12))
    write_csv("s_family_multi_coord_set.csv", rows)


# ── s_combine_data ────────────────────────────────────
def make_combine_data():
    """PARA 조합 회귀 detector 용 — T1, T2 같은 좌표 X/Y."""
    recipe = "RECIPE_FAM"
    rows = []
    for i in range(2):
        lot = "LX006"
        wafer = f"LX006.0{i+1}"
        slot = i + 1
        rows.append(row(META, recipe, lot, wafer, slot, "T1", 13, gen_t1(i)))
        rows.append(row(META, recipe, lot, wafer, slot, "T2", 13, gen_t2(i)))
        rows.append(row(META, recipe, lot, wafer, slot, "X", 13, X13))
        rows.append(row(META, recipe, lot, wafer, slot, "Y", 13, Y13))
    write_csv("s_combine_data.csv", rows)


# ── DELTA samples ─────────────────────────────────────
def make_delta_normal():
    """A·B 양쪽 정상, RECIPE PRE/POST 호환. 같은 WAFERID 로 매칭."""
    for side, recipe in [("A", "RECIPE_PRE"), ("B", "RECIPE_POST")]:
        rows = []
        for i in range(3):
            lot = f"LX10{side}"  # 다른 LOT 이지만
            wafer = f"LX10.0{i+1}"  # 같은 WAFERID 로 매칭
            slot = i + 1
            rows.append(row(META, recipe, lot, wafer, slot, "T1", 13, gen_t1(i + (10 if side == "B" else 0))))
            rows.append(row(META, recipe, lot, wafer, slot, "X", 13, X13))
            rows.append(row(META, recipe, lot, wafer, slot, "Y", 13, Y13))
        write_csv(f"d_normal_{side}.csv", rows)


def make_delta_partial():
    """A 한 wafer 좌표 누락. B 정상."""
    # A
    recipe_a = "RECIPE_PRE"
    rows = []
    for i in range(3):
        lot = "LX11A"
        wafer = f"LX11A.0{i+1}"
        slot = i + 1
        rows.append(row(META, recipe_a, lot, wafer, slot, "T1", 13, gen_t1(i)))
        if i == 2:
            # W3 좌표 누락
            pass
        else:
            rows.append(row(META, recipe_a, lot, wafer, slot, "X", 13, X13))
            rows.append(row(META, recipe_a, lot, wafer, slot, "Y", 13, Y13))
    write_csv("d_partial_A.csv", rows)

    # B 정상
    recipe_b = "RECIPE_POST"
    rows = []
    for i in range(3):
        lot = "LX11B"
        wafer = f"LX11A.0{i+1}"  # 같은 WAFERID 로 매칭
        slot = i + 1
        rows.append(row(META, recipe_b, lot, wafer, slot, "T1", 13, gen_t1(i + 10)))
        rows.append(row(META, recipe_b, lot, wafer, slot, "X", 13, X13))
        rows.append(row(META, recipe_b, lot, wafer, slot, "Y", 13, Y13))
    write_csv("d_partial_B.csv", rows)


def make_delta_recipe_diff():
    """A·B RECIPE 비호환 (PRE/POST 외)."""
    for side, recipe in [("A", "RECIPE_X"), ("B", "RECIPE_Y")]:
        rows = []
        for i in range(2):
            lot = f"LX12{side}"
            wafer = f"LX12.0{i+1}"  # 같은 WAFERID
            slot = i + 1
            rows.append(row(META, recipe, lot, wafer, slot, "T1", 13, gen_t1(i + (10 if side == "B" else 0))))
            rows.append(row(META, recipe, lot, wafer, slot, "X", 13, X13))
            rows.append(row(META, recipe, lot, wafer, slot, "Y", 13, Y13))
        write_csv(f"d_recipe_diff_{side}.csv", rows)


if __name__ == "__main__":
    make_family_normal()
    make_family_partial_coord()
    make_family_short_n()
    make_family_multi_recipe()
    make_family_multi_coord_set()
    make_combine_data()
    make_delta_normal()
    make_delta_partial()
    make_delta_recipe_diff()
    print("DONE")
