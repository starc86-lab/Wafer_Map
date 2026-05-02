"""
RECIPE 이름 처리 유틸 — 사내 RECIPEID 규칙 기반.

규칙 (사용자 정책 2026-04-27):
- 구분자는 `_` 만 (RECIPEID 규칙)
- 대소문자 무관
- _PRE / _POST 토큰은 끝 또는 중간 어디 있어도 제외 후 베이스 비교
  (맨 앞 PRE_ / POST_ 케이스는 사내 데이터에 존재 안 함 — 처리 X)
- DELTA 모드 호환 판정 + 라이브러리 매칭 양쪽에서 사용 (단일 진실 원천)
"""
from __future__ import annotations

import re

# PRE/POST 토큰 제거 패턴 — 앞에 `_` 1+ 필요 (시작 위치 제외). 뒤에는 다음 `_`
# 또는 문자열 끝 (lookahead). 대소문자 무관.
#
# 매치 케이스:
#   끝:    Z_TEST_01__PRE        → Z_TEST_01
#          Z_TEST_01_POST        → Z_TEST_01
#   중간:  Z_PRE_TEST_01         → Z_TEST_01
#          Z_TEST_PRE_01         → Z_TEST_01
#          Z_TEST_PRE_POST_01    → Z_TEST_01 (PRE/POST 양쪽 다 제거)
# 미매치:
#   맨 앞: PRE_TEST_01            → PRE_TEST_01 (앞 `_` 없음)
#   부분일치: Z_PRESET_01         → Z_PRESET_01 (PRE 뒤 SET, lookahead 미충족)
#   비표준 구분자: Z_TEST_01-POST → Z_TEST_01-POST (하이픈 sep)
#                  Z_TEST_01POST  → Z_TEST_01POST (구분자 없음)
_PRE_POST_RE = re.compile(r"_+(PRE|POST)(?=_|$)", re.IGNORECASE)


def strip_pre_post(recipe: str) -> str:
    """RECIPE 의 `_PRE` / `_POST` 토큰 (끝 또는 중간) 제거 + 대소문자 통일."""
    return _PRE_POST_RE.sub("", recipe.strip().upper())


def recipes_compatible(ra: str, rb: str) -> bool:
    """두 RECIPE 가 호환 (같은 공정으로 간주) 인지.

    `_PRE` / `_POST` 토큰을 끝 / 중간에서 제외 후 베이스 비교. 양방향
    (A=POST / B=PRE 도 OK).

    빈 RECIPE 처리 (사용자 정책 2026-05-03):
    - 둘 다 빈 문자열 → True (모두 동일하게 비어있음, 호환)
    - 한쪽만 빈 문자열 → False (정상 vs 누락 — 명백히 다름)

    이전 정책 (2026-04-27, "한쪽 비어있으면 True") 은 자연 데이터의 일부 wafer
    RECIPE 누락에 대한 false alarm 회피 의도였으나, 사용자 정책 명시 ("정상 데이터
    = RECIPE 모두 채워짐, 가족 모두 동일") 와 충돌해 strict 로 변경. 빈 RECIPE
    자체를 비정상 데이터 신호로 판단.
    """
    if not ra and not rb:
        return True
    if not ra or not rb:
        return False
    return strip_pre_post(ra) == strip_pre_post(rb)
