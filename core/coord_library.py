"""
좌표 프리셋 라이브러리 — `coord_library.json` I/O + 중복 판정 + RECIPE 조회.

무설치 포터블 배포 정책: 파일은 앱 실행 폴더 기준 상대 경로 `coord_library.json`.

중복 판정 키: `(recipe, x_mm, y_mm)` — 셋 다 tolerance 내 일치해야 동일 레코드.
- recipe 같아도 좌표 다르면 별도 레코드 (레시피 수정·장비별 좌표 차이)
- 좌표 같아도 recipe 다르면 별도 레코드 (흔한 관례)

저장은 자동. 사용자는 관리 UI에서 삭제·이름변경만 가능.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

LIBRARY_FILE = "coord_library.json"  # 앱 실행 폴더 기준
COORD_TOLERANCE_MM = 5e-3            # 중복 판정·매칭 tolerance (5μm)

# RECIPE 이름 토큰 분리용 (공백·언더바·하이픈 구분)
_RECIPE_SPLIT_RE = re.compile(r"[\s_\-]+")

# 완전 일치 가중치 (토큰 수 차이를 압도하도록 큰 값)
_EXACT_MATCH_BONUS = 10_000


def _recipe_tokens(recipe: str) -> set[str]:
    if not recipe:
        return set()
    return {t for t in _RECIPE_SPLIT_RE.split(recipe.lower()) if t}


def recipe_similarity(a: str, b: str) -> int:
    """두 RECIPE 이름 간 유사도 점수.

    - 완전 일치: `_EXACT_MATCH_BONUS + 토큰 수`
    - 부분 일치: 공통 토큰 개수 (언더바·공백·하이픈 분리, 대소문자 무관)

    예시:
      - "ER_DSPIRAL_POLY_55PT" vs "ER_DSPIRAL_NIT_55PT" → 3 ({ER, DSPIRAL, 55PT} 공유)
      - 동일 문자열 → 10003 (4 tokens)
      - 무관: 0
    """
    if a == b and a:
        return _EXACT_MATCH_BONUS + len(_recipe_tokens(a))
    return len(_recipe_tokens(a) & _recipe_tokens(b))


@dataclass
class CoordPreset:
    recipe: str
    n_points: int
    x_mm: list[float]
    y_mm: list[float]
    created_at: str
    last_used: str
    x_name: str = "X"   # 원본 X PARAMETER 이름 (예: "X", "X_1000", "X_1000_A")
    y_name: str = "Y"   # 원본 Y PARAMETER 이름

    # recipe + pair 로 자동 표시 이름 (UI 전용, 저장 X)
    @property
    def display_name(self) -> str:
        return f"{self.recipe} ({self.x_name}/{self.y_name})"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> CoordPreset:
        return cls(
            recipe=str(d.get("recipe", "")),
            n_points=int(d.get("n_points", 0)),
            x_mm=list(d.get("x_mm", [])),
            y_mm=list(d.get("y_mm", [])),
            created_at=str(d.get("created_at", "")),
            last_used=str(d.get("last_used", "")),
            x_name=str(d.get("x_name", "X")),
            y_name=str(d.get("y_name", "Y")),
        )


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def format_dt_display(iso: str) -> str:
    """ISO 문자열(`...+09:00`)을 `YYYY-MM-DD HH:MM:SS` 표시용으로 포맷. 실패 시 원문.

    초까지 표시 — 1분 이내 레시피 두 개 저장 시 사용자가 순서 구분할 수 있어야 함.
    """
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return iso


def _arrays_close(
    a: np.ndarray, b: np.ndarray, tol: float = COORD_TOLERANCE_MM,
) -> bool:
    """두 좌표 배열이 tolerance 내 일치 여부. 길이 다르면 False."""
    if len(a) != len(b):
        return False
    if len(a) == 0:
        return True
    return bool(np.allclose(a, b, atol=tol, equal_nan=False))


class CoordLibrary:
    """프리셋 목록 + 로드/저장/조회/중복 판정."""

    def __init__(self, path: str | Path = LIBRARY_FILE) -> None:
        self.path = Path(path)
        self.presets: list[CoordPreset] = []
        self.load()

    # ── I/O ──────────────────────────────────────────
    def load(self) -> None:
        if not self.path.exists():
            self.presets = []
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("presets", []) if isinstance(data, dict) else []
            self.presets = [CoordPreset.from_dict(p) for p in raw if isinstance(p, dict)]
        except Exception:
            self.presets = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"presets": [p.to_dict() for p in self.presets]}
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    # ── 조회 ─────────────────────────────────────────
    def find_match_by_names(
        self, recipe: str, x_name: str, y_name: str,
    ) -> CoordPreset | None:
        """(recipe, x_name, y_name) 키 매칭 — per-pair preset 조회.

        대소문자 무시 recipe 매칭. x_name, y_name 은 대소문자 구분.
        """
        rec_lower = recipe.lower() if recipe else ""
        for p in self.presets:
            if p.recipe.lower() == rec_lower and p.x_name == x_name and p.y_name == y_name:
                return p
        return None

    def find_match(
        self, recipe: str, x_mm: np.ndarray, y_mm: np.ndarray,
    ) -> CoordPreset | None:
        """legacy — (recipe, 좌표) 일치. 신규 경로는 find_match_by_names 사용."""
        x = np.asarray(x_mm, dtype=float)
        y = np.asarray(y_mm, dtype=float)
        for p in self.presets:
            if p.recipe != recipe:
                continue
            if p.n_points != len(x):
                continue
            if _arrays_close(np.asarray(p.x_mm, dtype=float), x) \
               and _arrays_close(np.asarray(p.y_mm, dtype=float), y):
                return p
        return None

    def find_by_recipe(self, recipe: str, n_points: int | None = None) -> list[CoordPreset]:
        """RECIPE 매칭 — 3단계 폴백 (사용자 정책 2026-04-27 일관 적용).

        1단계: 대소문자 무시 완전일치 → `last_used` 내림차순
        2단계: `_PRE` / `_POST` suffix 제외 후 베이스 일치 (양방향) →
          `last_used` 내림차순. 정책 단일 진실 원천: `core.recipe_util`.
        3단계 (`n_points` 주어졌을 때): recipe_similarity >= 3 AND
          p.n_points == n_points → (유사도, last_used) 내림차순
        """
        if not recipe:
            return []
        from core.recipe_util import strip_pre_post  # lazy: 순환 회피
        rec_lower = recipe.lower()
        exact = [p for p in self.presets if p.recipe.lower() == rec_lower]
        if exact:
            exact.sort(key=lambda p: p.last_used, reverse=True)
            return exact
        # 2단계: PRE/POST 제외 후 베이스 일치
        target_base = strip_pre_post(recipe)
        compat = [p for p in self.presets
                  if p.recipe and strip_pre_post(p.recipe) == target_base]
        if compat:
            compat.sort(key=lambda p: p.last_used, reverse=True)
            return compat
        if n_points is None:
            return []
        MIN_SHARED_TOKENS = 3
        partial: list[tuple[CoordPreset, int]] = []
        for p in self.presets:
            if p.n_points != n_points:
                continue
            sim = recipe_similarity(p.recipe, recipe)
            if sim >= MIN_SHARED_TOKENS:
                partial.append((p, sim))
        partial.sort(key=lambda pair: (pair[1], pair[0].last_used), reverse=True)
        return [p for p, _ in partial]

    def filter_by_n(self, n: int) -> list[CoordPreset]:
        """`n_points == n` 인 프리셋 — `last_used` 내림차순."""
        hits = [p for p in self.presets if p.n_points == n]
        hits.sort(key=lambda p: p.last_used, reverse=True)
        return hits

    # ── 변경 ─────────────────────────────────────────
    def add_or_touch(
        self,
        recipe: str,
        x_mm: np.ndarray,
        y_mm: np.ndarray,
        *,
        x_name: str = "X",
        y_name: str = "Y",
        save: bool = True,
    ) -> tuple[CoordPreset, bool]:
        """`(recipe, x_name, y_name)` 키 기반 저장 — Option B (overwrite).

        - 동일 키 레코드 있음:
          * 좌표가 tolerance 내 동일 → `last_used` 만 갱신
          * 좌표 다름 → **기존 레코드의 좌표를 새 좌표로 덮어쓰기** (페어당 1 레코드)
        - 동일 키 레코드 없음 → 신규 추가

        Returns:
            (preset, added). `added=True` 면 새 레코드, `False` 면 기존 (touch/overwrite).
        """
        x = np.asarray(x_mm, dtype=float)
        y = np.asarray(y_mm, dtype=float)
        if len(x) == 0 or len(x) != len(y):
            raise ValueError(f"invalid coord lengths: x={len(x)}, y={len(y)}")

        now = _iso_now()
        existing = self.find_match_by_names(recipe, x_name, y_name)
        if existing is not None:
            # 좌표 동일 (tolerance 내) 이면 touch 만, 다르면 overwrite
            same_coords = (
                len(existing.x_mm) == len(x)
                and _arrays_close(np.asarray(existing.x_mm, dtype=float), x)
                and _arrays_close(np.asarray(existing.y_mm, dtype=float), y)
            )
            if not same_coords:
                existing.x_mm = [float(v) for v in x]
                existing.y_mm = [float(v) for v in y]
                existing.n_points = len(x)
            existing.last_used = now
            if save:
                self.save()
            return existing, False

        # 신규 추가 — 페어 단위 overwrite 라 이름 자동생성 불필요
        preset = CoordPreset(
            recipe=recipe,
            n_points=len(x),
            x_name=x_name,
            y_name=y_name,
            x_mm=[float(v) for v in x],
            y_mm=[float(v) for v in y],
            created_at=now,
            last_used=now,
        )
        self.presets.append(preset)
        if save:
            self.save()
        return preset, True

    def touch(self, preset: CoordPreset, *, save: bool = True) -> None:
        """프리셋 `last_used` 갱신 (불러오기 시 호출)."""
        preset.last_used = _iso_now()
        if save:
            self.save()

    def delete(self, preset: CoordPreset, *, save: bool = True) -> bool:
        try:
            self.presets.remove(preset)
        except ValueError:
            return False
        if save:
            self.save()
        return True

    def set_recipe(self, preset: CoordPreset, new_recipe: str, *, save: bool = True) -> None:
        preset.recipe = new_recipe
        if save:
            self.save()

    # ── 자동 정리 ──────────────────────────────────
    def enforce_limits(
        self,
        max_count: int = 0,
        max_days: int = 0,
        *,
        save: bool = True,
    ) -> list[CoordPreset]:
        """최대 레코드 수·보관 일수 초과 레코드 삭제. 삭제된 레코드 목록 반환.

        - `max_count > 0`: **레코드 개수 기준** (표의 행 개수). `last_used` 내림차순
          정렬 후 상위 `max_count` 레코드만 유지.
        - `max_days > 0`:  `last_used` 가 `max_days` 일 이전인 레코드 삭제.
        - 둘 다 0 이면 no-op
        """
        removed: list[CoordPreset] = []

        if max_days > 0:
            cutoff = datetime.now(timezone.utc).astimezone() - timedelta(days=max_days)
            keep: list[CoordPreset] = []
            for p in self.presets:
                try:
                    last = datetime.fromisoformat(p.last_used)
                except Exception:
                    keep.append(p); continue
                if last >= cutoff:
                    keep.append(p)
                else:
                    removed.append(p)
            self.presets = keep

        if max_count > 0 and len(self.presets) > max_count:
            sorted_presets = sorted(
                self.presets, key=lambda p: p.last_used, reverse=True,
            )
            self.presets = sorted_presets[:max_count]
            removed.extend(sorted_presets[max_count:])

        if removed and save:
            self.save()
        return removed

