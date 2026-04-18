"""
VALUE/X/Y PARAMETER 자동 선택.

- 매칭 조건: 패턴(fnmatch 와일드카드, 대소문자 무관) + 값 개수가 `required_n`과 일치.
- 우선순위: 패턴 목록 순서 → 같은 패턴 내 알파벳 순 → 매칭 안 된 것(알파벳).
- Y는 X 이름의 suffix 를 물려받아 `Y{suffix}`를 1순위로 사용.

ex.
    available_ns = {"T1": 13, "T1_B": 4, "X": 13, "Y": 13, "GOF": 13}
    select_value(available_ns, ["T*"], required_n=13) -> ("T1", ["T1", "GOF", ..., "T1_B"])
"""
from __future__ import annotations

import fnmatch
from typing import Iterable


def _matches(name: str, pattern: str) -> bool:
    """fnmatch 스타일 와일드카드 매칭 (대소문자 무관)."""
    return fnmatch.fnmatchcase(name.casefold(), pattern.casefold())


def prioritized_list(
    available_ns: dict[str, int],
    patterns: Iterable[str],
    required_n: int,
) -> tuple[list[str], set[str]]:
    """우선순위 정렬된 이름 리스트 + 매칭된 이름 집합.

    - 매칭 그룹: `n == required_n` 이면서 패턴에 맞는 이름. 알파벳 순.
    - 그 다음: 매칭 안 된 나머지 전부 (n 조건 관계없이). 알파벳 순.
    """
    ordered: list[str] = []
    matched_set: set[str] = set()
    for pat in patterns:
        group = sorted(
            name for name, n in available_ns.items()
            if n == required_n
            and name not in matched_set
            and _matches(name, pat)
        )
        ordered.extend(group)
        matched_set.update(group)
    others = sorted(set(available_ns) - matched_set)
    return ordered + others, matched_set


def _fallback_alpha_first(available_ns: dict[str, int], required_n: int) -> str | None:
    """패턴 매칭 실패 시 폴백: `n == required_n` 인 이름 중 알파벳 첫 번째."""
    candidates = sorted(
        name for name, n in available_ns.items() if n == required_n
    )
    return candidates[0] if candidates else None


def select_value(
    available_ns: dict[str, int],
    patterns: Iterable[str],
    required_n: int,
) -> tuple[str | None, list[str]]:
    """VALUE 또는 X용 자동 선택.

    1순위: 패턴 매칭 + `n == required_n` 중 (패턴 순 → 알파벳) 첫
    폴백:  `n == required_n` 중 알파벳 첫
    둘 다 실패: None

    Returns:
        (selected, ordered_list)
    """
    ordered, matched = prioritized_list(available_ns, patterns, required_n)
    selected = next((n for n in ordered if n in matched), None)
    if selected is None:
        selected = _fallback_alpha_first(available_ns, required_n)
    return selected, ordered


def select_y_with_suffix(
    x_name: str | None,
    available_ns: dict[str, int],
    y_patterns: Iterable[str],
    required_n: int,
) -> tuple[str | None, list[str]]:
    """Y 자동 선택 — X suffix 우선, y_patterns 매칭, n 폴백 순.

    1. X가 `X{suffix}` 면 `Y{suffix}` 정확 매칭 시도 (있으면 ordered 맨 앞에 배치)
    2. 실패 시 `y_patterns` 기반 일반 매칭
    3. 그것도 실패 시 `n == required_n` 인 이름 중 알파벳 첫 폴백
    """
    ordered, matched = prioritized_list(available_ns, y_patterns, required_n)

    # 1. X suffix 매칭
    if x_name and x_name[:1].casefold() == "x":
        suffix = x_name[1:]
        preferred = f"Y{suffix}"
        hit = next(
            (
                name for name in available_ns
                if name.casefold() == preferred.casefold()
                and available_ns[name] == required_n
            ),
            None,
        )
        if hit:
            ordered = [hit] + [n for n in ordered if n != hit]
            return hit, ordered

    # 2. y_patterns 매칭
    selected = next((n for n in ordered if n in matched), None)

    # 3. n 일치 알파벳 폴백
    if selected is None:
        selected = _fallback_alpha_first(available_ns, required_n)
    return selected, ordered
