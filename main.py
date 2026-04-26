"""
Wafer Map long-form CSV 파서.

입력: CSV 파일 경로, 클립보드/파일에서 읽은 원시 텍스트, 또는 이미 만든 DataFrame.
출력: ParseResult — {WAFERID: WaferData} 딕셔너리 + 컬럼 매핑 + 경고 목록.

규약 요약 (상세: CLAUDE.md):
- Long-form: 각 행 = 한 웨이퍼 × 한 PARAMETER 레코드.
- 필수 컬럼: WAFERID, LOT ID, SLOTID, PARAMETER, RECIPE, DATA\\d+ (1개 이상).
- 선택 컬럼: MAX_DATA_ID (있으면 검증용, 없거나 실제 DATA 셀 수와 다르면 실제 값 우선).
- 헤더 매칭은 대소문자·공백·언더바 무관 정규화 기반.
- 웨이퍼 그룹핑 키는 WAFERID 문자열 그대로 (LOT.SLOT 분해 금지).
- 한 웨이퍼의 LOT/SLOT/RECIPE는 최빈값 채택.
"""
from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ────────────────────────────────────────────────────────────────
# 기본 컬럼 이름 alias (정규화 전). settings.json에서 확장 가능.
# ────────────────────────────────────────────────────────────────
DEFAULT_COLUMN_ALIASES: dict[str, list[str]] = {
    "waferid":     ["WAFERID", "Wafer ID"],
    "lot_id":      ["LOT ID", "Lot ID"],
    "slot_id":     ["SLOTID", "Slot ID", "SLOT ID"],
    "parameter":   ["PARAMETER", "Parameter"],
    "recipe":      ["RECIPE", "Recipe"],
    "max_data_id": ["MAX_DATA_ID", "Max Data ID"],
}

REQUIRED_KEYS = ("waferid", "lot_id", "slot_id", "parameter", "recipe")
OPTIONAL_KEYS = ("max_data_id",)

# DATA1 / DATA_1 / DATA 1 모두 매칭 (case-insensitive)
DATA_COL_PATTERN = re.compile(r"^data[\s_]?(\d+)$", re.IGNORECASE)


# ────────────────────────────────────────────────────────────────
# Data classes
# ────────────────────────────────────────────────────────────────
@dataclass
class WaferRecord:
    """한 웨이퍼의 한 PARAMETER 측정 레코드."""
    values: np.ndarray             # shape=(n,), float
    n: int                         # 실제 유효 DATA 개수
    max_data_id: int | None        # 원본 MAX_DATA_ID (검증용, 없을 수 있음)


@dataclass
class WaferData:
    """한 웨이퍼의 전체 정보."""
    wafer_id: str
    lot_id: str
    slot_id: str
    recipe: str
    parameters: dict[str, WaferRecord]
    extra_meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    """파싱 결과 번들."""
    wafers: dict[str, WaferData]
    column_mapping: dict[str, str]   # 논리 키 → 실제 헤더 이름
    data_columns: list[str]          # 정렬된 DATA 컬럼 이름
    warnings: list[str]              # N 불일치 등 안내 (GUI가 팝업)
    delimiter: str = ""              # 자동 감지된 구분자 (\t / , / ; / |). DataFrame 직접 전달 시 빈 문자열


class MissingColumnsError(Exception):
    """필수 컬럼 자동 매칭 실패. GUI는 이 예외를 catch 후 매핑 다이얼로그로 fallback."""

    def __init__(self, missing: list[str], available: list[str]):
        self.missing = missing
        self.available = available
        super().__init__(f"필수 컬럼 누락: {missing} / 실제 컬럼: {available}")


class DelimiterDetectError(Exception):
    """csv.Sniffer 가 구분자(`,`, `\\t`, `;`, `|`) 자동 감지 실패."""


