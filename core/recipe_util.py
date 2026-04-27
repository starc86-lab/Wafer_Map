"""
RECIPE 이름 처리 유틸 — 사내 RECIPEID 규칙 기반.

규칙 (사용자 정책 2026-04-27):
- 구분자는 `_` 만 (RECIPEID 규칙)
- 대소문자 무관
- _PRE / _POST suffix 는 항상 제외 후 베이스 비교
- DELTA 모드 호환 판정 + 라이브러리 매칭 양쪽에서 사용 (단일 진실 원천)
"""
from __future__ import annotations

import re

# PRE/POST suffix 제거 패턴 — 구분자 `_` 1+ 매칭. 대소문자 무관.
_PRE_POST_TAIL_RE = re.compile(r"_+(PRE|POST)$", re.IGNORECASE)


def strip_pre_post(recipe: str) -> str:
    """RECIPE 끝의 `_PRE` / `_POST` suffix 제거 + 대소문자 통일.

    예:
        Z_TEST_01__PRE  → Z_TEST_01
        Z_TEST_01__POST → Z_TEST_01
        Z_TEST_01_post  → Z_TEST_01
        Z_TEST_01       → Z_TEST_01 (suffix 없음, 그대로)
        Z_TEST_01POST   → Z_TEST_01POST (구분자 없음, 강제 매칭 X)
    """
    return _PRE_POST_TAIL_RE.sub("", recipe.strip().upper())


def recipes_compatible(ra: str, rb: str) -> bool:
    """두 RECIPE 가 호환 (같은 공정으로 간주) 인지.

    `_PRE` / `_POST` suffix 항상 제외 후 베이스 비교. 양방향 (A=POST/B=PRE 도 OK).
    한쪽이라도 비어있으면 비교 불가 → True (호환 처리, 메시지 안 띄움).
    """
    if not ra or not rb:
        return True
    return strip_pre_post(ra) == strip_pre_post(rb)
