"""
Wafer Map long-form CSV 파서.

입력: CSV 파일 경로, 클립보드/파일에서 읽은 원시 텍스트, 또는 이미 만든 DataFrame.
출력: ParseResult — {WAFERID: WaferData} 딕셔너리 + 컬럼 매핑 + raw 처리 메타.

규약 요약 (상세: CLAUDE.md):
- Long-form: 각 행 = 한 웨이퍼 × 한 PARAMETER 레코드.
- 필수 컬럼: WAFERID, LOT ID, SLOTID, PARAMETER, RECIPE, DATA\\d+ (1개 이상).
- 선택 컬럼: MAX_DATA_ID (있으면 검증용, 없거나 실제 DATA 셀 수와 다르면 실제 값 우선).
- 헤더 매칭은 대소문자·공백·언더바 무관 정규화 기반.
- 웨이퍼 그룹핑 키는 WAFERID 문자열 그대로 (LOT.SLOT 분해 금지).
- 한 웨이퍼의 LOT/SLOT/RECIPE는 최빈값 채택.

책임 경계:
- 본 모듈은 파싱 자체와 무결성 보장에 필요한 raw 단계 처리만 담당.
- 처리 과정에서 발견한 사실은 `ParseResult.metadata` 에 구조화해 기록.
- 사용자 안내 메시지 생성·표시는 `core.input_validation` 의 책임.
"""
from __future__ import annotations

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
class ParseMetadata:
    """raw 단계 처리 결과의 구조화된 사실.

    `core.input_validation` 이 이 메타를 보고 사용자 메시지를 생성한다.
    """
    extra_header_rows: int = 0              # 첫 헤더 행 외에 절단된 헤더 행 수 (paste 2회 의심)
    repeat_measurement_groups: int = 0      # 같은 (WAFERID, PARA) 재등장으로 분리된 추가 측정 set 수
                                             # (재측정 / 반복 측정 케이스 — 데이터 보존 + suffix 로 분리)


@dataclass
class ParseResult:
    """파싱 결과 번들."""
    wafers: dict[str, WaferData]
    column_mapping: dict[str, str]   # 논리 키 → 실제 헤더 이름
    data_columns: list[str]          # 정렬된 DATA 컬럼 이름
    metadata: ParseMetadata = field(default_factory=ParseMetadata)


class MissingColumnsError(Exception):
    """필수 컬럼 자동 매칭 실패. GUI는 이 예외를 catch 후 매핑 다이얼로그로 fallback."""

    def __init__(self, missing: list[str], available: list[str]):
        self.missing = missing
        self.available = available
        super().__init__(f"필수 컬럼 누락: {missing} / 실제 컬럼: {available}")