# ────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────
def parse_wafer_csv(
    source: str | Path | pd.DataFrame,
    *,
    aliases: dict[str, list[str]] | None = None,
    column_mapping_override: dict[str, str] | None = None,
    delimiter: str = "",
    extra_warnings: list[str] | None = None,
) -> ParseResult:
    """
    Long-form 웨이퍼 측정 데이터 파싱.

    Args:
        source: CSV 경로 / 클립보드·파일에서 읽은 원시 텍스트 / 이미 만든 DataFrame.
        aliases: 사용자 지정 컬럼 이름 별칭 (기본값과 merge됨).
        column_mapping_override: GUI 매핑 다이얼로그가 넘겨주는 {논리 키: 실제 헤더}.
        delimiter: 외부에서 이미 감지된 구분자(원시 텍스트→DataFrame 변환을 paste_area 가
            먼저 수행한 케이스). 없으면 _load_dataframe 결과 사용.
        extra_warnings: paste_area 가 _load_dataframe 으로 이미 받은 텍스트 단계 경고
            (헤더 행 2개 이상 등). DataFrame 으로 재호출 시 다시 감지 못 하니 명시 전달.

    Raises:
        MissingColumnsError: 필수 컬럼 자동 매칭 실패 + 오버라이드도 없을 때.
        DelimiterDetectError: 원시 텍스트 sep 자동 감지 실패.
    """
    df, detected_sep, load_warnings = _load_dataframe(source)
    sep_used = delimiter or detected_sep
    extra = list(extra_warnings or []) + load_warnings

    col_map = _match_columns(
        list(df.columns),
        aliases=_merge_aliases(aliases),
        override=column_mapping_override,
    )
    data_cols = _extract_data_columns(list(df.columns))
    if not data_cols:
        raise MissingColumnsError(missing=[r"DATA\d+"], available=list(df.columns))

    dup_warnings = _detect_duplicate_columns(list(df.columns))
    wafers, warnings = _group_by_waferid(df, col_map, data_cols)
    return ParseResult(
        wafers=wafers,
        column_mapping=col_map,
        data_columns=data_cols,
        warnings=extra + dup_warnings + warnings,
        delimiter=sep_used,
    )


# ────────────────────────────────────────────────────────────────
# Internals
# ────────────────────────────────────────────────────────────────
def _normalize(name: str) -> str:
    """헤더 정규화: 소문자 + 공백·언더바·하이픈 제거.

    대시 포함 — `Lot-ID` / `LOT ID` / `lot_id` 모두 `lotid` 로 매칭.
    """
    return re.sub(r"[\s_\-]+", "", str(name)).lower()


def _merge_aliases(user: dict[str, list[str]] | None) -> dict[str, list[str]]:
    merged = {k: list(v) for k, v in DEFAULT_COLUMN_ALIASES.items()}
    if user:
        for k, lst in user.items():
            merged.setdefault(k, []).extend(lst)
    return merged


def _preclean(text: str) -> str:
    """클립보드 / Word / PDF 복사 흔적 정리.

    - 유니코드 minus(`−`, U+2212) → ASCII `-`
    - Non-breaking space(U+00A0) → 일반 공백
    - Zero-width space(U+200B) → 제거
    - UTF-8 BOM 제거
    pd.to_numeric 이 ASCII 만 인식하므로 숫자 NaN 화 방지.

    중복 헤더 행 제거는 `_strip_extra_header_rows` 가 별도 처리 (두번째 헤더 +
    이후 행 모두 truncate, warning 누적).
    """
    text = (
        text.replace("\u2212", "-")
        .replace("\u00a0", " ")
        .replace("\u200b", "")
        .replace("\ufeff", "")
    )
    return text


def _strip_extra_header_rows(text: str) -> tuple[str, int]:
    """헤더 행이 2번 이상 등장하면 두번째 헤더 + 그 이후 모두 truncate.

    사용자가 두 batch 데이터를 한 번에 paste 한 케이스 (다른 lot 의 동일 시스템
    출력) 대응. 첫 batch 만 안전하게 사용 + warning 으로 알림.

    반환: `(정리된 텍스트, 추가 헤더 개수)`. 추가 헤더 = 0 이면 변경 없음.
    """
    lines = text.splitlines()
    if not lines:
        return text, 0
    header = lines[0].strip()
    if not header:
        return text, 0
    truncate_at: int | None = None
    n_extra = 0
    for i in range(1, len(lines)):
        if lines[i].strip() == header:
            if truncate_at is None:
                truncate_at = i
            n_extra += 1
    if truncate_at is None:
        return text, 0
    return "\n".join(lines[:truncate_at]), n_extra


