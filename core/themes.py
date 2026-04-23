"""
Wafer Map — 테마·폰트·기본 설정 상수.

이 모듈은 의존성이 없어야 함 (다른 core 모듈은 여기서 import 해도 됨).
Profile Vision의 테마 팔레트를 참고해 UI 일관성을 유지.
"""

# ────────────────────────────────────────────────────────────────
# UI 폰트 후보 (Settings 다이얼로그 콤보용)
# ────────────────────────────────────────────────────────────────
FONTS = [
    # 한글
    "굴림", "궁서", "돋움", "맑은 고딕", "바탕",
    # 영문
    "Arial", "Calibri", "Cambria", "Candara", "Consolas",
    "Segoe UI", "Tahoma", "Times New Roman", "Trebuchet MS",
    "Yu Gothic UI",
]


# ────────────────────────────────────────────────────────────────
# UI 테마 팔레트 (Profile Vision과 동일 키 규격)
# ────────────────────────────────────────────────────────────────
THEMES = {
    "Light": {
        "bg": "#f8f9fa",
        "surface": "#ffffff",
        "surface_alt": "#f1f3f5",
        "text": "#212529",
        "text_sub": "#868e96",
        "accent": "#4361ee",
        "border": "#dee2e6",
        "header_bg": "#e9ecef",
        "danger": "#e63946",
        "success": "#2a9d8f",
        "title_color": "#4361ee",
        "chart_lines": ["#4361ee", "#e63946", "#2a9d8f", "#f77f00"],
    },
    "Dark": {
        "bg": "#1e1e2e",
        "surface": "#313244",
        "surface_alt": "#363848",
        "text": "#cdd6f4",
        "text_sub": "#6c7086",
        "accent": "#89b4fa",
        "border": "#45475a",
        "header_bg": "#45475a",
        "danger": "#f38ba8",
        "success": "#a6e3a1",
        "title_color": "#cba6f7",
        "chart_lines": ["#89b4fa", "#f38ba8", "#a6e3a1", "#fab387"],
    },
    "Slate": {
        "bg": "#f1f5f9",
        "surface": "#f8fafc",
        "surface_alt": "#e2e8f0",
        "text": "#334155",
        "text_sub": "#64748b",
        "accent": "#475569",
        "border": "#cbd5e1",
        "header_bg": "#e2e8f0",
        "danger": "#dc2626",
        "success": "#16a34a",
        "title_color": "#475569",
        "chart_lines": ["#475569", "#dc2626", "#16a34a", "#ea580c"],
    },
    "Blue Ocean": {
        "bg": "#0A1929",
        "surface": "#132f4c",
        "surface_alt": "#173a5e",
        "text": "#b2bac2",
        "text_sub": "#5a7a94",
        "accent": "#5090d3",
        "border": "#1e4976",
        "header_bg": "#1a3d5c",
        "danger": "#ff6d75",
        "success": "#66bb6a",
        "title_color": "#5090d3",
        "chart_lines": ["#5090d3", "#ff6d75", "#66bb6a", "#ffab40"],
    },
    "Nord": {
        "bg": "#2e3440",
        "surface": "#3b4252",
        "surface_alt": "#434c5e",
        "text": "#eceff4",
        "text_sub": "#6c7a8d",
        "accent": "#88c0d0",
        "border": "#4c566a",
        "header_bg": "#434c5e",
        "danger": "#bf616a",
        "success": "#a3be8c",
        "title_color": "#88c0d0",
        "chart_lines": ["#88c0d0", "#bf616a", "#a3be8c", "#ebcb8b"],
    },
    "Solarized": {
        "bg": "#fdf6e3",
        "surface": "#eee8d5",
        "surface_alt": "#f5efdc",
        "text": "#657b83",
        "text_sub": "#93a1a1",
        "accent": "#268bd2",
        "border": "#d3cbb7",
        "header_bg": "#eee8d5",
        "danger": "#dc322f",
        "success": "#859900",
        "title_color": "#268bd2",
        "chart_lines": ["#268bd2", "#dc322f", "#859900", "#cb4b16"],
    },
    "Rose Pine": {
        "bg": "#191724",
        "surface": "#1f1d2e",
        "surface_alt": "#26233a",
        "text": "#e0def4",
        "text_sub": "#6e6a86",
        "accent": "#c4a7e7",
        "border": "#393552",
        "header_bg": "#26233a",
        "danger": "#eb6f92",
        "success": "#9ccfd8",
        "title_color": "#c4a7e7",
        "chart_lines": ["#c4a7e7", "#eb6f92", "#9ccfd8", "#f6c177"],
    },
    "Catppuccin Latte": {
        "bg": "#eff1f5",
        "surface": "#e6e9ef",
        "surface_alt": "#ccd0da",
        "text": "#4c4f69",
        "text_sub": "#6c6f85",
        "accent": "#8839ef",
        "border": "#dce0e8",
        "header_bg": "#e6e9ef",
        "danger": "#d20f39",
        "success": "#40a02b",
        "title_color": "#8839ef",
        "chart_lines": ["#1e66f5", "#d20f39", "#40a02b", "#fe640b"],
    },
    "Mint Cream": {
        "bg": "#f0fdf4",
        "surface": "#ffffff",
        "surface_alt": "#dcfce7",
        "text": "#14532d",
        "text_sub": "#4d7c5f",
        "accent": "#10b981",
        "border": "#bbf7d0",
        "header_bg": "#dcfce7",
        "danger": "#dc2626",
        "success": "#10b981",
        "primary_btn": "#047857",  # 메인 액션 강조 (success가 accent와 같아 fallback 분리)
        "title_color": "#10b981",
        "chart_lines": ["#10b981", "#3b82f6", "#a855f7", "#14b8a6"],
    },
    "Lavender Haze": {
        "bg": "#f5f3ff",
        "surface": "#ffffff",
        "surface_alt": "#ede9fe",
        "text": "#4c1d95",
        "text_sub": "#7c6fa6",
        "accent": "#8b5cf6",
        "border": "#ddd6fe",
        "header_bg": "#ede9fe",
        "danger": "#dc2626",
        "success": "#10b981",
        "title_color": "#8b5cf6",
        "chart_lines": ["#8b5cf6", "#3b82f6", "#10b981", "#14b8a6"],
    },
    "Everforest Light": {
        "bg": "#efebd4",
        "surface": "#fdf6e3",
        "surface_alt": "#e5dfbf",
        "text": "#5c6a72",
        "text_sub": "#829181",
        "accent": "#8da101",
        "border": "#bdc3af",
        "header_bg": "#e5dfbf",
        "danger": "#f85552",
        "success": "#8da101",
        "primary_btn": "#3a94c5",  # 메인 액션 강조 (success가 accent와 같아 fallback 분리)
        "title_color": "#8da101",
        "chart_lines": ["#8da101", "#f85552", "#3a94c5", "#f57d26"],
    },
    "Zinc": {
        "bg": "#f4f4f5",
        "surface": "#fafafa",
        "surface_alt": "#e4e4e7",
        "text": "#27272a",
        "text_sub": "#71717a",
        "accent": "#52525b",
        "border": "#d4d4d8",
        "header_bg": "#e4e4e7",
        "danger": "#dc2626",
        "success": "#16a34a",
        "title_color": "#52525b",
        "chart_lines": ["#52525b", "#dc2626", "#16a34a", "#ea580c"],
    },
    "Fog": {
        "bg": "#e5e7eb",
        "surface": "#f3f4f6",
        "surface_alt": "#d1d5db",
        "text": "#374151",
        "text_sub": "#6b7280",
        "accent": "#4b5563",
        "border": "#9ca3af",
        "header_bg": "#d1d5db",
        "danger": "#dc2626",
        "success": "#16a34a",
        "title_color": "#4b5563",
        "chart_lines": ["#4b5563", "#dc2626", "#16a34a", "#ea580c"],
    },
    "Papercolor Light": {
        "bg": "#eeeeee",
        "surface": "#ffffff",
        "surface_alt": "#e4e4e4",
        "text": "#444444",
        "text_sub": "#878787",
        "accent": "#0087af",
        "border": "#bcbcbc",
        "header_bg": "#e4e4e4",
        "danger": "#d70000",
        "success": "#5f8700",
        "title_color": "#0087af",
        "chart_lines": ["#0087af", "#d70000", "#5f8700", "#d70087"],
    },
}


