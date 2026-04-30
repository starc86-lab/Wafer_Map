"""
CoordLibrary id 필드 + smallest-unused 부여 + migration 검증.

실행:
    venv/Scripts/python tests/library_id_test.py

사용자 실제 coord_library.json 영향 X — temp 파일 사용.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.coord_library import CoordLibrary, CoordPreset


def _make_lib(presets_dict: list[dict]) -> tuple[CoordLibrary, str]:
    """temp file 에 presets 저장 후 CoordLibrary load."""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"presets": presets_dict}, f, ensure_ascii=False)
    return CoordLibrary(path=path), path


def test_migration_no_id():
    """기존 entry 들이 모두 id 미보유 — created_at 순으로 1, 2, 3, ... 부여."""
    presets = [
        {"recipe": "R1", "n_points": 13, "x_mm": [0]*13, "y_mm": [0]*13,
         "created_at": "2026-01-03T00:00:00", "last_used": "2026-01-03T00:00:00",
         "x_name": "X", "y_name": "Y"},
        {"recipe": "R2", "n_points": 13, "x_mm": [0]*13, "y_mm": [0]*13,
         "created_at": "2026-01-01T00:00:00", "last_used": "2026-01-01T00:00:00",
         "x_name": "X", "y_name": "Y"},
        {"recipe": "R3", "n_points": 13, "x_mm": [0]*13, "y_mm": [0]*13,
         "created_at": "2026-01-02T00:00:00", "last_used": "2026-01-02T00:00:00",
         "x_name": "X", "y_name": "Y"},
    ]
    lib, path = _make_lib(presets)
    try:
        # created_at 순서: R2 → R3 → R1 → id 1, 2, 3
        ids_by_recipe = {p.recipe: p.id for p in lib.presets}
        assert ids_by_recipe == {"R2": 1, "R3": 2, "R1": 3}, ids_by_recipe
        print(f"  migration OK: {ids_by_recipe}")
    finally:
        os.unlink(path)


def test_migration_partial_id():
    """일부 entry 만 id 보유 — 누락 entry 들이 smallest-unused 채움."""
    presets = [
        {"recipe": "R1", "id": 5, "n_points": 13, "x_mm": [0]*13, "y_mm": [0]*13,
         "created_at": "2026-01-01T00:00:00", "last_used": "2026-01-01T00:00:00",
         "x_name": "X", "y_name": "Y"},
        {"recipe": "R2", "id": 0, "n_points": 13, "x_mm": [0]*13, "y_mm": [0]*13,
         "created_at": "2026-01-02T00:00:00", "last_used": "2026-01-02T00:00:00",
         "x_name": "X", "y_name": "Y"},
        {"recipe": "R3", "id": 0, "n_points": 13, "x_mm": [0]*13, "y_mm": [0]*13,
         "created_at": "2026-01-03T00:00:00", "last_used": "2026-01-03T00:00:00",
         "x_name": "X", "y_name": "Y"},
    ]
    lib, path = _make_lib(presets)
    try:
        # R1=5 fixed. R2, R3 (created_at 순) → smallest-unused = 1, 2
        ids = {p.recipe: p.id for p in lib.presets}
        assert ids == {"R1": 5, "R2": 1, "R3": 2}, ids
        print(f"  partial migration OK: {ids}")
    finally:
        os.unlink(path)


def test_next_id_smallest_unused():
    """next_id() 가 smallest-unused 반환 — 1,2,4,5 → 3."""
    presets = [
        {"recipe": f"R{i}", "id": i, "n_points": 13, "x_mm": [0]*13, "y_mm": [0]*13,
         "created_at": f"2026-01-0{i}T00:00:00", "last_used": f"2026-01-0{i}T00:00:00",
         "x_name": "X", "y_name": "Y"}
        for i in (1, 2, 4, 5)
    ]
    lib, path = _make_lib(presets)
    try:
        next_id = lib.next_id()
        assert next_id == 3, f"expected 3, got {next_id}"
        print(f"  next_id(1,2,4,5) = {next_id} (expected 3) OK")
    finally:
        os.unlink(path)


def test_next_id_empty():
    lib, path = _make_lib([])
    try:
        assert lib.next_id() == 1
        print("  next_id (empty lib) = 1 OK")
    finally:
        os.unlink(path)


def test_next_id_consecutive():
    """1, 2, 3 다 사용 → next = 4."""
    presets = [
        {"recipe": f"R{i}", "id": i, "n_points": 13, "x_mm": [0]*13, "y_mm": [0]*13,
         "created_at": "2026-01-01T00:00:00", "last_used": "2026-01-01T00:00:00",
         "x_name": "X", "y_name": "Y"}
        for i in (1, 2, 3)
    ]
    lib, path = _make_lib(presets)
    try:
        assert lib.next_id() == 4
        print("  next_id(1,2,3) = 4 OK")
    finally:
        os.unlink(path)


def test_save_load_roundtrip():
    """id 가 save 후 load 에서 보존됨."""
    presets = [
        {"recipe": "R1", "id": 7, "n_points": 13, "x_mm": [0]*13, "y_mm": [0]*13,
         "created_at": "2026-01-01T00:00:00", "last_used": "2026-01-01T00:00:00",
         "x_name": "X", "y_name": "Y"},
    ]
    lib, path = _make_lib(presets)
    try:
        lib.save()  # 다시 저장
        lib2 = CoordLibrary(path=path)
        assert lib2.presets[0].id == 7, lib2.presets[0].id
        print(f"  save/load roundtrip id={lib2.presets[0].id} OK")
    finally:
        os.unlink(path)


def test_add_or_touch_assigns_id():
    """신규 add_or_touch → next_id() 자동 부여."""
    import numpy as np
    lib, path = _make_lib([])
    try:
        x = np.array([0, 1, 2], dtype=float)
        y = np.array([0, 0, 0], dtype=float)
        preset, added = lib.add_or_touch("R_NEW", x, y, save=False)
        assert added is True
        assert preset.id == 1, f"expected id=1, got {preset.id}"
        # 한 번 더 — 다른 (recipe, x_name, y_name) 조합이라 신규
        preset2, added2 = lib.add_or_touch("R_NEW2", x, y, save=False)
        assert added2 is True
        assert preset2.id == 2
        print(f"  add_or_touch id assignment: 1, 2 OK")
    finally:
        os.unlink(path)


def test_delete_then_add_fills_gap():
    """삭제 후 빈 번호 → 다음 add 가 채움."""
    import numpy as np
    presets = [
        {"recipe": f"R{i}", "id": i, "n_points": 13, "x_mm": [0]*13, "y_mm": [0]*13,
         "created_at": f"2026-01-0{i}T00:00:00", "last_used": f"2026-01-0{i}T00:00:00",
         "x_name": "X", "y_name": "Y"}
        for i in (1, 2, 3)
    ]
    lib, path = _make_lib(presets)
    try:
        # id=2 삭제
        target = next(p for p in lib.presets if p.id == 2)
        lib.delete(target, save=False)
        # 새 add — 빈 번호 2 채움
        preset, _ = lib.add_or_touch(
            "R_NEW", np.array([0,1,2], dtype=float), np.array([0,0,0], dtype=float),
            save=False,
        )
        assert preset.id == 2, f"expected id=2 (filled gap), got {preset.id}"
        print(f"  delete+add fills gap: id={preset.id} OK")
    finally:
        os.unlink(path)


def main():
    tests = [
        test_migration_no_id,
        test_migration_partial_id,
        test_next_id_smallest_unused,
        test_next_id_empty,
        test_next_id_consecutive,
        test_save_load_roundtrip,
        test_add_or_touch_assigns_id,
        test_delete_then_add_fills_gap,
    ]
    print(f"running {len(tests)} tests:")
    for t in tests:
        print(f"\n[{t.__name__}]")
        t()
    print(f"\n=== ALL {len(tests)} TESTS PASSED ===")


if __name__ == "__main__":
    main()