def _load_dataframe(
    source: str | Path | pd.DataFrame,
) -> tuple[pd.DataFrame, str, list[str]]:
    """소스를 DataFrame 으로 로드 + 사용된 구분자 + 로드 단계 경고 반환.

    구분자 자동 감지 — `csv.Sniffer` 로 `, \\t ; |` 4종 중 결정. 실패 시
    `DelimiterDetectError` raise (paste_area 가 catch 후 사용자 안내).
    DataFrame 직접 전달 시 구분자 정보 없음 → 빈 문자열.

    extra_warnings: 텍스트 정제 단계에서 발견된 경고 (현재는 헤더 행 2개 이상).
    parse_wafer_csv 가 받아서 ParseResult.warnings 에 누적.
    """
    if isinstance(source, pd.DataFrame):
        return source.copy(), "", []
    if isinstance(source, (str, Path)):
        s = str(source)
        # 개행/탭이 있으면 원시 텍스트, 아니면 파일 경로로 해석
        if "\n" in s or "\t" in s:
            s = _preclean(s)
            extra_warnings: list[str] = []
            # D-2: 헤더 행 2개 이상이면 두번째부터 truncate + warning
            s, n_extra = _strip_extra_header_rows(s)
            if n_extra > 0:
                extra_warnings.append(
                    f"헤더 행 {n_extra + 1}개 발견 — 첫 헤더만 사용, 이후 행 무시"
                )
            try:
                # 첫 8KB 만 sample (긴 paste 의 sniff 비용 제한)
                dialect = csv.Sniffer().sniff(s[:8192], delimiters=",\t;|")
                sep = dialect.delimiter
            except csv.Error as e:
                raise DelimiterDetectError(str(e))
            return pd.read_csv(io.StringIO(s), sep=sep), sep, extra_warnings
        path = Path(s)
        if not path.exists():
            raise FileNotFoundError(path)
        # 파일 경로 모드 — pandas 자동 감지 (engine="python", sep=None)
        df = pd.read_csv(path, sep=None, engine="python")
        return df, "", []
    raise TypeError(f"지원하지 않는 source 타입: {type(source)}")


def _match_columns(
    columns: list[str],
    *,
    aliases: dict[str, list[str]],
    override: dict[str, str] | None,
) -> dict[str, str]:
    col_map: dict[str, str] = {}
    norm_to_orig = {_normalize(c): c for c in columns}

    for key in (*REQUIRED_KEYS, *OPTIONAL_KEYS):
        if override and key in override and override[key] in columns:
            col_map[key] = override[key]
            continue
        for alias in aliases.get(key, []):
            actual = norm_to_orig.get(_normalize(alias))
            if actual is not None:
                col_map[key] = actual
                break

    missing = [k for k in REQUIRED_KEYS if k not in col_map]
    if missing:
        raise MissingColumnsError(missing=missing, available=columns)
    return col_map


def _detect_duplicate_columns(columns: list[str]) -> list[str]:
    """동일 헤더(정규화 후) 2개 이상 감지 → 경고 문자열 목록.

    pandas 는 동명 컬럼을 `Name`, `Name.1` 로 자동 suffix 처리하지만, 사용자 의도상
    원본 헤더 중복이면 데이터 손실·혼동 위험. 정규화 후 비교로 `LOT ID` / `Lot_ID`
    같은 동의어 중복도 잡음.
    """
    from collections import Counter
    warns: list[str] = []
    # pandas 의 `.N` suffix 는 벗긴 후 정규화 비교
    raw = [re.sub(r"\.\d+$", "", str(c)) for c in columns]
    norm_counts = Counter(_normalize(r) for r in raw if r)
    for norm, cnt in norm_counts.items():
        if cnt <= 1 or not norm:
            continue
        # 정규화 결과가 같은 원본 헤더들 수집
        origs = sorted({r for r in raw if _normalize(r) == norm})
        # 정규화 매칭상 첫 컬럼만 사용됨 (pandas `.1` suffix 가 정규화 결과 다르게 만듦).
        warns.append(f"중복 컬럼 감지: {', '.join(origs)} ({cnt}회) — 첫 컬럼만 사용됨")
    return warns


def _extract_data_columns(columns: list[str]) -> list[str]:
    """헤더에서 DATA\\d+ 패턴만 골라 숫자 suffix 오름차순 정렬."""
    hits: list[tuple[int, str]] = []
    for c in columns:
        m = DATA_COL_PATTERN.match(str(c).strip())
        if m:
            hits.append((int(m.group(1)), c))
    hits.sort(key=lambda x: x[0])
    return [c for _, c in hits]


def _row_values(row: pd.Series, data_cols: list[str]) -> np.ndarray:
    """한 행의 DATA 컬럼에서 유효한 값 배열.

    정책: 뒤쪽 NaN을 잘라냄 (`MAX_DATA_ID` 뒤쪽은 빈칸이라는 데이터 특성).
    중간 NaN은 보존 (의도적 결측일 수 있음).
    """
    arr = pd.to_numeric(row[data_cols], errors="coerce").to_numpy(dtype=float)
    valid = ~np.isnan(arr)
    if not valid.any():
        return arr[:0]
    last = int(np.where(valid)[0].max())
    return arr[: last + 1]


