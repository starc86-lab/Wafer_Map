"""
입력 데이터 요약 — `ParseResult` 를 받아 한 곳에서 카운트·검증.

원칙:
  - 파싱 자체는 `main.parse_wafer_csv` 가 담당. 본 모듈은 `ParseResult` 만 입력.
  - 호출처에서 직접 카운트 금지 — 본 모듈 함수만 사용.

호출처:
  - `paste_area` — 자기 입력 한 줄 표시 ("웨이퍼 X장, Parameter N개, 좌표 M개")
  - 향후 새 사유 표시 바, DELTA 사전 검사 등도 본 모듈 재사용
"""
from __future__ import annotations

from dataclasses import dataclass

from core.auto_select import select_xy_pairs
from core.settings import load_settings
from main import ParseResult


@dataclass
class InputSummary:
    """단일 입력의 카운트 결과.

    - n_parameter: 좌표 페어 PARA 를 제외한 나머지 PARAMETER 개수
      (미페어 X/Y 단독은 여기 포함 — 사용자 룰: 미페어는 신경쓰지 말 것)
    - n_coord_pairs: settings.auto_select 의 x_patterns/y_patterns 로 매칭된 X/Y 쌍 수
    """
    n_wafers: int
    n_parameter: int
    n_coord_pairs: int


def summarize(result: ParseResult | None) -> InputSummary:
    """ParseResult → InputSummary. None / 빈 결과는 (0, 0, 0)."""
    if result is None or not result.wafers:
        return InputSummary(0, 0, 0)

    # PARA 합집합 — wafer 별 PARA 다를 가능성 (무결성 검사 A 위반 케이스) 도 안전하게 union
    all_paras: set[str] = set()
    for w in result.wafers.values():
        all_paras.update(w.parameters)

    # 좌표 페어 — 첫 wafer 의 (name -> n) 기준. wafer 별 n 차이는 흔치 않음.
    first = next(iter(result.wafers.values()))
    available_ns = {name: rec.n for name, rec in first.parameters.items()}

    auto = load_settings().get("auto_select", {})
    xpat = auto.get("x_patterns", ["X", "X*"])
    ypat = auto.get("y_patterns", ["Y", "Y*"])
    _, _, x_ordered, _ = select_xy_pairs(available_ns, xpat, ypat)

    n_coord_pairs = len(x_ordered)
    n_parameter = len(all_paras) - 2 * n_coord_pairs

    return InputSummary(
        n_wafers=len(result.wafers),
        n_parameter=n_parameter,
        n_coord_pairs=n_coord_pairs,
    )
