"""
가족 좌표 정책 회귀 검증 — baseline vs current 결과 diff.

실행:
    venv/Scripts/python tests/family_compare.py [baseline.json] [current.json]

기본 비교: tests/baseline/results.json vs tests/current/results.json.

각 sample 별로 dict 깊이 비교 → 차이만 출력. 차이 있으면 exit 1.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def diff_value(base, curr, path=""):
    diffs = []
    if isinstance(base, dict) and isinstance(curr, dict):
        keys = set(base) | set(curr)
        for k in sorted(keys):
            p = f"{path}.{k}" if path else k
            if k not in base:
                diffs.append(f"+ {p}: {curr[k]!r}")
            elif k not in curr:
                diffs.append(f"- {p}")
            else:
                diffs.extend(diff_value(base[k], curr[k], p))
    elif isinstance(base, list) and isinstance(curr, list):
        if len(base) != len(curr):
            diffs.append(f"~ {path}: list len {len(base)} → {len(curr)}")
            return diffs
        for i, (b, c) in enumerate(zip(base, curr)):
            diffs.extend(diff_value(b, c, f"{path}[{i}]"))
    else:
        if base != curr:
            diffs.append(f"~ {path}: {base!r} → {curr!r}")
    return diffs


def main():
    base_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/baseline/results.json")
    curr_file = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("tests/current/results.json")

    if not base_file.exists():
        print(f"NO BASELINE: {base_file}")
        return 2
    if not curr_file.exists():
        print(f"NO CURRENT: {curr_file}")
        return 2

    base = json.loads(base_file.read_text(encoding="utf-8"))
    curr = json.loads(curr_file.read_text(encoding="utf-8"))

    all_samples = sorted(set(base) | set(curr))
    any_diff = False
    for name in all_samples:
        b = base.get(name, {})
        c = curr.get(name, {})
        diffs = diff_value(b, c)
        if diffs:
            any_diff = True
            print(f"\n=== {name} ===")
            for d in diffs:
                print(f"  {d}")
    if not any_diff:
        print("No differences.")
    return 1 if any_diff else 0


if __name__ == "__main__":
    sys.exit(main())