# ────────────────────────────────────────────────────────────────
# Heatmap 컬러맵 (pyqtgraph 내장 이름)
# ────────────────────────────────────────────────────────────────
HEATMAP_COLORMAPS = [
    "CET-L17",   # 기본
    "CET-L4",
    "CET-L8",
    "CET-L16",
    "CET-L19",
    "Viridis",
    "Reverse-Viridis",
    "Plasma",
    "Reverse-Plasma",
    "Inferno",
    "Reverse-Inferno",
    "Magma",
    "Reverse-Magma",
    "Cividis",
    "Reverse-Cividis",
    "Turbo",
    "CET-D1",
    "CET-D4",
    "CET-D8",
    "CET-D13",
    "CET-R4",
    # 커스텀 — wafer_cell._CUSTOM_CMAPS에 실제 pg.ColorMap 정의 (min=White, max=지정색)
    "Red-White",
    "Blue-White",
    "Black-White",
    "Navy-White",
    "Pink-White",
    "Brown-White",
    "Charcoal-White",
]


# ────────────────────────────────────────────────────────────────
# 글로벌 폰트 크기 (모든 위젯이 이 값 참조)
# ────────────────────────────────────────────────────────────────
FONT_SIZES = {
    "app_title": 21,
    "section": 15,
    "subtitle": 14,
    "body": 14,        # 표 + 전역 UI 기준
    "small": 12,
    "caption": 12,     # 컬러바 + 1D 그래프 축 (표보다 작음)
    "run_btn": 19,
    "version": 13,
}

