"""
PARA 합성 데이터 모델 — 단일 진실원.

`MainWindow` 가 PARA 조합 다이얼로그 결과를 받아 `CombinedItem` 으로 만들고
`CombinedState` 에 누적. 콤보 sentinel / wafer.parameters 임시 키 / 친화 라벨
모두 여기서 결정 — UI 는 이 모델만 보고 동작.

Qt 의존 없음 (pure data + helpers). UI 코드 (`widgets/main_window.py`,
`widgets/para_combine_dialog.py`) 가 import 해 사용.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Qt itemData sentinel — 단일 PARA(str) 와 구분되는 tuple-tag 형식.
# 모든 sentinel 생성/검사는 헬퍼 경유 (포맷 산재 방지, 사용자 정책 2026-04-29).
COMBINED_TAG = "__combined__"


def is_combined_data(data) -> bool:
    """itemData 가 합성 sentinel tuple 인지 판정."""
    return isinstance(data, tuple) and len(data) >= 1 and data[0] == COMBINED_TAG


def wrap_if_composite(name: str) -> str:
    """operand 가 합성 친화 키 (` + ` 또는 ` ∪ ` 포함) 면 괄호로 감싸 우선순위 명시.

    예: 'T1' → 'T1', 'T1 + T2' → '(T1 + T2)', '(T1 ∪ T2) + T3' → '((T1 ∪ T2) + T3)'.
    임의 깊이 합성에서 sum/concat 혼합 시 모호성 제거 (사용자 정책 2026-04-29).
    """
    if " + " in name or " ∪ " in name:
        return f"({name})"
    return name


@dataclass
class CombinedItem:
    """한 합성 단위 — N-ary operands + per-operand coord + mode.

    mode:
      - "concat" : 두 (이상) 점 집합을 단순 연결 (다른 좌표 합치는 케이스)
      - "sum"    : 모든 operand 좌표 동일 — 값 element-wise 합. coords 모두 같음.

    invariant: len(operands) == len(coords) >= 2. mode=="sum" 이면 coords 전부 동일.
    operand 는 plain PARA 이름 ("T1") 또는 다른 합성의 친화 키 ("T1 + T2") —
    recursive 단계에서 자동 활용. 친화 키 (`v_key`/`x_key`/`y_key`) 는
    wafer.parameters 에 임시 등록될 사용자 친화 이름.
    """
    operands: list[str]
    coords: list[tuple[str, str]]
    mode: str = "concat"

    @property
    def v_sentinel(self) -> tuple:
        return (COMBINED_TAG, "v", self.mode, tuple(self.operands))

    @property
    def coord_sentinel(self) -> tuple:
        return (COMBINED_TAG, "c", self.mode, tuple(self.coords))

    @property
    def v_key(self) -> str:
        # sum: ` + ` (element-wise 덧셈) / concat: ` ∪ ` (합집합)
        # 합성 operand 자동 괄호 — 임의 깊이 sum/concat 혼합 시 우선순위 명시
        sep = " + " if self.mode == "sum" else " ∪ "
        return sep.join(wrap_if_composite(op) for op in self.operands)

    @property
    def x_key(self) -> str:
        if self.mode == "sum":
            return self.coords[0][0]
        return " ∪ ".join(wrap_if_composite(c[0]) for c in self.coords)

    @property
    def y_key(self) -> str:
        if self.mode == "sum":
            return self.coords[0][1]
        return " ∪ ".join(wrap_if_composite(c[1]) for c in self.coords)


@dataclass
class CombinedState:
    """합성 항목 누적 상태 — 콤보 sentinel/wafer.parameters 임시 키의 단일 진실원.

    paste 변경 / Run Analysis 와 무관하게 사용자가 "Para 조합" 으로 추가하는
    동안만 누적. paste 변경 시 호출자가 `clear()` 호출 → 임시 키 정리도
    `temp_keys()` 가 반환하는 키 set 기준으로 일괄 처리.
    """
    items: list[CombinedItem] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def add(self, item: CombinedItem) -> None:
        """같은 v_sentinel 이미 있으면 무시 (재선택만, 중복 추가 X)."""
        for existing in self.items:
            if existing.v_sentinel == item.v_sentinel:
                return
        self.items.append(item)

    def get_by_v_sentinel(self, v_data) -> CombinedItem | None:
        for item in self.items:
            if item.v_sentinel == v_data:
                return item
        return None

    def temp_keys(self) -> set[str]:
        """wafer.parameters 에 등록된 모든 임시 키 (정리용)."""
        keys: set[str] = set()
        for item in self.items:
            keys.update({item.v_key, item.x_key, item.y_key})
        return keys

    def clear(self) -> None:
        self.items.clear()
