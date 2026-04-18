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
from typing import Iterable

import numpy as np

LIBRARY_FILE = "coord_library.json"  # 앱 실행 폴더 기준
COORD_TOLERANCE_MM = 1e-3            # 중복 판정·매칭 tolerance

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
    name: str
    recipe: str
    n_points: int
    x_mm: list[float]
    y_mm: list[float]
    created_at: str
    last_used: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> CoordPreset:
        return cls(
            name=str(d.get("name", "")),
            recipe=str(d.get("recipe", "")),
            n_points=int(d.get("n_points", 0)),
            x_mm=list(d.get("x_mm", [])),
            y_mm=list(d.get("y_mm", [])),
            created_at=str(d.get("created_at", "")),
            last_used=str(d.get("last_used", "")),
        )


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


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
    def find_match(
        self, recipe: str, x_mm: np.ndarray, y_mm: np.ndarray,
    ) -> CoordPreset | None:
        """(recipe, 좌표) 셋 다 일치하는 레코드 — 있으면 반환."""
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

    def find_by_recipe(self, recipe: str) -> list[CoordPreset]:
        """RECIPE 일치 레코드들 — `last_used` 내림차순 (최신 우선)."""
        hits = [p for p in self.presets if p.recipe == recipe]
        hits.sort(key=lambda p: p.last_used, reverse=True)
        return hits

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
        save: bool = True,
    ) -> tuple[CoordPreset, bool]:
        """중복 없으면 추가, 있으면 `last_used` 갱신.

        Returns:
            (preset, added). `added=True` 면 새 레코드, `False` 면 기존.
        """
        x = np.asarray(x_mm, dtype=float)
        y = np.asarray(y_mm, dtype=float)
        if len(x) == 0 or len(x) != len(y):
            raise ValueError(f"invalid coord lengths: x={len(x)}, y={len(y)}")

        now = _iso_now()
        existing = self.find_match(recipe, x, y)
        if existing is not None:
            existing.last_used = now
            if save:
                self.save()
            return existing, False

        preset = CoordPreset(
            name=f"{recipe}_{len(x)}P" if recipe else f"{len(x)}P",
            recipe=recipe,
            n_points=len(x),
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

    def rename(self, preset: CoordPreset, new_name: str, *, save: bool = True) -> None:
        preset.name = new_name
        if save:
            self.save()

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
        """최대 개수·보관 일수 초과 레코드 삭제. 삭제된 목록 반환.

        - `max_count > 0`: `last_used` 오래된 순으로 초과분 삭제 (가장 최근 `max_count`개 유지)
        - `max_days > 0`:  `created_at` 이 `max_days` 일 이전 레코드 삭제
        - 둘 다 0 이면 no-op
        """
        removed: list[CoordPreset] = []

        if max_days > 0:
            cutoff = datetime.now(timezone.utc).astimezone() - timedelta(days=max_days)
            keep: list[CoordPreset] = []
            for p in self.presets:
                try:
                    created = datetime.fromisoformat(p.created_at)
                except Exception:
                    keep.append(p); continue
                if created >= cutoff:
                    keep.append(p)
                else:
                    removed.append(p)
            self.presets = keep

        if max_count > 0 and len(self.presets) > max_count:
            # last_used 내림차순으로 정렬 → 상위 max_count만 유지
            ordered = sorted(self.presets, key=lambda p: p.last_used, reverse=True)
            self.presets = ordered[:max_count]
            removed.extend(ordered[max_count:])

        if removed and save:
            self.save()
        return removed

    # ── 그룹핑 (불러오기 UI용 중복 병합 표시) ─────────
    def group_by_coords(
        self, presets: Iterable[CoordPreset],
    ) -> list[list[CoordPreset]]:
        """좌표 배열이 tolerance 내 동일한 프리셋들을 묶어 리스트 반환.

        성능: 좌표 첫/중간/끝 3점을 tolerance 단위로 양자화한 해시 키로 **선 버킷팅**
        → 같은 버킷끼리만 정밀 비교 (`np.allclose`). 대부분 서로 다른 좌표일 때
        사실상 O(N). 같은 해시를 공유하는 프리셋이 많으면 그 버킷 내에서만 O(k²).

        각 그룹은 `last_used` 내림차순 정렬. 대표(첫 원소)는 최신 레코드.
        """
        buckets: dict[tuple, list[CoordPreset]] = {}
        for p in presets:
            buckets.setdefault(_coord_hash_key(p), []).append(p)

        groups: list[list[CoordPreset]] = []
        for bucket in buckets.values():
            remaining = bucket
            while remaining:
                pivot = remaining[0]
                px = np.asarray(pivot.x_mm, dtype=float)
                py = np.asarray(pivot.y_mm, dtype=float)
                grp: list[CoordPreset] = [pivot]
                leftover: list[CoordPreset] = []
                for p in remaining[1:]:
                    if _arrays_close(np.asarray(p.x_mm, dtype=float), px) \
                       and _arrays_close(np.asarray(p.y_mm, dtype=float), py):
                        grp.append(p)
                    else:
                        leftover.append(p)
                groups.append(grp)
                remaining = leftover

        for grp in groups:
            grp.sort(key=lambda p: p.last_used, reverse=True)
        return groups


def _coord_hash_key(
    preset: CoordPreset,
    tol: float = COORD_TOLERANCE_MM,
) -> tuple:
    """좌표 첫·중간·끝 3점의 tolerance 단위 양자화 튜플.

    이 값이 같은 프리셋끼리만 `np.allclose` 정밀 비교. tolerance 경계에서는
    같은 좌표가 다른 버킷에 들어갈 수 있으나 (드묾) — 병합이 누락될 뿐
    "다른 좌표를 같게 판정"하는 오류는 없음.
    """
    x = preset.x_mm
    y = preset.y_mm
    n = len(x)
    if n == 0 or len(y) != n:
        return (n,)
    q = 1.0 / tol
    idxs = (0, n // 2, n - 1)
    parts: list = [n]
    for i in idxs:
        parts.append(int(round(float(x[i]) * q)))
        parts.append(int(round(float(y[i]) * q)))
    return tuple(parts)
