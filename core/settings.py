"""
settings.json I/O.

- 앱 실행 폴더 기준 `settings.json` (무설치 포터블 배포 정책).
- 로드 시 누락 키는 `DEFAULT_SETTINGS` 로부터 재귀적으로 merge.
- 최소 변경: 앱 시작 시 `load_settings()`, 변경 시 `save_settings(settings)`.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from core.themes import DEFAULT_CUSTOM_COLORS, DEFAULT_SETTINGS

SETTINGS_FILE = "settings.json"  # 앱 실행 폴더 기준 상대 경로

# 런타임 캐시 — 다이얼로그에서 "메모리만 갱신(Save 전)" 상태를 공유하기 위함.
# WaferCell / apply_global_style 등 읽기 경로는 load_settings() 한 번이면 충분하도록.
_cache: dict[str, Any] | None = None


def _merge_defaults(loaded: dict, defaults: dict) -> dict:
    """loaded + defaults nested merge. loaded 우선, 누락 키만 defaults에서 채움."""
    result = copy.deepcopy(defaults)
    for k, v in loaded.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _merge_defaults(v, result[k])
        else:
            result[k] = v
    return result


def load_settings() -> dict[str, Any]:
    """설정 반환 — 런타임 캐시 우선, 없으면 파일 로드.

    미저장 변경분(set_runtime)도 같은 dict로 반환되므로 WaferCell 등이 즉시 반영.
    """
    global _cache
    if _cache is not None:
        return _cache
    path = Path(SETTINGS_FILE)
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            _migrate_chart_common(loaded)
            _cache = _merge_defaults(loaded, DEFAULT_SETTINGS)
            return _cache
        except Exception:
            pass
    _cache = copy.deepcopy(DEFAULT_SETTINGS)
    return _cache


def _migrate_chart_common(loaded: dict[str, Any]) -> None:
    """구 settings(chart_2d/chart_3d에 공통 키 보유) → chart_common 키로 이동.

    호환성 1회 마이그레이션. 다음 Save 시 정리됨.
    """
    # r-symmetry 관련 키는 **세션 휘발** 원칙 — 저장돼 있으면 제거하고 항상 False 로
    # 시작. 구 이름 `r_asymmetry_mode` 도 함께 청소.
    loaded.pop("r_asymmetry_mode", None)
    loaded.pop("r_symmetry_mode", None)
    # Z-Margin 도 세션 휘발 — 과거 저장돼 있으면 제거. 메인 윈도우 default 사용.
    _cc_stale = loaded.get("chart_common")
    if isinstance(_cc_stale, dict):
        _cc_stale.pop("z_range_expand_pct", None)

    common_keys = ("colormap", "interp_method", "grid_resolution", "show_circle")
    common = loaded.setdefault("chart_common", {})
    for src in ("chart_2d", "chart_3d"):
        block = loaded.get(src)
        if not isinstance(block, dict):
            continue
        for k in common_keys:
            if k in block and k not in common:
                common[k] = block[k]
            block.pop(k, None)
    # 3D 전용에서 더 이상 안 쓰는 키 정리
    c3d = loaded.get("chart_3d")
    if isinstance(c3d, dict):
        c3d.pop("z_scale_mode", None)
        c3d.pop("show_axes", None)
        c3d.pop("shading", None)
        c3d.pop("camera_fov", None)
        c3d.pop("x_stretch", None)
        # camera_distance 는 chart_3d → chart_common 이동. chart_common 에 값이
        # 없으면 chart_3d 값을 옮기고, 있으면 chart_3d 쪽만 제거.
        if "camera_distance" in c3d:
            if "camera_distance" not in common:
                common["camera_distance"] = c3d["camera_distance"]
            c3d.pop("camera_distance", None)
        # z_exaggeration None(자동) → 1.0 (동등 결과)
        if c3d.get("z_exaggeration") is None:
            c3d["z_exaggeration"] = 1.0
    # interp_method 이름 표기 통일 (소문자 snake_case → PascalCase + dash).
    # 삭제된 방식(cubic/idw 등)은 default(RBF-ThinPlate)로.
    _INTERP_ALIASES = {
        "rbf_thin_plate":   "RBF-ThinPlate",
        "rbf_multiquadric": "RBF-Multiquadric",
        "rbf_gaussian":     "RBF-Gaussian",
        "rbf_quintic":      "RBF-Quintic",
        # 삭제된 것들 → default
        "rbf": "RBF-ThinPlate",
        "cubic": "RBF-ThinPlate",
        "cubic_nearest": "RBF-ThinPlate",
        "phantom_ring": "RBF-ThinPlate",
        "idw": "RBF-ThinPlate",
    }
    im = common.get("interp_method")
    if im in _INTERP_ALIASES:
        common["interp_method"] = _INTERP_ALIASES[im]
    # colormap 소문자 mpl 이름(viridis, plasma 등) → 첫글자 대문자 표기로 통일
    cmap = common.get("colormap")
    if cmap in ("viridis", "plasma", "inferno", "magma", "cividis", "turbo"):
        common["colormap"] = cmap.capitalize()


def save_settings(settings: dict[str, Any]) -> None:
    """파일 저장 + 캐시 동기화."""
    global _cache
    path = Path(SETTINGS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    _cache = copy.deepcopy(settings)


def set_runtime(settings: dict[str, Any]) -> None:
    """파일 저장 없이 캐시만 갱신 — Settings 다이얼로그의 즉시 반영 경로."""
    global _cache
    _cache = copy.deepcopy(settings)


def invalidate_cache() -> None:
    """다음 load_settings 호출 시 파일에서 재로드하도록 캐시 폐기 (Close 등에서 사용)."""
    global _cache
    _cache = None


# ────────────────────────────────────────────────────────────────
# QColorDialog Custom Colors (Profile Vision과 동일 패턴)
# ────────────────────────────────────────────────────────────────
def load_custom_colors() -> list[str]:
    saved = load_settings().get("custom_colors")
    if isinstance(saved, list) and len(saved) == 16:
        return list(saved)
    return list(DEFAULT_CUSTOM_COLORS)


def apply_custom_colors_to_dialog(colors: list[str]) -> None:
    """16개 hex 문자열을 QColorDialog 전역 custom color 슬롯에 적용."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog
    for i, hex_str in enumerate(colors[:16]):
        try:
            QColorDialog.setCustomColor(i, QColor(hex_str))
        except Exception:
            pass


def save_custom_colors_from_dialog() -> None:
    """QColorDialog 전역 custom color 16개를 settings.json에 저장."""
    from PySide6.QtGui import QColor  # noqa: F401  (QColorDialog 의존)
    from PySide6.QtWidgets import QColorDialog
    colors: list[str] = []
    for i in range(16):
        c = QColorDialog.customColor(i)
        colors.append(c.name() if c.isValid() else "#ffffff")
    settings = load_settings()
    settings["custom_colors"] = colors
    save_settings(settings)
