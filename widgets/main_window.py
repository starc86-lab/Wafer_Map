"""
메인 윈도우 — 3-패널 세로 스택 (Input / Control / Result).

뼈대 단계:
- Input: A/B PasteArea (가로 1:1 고정)
- Control: VALUE/X/Y 콤보, View(2D/3D) 콤보, Z 스케일, Visualize 버튼
- Result: placeholder (Visualize 연결은 후속)
- 우상단 ⚙ Settings 버튼 (현재는 알림만)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QIcon, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QSizePolicy, QSpinBox, QSplitter, QToolBar,
    QToolButton, QVBoxLayout, QWidget,
)

import numpy as np

from core import runtime
from core.auto_select import (
    select_value, select_value_by_variability, select_xy_pairs,
    select_y_with_suffix,
)
from core.coord_library import CoordLibrary, CoordPreset
from core.coords import normalize_to_mm
from core.settings import load_settings
from main import ParseResult

from widgets.paste_area import PasteArea
from widgets.result_panel import ResultPanel
from widgets.wafer_cell import WaferDisplay


def _pad_slot(slot: str) -> str:
    """Slot ID 두 자릿수 zero-pad. 숫자 아닌 경우 원본 유지."""
    try:
        return f"{int(slot):02d}"
    except (ValueError, TypeError):
        return str(slot)


PRESET_BUTTON_DEFAULT_TEXT = "좌표 불러오기"


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
            self.resize(int(saved_main[0]), int(saved_main[1]))
        else:
            w, h = runtime.default_window_size("main")
            self.resize(w, h)
        # 최대화 상태 복원 — resize()로 normal 크기를 먼저 넣고 최대화 플래그만 얹어야
        # 복원 버튼 / 엣지 드래그가 정상 동작 (window.main에 스크린 크기가 박히는 문제 해결)
        if win_cfg.get("maximized"):
            self.setWindowState(Qt.WindowState.WindowMaximized)

        self._result_a: ParseResult | None = None
        self._result_b: ParseResult | None = None
        # 마지막 Run signature — 동일 입력 재Run 시 재렌더 skip (cell 재생성/RBF 재계산
        # 비용 제거 + 카메라 각도·ER time 등 cell 내부 상태 보존). Settings/r-symmetry/
        # Z-Scale 등 Run 과 무관한 변경은 즉시 반영 경로라 영향 없음.
        self._last_run_signature: tuple | None = None
        self._main_splitter_restored = False
        self._preset_override: CoordPreset | None = None

        self._build_toolbar()
        self._build_central()

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
        if isinstance(sizes, (list, tuple)) and len(sizes) == 3:
            try:
                self._main_splitter.setSizes([int(v) for v in sizes])
            except Exception:
                pass
        self._main_splitter_restored = True

    def closeEvent(self, event) -> None:
        # Settings 창이 열려 있으면 함께 종료 (parent=None 으로 독립 창이라 수동 처리)
        dlg = getattr(self, "_settings_dialog", None)
        if dlg is not None:
            try:
                if dlg.isVisible():
                    dlg.close()
            except Exception:
                pass
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
            from core import settings as settings_io
            settings_io.save_settings(s)
        super().closeEvent(event)

    # ── 빌드 ────────────────────────────────────────────────
    def _build_toolbar(self) -> None:
        from app import VERSION

        tb = QToolBar("Top")
        tb.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        # 좌·중·우 3-칼럼: 가운데 타이틀이 정확히 화면 가운데 오게 좌측 더미 컬럼은 우측과 동폭
        bar = QWidget()
        grid = QGridLayout(bar)
        grid.setContentsMargins(8, 4, 8, 4)
        grid.setHorizontalSpacing(8)

        # 우측 컬럼: 버전 라벨(위) + Settings 버튼(아래)
        right_col = QWidget()
        right_lay = QVBoxLayout(right_col)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(4)
        version_label = QLabel(f"v{VERSION} | © 2026 SK hynix | Jihwan Park")
        version_label.setStyleSheet(
            "color: gray; background: transparent; "
            "font-size: 9pt; font-style: italic;"
        )
        version_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_lay.addWidget(version_label)
        btn_settings = QToolButton()
        btn_settings.setText("⚙ Settings")
        btn_settings.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        btn_settings.setStyleSheet("QToolButton { font-weight: bold; padding: 4px 10px; }")
        btn_settings.clicked.connect(self._open_settings)
        right_lay.addWidget(btn_settings, alignment=Qt.AlignmentFlag.AlignRight)

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
        splitter.addWidget(self._make_control_panel())
        splitter.addWidget(self._make_result_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 0)   # control은 fixed라 stretch 의미 없음
        splitter.setStretchFactor(2, 3)
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
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)

        self.cb_value = QComboBox()
        # 통합 좌표 콤보 — "X / Y" 페어 단위 선택. 사용자가 X, Y 별도 선택하지
        # 않아도 되고 suffix 불일치(X_1000/Y_A) 조합 실수 원천 차단.
        self.cb_coord = QComboBox()
        # 공용 폭 — `X_1000_A / Y_1000_A [99 pt]` 워스트 케이스 기준 QFontMetrics 계산.
        # font_scale 대응 버퍼 후 0.9× 축소.
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self.cb_value.font())
        combo_w = int((fm.horizontalAdvance("X_1000_A / Y_1000_A [99 pt]") * 1.15 + 40) * 0.9)
        self.cb_value.setFixedWidth(combo_w)
        self.cb_coord.setFixedWidth(combo_w)

        self.btn_load_preset = QPushButton(PRESET_BUTTON_DEFAULT_TEXT)
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
        self.lbl_z_range = QLabel("Z-Margin:")
        self.sp_z_range = QSpinBox()
        self.sp_z_range.setRange(0, 200)
        self.sp_z_range.setSingleStep(5)
        self.sp_z_range.setSuffix("%")
        _init_pct = (self._z_margin_pct_common if self._last_zscale_mode == "공통"
                     else self._z_margin_pct_indiv)
        self.sp_z_range.setValue(_init_pct)
        self.sp_z_range.setFixedWidth(72)
        self.sp_z_range.valueChanged.connect(self._on_z_range_changed)

        self.btn_visualize = QPushButton("▶  Run Analysis")
        self.btn_visualize.setProperty("class", "primary")
        # Input B 헤더 Text+Table+Clear 폭 합과 동일 (시작/끝 X가 일치하도록)
        from widgets.paste_area import HEADER_BUTTON_WIDTH, HEADER_BUTTON_SPACING
        self.btn_visualize.setFixedWidth(
            HEADER_BUTTON_WIDTH * 3 + HEADER_BUTTON_SPACING * 2
        )
        self.btn_visualize.setEnabled(False)
        self.btn_visualize.clicked.connect(self._on_visualize)

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
        self.chk_r_symmetry = QCheckBox("r-symmetry mode")
        self.chk_r_symmetry.setStyleSheet(
            f"QCheckBox {{ font-size: {FONT_SIZES.get('body', 14)}px; }}"
        )
        self.chk_r_symmetry.setChecked(False)  # 저장값 무시, 항상 해제 시작
        self.chk_r_symmetry.toggled.connect(self._on_r_symmetry_toggled)

        for label, widget in [
            ("VALUE:", self.cb_value),
            ("좌표:", self.cb_coord),
        ]:
            lay.addWidget(QLabel(label))
            lay.addWidget(widget)
        lay.addWidget(self.btn_load_preset)
        lay.addSpacing(16)
        lay.addWidget(QLabel("View:"))
        lay.addWidget(self.cb_view)
        lay.addWidget(QLabel("Z-Scale:"))
        lay.addWidget(self.cb_zscale)
        lay.addWidget(self.lbl_z_range)
        lay.addWidget(self.sp_z_range)
        lay.addSpacing(16)
        lay.addWidget(self.chk_r_symmetry)
        lay.addStretch(1)
        lay.addWidget(self.btn_visualize)
        # 자연 높이를 측정해 fix — splitter 안에서 핸들로 변경 불가
        w.adjustSize()
        w.setFixedHeight(w.sizeHint().height())
        return w

    def _make_result_panel(self) -> QWidget:
        self._result_panel = ResultPanel()
        return self._result_panel

    # ── 시그널 핸들러 ────────────────────────────────────────
    def _on_a_parsed(self, result: ParseResult | None) -> None:
        self._result_a = result
        self._reset_preset_override()
        self._refresh_controls()

    def _on_b_parsed(self, result: ParseResult | None) -> None:
        self._result_b = result
        self._reset_preset_override()
        self._refresh_controls()

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

        # 1-2) X/Y pair 기반 선택 — suffix 매칭·n 필터·페어 없는 이름 제외
        x_sel, y_sel, x_ordered, y_ordered = select_xy_pairs(
            available_ns, xpat, ypat,
        )

        # 3) VALUE — X 의 n (좌표 개수) 기준으로 3σ/AVG 휴리스틱
        n_coords = int(available_ns.get(x_sel, data_cols_n)) if x_sel else int(data_cols_n)
        exclude = {x_sel, y_sel} - {None}
        value_sel, value_ordered = select_value_by_variability(
            params, n_coords, vpat, exclude_names=exclude,
        )

        self._fill_value_combo(value_ordered, value_sel)
        # 좌표 콤보: pair 단위 — "x / y" 표시, itemData = (x, y) 튜플
        pairs = list(zip(x_ordered, y_ordered))
        self._fill_coord_combo(pairs, (x_sel, y_sel) if x_sel and y_sel else None)

        any_input = bool(self._result_a or self._result_b)
        self.btn_visualize.setEnabled(any_input and bool(available_ns))
        self.btn_load_preset.setEnabled(any_input)

        # 자동 프리셋 감지 — 입력에 X/Y 없고 RECIPE 로 라이브러리 매칭 되면 자동 적용.
        # 사용자 explicit override 가 없을 때만.
        if self._preset_override is None and any_input:
            self._try_auto_preset(value_sel, x_sel, y_sel, available_ns)
        # 프리셋 active 상태면 콤보 상단에 X_Preset / Y_Preset 합성 아이템 삽입
        self._apply_preset_indicator()

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

        # VALUE 후보 PARAMETER — **합집합(union)** 사용. 일부 웨이퍼만 가진 PARAMETER
        # 도 콤보에 노출 → 해당 VALUE 선택 시 누락 웨이퍼는 NaN 으로 시각화.
        # 이전 intersection 방식은 한 웨이퍼라도 누락이면 콤보에서 제외되어 선택
        # 불가한 버그.
        if a is not None and b is not None:
            matched_ids = set(a.wafers) & set(b.wafers)
            if matched_ids:
                per_wafer_params = (
                    [set(a.wafers[w].parameters) for w in matched_ids] +
                    [set(b.wafers[w].parameters) for w in matched_ids]
                )
                common = set.union(*per_wafer_params)
            else:
                # 교집합 0 — DELTA 시각화 불가하지만 Run 버튼은 클릭 가능해야
                # paste_b 셋째 줄에 ⚠ 안내 가능. 양측 union 으로 콤보 채움.
                common = set().union(
                    *(set(w.parameters) for w in a.wafers.values()),
                    *(set(w.parameters) for w in b.wafers.values()),
                )
        else:
            r = results[0]
            per_result = [set(w.parameters) for w in r.wafers.values()]
            common = set.union(*per_result) if per_result else set()

        # 각 PARAMETER 의 n / WaferRecord 는 **그 PARAMETER 를 가진 첫 웨이퍼** 기준.
        # (first_wafer 고정이 아니라 param 별 개별 탐색 — union 이라 일부 param 은
        # first_wafer 에 없을 수 있음)
        all_wafers = []
        if a is not None and b is not None:
            matched_ids = set(a.wafers) & set(b.wafers)
            if matched_ids:
                for wid in matched_ids:
                    all_wafers.append(a.wafers[wid])
                    all_wafers.append(b.wafers[wid])
            else:
                # 교집합 0 fallback — 양측 모든 wafer (콤보 채우기 위해)
                all_wafers = list(a.wafers.values()) + list(b.wafers.values())
        else:
            all_wafers = list(results[0].wafers.values())
        if not all_wafers:
            return {}, {}, 0

        available_ns: dict[str, int] = {}
        params: dict = {}
        for name in common:
            for w in all_wafers:
                if name in w.parameters:
                    available_ns[name] = w.parameters[name].n
                    params[name] = w.parameters[name]
                    break
        return available_ns, params, len(results[0].data_columns)

    def _fill_coord_combo(
        self,
        pairs: list[tuple[str, str]],
        selected: tuple[str, str] | None,
    ) -> None:
        """cb_coord 를 (x, y) pair 리스트로 채움.

        각 아이템 표시: "x / y   [N pt]", UserRole: (x, y) 튜플.
        N 은 x 의 좌표 개수 (같은 pair 의 x/y 는 n 동일 전제).
        """
        prev = self._current_xy()
        available_ns = self._build_selection_context()[0]
        self.cb_coord.blockSignals(True)
        self.cb_coord.clear()
        for x, y in pairs:
            n = available_ns.get(x)
            label = f"{x} / {y} [{n} pt]" if n is not None else f"{x} / {y}"
            self.cb_coord.addItem(label, (x, y))
        target = selected if selected else prev
        if target:
            for i in range(self.cb_coord.count()):
                if self.cb_coord.itemData(i) == target:
                    self.cb_coord.setCurrentIndex(i)
                    break
        self.cb_coord.blockSignals(False)

    def _current_xy(self) -> tuple[str, str] | None:
        """cb_coord 현재 선택의 (x_name, y_name) 튜플. 선택 없으면 None."""
        data = self.cb_coord.currentData()
        if isinstance(data, tuple) and len(data) == 2:
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
        """
        prev = self._current_value()
        available_ns = self._build_selection_context()[0]
        self.cb_value.blockSignals(True)
        self.cb_value.clear()
        for name in items:
            n = available_ns.get(name)
            label = f"{name} [{n} pt]" if n is not None else name
            self.cb_value.addItem(label, name)
        target = selected or prev
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
        """좌표 pair 변경 — preset 소스면 override 유지·재매핑, 아니면 해제. VALUE 재필터."""
        if idx < 0:
            return
        is_preset = self.cb_coord.itemData(idx, self._ROLE_PRESET) == "preset"

        if is_preset and self._preset_override is not None:
            xy = self.cb_coord.itemData(idx)
            if isinstance(xy, tuple) and len(xy) == 2:
                xn, yn = xy
                library = CoordLibrary()
                matched = library.find_match_by_names(
                    self._preset_override.recipe, xn, yn,
                )
                if matched is not None:
                    self._preset_override = matched
                    self.btn_load_preset.setText(f"프리셋: {matched.display_name}")
                    self._refilter_value_combo()
                    return

        # 비-preset 경로 — override 해제 + VALUE 재필터
        self._reset_preset_override()
        self._refilter_value_combo()

    def _on_value_changed(self, idx: int) -> None:
        """VALUE 변경 — 프리셋 중엔 좌표 고정, 일반 모드에선 suffix+n 기반 좌표 자동 매칭.

        매칭 우선순위 (프리셋 아닐 때만):
          1순위: pair x 의 suffix == VALUE suffix AND pair n == VALUE n
          2순위: pair n == VALUE n (콤보 등장 순서 첫)
        매칭 안 되면 좌표 유지.
        그래프가 이미 그려진 상태면 재-Run.
        """
        new_v = self._current_value()
        if not new_v:
            return
        if self._preset_override is None:
            self._auto_match_coord_by_value(new_v)
        if self._result_panel.cells:
            self._on_visualize()

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

        candidates: list[tuple[int, int, str]] = []  # (idx, pair_n, x_suffix)
        for i in range(self.cb_coord.count()):
            data = self.cb_coord.itemData(i)
            if not (isinstance(data, tuple) and len(data) == 2):
                continue
            x, _ = data
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
        """
        available_ns, params, data_cols_n = self._build_selection_context()
        if not available_ns:
            return
        auto = load_settings().get("auto_select", {})
        vpat = auto.get("value_patterns", ["T*"])
        xy = self._current_xy() or ("", "")
        x_cur, y_cur = xy
        n_coords = int(available_ns.get(x_cur, data_cols_n))
        exclude = {x_cur, y_cur} - {""}
        _, value_ordered = select_value_by_variability(
            params, n_coords, vpat, exclude_names=exclude,
        )
        self._fill_value_combo(value_ordered, None)

    # ── 프리셋 override ───────────────────────────────
    def _open_preset_dialog(self) -> None:
        result = self._result_a or self._result_b
        if result is None or not result.wafers:
            return
        v = self._current_value()
        if not v:
            return
        first_wafer = next(iter(result.wafers.values()))
        if v not in first_wafer.parameters:
            return
        n = first_wafer.parameters[v].n
        current_recipe = first_wafer.recipe

        from widgets.preset_dialog import PresetSelectDialog
        library = CoordLibrary()
        dialog = PresetSelectDialog(library, current_recipe, n, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        preset = dialog.selected_preset()
        if preset is None:
            return
        library.touch(preset)
        self._preset_override = preset
        self.btn_load_preset.setText(f"프리셋: {preset.display_name}")
        self._apply_preset_indicator()

    def _reset_preset_override(self) -> None:
        if self._preset_override is None:
            return
        self._preset_override = None
        self.btn_load_preset.setText(PRESET_BUTTON_DEFAULT_TEXT)
        self._apply_preset_indicator()

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
            self._preset_override = preset
            self.btn_load_preset.setText(f"프리셋: {preset.display_name}")

    # preset 소스 마킹 role — UserRole 은 (x, y) tuple 로 이미 사용 중.
    # UserRole+1 을 별도 role 로 써서 "preset" 여부 플래그만 저장.
    _ROLE_PRESET = int(Qt.ItemDataRole.UserRole) + 1

    def _apply_preset_indicator(self):
        """preset 활성 시 cb_coord 상단에 해당 preset pair **하나만** "x / y   [N pt]" 로 삽입.

        - 저장 단위가 per-pair 로 바뀐 뒤 프리셋 로드 = pair 하나 → 상단에 그 하나만.
        - UserRole = (x_name, y_name) tuple (기존 아이템과 동일 규약 유지)
        - UserRole+1 = "preset" 플래그 (스타일 구분용)
        - 입력에 같은 pair 가 있으면 제거 (preset 버전이 대체).
        """
        from PySide6.QtGui import QBrush, QColor, QFont
        combo = self.cb_coord
        combo.blockSignals(True)
        try:
            for i in range(combo.count() - 1, -1, -1):
                if combo.itemData(i, self._ROLE_PRESET) == "preset":
                    combo.removeItem(i)

            if self._preset_override is None:
                return

            p = self._preset_override
            n = len(p.x_mm)
            label = f"{p.x_name} / {p.y_name} [{n} pt]"
            for j in range(combo.count() - 1, -1, -1):
                data = combo.itemData(j)
                if isinstance(data, tuple) and data == (p.x_name, p.y_name):
                    combo.removeItem(j)
            combo.insertItem(0, label, (p.x_name, p.y_name))
            combo.setItemData(0, "preset", self._ROLE_PRESET)
            f = QFont(combo.font())
            f.setBold(True)
            combo.setItemData(0, f, Qt.ItemDataRole.FontRole)
            combo.setItemData(0, QBrush(QColor("#4361ee")),
                              Qt.ItemDataRole.ForegroundRole)
            combo.setCurrentIndex(0)
        finally:
            combo.blockSignals(False)

    def _on_visualize(self) -> None:
        v = self._current_value()
        xy = self._current_xy()
        x = xy[0] if xy else ""
        y = xy[1] if xy else ""
        if not v:
            return

        # Run 변경 감지 — 같은 입력이면 skip (cell 재생성 안 함 → 카메라/휠 zoom/
        # ER time 등 cell 상태 유지 + RBF 재계산 비용 제거). signature 는 paste
        # 텍스트 + 콤보 선택 조합. 좌표 preset/라이브러리 자동 적용은 paste+VALUE
        # 로부터 결정론적이라 포함 불필요.
        signature = (
            self.paste_a.text(),
            self.paste_b.text(),
            v, x, y,
        )
        if signature == self._last_run_signature and self._result_panel.cells:
            return
        self._last_run_signature = signature
        # 좌표 콤보 비어있음 → 팝업 안내. 입력에 X/Y 없고 라이브러리 매칭도 없는 케이스.
        if not (x and y):
            QMessageBox.warning(
                self, "좌표 없음",
                "X / Y 좌표를 확인할 수 없어 시각화할 수 없습니다.\n\n"
                "다음 중 하나를 시도하세요:\n"
                "  · 입력 데이터에 X, Y 좌표 PARAMETER 행이 있는지 확인\n"
                "  · '좌표 불러오기' 로 저장된 프리셋 선택\n"
                "  · Settings → 좌표 라이브러리 → 수동 추가",
            )
            return

        # 렌더링 먼저 → Qt paint 완료 후 n 불일치 경고 팝업 (QTimer 한 틱 지연)
        a, b = self._result_a, self._result_b
        if a and b:
            self._visualize_delta(a, b, v, x, y)
        elif a or b:
            self._visualize_single(a or b, v, x, y)
        else:
            self._result_panel.clear()

        if self._preset_override is None:
            QTimer.singleShot(0, lambda: self._warn_n_mismatch_once(v, x, y))

    def _warn_n_mismatch_once(self, v: str, x: str, y: str) -> None:
        """현재 입력에서 VALUE/X/Y n 이 모두 같은지 검사. 다르면 경고 팝업 1회."""
        available_ns = self._build_selection_context()[0]
        v_n = available_ns.get(v)
        x_n = available_ns.get(x)
        y_n = available_ns.get(y)
        if v_n is None or x_n is None or y_n is None:
            return
        if v_n == x_n == y_n:
            return
        QMessageBox.warning(
            self, "포인트 개수 불일치",
            f"VALUE와 좌표 포인트 개수가 다릅니다.\n"
            f"{v}: {v_n} pt\n"
            f"{x} / {y}: {x_n if x_n == y_n else f'{x_n}/{y_n}'} pt",
        )


    def _visualize_single(
        self, result: ParseResult, v: str, x: str, y: str,
    ) -> None:
        from core.interp import is_collinear  # lazy: scipy.interpolate 무거움
        library = CoordLibrary()
        displays: list[WaferDisplay] = []
        # 좌표 선택 유효성: VALUE/X/Y 이름이 서로 달라야 좌표로 취급
        coord_valid = bool(v and x and y and v != x and v != y and x != y)
        view_mode = self.cb_view.currentText() or "2D"

        override = self._preset_override

        for w in result.wafers.values():
            # VALUE PARAMETER 가 이 wafer 에 없으면 **NaN 으로 표시** (skip 하지 않음).
            # 일부 wafer 만 특정 PARA 가 누락된 경우에도 cell 자체는 표시.
            has_value = v in w.parameters
            val = (np.asarray(w.parameters[v].values, dtype=float)
                   if has_value else None)

            # 우선순위: (1) 사용자가 선택한 프리셋 override
            #          (2) 사용자 콤보 X/Y 선택 (coord_valid 한 경우)
            #          (3) RECIPE 기반 라이브러리 자동 조회
            x_mm: np.ndarray | None = None
            y_mm: np.ndarray | None = None
            from_lib = False
            from_preset = False

            if override is not None:
                matched = library.find_match_by_names(override.recipe, x, y)
                if matched is not None:
                    x_mm = np.asarray(matched.x_mm, dtype=float)
                    y_mm = np.asarray(matched.y_mm, dtype=float)
                    library.touch(matched, save=False)
                    from_preset = True
            if x_mm is None and coord_valid and x in w.parameters and y in w.parameters:
                xr, _ = normalize_to_mm(w.parameters[x].values)
                yr, _ = normalize_to_mm(w.parameters[y].values)
                if len(xr) > 0 and len(yr) > 0:
                    x_mm, y_mm = xr, yr

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
                continue  # 좌표 해결 실패 → 스킵 (NaN cell 도 좌표 필요)

            n = min(len(x_mm), len(y_mm))
            if val is not None:
                n = min(n, len(val))
            if n == 0:
                continue
            x_mm, y_mm = x_mm[:n], y_mm[:n]
            val_n = val[:n] if val is not None else np.full(n, np.nan, dtype=float)

            # 좌표 저장은 VALUE 가 있고 실제 사용자 조합일 때만
            if has_value and not (from_preset or from_lib):
                self._save_used_pair_to_library(library, w, v, x, y)

            title = f"{w.lot_id}.{_pad_slot(w.slot_id)} – {v}"
            if not has_value:
                title += " (no data)"
            displays.append(WaferDisplay(
                title=title,
                meta_label=f"{w.lot_id} / {_pad_slot(w.slot_id)}",
                x_mm=x_mm, y_mm=y_mm, values=val_n,
                is_radial=bool(is_collinear(x_mm, y_mm)),
            ))

        self._enforce_library_limits(library)

        # 모든 웨이퍼 좌표 해결 실패 → 사용자에게 안내
        if not displays and len(result.wafers) > 0:
            QMessageBox.warning(
                self, "좌표 없음",
                "X/Y 좌표를 확인할 수 없어 시각화할 수 없습니다.\n\n"
                "다음 중 하나를 시도하세요:\n"
                "  · 입력 데이터에 X, Y 좌표 PARAMETER 가 있는지 확인\n"
                "  · Control 패널의 X / Y 콤보에서 올바른 좌표 이름 선택\n"
                "  · '좌표 불러오기' 로 저장된 프리셋 선택\n"
                "  · 좌표 라이브러리에 현재 RECIPE 에 맞는 프리셋 수동 추가",
            )
            return

        self._apply_z_scale_mode(displays, view_mode)
        self._result_panel.set_displays(displays, v, view_mode=view_mode)
        self._connect_cell_er_signals()

    def _visualize_delta(
        self, a: ParseResult, b: ParseResult, v: str, x: str, y: str,
    ) -> None:
        from core.delta import compute_delta  # lazy
        from core.interp import is_collinear  # lazy: scipy.interpolate 무거움
        # DELTA 모드 자동 저장 — A/B 각 웨이퍼에 실제 사용된 (x, y) pair 하나씩 저장
        coord_valid = bool(v and x and y and v != x and v != y and x != y)
        if coord_valid:
            library = CoordLibrary()
            for result in (a, b):
                for w in result.wafers.values():
                    self._save_used_pair_to_library(library, w, v, x, y)
            self._enforce_library_limits(library)

        dr = compute_delta(a, b, v, x, y, tolerance_mm=1e-3)

        # ── DELTA 검사 → paste_b 한 줄 메시지 끝에 추가 ──
        # 1) WAFERID 교집합 0 → 시각화 skip + DELTA error. Input B 데이터는 유지.
        if dr.matched == 0:
            self.paste_b.set_delta_status("DELTA: 교집합 없음", severity="error")
            self._result_panel.clear()
            return

        # 2) RECIPE 일치 검사 — A/B 의 dominant recipe
        delta_warnings: list[str] = []
        recipe_a = self._dominant_recipe(a)
        recipe_b = self._dominant_recipe(b)
        if recipe_a and recipe_b and recipe_a.strip().lower() != recipe_b.strip().lower():
            delta_warnings.append(f"DELTA: RECIPE 다름 ({recipe_a}, {recipe_b})")

        # 3) PARA union 일치 검사 — A 의 union vs B 의 union
        para_a = set().union(*(set(w.parameters) for w in a.wafers.values())) if a.wafers else set()
        para_b = set().union(*(set(w.parameters) for w in b.wafers.values())) if b.wafers else set()
        if para_a != para_b:
            delta_warnings.append("DELTA: PARA 다름")

        if delta_warnings:
            head = delta_warnings[0]
            tail = f" 외 {len(delta_warnings) - 1}건" if len(delta_warnings) > 1 else ""
            self.paste_b.set_delta_status(f"{head}{tail}", severity="warn")
        else:
            self.paste_b.set_delta_status(
                f"DELTA OK 매칭 {dr.matched}", severity="ok",
            )

        displays = []
        for d in dr.deltas:
            title = f"{d.lot_a}.{_pad_slot(d.slot_a)} – Δ {v}"
            if np.all(np.isnan(d.delta_v)):
                title += " (no data)"
            displays.append(WaferDisplay(
                title=title,
                meta_label=f"{d.lot_a} / {_pad_slot(d.slot_a)}  ←  {d.lot_b} / {_pad_slot(d.slot_b)}",
                x_mm=d.x_mm, y_mm=d.y_mm, values=d.delta_v,
                is_radial=bool(is_collinear(d.x_mm, d.y_mm)),
                is_delta=True,
            ))
        view_mode = self.cb_view.currentText() or "2D"
        self._apply_z_scale_mode(displays, view_mode)
        self._result_panel.set_displays(displays, v, view_mode=view_mode)
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
        if is_common:
            view_mode = self.cb_view.currentText() or "2D"
            displays = [c.display for c in cells]
            self._apply_z_scale_mode(displays, view_mode)
            self._result_panel.refresh_all()
        else:
            if apply_all_on:
                for c in cells:
                    c.refresh()
            else:
                cell.refresh()

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
        pct = int(self.sp_z_range.value())
        if not is_common and pct == 0:
            # 개별 + margin 없음 → cell 자체 계산 (기존 경로, 비용 절약)
            for d in displays:
                d.z_range = None
                d.z_range_1d = None
            return

        # 각 wafer 의 rendered 범위 추정 — **실제 렌더와 동일 rings/seg** 로 샘플.
        # 이전 코드의 희소 샘플(15×90) 은 실제 렌더(20×180) 의 극값을 놓쳐 공통
        # z_range 가 일부 wafer 값 밖으로 → 해당 wafer 색이 전부 clip 되던 문제 원인.
        from core.interp import make_interp
        from core.coords import WAFER_RADIUS_MM
        from core.settings import load_settings as _ls
        R = float(WAFER_RADIUS_MM)
        cfg = _ls().get("chart_common", {})
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
                    force_radial=bool(cfg.get("r_symmetry_mode", False)),
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

    def _open_settings(self) -> None:
        from widgets.settings_dialog import SettingsDialog
        # 논모달 + parent=self — FBO 캡처 경로로 전환되어 Settings 창이 위에 떠있어도
        # Copy Graph 에 포함되지 않음. transient owner 우회 제거, 표준 Dialog 관계 복원.
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
        prev_pct = int(self.sp_z_range.value())
        if self._last_zscale_mode == "공통":
            self._z_margin_pct_common = prev_pct
        else:
            self._z_margin_pct_indiv = prev_pct
        new_pct = (self._z_margin_pct_common if mode == "공통"
                   else self._z_margin_pct_indiv)
        self.sp_z_range.blockSignals(True)
        self.sp_z_range.setValue(new_pct)
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
        """
        from core.settings import load_settings as _ls, set_runtime as _sr
        s = _ls()
        s["r_symmetry_mode"] = bool(checked)
        _sr(s)
        if not self._result_panel.cells:
            return
        self._result_panel.refresh_all()

    def _on_z_range_changed(self, value: int) -> None:
        """Z-Margin 스핀박스 변경 — 현재 모드 세션값 갱신 + 재렌더. 저장 안 함."""
        if self.cb_zscale.currentText() == "공통":
            self._z_margin_pct_common = int(value)
        else:
            self._z_margin_pct_indiv = int(value)
        cells = self._result_panel.cells
        if not cells:
            return
        view_mode = self.cb_view.currentText() or "2D"
        displays = [c.display for c in cells]
        self._apply_z_scale_mode(displays, view_mode)
        self._result_panel.refresh_all()