def _mode_str(series: pd.Series) -> str:
    """결측 제외 최빈값 (문자열). 동률이면 먼저 등장한 값."""
    vals = series.dropna().astype(str)
    if vals.empty:
        return ""
    return Counter(vals).most_common(1)[0][0]


def _group_by_waferid(
    df: pd.DataFrame,
    col_map: dict[str, str],
    data_cols: list[str],
) -> tuple[dict[str, WaferData], list[str]]:
    warnings: list[str] = []
    wafers: dict[str, WaferData] = {}

    wid_col = col_map["waferid"]
    param_col = col_map["parameter"]
    lot_col = col_map["lot_id"]
    slot_col = col_map["slot_id"]
    recipe_col = col_map["recipe"]
    max_col = col_map.get("max_data_id")

    # Excel 셀 포맷 이슈로 WAFERID 앞뒤 공백 섞이면 같은 웨이퍼가 두 그룹으로 분산됨.
    # groupby 전에 일괄 strip → 같은 WAFERID 로 합쳐지게.
    df = df.copy()
    df[wid_col] = df[wid_col].astype(str).str.strip()

    for wid_raw, subset in df.groupby(wid_col, sort=False):
        wid = str(wid_raw)
        wafer = WaferData(
            wafer_id=wid,
            lot_id=_mode_str(subset[lot_col]),
            slot_id=_mode_str(subset[slot_col]),
            recipe=_mode_str(subset[recipe_col]),
            parameters={},
        )

        for _, row in subset.iterrows():
            param_name = str(row[param_col]).strip()
            if not param_name or param_name.lower() == "nan":
                continue

            # 같은 (WAFERID, PARAMETER) 조합 중복 — warning 만. 값 자체는 0.2.0 동작
            # 유지(dict 덮어쓰기 → 마지막 행 keep). 변화 최소화 목적.
            if param_name in wafer.parameters:
                warnings.append(
                    f"WAFERID 중복: {wid}, PARAMETER={param_name} → 마지막 행 사용"
                )

            values = _row_values(row, data_cols)
            n_actual = len(values)

            max_id: int | None = None
            if max_col is not None and pd.notna(row[max_col]):
                try:
                    max_id = int(row[max_col])
                except (ValueError, TypeError):
                    max_id = None
                if max_id is not None and max_id != n_actual:
                    warnings.append(
                        f"WAFERID={wid}  PARAMETER={param_name}: "
                        f"MAX_DATA_ID={max_id} ≠ 실제 DATA 개수={n_actual} → 실제값 사용"
                    )

            wafer.parameters[param_name] = WaferRecord(
                values=values, n=n_actual, max_data_id=max_id
            )

        # groupby 가 같은 strip 후 wid 를 여러번 넘기면 (공백 섞임) 뒷 것이 덮어쓰게 둠.
        # 합치고 싶으면 별도 머지 로직 필요하지만, 실사용에서 드문 케이스.
        wafers[wid] = wafer

    return wafers, warnings


# ────────────────────────────────────────────────────────────────
# CLI 검증
# ────────────────────────────────────────────────────────────────
def _cli() -> None:
    import sys

    # Windows 콘솔 한글 깨짐 대비 — reconfigure 미지원 환경이면 조용히 통과
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    path = sys.argv[1] if len(sys.argv) > 1 else "samples/sample_data.csv"
    result = parse_wafer_csv(path)

    print(f"파일: {path}")
    print(f"컬럼 매핑: {result.column_mapping}")
    print(f"DATA 컬럼 ({len(result.data_columns)}개): {result.data_columns}")
    print(f"웨이퍼 수: {len(result.wafers)}")
    print()

    for w in result.wafers.values():
        print(f"── WAFERID={w.wafer_id}  LOT={w.lot_id}  SLOT={w.slot_id}  RECIPE={w.recipe}")
        for pname, rec in w.parameters.items():
            preview_n = min(6, rec.n)
            preview = np.array2string(
                rec.values[:preview_n], precision=4, separator=", ",
            )
            more = " ..." if rec.n > preview_n else ""
            max_id_str = "" if rec.max_data_id is None else f" (MAX_DATA_ID={rec.max_data_id})"
            print(f"   {pname:14s} n={rec.n:3d}{max_id_str}  {preview}{more}")
        print()

    if result.warnings:
        print("[경고]")
        for w in result.warnings:
            print(" -", w)
    else:
        print("(경고 없음)")


if __name__ == "__main__":
    _cli()