# ────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────
def parse_wafer_csv(
    source: str | Path | pd.DataFrame,
    *,
    aliases: dict[str, list[str]] | None = None,
    column_mapping_override: dict[str, str] | None = None,
    metadata: ParseMetadata | None = None,
) -> ParseResult:
    """
    Long-form 웨이퍼 측정 데이터 파싱.

    Args:
        source: CSV 경로 / 클립보드·파일에서 읽은 원시 텍스트 / 이미 만든 DataFrame.
        aliases: 사용자 지정 컬럼 이름 별칭 (기본값과 merge됨).
        column_mapping_override: GUI 매핑 다이얼로그가 넘겨주는 {논리 키: 실제 헤더}.
        metadata: source 가 DataFrame 일 때, 호출자가 미리 `_load_dataframe`
            결과로 받은 메타를 그대로 보존하기 위해 전달. raw text/Path 일 때는
            `_load_dataframe` 이 자체적으로 메타를 채우므로 None 그대로 둠.

    Raises:
        MissingColumnsError: 필수 컬럼 자동 매칭 실패 + 오버라이드도 없을 때.
    """
    if isinstance(source, pd.DataFrame):
        df = source.copy()
        meta = metadata or ParseMetadata()
    else:
        df, meta = _load_dataframe(source)

    col_map = _match_columns(
        list(df.columns),
        aliases=_merge_aliases(aliases),
        override=column_mapping_override,
    )
    data_cols = _extract_data_columns(list(df.columns))
    if not data_cols:
        raise MissingColumnsError(missing=[r"DATA\d+"], available=list(df.columns))

    wafers, repeat_groups = _group_by_waferid(df, col_map, data_cols)
    meta.repeat_measurement_groups = repeat_groups
    return ParseResult(
        wafers=wafers,
        column_mapping=col_map,
        data_columns=data_cols,
        metadata=meta,
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

    헤더 행 절단은 `_strip_extra_header_rows` 가 별도로 처리 (메타 카운트 보존).
    """
    text = (
        text.replace("\u2212", "-")
        .replace("\u00a0", " ")
        .replace("\u200b", "")
        .replace("\ufeff", "")
    )
    # \uc904\ubcc4 trailing separator \uc81c\uac70 \u2014 Excel \ubcf5\uc0ac \uc2dc \uc77c\ubd80 \uc904\uc5d0\ub9cc trailing \ube48 \uc140\uc774
    # \ubd99\uc5b4 \uceec\ub7fc \uc218 \ubd88\uc77c\uce58 (`expected N fields, saw N+1`) \ub098\ub294 \ucf00\uc774\uc2a4 \ub300\uc751
    text = re.sub(r"[,\t]+\s*$", "", text, flags=re.MULTILINE)
    return text


def _strip_extra_header_rows(text: str) -> tuple[str, int]:
    """첫 헤더 행 외에 같은 텍스트로 등장하는 헤더 행을 절단.

    paste 2회 시 raw 텍스트에 헤더 행이 여러 번 박힘 → 둘째부터 제거.
    절단된 행 수를 함께 리턴해 `ParseMetadata.extra_header_rows` 로 기록.
    """
    lines = text.splitlines(keepends=True)
    if len(lines) < 2:
        return text, 0
    header = lines[0].strip()
    if not header:
        return text, 0
    cleaned: list[str] = [lines[0]]
    skipped = 0
    for line in lines[1:]:
        if line.strip() == header:
            skipped += 1
            continue
        cleaned.append(line)
    return "".join(cleaned), skipped


def _drop_leading_empty_columns(df: pd.DataFrame) -> pd.DataFrame:
    """헤더 시작부의 빈 컬럼들을 drop.

    엑셀에서 셀 영역 복사 시 좌측에 행 번호·빈 열 등이 섞여 들어오는 케이스 대비.
    헤더 셀이 비었거나 (`Unnamed: 0` 같은 자동 이름) + 컬럼 데이터가 모두 NaN
    이면 drop. 연속된 만큼 반복.
    """
    while len(df.columns) > 0:
        first_col = df.columns[0]
        name = str(first_col).strip()
        is_unnamed = name.startswith("Unnamed:") or name == "" or name.lower() == "nan"
        if is_unnamed and df.iloc[:, 0].isna().all():
            df = df.iloc[:, 1:]
        else:
            break
    return df


def _load_dataframe(
    source: str | Path | pd.DataFrame,
) -> tuple[pd.DataFrame, ParseMetadata]:
    """source → (DataFrame, ParseMetadata).

    raw 텍스트는 `_preclean` + `_strip_extra_header_rows` 처리 후 메타에
    `extra_header_rows` 카운트 기록. 파일 경로 / DataFrame 입력은 메타 빈 채로.

    DataFrame 결과는 항상 `_drop_leading_empty_columns` 적용 — 엑셀 복사 시
    좌측 빈 열이 끼어들어오는 케이스 자동 제거.
    """
    metadata = ParseMetadata()
    if isinstance(source, pd.DataFrame):
        return _drop_leading_empty_columns(source.copy()), metadata
    if isinstance(source, (str, Path)):
        s = str(source)
        # 개행/탭이 있으면 원시 텍스트, 아니면 파일 경로로 해석
        if "\n" in s or "\t" in s:
            s = _preclean(s)
            s, metadata.extra_header_rows = _strip_extra_header_rows(s)
            # 줄 시작 공백/탭 제거 — 모든 sep 에 일괄 적용. Excel 복사 시 줄 앞
            # 노이즈 (공백·탭) 가 컬럼명에 붙거나 sep 인식 깨지는 케이스 대응.
            # 탭 sep 의 진짜 leading 빈 셀은 사실상 의미 없는 케이스 — 제거 안전.
            s = re.sub(r"^[ \t]+", "", s, flags=re.MULTILINE)
            first_line = s.splitlines()[0] if s.splitlines() else ""
            sep = "\t" if "\t" in first_line else ","
            df = pd.read_csv(io.StringIO(s), sep=sep, on_bad_lines="warn")
            return _drop_leading_empty_columns(df), metadata
        path = Path(s)
        if not path.exists():
            raise FileNotFoundError(path)
        df = pd.read_csv(path, on_bad_lines="warn")
        return _drop_leading_empty_columns(df), metadata
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

    방어: `row[data_cols]` 가 1D 가 아닌 경우 (헤더 컬럼명 중복 등) 첫 발생만 사용.
    """
    sel = row[data_cols]
    if isinstance(sel, pd.DataFrame):
        # 컬럼명 중복으로 DataFrame 반환 — row 가 한 행이라 (1, N) 모양이지만
        # 더 안전하게 첫 행만 추출
        sel = sel.iloc[0] if sel.shape[0] >= 1 else pd.Series(dtype=float)
    arr = pd.to_numeric(sel, errors="coerce").to_numpy(dtype=float)
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
) -> tuple[dict[str, WaferData], int]:
    """raw 행 순서 보존 + (WAFERID, PARAMETER) 재등장 시 측정 set 분리.

    같은 `WAFERID` 안에서 같은 `PARAMETER` 가 다시 등장하면 새로운 측정 set
    시작 — wafer_id 에 `__rep{N}` suffix 를 붙여 별도 wafer 로 분리.

    행 순서 보존: 입력이 W1/W2/W3/W1/W2/W3 순으로 paste 되면 wafer 순서는
    W1 → W2 → W3 → W1__rep1 → W2__rep1 → W3__rep1. 사용자가 페이스트한
    순서대로 시각화 cell 이 가로 나열되도록 row 단위 순회 + dict insertion
    order 활용 (`groupby(sort=False)` 는 같은 wid 를 묶어버려 부적합).

    가정: raw 텍스트가 "한 측정 set 의 모든 PARA 행 → 다음 set" 순서로 나열.
    같은 (wafer, PARA) 의 재등장이 새 set 의 시작 신호.

    분리된 추가 측정 set 수를 리턴 → `ParseMetadata.repeat_measurement_groups`.
    """
    wid_col = col_map["waferid"]
    param_col = col_map["parameter"]
    lot_col = col_map["lot_id"]
    slot_col = col_map["slot_id"]
    recipe_col = col_map["recipe"]
    max_col = col_map.get("max_data_id")

    # Excel 셀 포맷 이슈로 WAFERID 앞뒤 공백 섞이면 같은 웨이퍼가 두 그룹으로 분산됨.
    df = df.copy()
    df[wid_col] = df[wid_col].astype(str).str.strip()

    # Pass 1: row 순회하며 (df_idx, param_name) 을 어느 wafer_id 에 넣을지 결정.
    # base_wid 별로 (current_wid, seen_params, rep_idx) state 추적.
    state: dict[str, tuple[str, set[str], int]] = {}
    rows_per_wafer: dict[str, list[tuple[int, str]]] = {}   # insertion order = 시각화 순서
    repeat_groups = 0

    for df_idx, row in df.iterrows():
        base_wid = str(row[wid_col]).strip()
        if not base_wid:
            continue
        param_name = str(row[param_col]).strip()
        if not param_name or param_name.lower() == "nan":
            continue

        if base_wid not in state:
            state[base_wid] = (base_wid, set(), 0)
        current_wid, seen_params, rep_idx = state[base_wid]

        if param_name in seen_params:
            rep_idx += 1
            repeat_groups += 1
            current_wid = f"{base_wid}__rep{rep_idx}"
            seen_params = set()
        seen_params.add(param_name)
        state[base_wid] = (current_wid, seen_params, rep_idx)

        rows_per_wafer.setdefault(current_wid, []).append((df_idx, param_name))

    # Pass 2: wafer 별 WaferData 생성. lot/slot/recipe 는 해당 wafer 의 행들로
    # `_mode_str` 채택 (한 wafer 안에서 일관성 보호).
    wafers: dict[str, WaferData] = {}
    for wid, rows in rows_per_wafer.items():
        indices = [r[0] for r in rows]
        subset = df.loc[indices]

        wafer = WaferData(
            wafer_id=wid,
            lot_id=_mode_str(subset[lot_col]),
            slot_id=_mode_str(subset[slot_col]),
            recipe=_mode_str(subset[recipe_col]),
            parameters={},
        )

        for df_idx, param_name in rows:
            row = df.loc[df_idx]
            values = _row_values(row, data_cols)
            n_actual = len(values)

            max_id: int | None = None
            if max_col is not None and pd.notna(row[max_col]):
                try:
                    max_id = int(row[max_col])
                except (ValueError, TypeError):
                    max_id = None

            wafer.parameters[param_name] = WaferRecord(
                values=values, n=n_actual, max_data_id=max_id
            )

        wafers[wid] = wafer

    return wafers, repeat_groups


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

    m = result.metadata
    print(f"[메타] extra_header_rows={m.extra_header_rows}, "
          f"repeat_measurement_groups={m.repeat_measurement_groups}")


if __name__ == "__main__":
    _cli()
