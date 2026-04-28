"""
입력 데이터 정합성 검증 — 단일 `ParseResult` 분석.

호출처가 받는 list 의 각 항목 (`ValidationWarning`) 은 사유 코드 + 메시지 + 심각도.
호출처가 적절한 채널 (paste 영역, ReasonBar 등) 에 표시한다. 본 모듈은 데이터를
수정하지 않음.

검사 대상 4가지 케이스 중 본 모듈이 다루는 1가지 (warn):
- 케이스 2 (헤더 행 2개+): main.py 의 `_strip_extra_header_rows` 가 자동 처리.
  메시지 X.
- 케이스 3: wafer 별 PARA set 다름 → 직접 분석 (severity=warn, Run 활성).
  사내 실제 데이터에 흔한 케이스. VALUE 콤보 union + `_visualize_single` 이
  PARA 없는 wafer 는 NaN cell + (no data) 타이틀로 처리.
- 케이스 4: (WAFERID, PARAMETER) 재등장 → cell 타이틀의 __rep suffix 로 인지.
  메시지 X.

케이스 1 (필수 컬럼 누락) 은 `main.parse_wafer_csv` 가 `MissingColumnsError` 로
raise — 호출처 (paste_area) 가 catch 후 자체 메시지 표시. 본 모듈 영역 외.

severity 정책 — 호출자가 Run 비활성 결정에 사용:
- `error` (Run 차단 / 시각화 불가): 현재 단일 입력 검증에선 미사용
- `warn`  (Run 활성 / 주의 알림): 케이스 3 (PARA set 다름) / DELTA 모드 PARA·RECIPE·반복 측정
- `ok`    (Run 활성 / 성공 알림): DELTA 좌표 fallback 성공
- `info`  (Run 활성 / 정보 알림): 케이스 2, 4
"""
from __future__ import annotations

from dataclasses import dataclass

from main import ParseResult


@dataclass
class ValidationWarning:
    """검증 결과 1건.

    Fields:
        code: 사유 식별자 (분기/테스트/디버그용)
        severity: "error" / "warn" / "info"
        message: 사용자 표시 한국어 텍스트
    """
    code: str
    severity: str
    message: str


def validate(result: ParseResult) -> list[ValidationWarning]:
    """ParseResult 의 정합성 검증. 빈 리스트 = OK.

    검사 항목 추가/변경 시 본 함수만 손대면 됨. 메타 (raw 처리 결과) + ParseResult
    분석 (PARA set 비교) 양쪽을 사용.
    """
    warnings: list[ValidationWarning] = []

    if not result.wafers:
        return warnings  # 방어적 — 빈 결과는 호출처가 별도 처리

    # 케이스 2 (헤더 행 2개+) 메시지 제거 — 파서가 첫 헤더만 사용 + 데이터 합치기로
    # 자동 처리. 실수 반복이면 `repeat_measurement_groups` 가 __rep1 으로 분리해
    # 사용자 인지. 의도 통합이면 그래프로 자연스럽게 보임. 별도 알림 불필요.

    # 케이스 3 — wafer 별 PARA set 다름 — warn (Run 활성)
    # 정책 (사용자 정책 2026-04-27, #6): 사내 실제 데이터에 wafer 별 PARA 다른
    # 케이스 다수 존재. 이전엔 error 로 차단했지만 너무 엄격. VALUE 콤보는
    # union 으로 채우고, 선택한 PARA 가 없는 wafer 는 _visualize_single 이
    # NaN cell + (no data) 타이틀로 처리.
    para_sets = [frozenset(w.parameters.keys()) for w in result.wafers.values()]
    if len(set(para_sets)) > 1:
        union = set().union(*para_sets)
        intersection = set.intersection(*(set(p) for p in para_sets))
        diff = sorted(union - intersection)
        head = ", ".join(diff[:3])
        tail = f" 외 {len(diff) - 3}개" if len(diff) > 3 else ""
        warnings.append(ValidationWarning(
            code="para_set_mismatch",
            severity="warn",
            message=(f"일부 웨이퍼 PARA 다름 ({head}{tail}) — "
                     "없는 wafer 는 NaN cell 로 표시"),
        ))

    # 케이스 4 (반복 측정) 메시지 제거 — cell 타이틀의 __rep1/__rep2 suffix 가
    # 시각적 인지 충분. 별도 알림 불필요.

    return warnings
