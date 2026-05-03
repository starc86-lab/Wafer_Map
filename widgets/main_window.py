"""
메인 윈도우 — 3-패널 세로 스택 (Input / Control / Result).

- Input: A/B PasteArea (가로 1:1 고정), Ctrl+V 타겟 + 단일 입력 검증 라벨
- Control: VALUE/X/Y 콤보, View(2D/3D) 콤보, Z 스케일, ▶ Run 버튼
- Result: cell 가로 나열 (cell 당 차트 + 컬러바 + 1D + Summary 표 합성)
- 우상단 ⚙ Settings 버튼 — non-modal 다이얼로그 (Save / Close)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QIcon, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QDoubleSpinBox, QProgressBar, QPushButton, QSizePolicy, QSpinBox, QSplitter,
    QToolBar, QToolButton, QVBoxLayout, QWidget,
)

import numpy as np

from core import runtime
from core.auto_select import (
    select_value, select_value_by_variability, select_xy_pairs,
    select_y_with_suffix,
)
from core.combine import (
    CombinedItem, CombinedState, is_combined_data, wrap_if_composite,
)
from core.coord_library import CoordLibrary, CoordPreset
from core.coords import normalize_to_mm
from core.settings import load_settings
from main import ParseResult

from widgets.paste_area import PasteArea
from widgets.reason_bar import ReasonBar
from widgets.result_panel import ResultPanel
from widgets.wafer_cell import WaferDisplay


def _pad_slot(slot: str) -> str:
    """Slot ID 두 자릿수 zero-pad. 숫자 아닌 경우 원본 유지."""
    try:
        return f"{int(slot):02d}"
    except (ValueError, TypeError):
        return str(slot)


def _rep_suffix(wafer_id: str) -> str:
    """`__repN` suffix 가 있으면 `(repN)` 형태로 추출. 없으면 빈 문자열.

    `_group_by_waferid` 가 같은 (wafer, PARA) 재등장 시 wafer_id 에 `__repN`
    suffix 를 붙인다. 시각화 title 에 사람 친화 형태로 표시.
    """
    idx = wafer_id.rfind("__rep")
    if idx < 0:
        return ""
    tail = wafer_id[idx + 2:]   # "rep1", "rep2"
    return f" ({tail})"


PRESET_BUTTON_TEXT = "좌표 추가"
# 버튼 텍스트 고정 (사용자 정책 2026-04-30) — 추가하면 콤보에 entry 가 늘어나는
# 것 자체가 시각적 피드백. 활성/비활성 텍스트 분기 폐지.


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Wafer Map")
        # 창 아이콘 (작업표시줄 / 타이틀바 / Alt+Tab) — frozen exe 와 dev 환경 둘 다 지원.
        # PyInstaller --onedir 6.x 는 datas 를 `_internal/` 에 넣음 → sys._MEIPASS 가
        # 해당 경로를 가리킴 (onedir/onefile 공통 동작).
        if getattr(sys, "frozen", False):
            _base = Path(getattr(sys, "_MEIPASS", str(Path(sys.executable).resolve().parent)))
        else:
            _base = Path(__file__).resolve().parent.parent
        _icon = _base / "assets" / "icon.ico"
        if _icon.exists():
            self.setWindowIcon(QIcon(str(_icon)))

        # 저장된 윈도우 크기가 있으면 우선, 없으면 해상도 티어 기반
        s = load_settings()
        win_cfg = s.get("window", {}) or {}
        saved_main = win_cfg.get("main")
        if isinstance(saved_main, (list, tuple)) and len(saved_main) == 2:
            target_w, target_h = int(saved_main[0]), int(saved_main[1])
        else:
            target_w, target_h = runtime.default_window_size("main")
        # 화면 영역 초과 방지 — 작은 모니터에서 UI 해상도 UHD 모드 등 큰 scale
        # 적용 시 윈도우가 화면 밖으로 나가 Settings 버튼 클릭 불가 deadlock
        # 회피 (사용자 정책 2026-05-01).
        _scr = QGuiApplication.primaryScreen()
        if _scr is not None:
            _avail = _scr.availableGeometry()
            target_w = min(target_w, _avail.width())
            target_h = min(target_h, _avail.height())
        self.resize(target_w, target_h)
        # 최대화 상태 복원 — resize()로 normal 크기를 먼저 넣고 최대화 플래그만 얹어야
        # 복원 버튼 / 엣지 드래그가 정상 동작 (window.main에 스크린 크기가 박히는 문제 해결)
        if win_cfg.get("maximized"):
            self.setWindowState(Qt.WindowState.WindowMaximized)

        self._result_a: ParseResult | None = None
        self._result_b: ParseResult | None = None
        # DELTA 모드 검증 결과 cache — paste 변경 시점에 한 번 계산, _refresh_controls
        # (Run 활성화) + ReasonBar 양쪽에서 재사용. 단일 입력 / 빈 입력은 빈 list.
        self._delta_warnings: list = []
        self._main_splitter_restored = False
        # 사용자 명시 추가 / 자동 RECIPE 매칭으로 가족 좌표 list 에 추가될 라이브러리
        # entries (사용자 정책 2026-04-30 — 이전 _preset_override 대체).
        # 단일 entry 시 priority 1 강제 적용 (이전 override 동일). F4 에서 가족 list
        # 에 통합 + F6 에서 priority 1 폐지 예정.
        self._added_presets: list[CoordPreset] = []
        # PARA 합성 누적 상태 — 단일 진실원. sentinel/콤보 라벨/임시 키 모두 여기서.
        self._combined_state = CombinedState()

        # Stress test (사용자 정책 2026-05-02) — 누적 leak 검증용 (한 달 무중단
        # 사용 시나리오 대비). Ctrl+Shift+T 시작 / Esc 정지. CSV 매 cycle append.
        self._stress_active: bool = False
        self._stress_remaining: int = 0
        self._stress_total: int = 0
        self._stress_count: int = 0
        self._stress_csv_file = None
        self._stress_csv_writer = None
        self._stress_btn_stop = None
        self._stress_t0: float = 0.0

        self._build_toolbar()
        self._build_central()

        # Stress test 단축키 — Ctrl+Shift+T 시작 / Esc 정지 (정지는 _stop_stress 가
        # _stress_active 검사 후 noop)
        from PySide6.QtGui import QKeySequence, QShortcut
        QShortcut(QKeySequence("Ctrl+Shift+T"), self).activated.connect(
            self._show_stress_dialog,
        )
        QShortcut(QKeySequence("Esc"), self).activated.connect(
            self._stop_stress,
        )

        # 화면 정중앙 배치 — PyInstaller splash 가 화면 중앙 hardcoded 라
        # 메인 윈도우도 중앙에 위치시켜 splash → main 전환 시 위치 일치.
        # maximized 상태면 영향 없음 (Qt 가 normal geometry 만 변경).
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            frame = self.frameGeometry()
            frame.moveCenter(avail.center())
            self.move(frame.topLeft())

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._main_splitter_restored:
            QTimer.singleShot(0, self._restore_main_splitter)

    def _restore_main_splitter(self) -> None:
        """저장된 splitter sizes 복원 (Control 항목은 항상 fixed height 로 강제)."""
        sizes = (load_settings().get("window", {}) or {}).get("splitter_sizes")
        # 사용자 정책 2026-05-04 — control_section (index 1) 은 저장값 무시하고
        # 항상 현재 sizeHint 로 override. 옛날 (button 32px, margin 6+6) 빌드의
        # 저장값이 새 (button 28px, margin 0+0) 빌드를 fat 하게 만드는 회귀 fix.
        ctl_h = self._main_splitter.widget(1).sizeHint().height()
        if isinstance(sizes, (list, tuple)) and len(sizes) == 3:
            try:
                ints = [int(v) for v in sizes]
                ints[1] = ctl_h
                self._main_splitter.setSizes(ints)
            except Exception:
                pass
        self._main_splitter_restored = True

    def closeEvent(self, event) -> None:
        # Stress test 진행 중이면 정리 (CSV close)
        if self._stress_active:
            self._stop_stress()
        # Settings 창이 열려 있으면 함께 종료 (parent=None 으로 독립 창이라 수동 처리)
        dlg = getattr(self, "_settings_dialog", None)
        if dlg is not None:
            try:
                if dlg.isVisible():
                    dlg.close()
            except Exception:
                pass
        # 메모리 캐시 폐기 → 디스크 값 fresh 로드. 사용자가 Settings 다이얼로그
        # 에서 Save 안 누르고 Close 한 변경분 (set_runtime 으로 _cache 에만 반영)
        # 이 종료 시 자동 저장되는 회귀 fix (사용자 정책 2026-05-01).
        from core import settings as settings_io
        settings_io.invalidate_cache()
        s = load_settings()
        if s.get("window_save_enabled", True):
            s.setdefault("window", {})
            # 최대화 상태면 pre-maximize 크기(normalGeometry)를 저장 —
            # 다음 실행 시 복원 버튼으로 돌아갈 크기
            if self.isMaximized():
                ng = self.normalGeometry()
                s["window"]["main"] = [ng.width(), ng.height()]
                s["window"]["maximized"] = True
            else:
                s["window"]["main"] = [self.width(), self.height()]
                s["window"]["maximized"] = False
            s["window"]["splitter_sizes"] = list(self._main_splitter.sizes())
            settings_io.save_settings(s)
        super().closeEvent(event)

    # ── 빌드 ────────────────────────────────────────────────
    def _build_toolbar(self) -> None:
        tb = QToolBar("Top")
        tb.setMovable(False)
        # 사용자 정책 2026-05-04 — 타이틀 행과 입력행 사이 구분선 삭제 + 우측 패딩 0
        # (Settings 버튼 우측 spacing 을 input B Clear 우측과 동일하게 맞춤)
        tb.setStyleSheet("QToolBar { border: 0px; padding: 0px; spacing: 0px; }")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        # 좌·중·우 3-칼럼: 가운데 타이틀이 정확히 화면 가운데 오게 좌측 더미 컬럼은 우측과 동폭
        # version 표시는 Settings dialog 우측 상단으로 이동 (사용자 정책 2026-05-04,
        # 메인 toolbar 세로 압축 — 우측 column 이 1줄로 줄어듦).
        bar = QWidget()
        grid = QGridLayout(bar)
        grid.setContentsMargins(8, 2, 8, 2)
        grid.setHorizontalSpacing(8)

        # 우측 컬럼 — 도움말 + Settings 버튼 한 줄 (우측 정렬)
        right_col = QWidget()
        right_lay = QHBoxLayout(right_col)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(4)
        right_lay.addStretch(1)

        # 사용자 정책 2026-05-04 — 도움말 ℹ️ / Settings ⚙️ 이모지만, 정사각형 28×28.
        # 외관은 글로벌 QSS `QToolButton[class="icon"]` 가 처리 (테마 자동 추종).
        btn_help = QToolButton()
        btn_help.setText("ℹ️")
        btn_help.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        btn_help.setProperty("class", "icon")
        btn_help.setFixedSize(34, 34)
        btn_help.setEnabled(False)
        btn_help.setToolTip("준비 중")
        btn_help.clicked.connect(self._open_help)
        right_lay.addWidget(btn_help)

        btn_settings = QToolButton()
        btn_settings.setText("⚙️")
        btn_settings.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        btn_settings.setProperty("class", "icon")
        btn_settings.setFixedSize(34, 34)
        btn_settings.setToolTip("Settings")
        btn_settings.clicked.connect(self._open_settings)
        right_lay.addWidget(btn_settings)

        # 좌측 더미 컬럼: 우측 컬럼과 동일 폭으로 가운데 정렬 보존
        left_dummy = QWidget()

        # 가운데 타이틀
        title = QLabel("Wafer Map")
        title.setStyleSheet("font-size: 22pt; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        grid.addWidget(left_dummy, 0, 0)
        grid.addWidget(title, 0, 1)
        grid.addWidget(right_col, 0, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 1)

        # 좌·우 컬럼이 동일 폭이 되어야 가운데가 진짜 가운데 — 우측의 sizeHint를 좌측에 강제
        left_dummy.setMinimumWidth(right_col.sizeHint().width())

        tb.addWidget(bar)
        bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def _build_central(self) -> None:
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._make_input_panel())
        # Control row + ReasonBar 묶음 (사용자 정책 2026-04-28):
        #   Control 위, ReasonBar 아래 — Run/Clear 가 ReasonBar 우측에 위치
        control_section = QWidget()
        control_section.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed,
        )
        cv = QVBoxLayout(control_section)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        self._reason_bar = ReasonBar()
        cv.addWidget(self._make_control_panel())
        cv.addWidget(self._reason_bar)
        # ReasonBar 우측에 Run / progress / Clear 만
        # (사용자 정책 2026-05-04 — View 콤보 / 체크박스 모두 control bar 로 이동)
        self._reason_bar.add_right_widget(self.btn_visualize)
        self._reason_bar.add_right_widget(self.progress_run)
        self._reason_bar.add_right_widget(self.btn_clear)
        splitter.addWidget(control_section)
        splitter.addWidget(self._make_result_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 0)   # control은 fixed라 stretch 의미 없음
        splitter.setStretchFactor(2, 5)   # 사용자 정책 2026-05-04 — Input:Result 2:5
        # Control + ReasonBar 묶음 collapse 차단 — splitter 핸들 위로 끌어올려도
        # 숨김되지 않도록 (사용자 정책 2026-04-29).
        splitter.setCollapsible(1, False)
        # 자연 높이 (Control panel + ReasonBar) 를 minimum 으로 강제
        control_section.setMinimumHeight(control_section.sizeHint().height())
        self._main_splitter = splitter
        self.setCentralWidget(splitter)

    def _make_input_panel(self) -> QWidget:
        # Input A / B 1:1 고정 (사용자 비율 조정 불가)
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.paste_a = PasteArea("Input A")
        self.paste_b = PasteArea("Input B")
        self.paste_a.parsed.connect(self._on_a_parsed)
        self.paste_b.parsed.connect(self._on_b_parsed)
        lay.addWidget(self.paste_a, stretch=1)
        lay.addWidget(self.paste_b, stretch=1)
        return w

    def _make_control_panel(self) -> QWidget:
        w = QWidget()
        # 컨트롤 패널 — 컨텐츠 자연 높이로 고정. 사용자가 splitter 핸들로 변경 불가
        w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(8)

        self.cb_value = QComboBox()
        # 통합 좌표 콤보 — "X / Y" 페어 단위 선택. 사용자가 X, Y 별도 선택하지
        # 않아도 되고 suffix 불일치(X_1000/Y_A) 조합 실수 원천 차단.
        self.cb_coord = QComboBox()
        # 공용 폭 — `X_1000_A / Y_1000_A [99 pt]` 워스트 케이스 기준 QFontMetrics 계산.
        # font_scale 대응 버퍼 후 0.9× 축소.
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self.cb_value.font())
        combo_w = int((fm.horizontalAdvance("X_1000_A / Y_1000_A [99 pt]") * 1.15 + 40) * 0.9 * 0.8)
        self.cb_value.setFixedWidth(combo_w)
        self.cb_coord.setFixedWidth(combo_w)

        self.btn_load_preset = QPushButton(PRESET_BUTTON_TEXT)
        self.btn_load_preset.setEnabled(False)
        self.btn_load_preset.clicked.connect(self._open_preset_dialog)

        self.cb_view = QComboBox(); self.cb_view.addItems(["2D", "3D"])
        self.cb_zscale = QComboBox(); self.cb_zscale.addItems(["공통", "개별"])
        self.cb_zscale.setCurrentText("개별")  # 세션 디폴트 (저장 X)

        # Z-Margin (%) — matplotlib `ax.margins()` 관례. midpoint 고정 + range*(1+pct/100).
        # 공통 / 개별 모드 각각 별도 세션 저장: 공통 default 20%, 개별 default 0%.
        # 저장 안 함 (세션 휘발 — 앱 재시작 시 default).
        self._z_margin_pct_common = 20
        self._z_margin_pct_indiv = 0
        self._last_zscale_mode = self.cb_zscale.currentText()  # "개별"
        # 변수명 `lbl_z_range` / `sp_z_range` (GUI 라벨 "Z-Margin" 과 mismatch)
        # — historical naming. settings 키는 `z_margin_pct_*` 가 진실. callsite
        # 다수라 보존, 의미는 z_margin (matplotlib margins() 관례).
        self.lbl_z_range = QLabel("Z-Margin:")
        # 5% 단위 step + 사용자 직접 입력 시 소수 1자리까지 허용. step 1→5 변경
        # (사용자 정책 2026-05-02, 미세 조정보다 큰 단위 빠른 변경이 유용)
        # FlexDoubleSpinBox — range 외 입력 자유 (예: 999 입력 후 Enter 시 200 clamp)
        from widgets.spinbox import FlexDoubleSpinBox
        self.sp_z_range = FlexDoubleSpinBox()
        self.sp_z_range.setRange(0.0, 200.0)
        self.sp_z_range.setSingleStep(5.0)
        self.sp_z_range.setDecimals(1)
        self.sp_z_range.setSuffix("%")
        # invalid 입력 → 가장 가까운 boundary 로 clamp (사용자 정책 2026-05-01).
        from PySide6.QtWidgets import QAbstractSpinBox as _ASB
        self.sp_z_range.setCorrectionMode(_ASB.CorrectionMode.CorrectToNearestValue)
        # keyboardTracking=False — 키보드 입력 중 매 자릿수 마다 valueChanged emit
        # 안 함. Enter / focus out / spin button 클릭 시 확정. "150" 입력 시
        # 1, 15, 150 매번 reapply 되던 회귀 fix (사용자 정책 2026-05-02).
        self.sp_z_range.setKeyboardTracking(False)
        _init_pct = (self._z_margin_pct_common if self._last_zscale_mode == "공통"
                     else self._z_margin_pct_indiv)
        self.sp_z_range.setValue(float(_init_pct))
        self.sp_z_range.setFixedWidth(72)
        self.sp_z_range.valueChanged.connect(self._on_z_range_changed)

        from widgets.paste_area import HEADER_BUTTON_WIDTH, HEADER_BUTTON_SPACING
        # Run — Input B 의 [Text]+[Table] 두 버튼 폭과 동일 (88*2+6=182). 그러면
        # 그 위 [Clear] 와 Run 옆 [Clear] 가 우측 정렬로 자동 일치.
        # (사용자 정책 2026-04-29: ReasonBar 이동 후 폭 넉넉해져 정렬 통일)
        # 변수명 `btn_visualize` (GUI 라벨 "Run" 과 mismatch) — historical
        # naming 유지. callsite 50+ 라 일괄 rename 회귀 위험 vs 이득 미미로 보존.
        self.btn_visualize = QPushButton("▶  Run")
        self.btn_visualize.setProperty("class", "primary")
        _run_btn_w = HEADER_BUTTON_WIDTH * 2 + HEADER_BUTTON_SPACING
        self.btn_visualize.setFixedWidth(_run_btn_w)
        self.btn_visualize.setEnabled(False)
        self.btn_visualize.clicked.connect(self._on_visualize)

        # Run 진행 중 표시 progress bar — 단계별 0~100%. indeterminate (range 0,0)
        # 은 _do_visualize 동기 block 시 paint 안 들어와 애니메이션 멈춤.
        # 각 단계마다 _set_progress() helper 가 setValue + processEvents 호출
        # (사용자 정책 2026-05-02). button 자리에 swap.
        self.progress_run = QProgressBar()
        self.progress_run.setRange(0, 100)
        self.progress_run.setValue(0)
        self.progress_run.setTextVisible(True)
        self.progress_run.setFormat("처리 중... %p%")
        self.progress_run.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_run.setFixedWidth(_run_btn_w)
        self.progress_run.setFixedHeight(28)  # QPushButton 글로벌 height 와 일관
        self.progress_run.hide()
        # progress_run 클릭 swallow — 기본 QProgressBar.mousePressEvent 는
        # ignore() 라 부모로 propagate. progress 위치(=button 위치)에 클릭이
        # 쌓이면 _restore_run_button 직후 button 에 전달되어 Run 재실행됨.
        # 명시 accept() 로 propagate 차단 (사용자 정책 2026-05-02).
        self.progress_run.mousePressEvent = lambda ev: ev.accept()
        self.progress_run.mouseReleaseEvent = lambda ev: ev.accept()
        self.progress_run.mouseDoubleClickEvent = lambda ev: ev.accept()

        # Clear — 결과 영역 비움
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setFixedWidth(HEADER_BUTTON_WIDTH)
        self.btn_clear.clicked.connect(self._on_clear_results)

        # Para 조합 — 두 PARA + 두 좌표 합쳐 시각화
        self.btn_para_combine = QPushButton("Para 조합")
        self.btn_para_combine.setEnabled(False)  # 입력 있을 때만 활성
        self.btn_para_combine.clicked.connect(self._open_para_combine_dialog)

        # 좌표 콤보 변경 시 pair 기반 로직 + VALUE 리스트 재필터
        self.cb_coord.currentIndexChanged.connect(self._on_coord_changed)
        # VALUE 변경 시 suffix 자동 좌표 매칭 + 이미 그려진 상태면 즉시 재-Run
        self.cb_value.currentIndexChanged.connect(self._on_value_changed)
        # View(2D/3D) 변경 — cell 재생성 없이 stack 인덱스만 토글 (캐시 활용)
        self.cb_view.currentTextChanged.connect(self._on_view_toggle)
        # Z scale 변경 — z_range만 갈아끼우고 3D 캐시 무효화 (2D 캐시 유지)
        self.cb_zscale.currentTextChanged.connect(self._on_zscale_toggle)

        # r-symmetry mode 체크 — 정상 2D 데이터를 강제로 radial symmetric 처리.
        # r,v 뽑아 1D fitting 후 원점 360° 회전 → 2D/3D map. 1D scan (auto-radial)
        # 데이터는 체크해도 변화 없음. 체크/해제 즉시 재렌더.
        # **세션 휘발** — settings.json 에 저장 안 함, 앱 재시작 시 항상 해제.
        # 폰트 크기: 다른 미들바 라벨과 동일하게 body 로 맞춤 (QSS 기본 체크박스는 small).
        from core.themes import FONT_SIZES
        self.chk_r_symmetry = QCheckBox("r-symmetry")
        self.chk_r_symmetry.setStyleSheet(
            f"QCheckBox {{ font-size: {FONT_SIZES.get('body', 14)}px; }}"
        )
        self.chk_r_symmetry.setChecked(False)  # 저장값 무시, 항상 해제 시작
        self.chk_r_symmetry.toggled.connect(self._on_r_symmetry_toggled)

        # Δ-Interp mode — DELTA 모드에서 좌표 일치 안 하는 점을 보간값으로 채워
        # 정상 delta 계산. Default 미체크 + 세션 휘발 (저장 안 함). A·B 모두
        # 유효한 입력일 때만 활성.
        self.chk_delta_interp = QCheckBox("Δ-Interp")
        self.chk_delta_interp.setStyleSheet(
            f"QCheckBox {{ font-size: {FONT_SIZES.get('body', 14)}px; }}"
        )
        self.chk_delta_interp.setChecked(False)
        self.chk_delta_interp.setEnabled(False)
        self.chk_delta_interp.toggled.connect(self._on_delta_interp_toggled)

        # 좌측 그룹 — Para / 좌표 / 좌표 추가 / Para 조합 (사용자 정책 2026-05-04)
        for label, widget in [
            ("Para:", self.cb_value),
            ("좌표:", self.cb_coord),
        ]:
            lay.addWidget(QLabel(label))
            lay.addWidget(widget)
        lay.addWidget(self.btn_load_preset)
        lay.addWidget(self.btn_para_combine)
        lay.addStretch(1)
        # 우측 그룹 — View / Z-Scale / Z-Margin / r-symmetry / Δ-Interp
        # (사용자 정책 2026-05-04 — View 토글 control bar 잔류, 체크박스 두 개도
        # control bar 로 복귀. ReasonBar 는 Run/Clear 만)
        lay.addWidget(QLabel("View:"))
        lay.addWidget(self.cb_view)
        lay.addWidget(QLabel("Z-Scale:"))
        lay.addWidget(self.cb_zscale)
        lay.addWidget(self.lbl_z_range)
        lay.addWidget(self.sp_z_range)
        lay.addWidget(self.chk_r_symmetry)
        lay.addWidget(self.chk_delta_interp)
        # btn_visualize / btn_clear 는 ReasonBar 우측에 add (Control 패널 X)
        # 사용자 정책 2026-05-04 — 36 (button 28 + margin 4+4) 강제. ReasonBar
        # 와 위·아래 마진 동일. 자연 sizeHint() 회귀 fix.
        w.setFixedHeight(36)
        return w

    def _make_result_panel(self) -> QWidget:
        self._result_panel = ResultPanel()
        return self._result_panel

    # ── 시그널 핸들러 ────────────────────────────────────────
    def _on_a_parsed(self, result: ParseResult | None) -> None:
        self._result_a = result
        self._clear_added_presets()
        self._clear_combined()  # 입력 변경 시 PARA 조합 자동 해제
        self._update_delta_validation()
        self._refresh_controls()

    def _on_b_parsed(self, result: ParseResult | None) -> None:
        self._result_b = result
        self._clear_added_presets()
        self._clear_combined()
        self._update_delta_validation()
        self._refresh_controls()

    def _on_clear_results(self) -> None:
        """Clear 버튼 — 결과 영역 비우고 ReasonBar 초기화. 입력 데이터는 유지."""
        self._result_panel.clear()
        self._reason_bar.set_warnings(self._delta_warnings)

    def _show_blocking_reason(
        self, code: str, severity: str, message: str,
    ) -> None:
        """Run 차단 사유를 단일 채널 (ReasonBar) 로 표시 + 결과 영역 비움.

        규약 (사용자 정책 2026-04-27 — silent 분기 일관화):
          - 결과 영역 = 항상 "현재 입력 상태" 동기화. 잔재 없음.
          - 사유 = ReasonBar 단일 채널. 다이얼로그·_summary 사용 안 함.
          - paste 시점 `_delta_warnings` 는 보존 — 차단 사유와 합쳐 표시.

        Args:
            code: 사유 식별자 (분기 분류용)
            severity: "error" / "warn" / "ok" / "info"
            message: 사용자 표시 한국어 텍스트
        """
        from core.input_validation import ValidationWarning  # 재사용
        extra = list(self._delta_warnings) + [
            ValidationWarning(code=code, severity=severity, message=message)
        ]
        self._reason_bar.set_warnings(extra)
        self._result_panel.clear()

    def _prefixed(self, prefix: str, warnings: list) -> list:
        """ValidationWarning 리스트에 메시지 prefix 추가 (`A: ...` / `B: ...`)."""
        from core.input_validation import ValidationWarning
        return [
            ValidationWarning(
                code=w.code, severity=w.severity,
                message=f"{prefix}: {w.message}",
            )
            for w in warnings
        ]

    def _update_delta_validation(self) -> None:
        """모든 검증 결과 (A 단일 + B 단일 + DELTA) 를 한 번 모아 ReasonBar 표시.

        paste 라벨은 카운트만 — warning 은 모두 ReasonBar 단일 채널 (사용자 정책
        2026-04-28). cache (`self._delta_warnings`) 는 `_refresh_controls` 가
        Run 활성화 결정에 사용 + `_show_blocking_reason` 이 Run 결과와 합쳐 표시.
        """
        from core.delta_validation import validate_delta  # lazy
        from core.input_validation import validate as validate_single  # lazy

        a, b = self._result_a, self._result_b
        all_warnings: list = []
        is_delta = bool(a and b)
        # A/B prefix 는 DELTA 모드 (양쪽 paste 사용) 일 때만 — 어느 pane 의 warning
        # 인지 구분 필요. single 모드면 prefix redundant 라 부착 X (사용자 정책 2026-04-30).
        if a:
            warns = validate_single(a)
            all_warnings.extend(self._prefixed("A", warns) if is_delta else warns)
        if b:
            warns = validate_single(b)
            all_warnings.extend(self._prefixed("B", warns) if is_delta else warns)
        if is_delta:
            all_warnings.extend(validate_delta(a, b))

        self._delta_warnings = all_warnings
        self._reason_bar.set_warnings(all_warnings)

    def _refresh_controls(self) -> None:
        """입력 결과를 바탕으로 콤보 리스트·기본값 갱신.

        순서: X/Y 먼저 결정 → X 의 n 으로 VALUE 의 required_n 확정 →
        VALUE 는 |3σ/AVG| 최대 휴리스틱으로 선택 (단일값·저변동 파라 자동 후순위).
        """
        available_ns, params, data_cols_n = self._build_selection_context()

        auto = load_settings().get("auto_select", {})
        vpat = auto.get("value_patterns", ["T*"])
        xpat = auto.get("x_patterns", ["X", "X*"])
        ypat = auto.get("y_patterns", ["Y", "Y*"])
        pmode = auto.get("priority_mode", "variability")

        # 1-2) X/Y pair 기반 선택 — suffix 매칭·n 필터·페어 없는 이름 제외
        x_sel, y_sel, x_ordered, y_ordered = select_xy_pairs(
            available_ns, xpat, ypat,
        )

        # 3) VALUE — X 의 n (좌표 개수) 기준으로 3σ/AVG 휴리스틱
        n_coords = int(available_ns.get(x_sel, data_cols_n)) if x_sel else int(data_cols_n)
        exclude = {x_sel, y_sel} - {None}
        value_sel, value_ordered = select_value_by_variability(
            params, n_coords, vpat, exclude_names=exclude, priority_mode=pmode,
        )

        any_input = bool(self._result_a or self._result_b)

        # 자동 RECIPE 매칭 — 가족 자체 페어 비어있고 사용자 명시 추가도 없으면
        # 라이브러리에서 좌표 자동 추가 (가족 list 에 silent 추가).
        # **콤보 빌드 전에** 호출 — _added_presets 가 셋된 상태에서 콤보 채워야
        # 자동 매칭 결과가 노출됨 (사용자 정책 2026-04-30, 회귀 fix).
        if (not self._added_presets and any_input
                and not (x_sel and y_sel and x_sel != value_sel
                         and y_sel != value_sel and x_sel != y_sel)):
            self._try_auto_preset(value_sel, x_sel, y_sel, available_ns)

        self._fill_value_combo(value_ordered, value_sel)
        # 좌표 콤보: itemData = (x_name, y_name, lib_id|None) 3-tuple.
        # 가족 자체 페어 (lib_id=None) + _added_presets (lib_id=preset.id).
        # 같은 (x, y) 라도 lib_id 다르면 별개 entry — 사용자 정책 2026-04-30 (a):
        # 라이브러리 다른 RECIPE entries 별개 콤보 항목, id 로 구분.
        family_pairs = set(zip(x_ordered, y_ordered))
        items: list[tuple[str, str, int | None]] = []
        seen: set[tuple[str, str, int | None]] = set()
        for x, y in zip(x_ordered, y_ordered):
            triple = (x, y, None)
            items.append(triple)
            seen.add(triple)
        for p in self._added_presets:
            triple = (p.x_name, p.y_name, p.id if p.id else None)
            if triple not in seen:
                items.append(triple)
                seen.add(triple)
        # 자동 매칭 결과 selected — 가족 페어 없을 때 _added_presets[0]
        selected_triple: tuple[str, str, int | None] | None = None
        if x_sel and y_sel:
            selected_triple = (x_sel, y_sel, None)
        elif self._added_presets:
            ap = self._added_presets[0]
            selected_triple = (ap.x_name, ap.y_name, ap.id if ap.id else None)
        self._fill_coord_combo(
            items,
            selected_triple,
            family_pairs=family_pairs,
        )

        # Run 분기 — 단일 입력 검증 (case 1/2/3) + DELTA 검증 (no_intersect 등)
        # 양쪽 모두 반영해 비활성.
        all_valid = self.paste_a.is_valid and self.paste_b.is_valid
        delta_blocking = any(
            w.severity == "error" for w in self._delta_warnings
        )
        self.btn_visualize.setEnabled(
            any_input and bool(available_ns) and all_valid and not delta_blocking
        )
        # 프리셋 수동 불러오기 — single + DELTA 모두 활성 (사용자 정책 2026-04-30,
        # 가족 좌표 정책 도입 후 DELTA 도 양 가족 공통 적용 가능).
        self.btn_load_preset.setEnabled(any_input)
        # PARA 조합 — 입력 + Run 활성 시점 (paste valid + delta 검증 통과) 에 활성
        self.btn_para_combine.setEnabled(
            any_input and bool(available_ns) and all_valid and not delta_blocking
        )
        # Δ-Interp mode — A·B 모두 유효한 입력일 때만 활성 (DELTA 모드 전용)
        delta_ready = (self._result_a is not None and self._result_b is not None
                       and self.paste_a.is_valid and self.paste_b.is_valid
                       and not delta_blocking)
        self.chk_delta_interp.setEnabled(delta_ready)
        if not delta_ready and self.chk_delta_interp.isChecked():
            self.chk_delta_interp.setChecked(False)

    def _build_selection_context(self) -> tuple[dict[str, int], dict, int]:
        """현재 양측 결과로부터 (available_ns, first_wafer_parameters, data_cols_n).

        available_ns: 모든 웨이퍼에 공통 존재하는 PARAMETER → 대표 n (첫 웨이퍼 기준).
        first_wafer_parameters: {name: WaferRecord} — VALUE 자동선택 (3σ/AVG) 계산에 필요.
        data_cols_n: DATA 컬럼 총 개수. 양쪽 모두 있으면 A 기준.
        """
        a, b = self._result_a, self._result_b
        results = [r for r in (a, b) if r is not None]
        if not results:
            return {}, {}, 0

        # VALUE 후보 PARAMETER — **합집합(union)** + **입력 순서 보존**.
        # 일부 웨이퍼만 가진 PARAMETER 도 콤보에 노출 → 누락 웨이퍼는 NaN 시각화.
        # 입력 순서: 첫 wafer 의 PARA 등장 순서대로 + 다른 wafer 의 추가 PARA 는
        # 처음 나타난 순서로 끝에 append (사용자 정책 2026-04-28).
        all_wafers = []
        if a is not None and b is not None:
            matched_ids = set(a.wafers) & set(b.wafers)
            for wid in matched_ids:
                all_wafers.append(a.wafers[wid])
                all_wafers.append(b.wafers[wid])
        else:
            all_wafers = list(results[0].wafers.values())
        if not all_wafers:
            return {}, {}, 0

        # 입력 순서대로 union — dict 사용해 자동 dedupe + insertion order 유지
        available_ns: dict[str, int] = {}
        params: dict = {}
        for w in all_wafers:
            for name, rec in w.parameters.items():
                if name not in available_ns:
                    available_ns[name] = rec.n
                    params[name] = rec
        return available_ns, params, len(results[0].data_columns)

    def _fill_coord_combo(
        self,
        items: list[tuple[str, str, int | None]],
        selected: tuple[str, str, int | None] | None,
        family_pairs: set[tuple[str, str]] | None = None,
    ) -> None:
        """cb_coord 를 (x_name, y_name, lib_id|None) 3-tuple list 로 채움.

        라벨:
          - 가족 자체 (lib_id=None): "x / y [N pt]"
          - 라이브러리 source (lib_id=int): "{id}. x / y [N pt]"

        같은 (x, y) 라도 lib_id 다르면 별개 entry (사용자 정책 2026-04-30).
        itemData = (x, y, lib_id) — 시각화 흐름에서 lib_id 로 정확한 좌표 entry 매칭.
        """
        prev = self._current_xy()
        available_ns = self._build_selection_context()[0]
        added_by_id = {
            p.id: p for p in self._added_presets if p.id
        }
        family_pairs = family_pairs or set()
        self.cb_coord.blockSignals(True)
        self.cb_coord.clear()
        for triple in items:
            x, y, lib_id = triple
            # n_points 출처:
            #   - lib_id 있음 (라이브러리 source) → preset.n_points 사용. 라이브러리
            #     entry 의 X 이름이 가족 wafer 의 X PARA 와 동일해도 라이브러리 자체
            #     n 이 정확 (사용자 정책 2026-04-30, 라벨 12pt 회귀 fix).
            #   - lib_id 없음 (가족 source) → available_ns[x] (가족 wafer 의 n).
            n: int | None = None
            if lib_id is not None:
                ap = added_by_id.get(lib_id)
                if ap is not None:
                    n = ap.n_points
            else:
                n = available_ns.get(x)
            prefix = f"{lib_id}. " if lib_id is not None else ""
            label = (f"{prefix}{x} / {y} [{n} pt]" if n is not None
                     else f"{prefix}{x} / {y}")
            self.cb_coord.addItem(label, triple)
        # prev 우선 — 새 list 에 prev 가 있으면 보존, 없으면 selected fallback.
        # 좌표 추가 시점엔 호출자 (_open_preset_dialog) 가 _refresh_controls 후
        # 직접 setCurrentIndex 로 추가된 entry 선택 (사용자 정책 2026-04-30).
        target = None
        if prev:
            for i in range(self.cb_coord.count()):
                if self.cb_coord.itemData(i) == prev:
                    target = prev
                    break
        if target is None:
            target = selected
        if target:
            for i in range(self.cb_coord.count()):
                if self.cb_coord.itemData(i) == target:
                    self.cb_coord.setCurrentIndex(i)
                    break
        self.cb_coord.blockSignals(False)

    def _current_xy(self) -> tuple[str, str, int | None] | None:
        """cb_coord 현재 선택의 (x_name, y_name, lib_id|None) 3-tuple. 선택 없으면 None.

        lib_id None = 가족 자체 페어, int = 라이브러리 source 페어 (사용자 정책 2026-04-30).
        PARA combine sentinel (`__combined__` tag) 은 별도 분기라 None 반환.
        """
        data = self.cb_coord.currentData()
        if (isinstance(data, tuple) and len(data) == 3
                and not is_combined_data(data)):
            return data
        return None

    def _fill_combo(
        self, combo: QComboBox, items: list[str], selected: str | None,
    ) -> None:
        prev = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(items)
        target = selected or prev
        if target:
            idx = combo.findText(target)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def _fill_value_combo(
        self, items: list[str], selected: str | None,
    ) -> None:
        """cb_value 를 "{name}   [N pt]" 표시로 채움. UserRole data = raw name.

        이름 획득은 _current_value() 로. currentText() 대신 UserRole 읽어야
        표시 텍스트 ([N pt] 포함) 가 아닌 순수 이름을 얻음.

        target 결정: prev (사용자 현재 선택) 우선 → selected (자동선택) fallback.
        paste 직후엔 cb_value 비어있어 prev='' → selected 자동선택 작동.
        이후 _refresh_controls 호출 (좌표 추가 등) 시 사용자 현재 선택 보존
        (사용자 정책 2026-04-30, 좌표 추가 후 VALUE 초기화 회귀 fix).
        """
        prev = self._current_value()
        available_ns = self._build_selection_context()[0]
        self.cb_value.blockSignals(True)
        self.cb_value.clear()
        for name in items:
            n = available_ns.get(name)
            label = f"{name} [{n} pt]" if n is not None else name
            self.cb_value.addItem(label, name)
        # prev 우선 — 새 list 에 prev 가 있으면 보존, 없으면 selected fallback
        target = None
        if prev:
            for i in range(self.cb_value.count()):
                if self.cb_value.itemData(i) == prev:
                    target = prev
                    break
        if target is None:
            target = selected
        if target:
            for i in range(self.cb_value.count()):
                if self.cb_value.itemData(i) == target:
                    self.cb_value.setCurrentIndex(i)
                    break
        self.cb_value.blockSignals(False)

    def _current_value(self) -> str:
        """cb_value 현재 선택의 raw 이름 (표시 텍스트의 [N pt] 접미사 제거). 없으면 ''."""
        data = self.cb_value.currentData()
        if isinstance(data, str) and data:
            return data
        return ""

    def _on_coord_changed(self, idx: int) -> None:
        """좌표 pair 변경 — VALUE 재필터.

        F6~ : preset_override 강제 1순위 폐지로 sentinel role 분기 폐지. 라이브러리
        source 페어도 가족 list 의 일반 entry 라 별도 처리 불필요. 사용자가 콤보에서
        선택한 페어가 그대로 적용 (사용자 정책 2026-04-30).
        """
        if idx < 0:
            return
        self._refilter_value_combo()

    def _on_value_changed(self, idx: int) -> None:
        """VALUE 변경 — 프리셋 중엔 좌표 고정, 일반 모드에선 suffix+n 기반 좌표 자동 매칭.

        매칭 우선순위 (프리셋 아닐 때만):
          1순위: pair x 의 suffix == VALUE suffix AND pair n == VALUE n
          2순위: pair n == VALUE n (콤보 등장 순서 첫)
        합성 sentinel 선택 시: cb_coord 의 합성 항목 자동 선택.
        그래프가 이미 그려진 상태면 재-Run.
        """
        v_data = self.cb_value.currentData()
        # 합성 sentinel 선택 → 합성 좌표 자동 선택 (사용자 정책 2026-04-28)
        if is_combined_data(v_data):
            self._auto_select_combined_coord()
            if self._result_panel.cells:
                self._on_visualize()
            return

        new_v = self._current_value()
        if not new_v:
            return
        self._auto_match_coord_by_value(new_v)
        if self._result_panel.cells:
            self._on_visualize()

    def _auto_select_combined_coord(self) -> None:
        """cb_value 의 현재 합성 sentinel 과 페어인 coord sentinel 을 cb_coord 에서 선택.

        `_combined_state` 에서 v_sentinel → CombinedItem 조회 후 item.coord_sentinel
        을 콤보에서 찾아 선택. 누적 합성에서 다른 좌표 잘못 선택되는 버그 방지
        (사용자 정책 2026-04-29).
        """
        v_data = self.cb_value.currentData()
        if not is_combined_data(v_data):
            return
        item = self._combined_state.get_by_v_sentinel(v_data)
        if item is None:
            return
        target_coord = item.coord_sentinel
        for i in range(self.cb_coord.count()):
            if self.cb_coord.itemData(i) == target_coord:
                if self.cb_coord.currentIndex() != i:
                    self.cb_coord.blockSignals(True)
                    self.cb_coord.setCurrentIndex(i)
                    self.cb_coord.blockSignals(False)
                return

    @staticmethod
    def _name_suffix(name: str) -> str:
        """이름의 첫 토큰 뒤 suffix. `T1` → '', `T1_A` → '_A', `X_1000` → '_1000', `X` → ''."""
        if "_" not in name:
            return ""
        return "_" + name.split("_", 1)[1]

    def _auto_match_coord_by_value(self, value_name: str) -> None:
        """VALUE suffix+n 기준으로 cb_coord 항목 자동 이동 (일반 모드 전용).

        signal block 으로 _on_coord_changed 재진입 차단 — VALUE 리스트는 그대로 유지.
        """
        available_ns = self._build_selection_context()[0]
        value_n = available_ns.get(value_name)
        if value_n is None:
            return
        v_suffix = self._name_suffix(value_name)

        # 라이브러리 entry n_points 는 preset 자체 값 (가족 wafer X 와 이름 같아도
        # n 다를 수 있음, 사용자 정책 2026-04-30, 라벨 12pt 회귀 fix 와 동일).
        added_by_id = {p.id: p for p in self._added_presets if p.id}
        candidates: list[tuple[int, int, str]] = []  # (idx, pair_n, x_suffix)
        for i in range(self.cb_coord.count()):
            data = self.cb_coord.itemData(i)
            if not (isinstance(data, tuple) and len(data) == 3):
                continue
            if is_combined_data(data):
                continue
            x, _y, lib_id = data
            if lib_id is not None:
                ap = added_by_id.get(lib_id)
                pair_n = ap.n_points if ap is not None else None
            else:
                pair_n = available_ns.get(x)
            if pair_n is None:
                continue
            candidates.append((i, pair_n, self._name_suffix(x)))
        if not candidates:
            return

        primary = [c for c in candidates if c[2] == v_suffix and c[1] == value_n]
        if primary:
            target_idx = primary[0][0]
        else:
            secondary = [c for c in candidates if c[1] == value_n]
            if not secondary:
                return
            target_idx = secondary[0][0]

        if target_idx == self.cb_coord.currentIndex():
            return
        self.cb_coord.blockSignals(True)
        self.cb_coord.setCurrentIndex(target_idx)
        self.cb_coord.blockSignals(False)

    def _refilter_value_combo(self) -> None:
        """좌표 pair 변경 후 VALUE 콤보 재정렬 — **현재 선택은 보존** (자동 변경 금지).

        `selected=None` 으로 `_fill_value_combo` 내부 `prev` fallback 이 동작 →
        현재 선택된 VALUE 가 새 리스트에 있으면 그대로 유지. 없으면 공백.

        합성 활성 시 콤보 재생성 skip (합성 항목 보존, 사용자 정책 2026-04-28).
        """
        if self._combined_state:
            return
        available_ns, params, data_cols_n = self._build_selection_context()
        if not available_ns:
            return
        auto = load_settings().get("auto_select", {})
        vpat = auto.get("value_patterns", ["T*"])
        pmode = auto.get("priority_mode", "variability")
        xy = self._current_xy() or ("", "", None)
        x_cur, y_cur, _lib_id = xy
        n_coords = int(available_ns.get(x_cur, data_cols_n))
        exclude = {x_cur, y_cur} - {""}
        _, value_ordered = select_value_by_variability(
            params, n_coords, vpat, exclude_names=exclude, priority_mode=pmode,
        )
        self._fill_value_combo(value_ordered, None)

    # ── 프리셋 override ───────────────────────────────
    def _open_preset_dialog(self) -> None:
        result = self._result_a or self._result_b
        if result is None or not result.wafers:
            return
        first_wafer = next(iter(result.wafers.values()))
        # VALUE n 결정 — 일반 PARA / 합성 PARA (sentinel) 분기.
        # 합성 PARA 선택 상태 (cb_value sentinel) 면 _current_value() 가 빈 문자열
        # 반환해 다이얼로그 안 열리던 버그 fix (사용자 정책 2026-04-30).
        v_data = self.cb_value.currentData()
        if is_combined_data(v_data):
            item = self._combined_state.get_by_v_sentinel(v_data)
            if item is None or item.v_key not in first_wafer.parameters:
                return
            n = first_wafer.parameters[item.v_key].n
        else:
            v = self._current_value()
            if not v or v not in first_wafer.parameters:
                return
            n = first_wafer.parameters[v].n
        current_recipe = first_wafer.recipe

        from widgets.preset_dialog import PresetSelectDialog
        library = CoordLibrary()
        dialog = PresetSelectDialog(library, current_recipe, n, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        presets = dialog.selected_presets()
        if not presets:
            return
        # 다이얼로그에서 선택한 모든 entries 추가 (다중, 사용자 정책 2026-04-30).
        # 같은 (x_name, y_name) 페어 중복 제거 (id 기준, 가족 list 에서 처리).
        existing_ids = {p.id for p in self._added_presets if p.id}
        newly_added: list[CoordPreset] = []
        for p in presets:
            library.touch(p, save=False)
            if p.id not in existing_ids:
                self._added_presets.append(p)
                existing_ids.add(p.id)
                newly_added.append(p)
        library.save()
        # 콤보 재빌드 → 추가된 페어들 노출 (VALUE 콤보는 prev 우선 = 사용자 현재
        # 선택 보존). 추가된 entry 가 있으면 좌표 콤보에서 첫 추가 entry 강제 선택
        # — "추가됨과 동시에 선택" 사용자 정책 2026-04-30.
        target_triple: tuple[str, str, int | None] | None = None
        if newly_added:
            ap = newly_added[0]
            target_triple = (ap.x_name, ap.y_name, ap.id if ap.id else None)
        self._refresh_controls()
        if target_triple is not None:
            for i in range(self.cb_coord.count()):
                if self.cb_coord.itemData(i) == target_triple:
                    self.cb_coord.setCurrentIndex(i)
                    break

    def _first_preset(self) -> CoordPreset | None:
        """`_added_presets` 의 첫 entry — 이전 `_preset_override` 호환 호출용."""
        return self._added_presets[0] if self._added_presets else None

    def _clear_added_presets(self) -> None:
        """추가된 라이브러리 좌표 모두 clear. paste 변경 시 호출 (사용자 정책
        2026-04-30: paste reset). 버튼 텍스트는 고정이라 변경 안 함."""
        if not self._added_presets:
            return
        self._added_presets.clear()

    def _try_auto_preset(self, value_sel, x_sel, y_sel, available_ns):
        """입력에 X/Y 좌표 PARAMETER 가 없으면 RECIPE 로 라이브러리 자동 매칭.

        기준: auto_select 가 고른 x_sel/y_sel 이 value_sel 과 같으면 (= 좌표로 쓸
        유효한 X/Y 가 없음) 또는 x_sel/y_sel 이 None 이면 — 자동 적용 대상.
        첫 웨이퍼의 RECIPE 로 library.find_by_recipe() 하고 결과 있으면 override 로.
        """
        # 유효한 X/Y 가 있는지 검사
        has_coord = (
            x_sel is not None and y_sel is not None
            and x_sel != value_sel and y_sel != value_sel and x_sel != y_sel
        )
        if has_coord:
            return
        # 첫 웨이퍼 RECIPE 로 조회
        first_result = self._result_a or self._result_b
        if first_result is None or not first_result.wafers:
            return
        first_wafer = next(iter(first_result.wafers.values()))
        if not first_wafer.recipe or not value_sel:
            return
        if value_sel not in first_wafer.parameters:
            return
        n = first_wafer.parameters[value_sel].n
        library = CoordLibrary()
        hits = library.find_by_recipe(first_wafer.recipe, n_points=int(n))
        if hits:
            preset = hits[0]
            self._added_presets = [preset]

    def _on_visualize(self) -> None:
        # Run 연타 차단 — 진행 중이면 즉시 무시. 핵심 흐름:
        #   1) flag set + button disable + visual feedback (text 변경)
        #   2) processEvents(ExcludeUserInputEvents) — paint 만 처리, 큐 click X
        #   3) QTimer.singleShot(0, _do_visualize) — work 다음 tick 에 deferred
        #   4) _on_visualize 즉시 return → event loop spin → 큐 click 들이
        #      disabled button 에 reject 됨
        #   5) timer 발화 → _do_visualize 동기 실행 (수 초)
        #   6) _do_visualize 끝 → finally 에서 _restore_button 도 deferred
        #      → spin 사이에 _do_visualize 동안 누적된 큐 click 들이 disabled
        #      button 에 reject → 그 후 button 활성화
        # 즉시 setEnabled(True) 하면 그 직후 spin 에서 큐 click 처리되어 회귀
        # (사용자 정책 2026-05-02, Run 연타 메모리 폭증 진짜 fix).
        if getattr(self, "_visualize_in_progress", False):
            return
        self._visualize_in_progress = True
        # stress mode: cycle timing 측정 시작
        if self._stress_active:
            import time as _time
            self._stress_t0 = _time.perf_counter()
        # button → progress bar swap (busy 애니메이션). button 은 hide 라
        # disabled click 큐 누적 방지 (Qt 가 hidden widget 의 mouse event 무시).
        self.btn_visualize.hide()
        self.progress_run.show()
        from PySide6.QtCore import QEventLoop
        from PySide6.QtWidgets import QApplication
        # paint 만 동기 처리 — user input 큐 안 건드림
        QApplication.processEvents(
            QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents,
        )
        QTimer.singleShot(0, self._do_visualize_and_defer_restore)

    def _do_visualize_and_defer_restore(self) -> None:
        try:
            self._do_visualize()
        finally:
            # button 복원도 deferred — 큐 click 들이 hidden 상태에서 무시될
            # spin 시간 확보
            QTimer.singleShot(0, self._restore_run_button)

    def _restore_run_button(self) -> None:
        # 큐에 쌓인 mouse click 을 progress_run 이 visible 인 동안 flush —
        # _set_progress 의 ExcludeUserInputEvents 때문에 처리 보류된 click 들이
        # button 표시 직후 button 에 전달되어 Run 재실행되는 회귀 fix.
        # 일반 processEvents() 로 input event 까지 처리 → progress_run 이 swallow
        # (사용자 정책 2026-05-02).
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        # 추가 안전장치 — 위 spin 후에도 OS 큐에서 새로 posting 된 mouse event 가
        # 있을 수 있어 명시 제거 (button hide 상태에서 button 으로 향하는 건 없지만
        # progress_run 으로 향하는 잔재 정리)
        QCoreApplication.removePostedEvents(
            self.progress_run, QEvent.Type.MouseButtonPress,
        )
        QCoreApplication.removePostedEvents(
            self.progress_run, QEvent.Type.MouseButtonRelease,
        )
        self.progress_run.hide()
        self.progress_run.setValue(0)  # 다음 Run 위해 reset
        self.btn_visualize.show()
        self._visualize_in_progress = False
        # stress mode chain — cycle 끝에서 csv append + 다음 cycle trigger
        if self._stress_active:
            import time as _time
            t_ms = (_time.perf_counter() - self._stress_t0) * 1000
            self._stress_log_cycle(t_ms)

    def _set_progress(self, value: int) -> None:
        """progress bar 값 갱신 + paint 강제 (user input 큐 안 건드림).

        _do_visualize 가 동기 CPU bound 라 paint event 가 안 처리됨 →
        명시 processEvents(ExcludeUserInputEvents) 호출 필요.
        """
        self.progress_run.setValue(value)
        from PySide6.QtCore import QEventLoop
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents(
            QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents,
        )

    # ─────────────────────────────────────────────────────────────
    # Stress test (사용자 정책 2026-05-02)
    # 한 달 무중단 사용 시나리오 대비 누적 leak 검증. 사용자가 paste 한 데이터로
    # N 번 자동 Run 반복 → 매 cycle CSV append (debug/stress_log_*.csv).
    # ─────────────────────────────────────────────────────────────
    def _show_stress_dialog(self) -> None:
        """Ctrl+Shift+T — stress test 시작 다이얼로그."""
        if self._stress_active:
            return
        if not (self._result_a or self._result_b):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Stress Test", "먼저 데이터를 paste 후 시작하세요.",
            )
            return
        from PySide6.QtWidgets import QInputDialog
        n, ok = QInputDialog.getInt(
            self, "Stress Test",
            "Number of runs?\n(Ctrl+Shift+T 다시 눌러도 무시 / Esc 로 정지)",
            1000, 1, 1000000, 100,
        )
        if not ok or n <= 0:
            return
        self._start_stress(n)

    def _start_stress(self, total: int) -> None:
        """CSV 파일 open + Stop 버튼 표시 + 첫 cycle trigger."""
        import csv
        from datetime import datetime
        debug_dir = Path(__file__).resolve().parent.parent / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = debug_dir / f"stress_log_{stamp}.csv"
        self._stress_csv_file = open(csv_path, "w", newline="", encoding="utf-8")
        self._stress_csv_writer = csv.writer(self._stress_csv_file)
        self._stress_csv_writer.writerow([
            "cycle", "timestamp", "n_wafers", "t_ms",
            "alive", "total_created", "rss_mb",
        ])
        self._stress_csv_file.flush()
        sys.stderr.write(f"[stress] started total={total} → {csv_path}\n")

        self._stress_active = True
        self._stress_total = total
        self._stress_remaining = total
        self._stress_count = 0

        # Stop 버튼 — ReasonBar 우측. 종료 시 제거.
        self._stress_btn_stop = QPushButton(f"Stop (0/{total})")
        self._stress_btn_stop.setFixedWidth(120)
        self._stress_btn_stop.setFixedHeight(28)  # QPushButton 글로벌 height 와 일관
        self._stress_btn_stop.clicked.connect(self._stop_stress)
        self._reason_bar.add_right_widget(self._stress_btn_stop)

        # 첫 cycle 시작
        QTimer.singleShot(50, self._on_visualize)

    def _stop_stress(self) -> None:
        """Esc 또는 Stop 버튼 — chain 끊기 + CSV close + 버튼 제거."""
        if not self._stress_active:
            return
        self._stress_active = False
        if self._stress_csv_file is not None:
            try:
                self._stress_csv_file.close()
            except Exception:
                pass
            self._stress_csv_file = None
            self._stress_csv_writer = None
        if self._stress_btn_stop is not None:
            try:
                self._reason_bar._lay.removeWidget(self._stress_btn_stop)
                self._stress_btn_stop.deleteLater()
            except Exception:
                pass
            self._stress_btn_stop = None
        sys.stderr.write(
            f"[stress] stopped at {self._stress_count}/{self._stress_total}\n"
        )

    def _stress_log_cycle(self, t_ms: float) -> None:
        """cycle 끝 — gc.collect + 측정 + CSV append + 다음 cycle trigger."""
        import gc
        from datetime import datetime
        gc.collect()
        gc.collect()  # cycle 끊기 후 회수까지 보장

        n_wafers = len(self._result_panel.cells)
        from widgets.wafer_cell import WaferCell
        alive = len(WaferCell._alive_instances)
        total_created = WaferCell._total_created
        try:
            import psutil
            rss_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        except Exception:
            rss_mb = -1.0

        self._stress_count += 1
        self._stress_remaining -= 1

        if self._stress_csv_writer is not None:
            self._stress_csv_writer.writerow([
                self._stress_count,
                datetime.now().isoformat(timespec="seconds"),
                n_wafers,
                f"{t_ms:.1f}",
                alive,
                total_created,
                f"{rss_mb:.1f}",
            ])
            self._stress_csv_file.flush()

        # 매 N/100 회 stderr 진행 상황 (sparse) + Stop 버튼 카운트 갱신
        log_every = max(1, self._stress_total // 100)
        if (self._stress_count % log_every == 0 or
                self._stress_count == self._stress_total):
            sys.stderr.write(
                f"[stress {self._stress_count}/{self._stress_total}] "
                f"n={n_wafers} t={t_ms:.0f}ms alive={alive} "
                f"rss={rss_mb:.0f}MB\n"
            )
        if self._stress_btn_stop is not None:
            self._stress_btn_stop.setText(
                f"Stop ({self._stress_count}/{self._stress_total})"
            )

        # 매 1000 회 full GC (gen 2)
        if self._stress_count % 1000 == 0:
            gc.collect(2)

        if self._stress_remaining > 0:
            QTimer.singleShot(50, self._on_visualize)
        else:
            self._stop_stress()

    def _do_visualize(self) -> None:
        self._set_progress(5)
        a, b = self._result_a, self._result_b

        if not (a or b):
            self._show_blocking_reason("no_input", "error", "입력 없음")
            return

        # ReasonBar baseline 복원 — 이전 Run 의 set_message (예: "측정점 개수 불일치")
        # stale 잔재 제거. 이후 _visualize_single/_delta 또는 _warn_n_mismatch_once
        # 가 필요 시 덮어씀 (사용자 정책 2026-04-30: DELTA 모드에서 콤보 수정 후
        # n 불일치 경고 안 사라지던 버그 fix).
        self._reason_bar.set_warnings(self._delta_warnings)

        # PARA 조합 모드 — sentinel 감지 시 state 에서 item 조회. 친화 키는 Apply
        # 시점에 wafer.parameters 에 등록되어 있음 (재 inject 불필요).
        v_data = self.cb_value.currentData()
        coord_data = self.cb_coord.currentData()
        item = None
        if is_combined_data(v_data) and is_combined_data(coord_data):
            item = self._combined_state.get_by_v_sentinel(v_data)
        if item is not None:
            v, x, y = item.v_key, item.x_key, item.y_key
            lib_id = None
        else:
            v = self._current_value()
            xy = self._current_xy()
            if xy:
                x, y, lib_id = xy
            else:
                x, y, lib_id = "", "", None
            if not v:
                self._show_blocking_reason("no_value_para", "error", "측정값 없음")
                return
            if not (x and y):
                self._show_blocking_reason("no_coord", "error", "좌표 없음")
                return

        # 렌더링 먼저 → Qt paint 완료 후 n 불일치 경고 (QTimer 한 틱 지연)
        self._set_progress(20)
        if a and b:
            self._visualize_delta(a, b, v, x, y, lib_id=lib_id)
        elif a or b:
            self._visualize_single(a or b, v, x, y, lib_id=lib_id)
        self._set_progress(95)

        # n_mismatch 검사 — preset_override 강제 1순위 폐지 후 가족 list 의 일반
        # entry 라 정상 검증 (사용자 정책 2026-04-30, F6).
        QTimer.singleShot(0, lambda: self._warn_n_mismatch_once(v, x, y))
        self._set_progress(100)

    def _inject_combined_temp_paras(
        self, a, b, item: CombinedItem,
    ) -> tuple[str | None, str | None, str | None]:
        """N-ary operands 를 wafer.parameters 에 합성 임시 키로 등록.

        concat: 좌표/값 모두 operand 별로 concatenate, 길이 = sum(n_i).
        sum: 좌표 동일 (coords[0]) — 그대로 사용, 값만 element-wise 합. 길이 = n.

        합성 키 = 친화 이름 (`item.v_key` / `item.x_key` / `item.y_key`). cell 타이틀 /
        Summary 자동으로 친화 이름 표시. paste 변경 시 result 새로 만들어져 임시
        PARA 자동 정리.

        Returns:
            (v_name, x_name, y_name) — 임시 키. 데이터 0 wafer 면 (None, None, None).
        """
        from main import WaferRecord  # lazy

        v_key, x_key, y_key = item.v_key, item.x_key, item.y_key

        injected = 0
        for result in (a, b):
            if result is None:
                continue
            for w in result.wafers.values():
                # 모든 operand + 좌표 PARA 가 wafer 에 있어야 합성 가능
                needed: set[str] = set(item.operands)
                for c in item.coords:
                    needed.add(c[0])
                    needed.add(c[1])
                if not all(n in w.parameters for n in needed):
                    continue

                if item.mode == "sum":
                    # 단일 좌표 (coords[0]). values 모두 같은 길이 가정 — 짧은 쪽 기준 정렬.
                    cx, cy = item.coords[0]
                    x_arr = np.asarray(w.parameters[cx].values, dtype=float)
                    y_arr = np.asarray(w.parameters[cy].values, dtype=float)
                    x_mm, _ = normalize_to_mm(x_arr)
                    y_mm, _ = normalize_to_mm(y_arr)
                    n = min(len(x_mm), len(y_mm))
                    v_sum = np.zeros(n, dtype=float)
                    for op in item.operands:
                        v = np.asarray(w.parameters[op].values, dtype=float)
                        n = min(n, len(v))
                        v_sum = v_sum[:n] + v[:n]
                    x_final = x_mm[:n]
                    y_final = y_mm[:n]
                    v_final = v_sum
                else:
                    # concat: operand 별로 (x,y,v) 슬라이스 → concatenate
                    xs, ys, vs = [], [], []
                    for op, (cx, cy) in zip(item.operands, item.coords):
                        x_arr = np.asarray(w.parameters[cx].values, dtype=float)
                        y_arr = np.asarray(w.parameters[cy].values, dtype=float)
                        v_arr = np.asarray(w.parameters[op].values, dtype=float)
                        x_mm, _ = normalize_to_mm(x_arr)
                        y_mm, _ = normalize_to_mm(y_arr)
                        nk = min(len(x_mm), len(y_mm), len(v_arr))
                        xs.append(x_mm[:nk])
                        ys.append(y_mm[:nk])
                        vs.append(v_arr[:nk])
                    x_final = np.concatenate(xs)
                    y_final = np.concatenate(ys)
                    v_final = np.concatenate(vs)

                n_total = len(x_final)
                # WaferRecord 임시 등록 (paste 변경 시 result 새로 만들어지면 자동 사라짐)
                w.parameters[v_key] = WaferRecord(
                    values=v_final, n=n_total, max_data_id=None,
                )
                w.parameters[x_key] = WaferRecord(
                    values=x_final, n=n_total, max_data_id=None,
                )
                w.parameters[y_key] = WaferRecord(
                    values=y_final, n=n_total, max_data_id=None,
                )
                injected += 1
        if injected == 0:
            return None, None, None
        return v_key, x_key, y_key

    def _warn_n_mismatch_once(self, v: str, x: str, y: str) -> None:
        """현재 입력에서 VALUE/X/Y n 이 모두 같은지 검사. 다르면 ReasonBar 에 warn.

        시각화는 성공한 케이스라 결과 영역 그대로 두고, ReasonBar 에 사후 알림만
        추가. paste-time baseline 위에 합쳐 표시 — 단독 set_message 로 baseline
        덮지 않음 (사용자 정책 2026-04-30).
        """
        available_ns = self._build_selection_context()[0]
        v_n = available_ns.get(v)
        x_n = available_ns.get(x)
        y_n = available_ns.get(y)
        if v_n is None or x_n is None or y_n is None:
            return
        if v_n == x_n == y_n:
            return
        from core.input_validation import ValidationWarning
        extra = list(self._delta_warnings) + [
            ValidationWarning(
                code="n_mismatch", severity="warn",
                message="측정점 개수 불일치",
            )
        ]
        self._reason_bar.set_warnings(extra)


    def _visualize_single(
        self, result: ParseResult, v: str, x: str, y: str,
        lib_id: int | None = None,
    ) -> None:
        """lib_id: 콤보 selected 의 라이브러리 entry id. None = 가족 자체 선택."""
        from core.interp import is_collinear  # lazy: scipy.interpolate 무거움
        from core.family_coord import compute_family_coords, get_family_coord
        library = CoordLibrary()
        displays: list[WaferDisplay] = []
        # ReasonBar 표시용 — cell 타이틀과 동일한 `LotID.SlotNo{rep}` 포맷
        skipped_labels: list[str] = []        # 좌표 해결 실패한 wafer (warn 알림)
        # 좌표 선택 유효성: VALUE/X/Y 이름이 서로 달라야 좌표로 취급
        coord_valid = bool(v and x and y and v != x and v != y and x != y)
        view_mode = self.cb_view.currentText() or "2D"

        # 가족 공통 좌표 정책 (F4~ 통합, 사용자 정책 2026-04-30):
        #   compute_family_coords 가 가족 자체 페어 + _added_presets (사용자 명시
        #   추가 / 자동 RECIPE 매칭) 통합한 list 반환. 각 wafer 의 좌표는
        #     priority 1: wafer 자체 X/Y (N == 가족 max 일 때)
        #     priority 2: 가족 좌표 (자체 또는 라이브러리 source)
        #     priority 3: 가족 페어 누락 시 RECIPE 라이브러리 lookup
        #   이전 preset_override 강제 1순위 폐지 (F6).
        family_coords = (
            compute_family_coords(result, added_presets=self._added_presets)
            if coord_valid else []
        )
        family_pair = (
            get_family_coord(family_coords, x, y, lib_id=lib_id)
            if coord_valid else None
        )

        for w in result.wafers.values():
            # VALUE PARAMETER 가 이 wafer 에 없으면 **NaN 으로 표시** (skip 하지 않음).
            # 일부 wafer 만 특정 PARA 가 누락된 경우에도 cell 자체는 표시.
            has_value = v in w.parameters
            val = (np.asarray(w.parameters[v].values, dtype=float)
                   if has_value else None)

            x_mm: np.ndarray | None = None
            y_mm: np.ndarray | None = None
            from_lib = False
            from_family = False

            # priority 1 — wafer 자체 X/Y. 단 N 이 가족 max 보다 작으면 가족 좌표
            # 차용 우선 (paste 잘림 시 짧은 좌표 사용 회피).
            # lib_id 있으면 wafer 자체 무시 — 사용자가 라이브러리 entry 명시 선택
            # 했으니 그 좌표 사용 (사용자 정책 2026-04-30).
            if (lib_id is None and coord_valid
                    and x in w.parameters and y in w.parameters):
                xr_raw = np.asarray(w.parameters[x].values, dtype=float)
                yr_raw = np.asarray(w.parameters[y].values, dtype=float)
                wn = min(len(xr_raw), len(yr_raw))
                family_n = family_pair.n if family_pair is not None else wn
                if wn >= family_n and wn > 0:
                    xr, _ = normalize_to_mm(xr_raw)
                    yr, _ = normalize_to_mm(yr_raw)
                    x_mm, y_mm = xr, yr

            # priority 2 — 가족 좌표 차용 (가족 페어 결정됨, source 무관)
            if x_mm is None and family_pair is not None:
                x_mm = family_pair.x_mm
                y_mm = family_pair.y_mm
                from_family = True

            # priority 3 — 라이브러리 RECIPE 자동 (가족 페어 누락 시만 — family_pair=None)
            # 정상 흐름은 _try_auto_preset 가 paste 시점에 _added_presets 추가하지만
            # 그것도 fail 한 edge 케이스 대비 방어 fallback (사용자 정책 2026-04-30).
            if x_mm is None and w.recipe:
                # val 없으면 n_points 제한 없이 library 조회 (fallback)
                n_points_arg = int(len(val)) if val is not None else None
                hits = (library.find_by_recipe(w.recipe, n_points=n_points_arg)
                        if n_points_arg is not None
                        else library.find_by_recipe(w.recipe))
                if hits:
                    preset = hits[0]
                    library.touch(preset, save=False)
                    x_mm = np.asarray(preset.x_mm, dtype=float)
                    y_mm = np.asarray(preset.y_mm, dtype=float)
                    from_lib = True

            if x_mm is None:
                # 좌표 해결 실패 → 스킵 + ReasonBar 알림용 카운트 (silent skip 금지)
                rep = _rep_suffix(w.wafer_id)
                skipped_labels.append(f"{w.lot_id}.{_pad_slot(w.slot_id)}{rep}")
                continue

            n = min(len(x_mm), len(y_mm))
            if val is not None:
                n = min(n, len(val))
            if n == 0:
                rep = _rep_suffix(w.wafer_id)
                skipped_labels.append(f"{w.lot_id}.{_pad_slot(w.slot_id)}{rep}")
                continue
            x_mm, y_mm = x_mm[:n], y_mm[:n]
            val_n = val[:n] if val is not None else np.full(n, np.nan, dtype=float)

            rep = _rep_suffix(w.wafer_id)
            title = f"{w.lot_id}.{_pad_slot(w.slot_id)}{rep} – {v}"
            if not has_value:
                title += " (no data)"
            displays.append(WaferDisplay(
                title=title,
                meta_label=f"{w.lot_id} / {_pad_slot(w.slot_id)}{rep}",
                x_mm=x_mm, y_mm=y_mm, values=val_n,
                is_radial=bool(is_collinear(x_mm, y_mm)),
            ))

        # 가족 단위 라이브러리 저장 — 가족 자체 좌표만 저장 (라이브러리 source
        # round-trip 회피, 사용자 정책 2026-04-30). family_pair.source == 'family'
        # 가 가족 자체 검증.
        coord_valid_for_save = (
            coord_valid and family_pair is not None
            and family_pair.source == "family"
        )
        if coord_valid_for_save:
            self._save_family_coords_to_library(library, result, v, x, y)
        self._enforce_library_limits(library)

        # 모든 웨이퍼 좌표 해결 실패 → 결과 영역 비우고 ReasonBar 에 사유 표시
        if not displays and len(result.wafers) > 0:
            self._show_blocking_reason(
                "single_no_coord_all", "error", "좌표 없음",
            )
            return

        # 그래프 출력 역순 적용 (사용자 정책 2026-05-03):
        # 사용자 paste 의 위쪽 행 = 최신, 아래쪽 행 = 시간순 첫번째.
        # 시간순으로 표시 (오래된 → 최신) 위해 입력 순서 reverse.
        displays.reverse()

        self._set_progress(40)
        self._apply_z_scale_mode(displays, view_mode)
        self._set_progress(60)
        # set_displays 의 cell 생성·prefetch·render 단계마다 60~86% 점진 갱신
        self._result_panel.set_displays(
            displays, v, view_mode=view_mode,
            progress_cb=self._set_progress,
        )
        self._set_progress(88)
        # ReasonBar — paste-time baseline (`_delta_warnings`) 은 _on_visualize
        # 시작 시 이미 복원됨. 여기선 일부 wafer 좌표 해결 실패만 추가 warn
        # (cell 수가 줄어든 사유). baseline 덮어쓰지 않고 합쳐서 표시.
        if skipped_labels:
            from core.input_validation import ValidationWarning
            extra = list(self._delta_warnings) + [
                ValidationWarning(
                    code="single_skipped_wafers", severity="warn",
                    message=f"좌표 해결 실패 wafer {len(skipped_labels)}개",
                )
            ]
            self._reason_bar.set_warnings(extra)
        # else: baseline 그대로 유지 (_on_visualize 에서 set 됨)
        self._connect_cell_er_signals()

    def _visualize_delta(
        self, a: ParseResult, b: ParseResult, v: str, x: str, y: str,
        lib_id: int | None = None,
    ) -> None:
        from core.delta import compute_delta  # lazy
        from core.interp import is_collinear  # lazy: scipy.interpolate 무거움
        # DELTA 모드 자동 저장 — A/B 각 웨이퍼에 실제 사용된 (x, y) pair 하나씩 저장
        coord_valid = bool(v and x and y and v != x and v != y and x != y)
        library = CoordLibrary()
        # 라이브러리 저장 가족 단위 — A 가족 + B 가족 각자 1번씩.
        # _save_family_coords_to_library 내부에서 wafer 자체 X/Y 보유 검사 →
        # 라이브러리 source 좌표는 자동 round-trip 회피 (사용자 정책 2026-04-30).
        if coord_valid:
            self._save_family_coords_to_library(library, a, v, x, y)
            self._save_family_coords_to_library(library, b, v, x, y)
            self._enforce_library_limits(library)

        # 좌표 결정 (사용자 정책 2026-04-27, A 기준):
        #   A 전체 좌표 있음 → A 좌표 사용 (wafer 별)
        #   A 전체 누락 + B 전체 있음 → B 좌표 사용
        #   A, B 양쪽 누락 → 라이브러리 (A RECIPE → B RECIPE)
        # 일부 누락은 input_validation case 3 가 paste 단계에서 Run 비활성으로 차단.
        coords_per_wafer = self._resolve_delta_coords(
            a, b, x, y, library, lib_id=lib_id,
        )
        if coords_per_wafer is None:
            # 좌표 결정 실패 (양쪽 누락 + 라이브러리 매칭 X). paste 시점 delta_validation
            # 이 이미 error 로 Run 비활성하지만 외부 라이브러리 변경 후 재시도 등
            # edge case 대비 방어적 분기 — ReasonBar 에 명시적 사유 표시.
            self._show_blocking_reason(
                "delta_coord_unresolved_runtime", "error",
                "A, B 좌표 없음",
            )
            return

        # Δ-Interp mode — 활성 시 a_only/b_only 점에 RBF 보간으로 채움.
        # Settings 의 보간법 그대로 사용 (chart_common.interp_method 등).
        interp_factory = None
        if self.chk_delta_interp.isChecked():
            from functools import partial
            from core.interp import make_interp
            sc = load_settings().get("chart_common", {})
            interp_factory = partial(
                make_interp,
                method=sc.get("interp_method", "RBF-ThinPlate"),
                radial_method=sc.get("radial_method", "Univariate Spline"),
                radial_smoothing_factor=sc.get("radial_smoothing_factor", 5.0),
                savgol_window=sc.get("savgol_window", 11),
                savgol_polyorder=sc.get("savgol_polyorder", 3),
                lowess_frac=sc.get("lowess_frac", 0.3),
                polyfit_degree=sc.get("polyfit_degree", 3),
                radial_bin_size_mm=sc.get("radial_bin_size_mm", 0),
                radial_line_width_mm=sc.get("radial_line_width_mm", 45.0),
            )

        dr = compute_delta(a, b, v, coords_per_wafer, interp_factory=interp_factory)
        if dr.matched == 0:
            # 좌표 합집합 룰로 a_only/b_only 도 매칭 카운트 — matched=0 은 거의 안 발생.
            # paste 시점 `delta_no_intersect` (WAFERID 교집합 0) 이 이미 error 로 차단되니
            # 여기 도달하면 진짜 edge case (모든 좌표 0개 등).
            self._show_blocking_reason(
                "delta_compute_failed", "error",
                "매칭 wafer 없음",
            )
            return

        displays = []
        for d in dr.deltas:
            rep = _rep_suffix(d.wafer_id)
            title = f"{d.lot_b}.{_pad_slot(d.slot_b)}{rep} – Δ {v}"
            if np.all(np.isnan(d.delta_v)):
                title += " (no data)"
            displays.append(WaferDisplay(
                title=title,
                meta_label=f"{d.lot_a} / {_pad_slot(d.slot_a)}  ←  {d.lot_b} / {_pad_slot(d.slot_b)}",
                x_mm=d.x_mm, y_mm=d.y_mm, values=d.delta_v,
                is_radial=bool(is_collinear(d.x_mm, d.y_mm)),
                is_delta=True,
                delta_interp_active=self.chk_delta_interp.isChecked(),
            ))
        # 그래프 출력 역순 (사용자 정책 2026-05-03) — single 모드와 일관.
        # compute_delta 가 A.wafers insertion order 보존이라 reverse() 만으로 충분.
        displays.reverse()
        view_mode = self.cb_view.currentText() or "2D"
        self._set_progress(40)
        self._apply_z_scale_mode(displays, view_mode)
        self._set_progress(60)
        # set_displays 의 cell 생성·prefetch·render 단계마다 60~86% 점진 갱신
        self._result_panel.set_displays(
            displays, v, view_mode=view_mode,
            progress_cb=self._set_progress,
        )
        self._set_progress(88)
        # ReasonBar — baseline (`_delta_warnings`) 은 _on_visualize 시작 시 복원됨.
        # 부분 좌표 누락 warn 은 paste 시점 validate_delta 가 이미 baseline 에
        # 포함시킴 (사용자 정책 2026-04-30 — Run 시점 surface 에서 paste 시점으로 이동).
        self._connect_cell_er_signals()

    def _connect_cell_er_signals(self) -> None:
        """set_displays 직후 각 cell 의 ER 관련 signal 연결 + 초기 master/slave 상태 적용.

        DELTA 모드 cell 만 er_row 보임. master (index 0) chk_apply_all default 체크 →
        slave 입력 disable. 이후 editingFinished/toggled 은 아래 핸들러가 처리.
        """
        cells = self._result_panel.cells
        if not cells:
            return
        for c in cells:
            c.er_time_changed.connect(
                lambda t, cell=c: self._on_cell_er_time_changed(cell, t)
            )
        master = cells[0]
        if master.chk_apply_all is not None:
            master.apply_all_toggled.connect(self._on_apply_all_toggled)
            # 초기 상태 — default 체크 → slave input disable
            initial = master.chk_apply_all.isChecked()
            for c in cells[1:]:
                c.le_time.setEnabled(not initial)
                c.lbl_time.setEnabled(not initial)

    def _on_cell_er_time_changed(self, cell, t) -> None:
        """cell 에서 ER time 값 변경 signal.

        - master + apply_all 체크 → slave 에 값 전파 + 모든 cell 재렌더
        - 그 외 → Z-Scale 모드에 따라 해당 cell or 전체 재렌더
        공통 Z-Scale 은 전체 z_range 재계산 필요 → refresh_all.
        """
        cells = self._result_panel.cells
        if not cells:
            return
        is_master = cell is cells[0] and cell.chk_apply_all is not None
        apply_all_on = is_master and cell.chk_apply_all.isChecked()
        if apply_all_on:
            for c in cells[1:]:
                c.set_er_time(t)

        is_common = self.cb_zscale.currentText() == "공통"
        view_mode = self.cb_view.currentText() or "2D"
        if is_common:
            displays = [c.display for c in cells]
            self._apply_z_scale_mode(displays, view_mode)
            self._result_panel.refresh_all()
        else:
            # 개별 모드 — z_range 도 ER time 적용된 값 기준으로 재계산해야
            # colorbar 가 stale 안 됨 (사용자 정책 2026-05-01).
            affected = list(cells) if apply_all_on else [cell]
            self._apply_z_scale_mode([c.display for c in affected], view_mode)
            for c in affected:
                c.refresh()

    def _on_apply_all_toggled(self, checked: bool) -> None:
        """master 의 '전체 적용' 체크 토글.

        체크 → slave 입력 disable + master 값으로 덮어쓰기 + 전체 재렌더.
        해제 → slave 입력 enable (값은 이미 동기된 상태, 재렌더 없음).
        """
        cells = self._result_panel.cells
        if not cells:
            return
        master = cells[0]
        if master.chk_apply_all is None:
            return
        master_t = master.display.er_time_sec
        for c in cells[1:]:
            c.le_time.setEnabled(not checked)
            c.lbl_time.setEnabled(not checked)
            if checked:
                c.set_er_time(master_t)
        if checked:
            is_common = self.cb_zscale.currentText() == "공통"
            if is_common:
                view_mode = self.cb_view.currentText() or "2D"
                displays = [c.display for c in cells]
                self._apply_z_scale_mode(displays, view_mode)
                self._result_panel.refresh_all()
            else:
                for c in cells:
                    c.refresh()

    @staticmethod
    def _dominant_recipe(result: ParseResult) -> str:
        """ParseResult 의 대표 RECIPE — 첫 웨이퍼 것. 없으면 ''."""
        if not result or not result.wafers:
            return ""
        first = next(iter(result.wafers.values()))
        return first.recipe or ""

    def _resolve_delta_coords(
        self,
        a: ParseResult,
        b: ParseResult,
        x_name: str,
        y_name: str,
        library: CoordLibrary,
        lib_id: int | None = None,
    ) -> dict[str, tuple[tuple[np.ndarray, np.ndarray],
                          tuple[np.ndarray, np.ndarray]]] | None:
        """DELTA 모드 wafer 별 좌표 결정 (가족 좌표 정책, 사용자 정책 2026-04-30).

        흐름:
          1. 양 가족 좌표 (`compute_family_coords` 의 (x_name, y_name) 페어) 결정.
          2. 가족 페어 없음 (전체 좌표 누락) → 옆집 borrow (RECIPE 호환 시) →
             라이브러리 lookup → 모두 fail 시 None.
          3. per-wafer:
             - wafer 자체 X/Y 보유 + N >= 가족 max → 자기 좌표
             - 그 외 (paste 잘림 등) → 가족 좌표 차용 (silent)

        Returns:
            {wafer_id: ((xa, ya), (xb, yb))}, 또는 None (좌표 결정 실패 → Run 비활성).
        """
        from core.coords import normalize_to_mm  # lazy
        from core.family_coord import compute_family_coords, get_family_coord
        from core.recipe_util import recipes_compatible

        common = sorted(set(a.wafers) & set(b.wafers))
        if not common:
            return {}

        # 1. 양 가족 좌표 — _added_presets 통합 (사용자 명시 추가 / 자동 매칭).
        # 가족 자체 + 라이브러리 source 모두 동일 자격 (preset_override 강제 1순위
        # 폐지, 사용자 정책 2026-04-30).
        fam_a = compute_family_coords(a, added_presets=self._added_presets)
        fam_b = compute_family_coords(b, added_presets=self._added_presets)
        fc_a = get_family_coord(fam_a, x_name, y_name, lib_id=lib_id)
        fc_b = get_family_coord(fam_b, x_name, y_name, lib_id=lib_id)

        recipe_a = self._dominant_recipe(a)
        recipe_b = self._dominant_recipe(b)
        can_borrow = recipes_compatible(recipe_a, recipe_b)

        def _lib_coord(recipe):
            if not recipe:
                return None
            hits = library.find_by_recipe(recipe)
            if not hits:
                return None
            return (np.asarray(hits[0].x_mm, dtype=float),
                    np.asarray(hits[0].y_mm, dtype=float))

        # 2. 가족 좌표 fallback chain — 옆집 borrow → 라이브러리.
        a_family = (fc_a.x_mm, fc_a.y_mm) if fc_a is not None else None
        b_family = (fc_b.x_mm, fc_b.y_mm) if fc_b is not None else None

        if a_family is None:
            if can_borrow and b_family is not None:
                a_family = b_family
            else:
                a_family = _lib_coord(recipe_a)

        if b_family is None:
            if can_borrow and fc_a is not None:
                b_family = (fc_a.x_mm, fc_a.y_mm)
            else:
                b_family = _lib_coord(recipe_b)

        if a_family is None or b_family is None:
            return None

        # 3. per-wafer — 자기 좌표 우선, 가족 좌표 fallback.
        # lib_id 있으면 wafer 자체 무시 (사용자가 라이브러리 entry 명시 선택,
        # 사용자 정책 2026-04-30, _visualize_single priority 1 가드와 동일).
        coords: dict = {}
        skip_own = lib_id is not None
        for wid in common:
            a_xy = (None if skip_own else
                    self._wafer_own_coord(a.wafers[wid], x_name, y_name, fc_a))
            b_xy = (None if skip_own else
                    self._wafer_own_coord(b.wafers[wid], x_name, y_name, fc_b))
            coords[wid] = (
                a_xy if a_xy is not None else a_family,
                b_xy if b_xy is not None else b_family,
            )
        return coords

    def _wafer_own_coord(
        self, wafer, x_name: str, y_name: str, family_pair,
    ):
        """wafer 자체 X/Y 좌표 — N >= 가족 max 일 때만 (paste 잘림 회피).

        Returns: (x_mm, y_mm) tuple 또는 None.
        """
        if x_name not in wafer.parameters or y_name not in wafer.parameters:
            return None
        xs = np.asarray(wafer.parameters[x_name].values, dtype=float)
        ys = np.asarray(wafer.parameters[y_name].values, dtype=float)
        wn = min(len(xs), len(ys))
        if wn == 0:
            return None
        family_n = family_pair.n if family_pair is not None else wn
        if wn < family_n:
            return None
        x_mm, _ = normalize_to_mm(xs[:wn])
        y_mm, _ = normalize_to_mm(ys[:wn])
        return (x_mm, y_mm)

    def _save_family_coords_to_library(
        self, library: CoordLibrary, result: ParseResult,
        v_name: str, x_name: str, y_name: str,
    ) -> None:
        """가족 단위 1회 저장 — 가족 내 v/x/y 모두 보유 + recipe 보유한 첫 wafer 의
        좌표를 라이브러리에 저장 (사용자 정책 2026-04-30, 가족 좌표 정책).

        가족이 같은 RECIPE 의 같은 좌표 PARA 이름 보유 시 좌표값 동일 보장 →
        per-wafer 저장 시도 폐지, 가족 단위 1번만.
        """
        if result is None or not result.wafers:
            return
        for w in result.wafers.values():
            if (v_name in w.parameters
                    and x_name in w.parameters and y_name in w.parameters
                    and w.recipe):
                self._save_used_pair_to_library(library, w, v_name, x_name, y_name)
                return  # 가족 단위 1번만

    def _save_used_pair_to_library(
        self, library: CoordLibrary, wafer, v_name: str, x_name: str, y_name: str,
    ) -> None:
        """실제 런에 사용된 (x_name, y_name) pair 하나만 저장.

        조건:
          - wafer 에 v/x/y parameter 모두 존재
          - 좌표 개수 n_x == n_y == n_v (유효 조합만 저장)
          - wafer.recipe 존재
        Option B — 같은 (recipe, x_name, y_name) 있으면 좌표 overwrite.
        """
        if not wafer.recipe:
            return
        # PARA 조합 합성 키 (sum: `X + Y`, concat: `X ∪ X_A`) 는 라이브러리 저장
        # 의미 X — skip. v0.4.0 의 ` ∪ ` 표기 도입으로 concat 도 필터 (사용자 정책
        # 2026-04-30, 회귀 fix).
        for n in (x_name, y_name, v_name):
            if " + " in n or " ∪ " in n:
                return
        if x_name not in wafer.parameters or y_name not in wafer.parameters:
            return
        if v_name not in wafer.parameters:
            return
        try:
            xr, _ = normalize_to_mm(wafer.parameters[x_name].values)
            yr, _ = normalize_to_mm(wafer.parameters[y_name].values)
        except (ValueError, KeyError):
            return
        v_n = int(wafer.parameters[v_name].n)
        if not (len(xr) == len(yr) == v_n) or v_n == 0:
            return
        library.add_or_touch(
            wafer.recipe, xr, yr,
            x_name=x_name, y_name=y_name, save=False,
        )

    def _enforce_library_limits(self, library: CoordLibrary) -> None:
        """Settings의 coord_library.max_count / max_days로 purge + save.

        purge 발생 여부와 무관하게 **항상 save** — `add_or_touch(save=False)` 로
        메모리에만 추가된 신규 레코드를 파일에 반영해야 함.
        """
        cl = (load_settings().get("coord_library") or {})
        mc = int(cl.get("max_count", 0) or 0)
        md = int(cl.get("max_days", 0) or 0)
        if mc > 0 or md > 0:
            library.enforce_limits(max_count=mc, max_days=md, save=False)
        library.save()

    def _apply_z_scale_mode(self, displays: list[WaferDisplay], view_mode: str) -> None:
        """cb_zscale을 ground truth로 모든 display의 z_range + z_range_1d 세팅.

        2D/3D (`z_range`): 각 wafer 의 **RBF 렌더링 값** min/max 수집 후 공통 범위.
        1D radial graph (`z_range_1d`): 각 wafer 의 **실측 v** min/max 수집 후 공통 범위.
        Z-Margin pct 는 두 범위 각각 독립 적용 (midpoint 고정).

        개별: pct=0 이면 cell 이 자체 계산 (z_range=None). pct>0 이면 각 display
        별 자체 min/max + margin 적용해서 z_range 주입 (공통과 같은 margin 메커니즘,
        단 범위만 wafer 자체).
        """
        is_common = self.cb_zscale.currentText() == "공통"
        pct = float(self.sp_z_range.value())
        # 이전엔 개별+pct=0 일 때 z_range=None 으로 cell 자체 계산 경로로 보냈으나,
        # cell 의 sampling grid (apply_cut 일 때 [0, eff_R] + [R]) 가 _apply 의 grid
        # (linspace(0, R)) 와 달라 r-symmetry mode 의 spline overshoot 시 capture
        # 되는 extreme 이 미세하게 달라짐. pct 0→1% 진입 순간 _apply 로 전환되며
        # 큰 jump 보임. 항상 _apply 경로로 통일해서 일관된 grid 사용 (사용자 정책
        # 2026-04-30).

        # 각 wafer 의 rendered 범위 추정 — **실제 렌더와 동일 rings/seg** 로 샘플.
        # 이전 코드의 희소 샘플(15×90) 은 실제 렌더(20×180) 의 극값을 놓쳐 공통
        # z_range 가 일부 wafer 값 밖으로 → 해당 wafer 색이 전부 clip 되던 문제 원인.
        from core.interp import make_interp
        from core.coords import WAFER_RADIUS_MM
        from core.settings import load_settings as _ls
        R = float(WAFER_RADIUS_MM)
        _all = _ls()
        cfg = _all.get("chart_common", {})
        # r_symmetry_mode 는 root 키 (wafer_cell render 경로와 일치).
        # 이전엔 cfg.get("r_symmetry_mode") 로 chart_common 안에서 읽어 항상 False
        # → cell 은 RadialInterp 로 그리는데 z_range 만 RBF 기준 → colorbar stale
        # (사용자 보고 2026-05-02, r-symmetry 토글 시 컬러스케일 자동 갱신 안됨 fix).
        r_sym = bool(_all.get("r_symmetry_mode", False))
        method = str(cfg.get("interp_method", "RBF-ThinPlate"))
        radial_width = float(cfg.get("radial_line_width_mm", 45.0))
        radial_method = str(cfg.get("radial_method", "Univariate Spline"))
        radial_smooth = float(cfg.get("radial_smoothing_factor", 5.0))
        savgol_w = int(cfg.get("savgol_window", 11))
        savgol_p = int(cfg.get("savgol_polyorder", 3))
        lowess_f = float(cfg.get("lowess_frac", 0.3))
        polyfit_d = int(cfg.get("polyfit_degree", 3))
        bin_size_mm = float(cfg.get("radial_bin_size_mm", 0))
        rings = max(5, int(cfg.get("radial_rings", 20)))
        seg = max(60, int(cfg.get("radial_seg", 180)))
        r_arr = np.linspace(0.0, R, rings + 1)
        theta = np.linspace(0.0, 2.0 * np.pi, seg, endpoint=False)
        Rm, Tm = np.meshgrid(r_arr, theta, indexing="ij")
        sample_pts = np.column_stack([(Rm * np.cos(Tm)).ravel(),
                                       (Rm * np.sin(Tm)).ravel()])

        # 각 wafer 의 **개별 렌더 범위** (min/max) 수집. 공통 모드 → 전체 min/max 로
        # 공통 범위. 개별 모드 → 각 wafer 자체 범위 그대로 사용.
        per_d_render: list[tuple[float, float] | None] = []
        per_d_measured: list[tuple[float, float] | None] = []
        for d in displays:
            x_arr = np.asarray(d.x_mm, dtype=float)
            y_arr = np.asarray(d.y_mm, dtype=float)
            v_arr = np.asarray(d.values, dtype=float)
            # ER Time 적용 — display.er_time_sec > 0 이면 v_arr 을 나누어 ER/RR 값으로
            # z_range 계산. cell render 경로와 일치하도록 동일 변환.
            _t = getattr(d, "er_time_sec", None)
            if _t and _t > 0:
                v_arr = v_arr / float(_t)
            m = ~np.isnan(v_arr) & ~np.isnan(x_arr) & ~np.isnan(y_arr)
            if m.sum() < 2:
                per_d_render.append(None); per_d_measured.append(None)
                continue
            valid = v_arr[m]
            # 실측 v 범위 (1D graph Y)
            per_d_measured.append(
                (float(valid.min()), float(valid.max())) if valid.size > 0 else None
            )
            # 렌더 범위 (2D/3D map Y)
            rend: tuple[float, float] | None = None
            try:
                rbf = make_interp(
                    x_arr[m], y_arr[m], v_arr[m], method=method,
                    radial_line_width_mm=radial_width,
                    radial_method=radial_method,
                    radial_smoothing_factor=radial_smooth,
                    savgol_window=savgol_w,
                    savgol_polyorder=savgol_p,
                    lowess_frac=lowess_f,
                    polyfit_degree=polyfit_d,
                    radial_bin_size_mm=bin_size_mm,
                    force_radial=r_sym,
                )
                z = rbf(sample_pts)
                zf = z[np.isfinite(z)]
                if zf.size > 0:
                    rend = (float(zf.min()), float(zf.max()))
            except Exception:
                pass
            if rend is None and valid.size > 0:
                rend = (float(valid.min()), float(valid.max()))
            per_d_render.append(rend)

        # Z-Margin — matplotlib margins() 관례. midpoint 고정 + range*(1+pct/100).
        def _margin(vmin: float, vmax: float) -> tuple[float, float]:
            if vmax <= vmin:
                vmax = vmin + 1e-9
            if pct > 0:
                midpoint = (vmin + vmax) / 2.0
                half = (vmax - vmin) / 2.0 * (1.0 + pct / 100.0)
                return midpoint - half, midpoint + half
            return vmin, vmax

        if is_common:
            rend_vals = [r for r in per_d_render if r is not None]
            meas_vals = [m for m in per_d_measured if m is not None]
            rendered_range = _margin(min(r[0] for r in rend_vals),
                                     max(r[1] for r in rend_vals)) if rend_vals else None
            measured_range = _margin(min(m[0] for m in meas_vals),
                                     max(m[1] for m in meas_vals)) if meas_vals else None
            for d in displays:
                d.z_range = rendered_range
                d.z_range_1d = measured_range
        else:
            # 개별 + pct>0 — 각 wafer 자체 범위에 margin 적용
            for d, rend, meas in zip(displays, per_d_render, per_d_measured):
                d.z_range = _margin(*rend) if rend is not None else None
                d.z_range_1d = _margin(*meas) if meas is not None else None

    def _open_para_combine_dialog(self) -> None:
        """Para 조합 다이얼로그 — 두 PARA + 두 좌표 페어 선택 후 합성 항목 등록.

        다이얼로그 콤보는 항상 오리지널 PARA 만 (이미 사용된 PARA 도 유지).
        예: T1+T1_A 만든 후에도 T1 으로 또 다른 조합 (T1+T1_B) 가능
        (사용자 정책 2026-04-29).
        """
        from widgets.para_combine_dialog import ParaCombineDialog
        a, b = self._result_a, self._result_b
        dlg = ParaCombineDialog(
            a, b, parent=self, combined_state=self._combined_state,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        result = dlg.result()
        if result is None:
            return
        # 다이얼로그가 mode 자동 판정 (좌표 동일 → sum, 아니면 concat)
        p1, p2 = result["value"]
        c1, c2 = result["coord1"], result["coord2"]
        mode = result.get("mode", "concat")
        # 같은 mode CombinedItem 의 v_key 면 자동 flatten (sum 도 concat 도 동일 정책).
        if mode == "sum":
            ops_a, _ = self._flatten_same_mode(p1, "sum", c1)
            ops_b, _ = self._flatten_same_mode(p2, "sum", c1)
            ops = ops_a + ops_b
            item = CombinedItem(operands=ops, coords=[c1] * len(ops), mode="sum")
        else:
            ops_a, coords_a = self._flatten_same_mode(p1, "concat", c1)
            ops_b, coords_b = self._flatten_same_mode(p2, "concat", c2)
            item = CombinedItem(
                operands=ops_a + ops_b,
                coords=coords_a + coords_b,
                mode="concat",
            )
        # Apply 시점에 즉시 wafer.parameters 등록 — 다이얼로그 재오픈 즉시 보이도록.
        # 실패 (operand wafer 매칭 0) 시 state 추가 안 함 + 사유 표시.
        a, b = self._result_a, self._result_b
        v, x, y = self._inject_combined_temp_paras(a, b, item)
        if v is None:
            self._show_blocking_reason(
                "combined_no_data", "error", "조합 대상 데이터 없음 (operand 누락)",
            )
            return
        self._combined_state.add(item)
        self._fill_combined_item_into_combos(item)

    def _flatten_same_mode(
        self, name: str, mode: str, fallback_coord: tuple[str, str],
    ) -> tuple[list[str], list[tuple[str, str]]]:
        """operand 가 같은 mode CombinedItem 의 v_key 면 그 operands/coords 로 펼침.

        sum 끼리 / concat 끼리는 평탄화 → 라벨 단순. 다른 mode 면 그대로 (+ 괄호 자동
        적용은 v_key 단계에서 처리). 사용자 정책 2026-04-29: "그냥 추가될 때마다
        이어붙이기".
        """
        for it in self._combined_state.items:
            if it.mode == mode and it.v_key == name:
                return list(it.operands), list(it.coords)
        return [name], [fallback_coord]
        # _refresh_controls() 호출 X — 콤보 재생성하면 합성 항목 사라짐.

    # 합성 항목 prefix 아이콘 — concat/sum 통일 (사용자 정책 2026-04-29)
    _COMBINED_ICON = "🔗"

    def _fill_combined_item_into_combos(self, item: CombinedItem) -> None:
        """합성 항목 한 개를 cb_value / cb_coord 에 추가 + 선택.

        같은 sentinel 이 이미 있으면 선택만 (중복 추가 X), 없으면 prepend (누적).
        라벨 포맷:
          - sum   : `🔗 T1 + T2 + T3  [N pt]`   / `X/Y  [N pt]` (좌표 plain)
          - concat: `🔗 T1 ∪ T1_A  [N1+N2 pt]` / `🔗 X/Y ∪ X_A/Y_A  [N1+N2 pt]`
        n_pt 는 첫 wafer 기준 (operand 가 plain PARA 든 합성 친화 키 든 동일하게 조회).
        """
        result = self._result_a or self._result_b
        first = next(iter(result.wafers.values())) if result and result.wafers else None

        def _n(name: str) -> int:
            if first is None or name not in first.parameters:
                return 0
            return first.parameters[name].n

        ic = self._COMBINED_ICON
        if item.mode == "sum":
            # sum: operands 의 n 은 모두 같아야 함 (좌표 동일이므로). 첫 항목 기준.
            n_pt = _n(item.operands[0])
            v_label = f"{ic} {item.v_key}  [{n_pt} pt]"
            x, y = item.coords[0]
            coord_label = f"{x}/{y}  [{n_pt} pt]"
        else:
            ns = [_n(p) for p in item.operands]
            cns = [_n(c[0]) for c in item.coords]
            v_label = (
                f"{ic} {item.v_key}  [{'+'.join(str(n) for n in ns)} pt]"
            )
            coord_label = (
                f"{ic} "
                f"{' ∪ '.join(f'{c[0]}/{c[1]}' for c in item.coords)}  "
                f"[{'+'.join(str(n) for n in cns)} pt]"
            )

        self.cb_value.blockSignals(True)
        self.cb_coord.blockSignals(True)
        try:
            v_idx = self._find_combo_item(self.cb_value, item.v_sentinel)
            if v_idx < 0:
                self.cb_value.insertItem(0, v_label, item.v_sentinel)
                v_idx = 0
            self.cb_value.setCurrentIndex(v_idx)

            c_idx = self._find_combo_item(self.cb_coord, item.coord_sentinel)
            if c_idx < 0:
                self.cb_coord.insertItem(0, coord_label, item.coord_sentinel)
                c_idx = 0
            self.cb_coord.setCurrentIndex(c_idx)
        finally:
            self.cb_value.blockSignals(False)
            self.cb_coord.blockSignals(False)
        # 콤보 변경 시그널 수동 emit (재시각화 등 후속 처리)
        self.cb_value.currentIndexChanged.emit(self.cb_value.currentIndex())

    @staticmethod
    def _find_combo_item(combo, target_data) -> int:
        for i in range(combo.count()):
            if combo.itemData(i) == target_data:
                return i
        return -1

    def _remove_combined_from_combos(self) -> None:
        """cb_value / cb_coord 에서 합성 sentinel 항목 제거 (있으면)."""
        for combo in (self.cb_value, self.cb_coord):
            for i in range(combo.count() - 1, -1, -1):
                if is_combined_data(combo.itemData(i)):
                    combo.removeItem(i)

    def _clear_combined(self) -> None:
        """합성 상태 해제 — sentinel 제거 + state 비우기 + wafer.parameters 임시 키 정리.

        Input A/B 어느 쪽 paste 변경 시에도 호출. state.temp_keys() 가 등록한 친화
        이름 (예: `T1 + T1_A`) 만 정확히 정리 — 사용자 PARA 에 우연히 ` + ` 포함되는
        경우에도 안전.
        """
        # sentinel 콤보 제거는 state 비우기 전에 실행 (잔재 방지)
        self._remove_combined_from_combos()
        # wafer.parameters 임시 키는 state 비우기 전에 수집해서 정리
        temp_keys = self._combined_state.temp_keys()
        self._combined_state.clear()
        for r in (self._result_a, self._result_b):
            if r is None:
                continue
            for w in r.wafers.values():
                for k in list(w.parameters):
                    if k in temp_keys:
                        del w.parameters[k]

    def _open_help(self) -> None:
        """통합 도움말 HTML 을 기본 브라우저로 오픈."""
        from widgets.help_dialog import open_help_in_browser
        open_help_in_browser()

    def _open_settings(self) -> None:
        from widgets.settings_dialog import SettingsDialog
        # 논모달 + parent=self — FBO 캡처 경로로 전환되어 Settings 창이 위에 떠있어도
        # Copy Image 에 포함되지 않음. transient owner 우회 제거, 표준 Dialog 관계 복원.
        dlg = getattr(self, "_settings_dialog", None)
        if dlg is None or not dlg.isVisible():
            dlg = SettingsDialog(parent=self)
            self._settings_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def revisualize(self) -> None:
        """현재 선택 기반으로 결과 패널 재렌더 — Run Analysis 재실행 경로 (cell 재생성)."""
        if self._result_a is None and self._result_b is None:
            return
        if not self.btn_visualize.isEnabled():
            return
        self._on_visualize()

    def refresh_graph(self) -> None:
        """Settings Graph 변경 — cell 재생성 없이 렌더 캐시만 reset + 재렌더.

        radial 경로는 RBF fit 이 ~1ms 수준으로 가벼워 별도 캐시 없이 매번 재계산.
        rings/seg/interp_method 가 바뀌면 공통 z_range 도 달라져야 하므로
        각 cell 의 display.z_range 를 재계산하고 colorbar vmin/vmax 도 맞춰 갱신.
        """
        view_mode = self.cb_view.currentText() or "2D"
        displays = [c._display for c in self._result_panel.cells]
        if displays:
            self._apply_z_scale_mode(displays, view_mode)
        self._result_panel.refresh_all()

    def _on_view_toggle(self, mode: str) -> None:
        """View 콤보 변경 — cell 재생성 없이 stack 인덱스만 토글.

        cell이 모드별 렌더 결과를 캐시 보유하므로 두 번째 진입부터는 0ms.
        """
        if mode:
            self._result_panel.set_view_mode(mode)

    def _on_zscale_toggle(self, mode: str) -> None:
        """Z scale 콤보 변경 — 이전 모드 Z-Margin 값 저장 + 새 모드 값 로드 + 재렌더.

        공통 / 개별 각각 별도 세션 저장 → 모드 간 전환 시 각자 마지막 값 복원.
        """
        prev_pct = float(self.sp_z_range.value())
        if self._last_zscale_mode == "공통":
            self._z_margin_pct_common = prev_pct
        else:
            self._z_margin_pct_indiv = prev_pct
        new_pct = (self._z_margin_pct_common if mode == "공통"
                   else self._z_margin_pct_indiv)
        self.sp_z_range.blockSignals(True)
        self.sp_z_range.setValue(float(new_pct))
        self.sp_z_range.blockSignals(False)
        self._last_zscale_mode = mode

        cells = self._result_panel.cells
        if not cells:
            return
        view_mode = self.cb_view.currentText() or "2D"
        displays = [c.display for c in cells]
        self._apply_z_scale_mode(displays, view_mode)
        self._result_panel.refresh_all()

    def _on_r_symmetry_toggled(self, checked: bool) -> None:
        """r-symmetry mode 체크 — 정상 2D 데이터를 강제 radial symmetric 처리.

        체크 시: is_radial_scan 판정 스킵하고 RadialInterp 경로로 보냄 (1D fitting
        곡선을 원점 360° 회전). 이미 auto-radial (collinear) 인 데이터는 변화 없음.
        체크/해제 모두 즉시 전 셀 재렌더.

        **세션 휘발** — settings.json 저장 안 함, set_runtime 으로 런타임 cache 만
        갱신. wafer_cell render 경로는 load_settings() 로 cache 를 읽으므로 반영됨.

        z_range 도 함께 재계산 (사용자 정책 2026-04-30) — RBF 와 RadialInterp 의
        rendered min/max 가 다를 수 있어 toggle 후 colorbar 가 stale 상태로 남으면
        Z-Margin 변경 시 처음 _apply 호출에서 큰 jump 가 보이는 버그 fix.
        """
        from core.settings import load_settings as _ls, set_runtime as _sr
        s = _ls()
        s["r_symmetry_mode"] = bool(checked)
        _sr(s)
        if not self._result_panel.cells:
            return
        view_mode = self.cb_view.currentText() or "2D"
        displays = [c.display for c in self._result_panel.cells]
        self._apply_z_scale_mode(displays, view_mode)
        self._result_panel.refresh_all()

    def _on_delta_interp_toggled(self, checked: bool) -> None:
        """Δ-Interp mode 체크 — DELTA 좌표 일치 안 하는 점을 보간으로 채움.

        DELTA 모드 전용. 체크 시 a_only/b_only 점에서 상대 측정값을 RBF 보간
        값으로 채워 정상 delta 계산 (사용자 정책 2026-04-27).

        **세션 휘발** — settings.json 저장 안 함. 이미 시각화된 cells 가 있을
        때만 재시각화 — Run 안 누른 상태에서 체크박스만 토글로 자동 렌더되던
        회귀 fix (사용자 정책 2026-05-01, r-symmetry 와 동일 가드).
        """
        if not self._result_panel.cells:
            return
        if self._result_a and self._result_b:
            self._on_visualize()

    def _on_z_range_changed(self, value: float) -> None:
        """Z-Margin 스핀박스 변경 — 현재 모드 세션값 갱신 + 재렌더. 저장 안 함."""
        if self.cb_zscale.currentText() == "공통":
            self._z_margin_pct_common = float(value)
        else:
            self._z_margin_pct_indiv = float(value)
        cells = self._result_panel.cells
        if not cells:
            return
        view_mode = self.cb_view.currentText() or "2D"
        displays = [c.display for c in cells]
        self._apply_z_scale_mode(displays, view_mode)
        self._result_panel.refresh_all()