# font_scale 적용 기준값 (immutable backup). apply_global_style 이 scale 적용 시
# 이 base 에서 multiply → FONT_SIZES 갱신. FONT_SIZES 를 읽는 코드는 항상 현재
# scale 반영된 값을 얻음. 이전엔 FONT_SIZES 가 QSS 빌드 직후 원복되어 연동 안 됐음.
BASE_FONT_SIZES = dict(FONT_SIZES)


# ────────────────────────────────────────────────────────────────
# 앱 전체 기본 설정 (settings.json 없거나 누락 키 채움용)
# 새 키 추가 시 반드시 여기에 등록 → settings 로드 시 merge.
# ────────────────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    # UI
    "theme": "Light",
    "font": "Segoe UI",
    "font_scale": 1.0,          # FONT_SIZES 전체 배율 (0.85 / 1.0 / 1.15 등)

    # 창 크기 (None이면 runtime 해상도 티어로 auto 결정)
    "window": {
        "main":   None,            # [w, h] — 사용자가 종료 시 마지막 크기 저장 시 자동 갱신
        "result": None,
        "splitter_sizes": None,    # [input_h, control_h, result_h] — 메인 splitter 비율
    },
    "window_save_enabled": True,   # True 면 종료 시 위 window 값 자동 갱신 (다음 실행 복원)

    # MAP 공통 설정 — 2D/3D 양쪽에 같이 적용
    "chart_common": {
        "colormap": "Turbo",
        "show_circle": True,       # 웨이퍼 경계 원
        "show_notch": True,        # 경계 원에 notch(V자 홈) 표시 — 6시 방향 고정
        "notch_depth_mm": 3.0,     # notch 깊이(mm, 시각적 과장)
        "boundary_r_mm": 153.0,    # 경계 원 반지름 (웨이퍼 바깥 여유 150~160). notch 는 이 원에만 표시
        # Radial mesh 밀도 — 2D top view / 3D 공통. RBF 1회 평가로 공유.
        "radial_rings": 20,        # 반경 방향 링 수 (5~60)
        "radial_seg": 180,         # 각도 세그먼트 수 (60~720)
        "show_scale_bar": True,    # 그래프 우측에 컬러맵 스케일바
        "chart_width": 360,        # 그래프 가로 (px) — 360:280 비율 기준 중
        "chart_height": 280,       # 그래프 세로 (px)
        # 보간 방법 — core/interp.py 참고
        "interp_method": "RBF-ThinPlate",
        "decimals": 2,             # 테이블 값 소수점 자릿수 (0/1/2/3, 컬러바는 별도 동적)
        "edge_cut_mm": 1.5,        # 웨이퍼 경계에서 안쪽으로 cut (mm). 0=cut 없음
        # 공통 Z-scale 모드에서 range 확장 비율 (%). 0=실제 min~max,
        # 50=range*1.5 (midpoint 중심), 100=range*2.0. 개별 모드에선 무시.
        "z_range_expand_pct": 50,
        # 1D radial scan 자동 감지 — 원점 중심 (길이 300 × 폭 `radial_line_width_mm`)
        # 직사각형에 모든 측정점 fit 되면 1D radial scan 으로 간주 → 1D spline 보간.
        # 그 외는 2D RBF. CMP 등 rotation symmetric 공정 라인 스캔이 주 사용처.
        "radial_line_width_mm": 45.0,
        # Radial 1D spline smoothing factor — 0.0~15.0 (0.1 step). 낮을수록
        # 산점도 추종, 높을수록 스무스. s = n × noise² × factor. 0 = 정확 보간.
        "radial_smoothing_factor": 5.0,
        # 1D Radial Graph 표시 — 체크 시 2D/3D 그래프와 Summary 표 사이에 (r, v)
        # 산점도 + spline 실선 위젯 추가. Y축은 2D/3D 와 독립, 실측 min/max 기반.
        # 개별/공통 Z-scale 모드와 Z-Margin 은 1D 그래프끼리 동작 (2D/3D 와 별도 계산).
        "show_1d_radial": False,
        # Map Size — 카메라 거리 (작을수록 확대). 2D top view / 3D 공통 적용.
        # 기존 chart_3d.camera_distance 에서 이동 (2D/3D 공통 성격).
        "camera_distance": 550,
    },

    # 2D MAP 전용 (공통은 chart_common 참조)
    "chart_2d": {
        "show_points": True,       # 측정점 마커 표시
        "point_size": 4,
        "show_value_labels": False, # 측정점 옆에 VALUE 텍스트 표시
        "label_font_scale": 0.85,  # 라벨 폰트 크기 배율 (작게 0.85 / 보통 1.0 / 크게 1.15)
    },

    # 3D MAP 전용 (공통은 chart_common, Z 스케일은 메인 윈도우 컨트롤)
    "chart_3d": {
        "smooth": True,
        "z_exaggeration": 0.6,     # Z 과장 배율 (0.5~3.0, 1.0=기준)
        "show_grid": True,         # 바닥 그리드
        # View angle — 사용자 조정 가능 (이전엔 하드코딩). FOV=45 고정.
        "elevation": 40,           # 수직 각도 (-90~90°)
        "azimuth": -90,            # 수평 회전 (-180~180°). notch 6시 방향
    },

    # Summary 표
    "table": {
        "decimals": 3,             # 소수점 자릿수
        "nu_percent_suffix": True, # True: "1.69%"  False: "0.0169"
    },

    # 파싱 컬럼 alias 확장 (main.DEFAULT_COLUMN_ALIASES와 merge)
    "column_aliases": {
        # "waferid": ["MyWaferCol"],
    },

    # 페이스트 후 VALUE/X/Y 자동 선택 — fnmatch 와일드카드, 대소문자 무관
    # 매칭 조건: 패턴 매칭 + "값 개수 == DATA 컬럼 총 개수"
    # 우선순위: 패턴 목록 순서 → 같은 패턴 내 알파벳 → 매칭 안 된 나머지(알파벳)
    # Y는 X 이름의 suffix를 자동 동기화 (X="X_1000" → Y="Y_1000" 우선)
    "auto_select": {
        "value_patterns": ["T*"],
        "x_patterns":     ["X", "X*"],
        "y_patterns":     ["Y", "Y*"],
    },

    # 좌표 프리셋 라이브러리 파일 경로 (앱 실행 폴더 기준)
    "coord_library_path": "coord_library.json",

    # 좌표 라이브러리 자동 정리
    "coord_library": {
        "max_count": 1000,       # 0 = 무제한
        "max_days":  1000,       # 0 = 무제한 (created_at 기준)
    },
}


# ────────────────────────────────────────────────────────────────
# QColorDialog Custom Colors 전역 팔레트 (16 슬롯)
# ────────────────────────────────────────────────────────────────
DEFAULT_CUSTOM_COLORS = [
    # 슬롯 0~3: 배경용 (흰색 ~ 중간 회색)
    "#ffffff", "#f5f5f5", "#e0e0e0", "#bdbdbd",
    # 슬롯 4~7: 부드러운 파스텔 배경
    "#fafaf0", "#f0f8ff", "#ffe4ec", "#fffacd",
    # 슬롯 8~11: 글자/그리드용 회색 계열
    "#212529", "#495057", "#6c757d", "#adb5bd",
    # 슬롯 12~15: 사용자 저장용 빈 슬롯
    "#ffffff", "#ffffff", "#ffffff", "#ffffff",
]
