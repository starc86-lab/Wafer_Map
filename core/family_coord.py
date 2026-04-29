"""
가족 (single 입력) 좌표 정책 — 검증 + 좌표 set 결정.

가족 = 한 입력 (A 또는 B) 의 모든 wafer. 가족은 단일 RECIPE 공유 (PRE/POST 호환).
가족 내 wafer 들은 공통 좌표 set 들 공유 — 같은 RECIPE 의 같은 좌표 PARA 이름은
좌표값 동일 보장 (사용자 정책 2026-04-30).

본 모듈은 검증 (`validate_family_recipe`) + 좌표 페어 list 추출 + 페어 좌표
조회 헬퍼 제공. 시각화 흐름 (`_visualize_single` 등) 에서 호출.

순환 import 방지를 위해 widgets/main_window 의 `_pad_slot` / `_rep_suffix` 는
자체 구현.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from core.input_validation import ValidationWarning
from core.recipe_util import recipes_compatible
from main import ParseResult


# ── helpers (main_window 와 동기, 순환 import 회피용 자체 구현) ────────────
def _pad_slot(slot) -> str:
    try:
        return f"{int(slot):02d}"
    except (ValueError, TypeError):
        return str(slot)


def _rep_suffix(wafer_id: str) -> str:
    idx = wafer_id.rfind("__rep")
    if idx < 0:
        return ""
    tail = wafer_id[idx + 2:]
    return f" ({tail})"


def _wafer_label(wafer) -> str:
    """`LX001.07` 또는 `LX001.07 (rep1)` 형식 wafer label."""
    return f"{wafer.lot_id}.{_pad_slot(wafer.slot_id)}{_rep_suffix(wafer.wafer_id)}"


# ── 가족 RECIPE 단일성 검증 ──────────────────────────────────────────────
def family_recipe(result: ParseResult) -> str:
    """가족 RECIPE — 가장 흔한 (mode) recipe 를 baseline 으로 채택.

    하나의 outlier wafer 가 baseline 을 흐트리지 않게 mode 사용. 단,
    `validate_family_recipe` 가 outlier 를 detect 하므로 baseline 자체는
    오염되지 않음.
    """
    if not result.wafers:
        return ""
    counter = Counter(w.recipe for w in result.wafers.values())
    return counter.most_common(1)[0][0]


def validate_family_recipe(result: ParseResult) -> list[ValidationWarning]:
    """가족 RECIPE 단일성 검증 — PRE/POST 베이스 비교로 호환 여부 판정.

    다른 RECIPE wafer 가 있으면 `single_recipe_mismatch` (error). 메시지에
    LOT.SLOT 라벨 + 그 wafer 의 RECIPE + 가족 baseline RECIPE 명시.
    """
    if not result.wafers:
        return []
    base = family_recipe(result)
    mismatched = [
        w for w in result.wafers.values()
        if not recipes_compatible(w.recipe, base)
    ]
    if not mismatched:
        return []
    labels = ", ".join(
        f"{_wafer_label(w)}: {w.recipe}" for w in mismatched
    )
    msg = f"RECIPE 다름 — {labels} vs 가족: {base}"
    return [ValidationWarning(
        code="single_recipe_mismatch",
        severity="error",
        message=msg,
    )]
