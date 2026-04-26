"""파싱 결과 무결성 검사.

`parse_wafer_csv()` 결과(`ParseResult`)를 받아 데이터 구조 무결성을 검사하고
사용자 표시용 경고 리스트를 반환한다. 검사 항목은 한 곳에 모아 두어 다른
개발자가 추가/수정하기 쉽게 한다.

검사 항목:
- **A** — 모든 wafer 가 동일한 PARAMETER set (이름 + 개수)
- **B** — 모든 wafer 가 동일한 RECIPEID
- **C** — `MAX_DATA_ID == 실제 n` (단, `max_id ∈ {None, 0, 1}` 인 PARA 는 검사 제외;
         단일 평균값 / 측정 실패 단일값 등 시각화 불가능한 PARA 라 무의미)
- **D-1** — 컬럼 헤더 중복 (정규화 후 동일 컬럼 2개 이상; main.py 의 `dup_warnings` 활용)
- **D-2** — 헤더 행 2개 이상 (main.py `_strip_extra_header_rows` 활용)
- **D-3** — (WAFERID, PARAMETER) 조합 중복 (main.py `_group_by_waferid` 의 첫번째 keep + warning)

사용:
    from core.integrity import check_integrity
    warnings = check_integrity(result)
    if warnings:
        # warnings[i].message 를 사용자에게 표시
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from main import ParseResult


@dataclass
class IntegrityWarning:
    """무결성 위반 1건. paste_area 가 둘째 줄에 `⚠ {message}` 형태로 표시."""
    code: str       # 'A' / 'B' / 'C' / 'D1' / 'D2' / 'unknown'
    message: str    # 사용자 표시용 한국어 (`⚠ ` prefix 없이 사유만)


def check_integrity(result: ParseResult) -> list[IntegrityWarning]:
    """ParseResult 무결성 검사. 빈 리스트 = OK.

    검사 순서는 우선순위 (구조적 문제 먼저). 한 번에 여러 위반이 있으면
    모두 누적 반환 (paste_area 가 첫 1건만 둘째 줄에 표시할지 모두 표시할지 결정).
    """
    warnings: list[IntegrityWarning] = []

    if not result.wafers:
        # 호출자(paste_area) 가 wafers=0 케이스를 별도로 잡으므로 여기는 안 옴.
        # 방어적으로 빈 리스트.
        return warnings

    # A — PARA set 일치
    warnings.extend(_check_para_sets(result))

    # B — RECIPE 일치
    warnings.extend(_check_recipe(result))

    # C — MAX_DATA_ID 일치
    warnings.extend(_check_max_data_id(result))

    # D-1 — 컬럼 헤더 중복 (main.py 의 dup_warnings 변환)
    warnings.extend(_check_duplicate_columns(result))

    # D-2 — 헤더 행 2개 이상 (main.py 의 _strip_extra_header_rows 결과 변환)
    warnings.extend(_check_extra_header_rows(result))

    # D-3 — (WAFERID, PARAMETER) 조합 중복 (main.py 의 _group_by_waferid 결과 변환)
    warnings.extend(_check_duplicate_wafer_rows(result))

    return warnings


# ── 개별 검사 ────────────────────────────────────────────────

def _check_para_sets(result: ParseResult) -> list[IntegrityWarning]:
    """A 검사 — 모든 wafer 의 PARAMETER set 동일 여부."""
    para_sets = [frozenset(w.parameters.keys()) for w in result.wafers.values()]
    if len(set(para_sets)) <= 1:
        return []
    # 어떤 PARA 가 wafer 별로 다른지 파악 — union 과 intersection 차이
    union = set().union(*para_sets)
    intersection = set.intersection(*(set(p) for p in para_sets))
    diff_paras = sorted(union - intersection)
    if not diff_paras:
        return [IntegrityWarning("A", "wafer별 PARA 불일치")]
    head = ", ".join(diff_paras[:3])
    tail = f" 외 {len(diff_paras) - 3}개" if len(diff_paras) > 3 else ""
    return [IntegrityWarning("A", f"wafer별 PARA 불일치 ({head}{tail})")]


def _check_recipe(result: ParseResult) -> list[IntegrityWarning]:
    """B 검사 — 모든 wafer 의 RECIPEID 동일 여부. 빈 RECIPE 는 무시."""
    recipes = sorted({w.recipe for w in result.wafers.values() if w.recipe})
    if len(recipes) <= 1:
        return []
    return [IntegrityWarning("B", f"RECIPE 다름 ({', '.join(recipes)})")]


def _check_max_data_id(result: ParseResult) -> list[IntegrityWarning]:
    """C 검사 — MAX_DATA_ID == 실제 n. max_id ∈ {None, 0, 1} 제외.

    여러 wafer × PARA 에서 발견되면 첫 케이스만 메시지에, 추가는 "외 N건".
    """
    mismatches: list[tuple[str, int, int]] = []   # (para_name, max_id, n)
    for w in result.wafers.values():
        for name, rec in w.parameters.items():
            if rec.max_data_id is None or rec.max_data_id in (0, 1):
                continue
            if rec.max_data_id != rec.n:
                mismatches.append((name, rec.max_data_id, rec.n))
    if not mismatches:
        return []
    name, mx, n = mismatches[0]
    tail = f" 외 {len(mismatches) - 1}건" if len(mismatches) > 1 else ""
    return [IntegrityWarning(
        "C",
        f"MAX_DATA_ID ({name}: {mx}≠{n}{tail})",
    )]


def _check_duplicate_columns(result: ParseResult) -> list[IntegrityWarning]:
    """D-1 검사 — main.py 의 `_detect_duplicate_columns` 결과(`result.warnings` 에
    `중복 컬럼 감지: ...` 형식으로 누적) 를 사용자 친화 메시지로 변환.

    `중복 컬럼 감지: LOT ID, Lot_ID (2회) — 첫 컬럼만 사용됨` →
    `컬럼 헤더 중복 (LOT ID)` 형식으로.
    """
    out: list[IntegrityWarning] = []
    for w_msg in result.warnings:
        if not w_msg.startswith("중복 컬럼 감지"):
            continue
        # "중복 컬럼 감지: <names> (N회) — ..." 에서 첫 이름 추출
        m = re.search(r"중복 컬럼 감지:\s*([^,()]+)", w_msg)
        first_name = m.group(1).strip() if m else "?"
        out.append(IntegrityWarning("D1", f"헤더 중복 ({first_name})"))
    return out


def _check_extra_header_rows(result: ParseResult) -> list[IntegrityWarning]:
    """D-2 검사 — main.py 의 `_strip_extra_header_rows` 결과(`result.warnings` 에
    `헤더 행 N개 발견 — ...` 형식) 를 변환."""
    out: list[IntegrityWarning] = []
    for w_msg in result.warnings:
        if not w_msg.startswith("헤더 행"):
            continue
        # "헤더 행 N개 발견 — 첫 헤더만 사용, 이후 행 무시"
        m = re.search(r"헤더 행\s*(\d+)\s*개", w_msg)
        n = m.group(1) if m else "?"
        out.append(IntegrityWarning("D2", f"헤더 행 {n}개"))
    return out


def _check_duplicate_wafer_rows(result: ParseResult) -> list[IntegrityWarning]:
    """D-3 검사 — (WAFERID, PARAMETER) 조합 중복 행 카운트.

    main.py `_group_by_waferid` 가 중복 발견 시 `WAFERID 중복: ...` 형식으로
    `result.warnings` 에 추가. 여러 건 누적될 수 있어 카운트만 해서 1줄 메시지.
    """
    n = sum(1 for w_msg in result.warnings if w_msg.startswith("WAFERID 중복"))
    if n == 0:
        return []
    return [IntegrityWarning("D3", f"WAFERID 중복 {n}")]
