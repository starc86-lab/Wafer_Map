"""
메인 윈도우 — 3-패널 세로 스택 (Input / Control / Result).

뼈대 단계:
- Input: A/B PasteArea (가로 1:1 고정)
- Control: VALUE/X/Y 콤보, View(2D/3D) 콤보, Z 스케일, Visualize 버튼
- Result: placeholder (Visualize 연결은 후속)
- 우상단 ⚙ Settings 버튼 (현재는 알림만)
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QShowEvent
from PySide6.QtWidgets import (
    QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
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
from core.delta import compute_delta
from core.interp import is_collinear
from core.settings import load_settings
from main import ParseResult

from widgets.paste_area import PasteArea
from widgets.preset_dialog import PresetSelectDialog
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
        self._main_splitter_restored = False
        self._preset_override: CoordPreset | None = None

        self._build_toolbar()
        self._build_central()

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
        version_label = QLabel(f"v{VERSION} | © 2026 KP TF | Jihwan Park")
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

        # Z-Margin (%) — 공통 모드에서만 활성. matplotlib `ax.margins()` 관례:
        # 데이터 min/max 양쪽에 padding 을 %로 추가. 중심값 midpoint 고정,
        # range 를 (1 + pct/100) 배로 확장. 각 wafer 가 palette 전체를 덜 쓰게
        # 되어 여러 wafer 비교 시 색/높이 대비가 부드러워짐.
        _stored_pct = int(load_settings().get("chart_common", {}).get(
            "z_range_expand_pct", 50
        ))
        self._z_range_pct_stored = _stored_pct   # 개별 모드 복귀 시 복원용
        self.lbl_z_range = QLabel("Z-Margin:")
        self.sp_z_range = QSpinBox()
        self.sp_z_range.setRange(0, 200)
        self.sp_z_range.setSingleStep(10)
        self.sp_z_range.setSuffix("%")
        self.sp_z_range.setValue(_stored_pct if self.cb_zscale.currentText() == "공통" else 0)
        self.sp_z_range.setFixedWidth(72)
        # 비활성 시 내부 배경도 회색처리 (Fusion 기본은 흰색 유지)
        self.sp_z_range.setStyleSheet(
            "QSpinBox:disabled { background-color: #e8e8e8; color: #999; }"
        )
        # 라벨도 같이 disable — 텍스트 자동 회색 (Qt 팔레트 disabled 색)
        _is_common = self.cb_zscale.currentText() == "공통"
        self.sp_z_range.setEnabled(_is_common)
        self.lbl_z_range.setEnabled(_is_common)
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

        # 공통 PARAMETER 집합
        param_sets: list[set[str]] = []
        for r in results:
            per_result = [set(w.parameters) for w in r.wafers.values()]
            if per_result:
                param_sets.append(set.intersection(*per_result))
        common = set.intersection(*param_sets) if param_sets else set()

        first_result = results[0]
        first_wafer = next(iter(first_result.wafers.values())) if first_result.wafers else None
        if first_wafer is None:
            return {}, {}, 0
        available_ns = {
            name: first_wafer.parameters[name].n
            for name in common if name in first_wafer.parameters
        }
        params = {
            name: first_wafer.parameters[name]
            for name in common if name in first_wafer.parameters
        }
        return available_ns, params, len(first_result.data_columns)

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
        library = CoordLibrary()
        displays: list[WaferDisplay] = []
        # 좌표 선택 유효성: VALUE/X/Y 이름이 서로 달라야 좌표로 취급
        coord_valid = bool(v and x and y and v != x and v != y and x != y)
        view_mode = self.cb_view.currentText() or "2D"

        override = self._preset_override

        for w in result.wafers.values():
            if v not in w.parameters:
                continue
            val = np.asarray(w.parameters[v].values, dtype=float)

            # 우선순위: (1) 사용자가 선택한 프리셋 override
            #          (2) 사용자 콤보 X/Y 선택 (coord_valid 한 경우)
            #          (3) RECIPE 기반 라이브러리 자동 조회
            x_mm: np.ndarray | None = None
            y_mm: np.ndarray | None = None
            from_lib = False
            from_preset = False

            if override is not None:
                # preset 활성 — 현재 cb_coord 에 해당하는 pair 를 라이브러리에서 조회
                # (사용자가 콤보에서 다른 pair 로 바꿨을 수 있음)
                matched = library.find_match_by_names(override.recipe, x, y)
                if matched is not None:
                    x_mm = np.asarray(matched.x_mm, dtype=float)
                    y_mm = np.asarray(matched.y_mm, dtype=float)
                    library.touch(matched, save=False)
                    from_preset = True
                # else: preset 모드지만 현재 pair 매칭 없음 → 아래 경로로 폴백
            if x_mm is None and coord_valid and x in w.parameters and y in w.parameters:
                xr, _ = normalize_to_mm(w.parameters[x].values)
                yr, _ = normalize_to_mm(w.parameters[y].values)
                if len(xr) > 0 and len(yr) > 0:
                    x_mm, y_mm = xr, yr

            if x_mm is None and w.recipe:
                hits = library.find_by_recipe(w.recipe, n_points=int(len(val)))
                if hits:
                    preset = hits[0]  # last_used 최신
                    library.touch(preset, save=False)
                    x_mm = np.asarray(preset.x_mm, dtype=float)
                    y_mm = np.asarray(preset.y_mm, dtype=float)
                    from_lib = True

            if x_mm is None:
                continue  # 좌표 해결 실패 → 스킵

            n = min(len(x_mm), len(y_mm), len(val))
            if n == 0:
                continue
            x_mm, y_mm, val_n = x_mm[:n], y_mm[:n], val[:n]

            # 사용자 콤보 좌표일 때만 저장 (override/library 경로는 이미 touch 됨).
            # 실제 런에 사용된 (x, y) pair 하나만 저장 — n 유효 조합일 때만.
            if not (from_preset or from_lib):
                self._save_used_pair_to_library(library, w, v, x, y)

            title = f"{w.lot_id}.{_pad_slot(w.slot_id)} – {v}"
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
        self._result_panel.set_displays(displays, v, view_mode=view_mode, summary_line="")

    def _visualize_delta(
        self, a: ParseResult, b: ParseResult, v: str, x: str, y: str,
    ) -> None:
        # DELTA 모드 자동 저장 — A/B 각 웨이퍼에 실제 사용된 (x, y) pair 하나씩 저장
        coord_valid = bool(v and x and y and v != x and v != y and x != y)
        if coord_valid:
            library = CoordLibrary()
            for result in (a, b):
                for w in result.wafers.values():
                    self._save_used_pair_to_library(library, w, v, x, y)
            self._enforce_library_limits(library)

        dr = compute_delta(a, b, v, x, y, tolerance_mm=1e-3)
        if dr.matched == 0:
            QMessageBox.warning(
                self,
                "DELTA",
                f"WAFERID 교집합 또는 좌표 일치점이 없어 DELTA를 계산할 수 없습니다.\n"
                f"A {dr.count_a}장 · B {dr.count_b}장",
            )
            self._result_panel.clear()
            return

        displays = []
        for d in dr.deltas:
            title = f"{d.lot_a}.{_pad_slot(d.slot_a)} – Δ {v}"
            displays.append(WaferDisplay(
                title=title,
                meta_label=f"{d.lot_a} / {_pad_slot(d.slot_a)}  ←  {d.lot_b} / {_pad_slot(d.slot_b)}",
                x_mm=d.x_mm, y_mm=d.y_mm, values=d.delta_v,
                is_radial=bool(is_collinear(d.x_mm, d.y_mm)),
            ))
        # A/B 의 대표 RECIPE 비교 — 다르면 summary 에 안내 (차단 말고 알림만).
        # 의도적으로 다른 레시피 DELTA 도 사용자 케이스 있음.
        recipe_a = self._dominant_recipe(a)
        recipe_b = self._dominant_recipe(b)
        recipe_note = ""
        if recipe_a and recipe_b and recipe_a.strip().lower() != recipe_b.strip().lower():
            recipe_note = f"  ·  ⚠ RECIPE 불일치: A={recipe_a} / B={recipe_b}"
        summary = (
            f"매칭 {dr.matched} / A {dr.count_a} vs B {dr.count_b}  "
            f"·  DELTA (A − B){recipe_note}"
        )
        view_mode = self.cb_view.currentText() or "2D"
        self._apply_z_scale_mode(displays, view_mode)
        self._result_panel.set_displays(displays, v, view_mode=view_mode, summary_line=summary)

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

        개별: 둘 다 None reset (cell이 자체 데이터로 계산).
        """
        if self.cb_zscale.currentText() != "공통":
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

        # 각 wafer 의 **개별 렌더 범위** (min/max) 수집 → 그 중 최소 min / 최대 max
        # 로 공통 범위 결정. 개별 모드가 각 wafer 에 쓰는 범위와 동일 기준 사용.
        # 동시에 실측 v 의 min/max 도 수집 → 1D radial graph Y 공통 범위.
        all_mins: list[float] = []
        all_maxes: list[float] = []
        all_v_mins: list[float] = []
        all_v_maxes: list[float] = []
        for d in displays:
            x_arr = np.asarray(d.x_mm, dtype=float)
            y_arr = np.asarray(d.y_mm, dtype=float)
            v_arr = np.asarray(d.values, dtype=float)
            m = ~np.isnan(v_arr) & ~np.isnan(x_arr) & ~np.isnan(y_arr)
            if m.sum() < 2:
                continue
            # 실측 v 범위 (1D graph Y 공통용)
            valid = v_arr[m]
            if valid.size > 0:
                all_v_mins.append(float(valid.min()))
                all_v_maxes.append(float(valid.max()))
            # 렌더 범위 (2D/3D 공통용)
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
                )
                z = rbf(sample_pts)
                zf = z[np.isfinite(z)]
                if zf.size > 0:
                    all_mins.append(float(zf.min()))
                    all_maxes.append(float(zf.max()))
                    continue
            except Exception:
                pass
            # RBF 실패 시 input 값 폴백
            if valid.size > 0:
                all_mins.append(float(valid.min()))
                all_maxes.append(float(valid.max()))

        # Z-Margin — matplotlib margins() 관례. midpoint 고정 + range*(1+pct/100).
        # pct=0 → 원본 min~max, pct=50 → range*1.5, pct=100 → range*2.0.
        # 2D/3D 공통 z_range 와 1D graph z_range_1d 에 독립 적용.
        pct = int(self.sp_z_range.value()) if self.sp_z_range.isEnabled() else 0

        def _margin(vmin: float, vmax: float) -> tuple[float, float]:
            if vmax <= vmin:
                vmax = vmin + 1e-9
            if pct > 0:
                midpoint = (vmin + vmax) / 2.0
                half = (vmax - vmin) / 2.0 * (1.0 + pct / 100.0)
                return midpoint - half, midpoint + half
            return vmin, vmax

        rendered_range = _margin(min(all_mins), max(all_maxes)) if all_mins else None
        measured_range = _margin(min(all_v_mins), max(all_v_maxes)) if all_v_mins else None

        for d in displays:
            d.z_range = rendered_range
            d.z_range_1d = measured_range

    def _open_settings(self) -> None:
        from widgets.settings_dialog import SettingsDialog
        # 논모달 + parent=None — Windows의 transient owner 관계 끊어 메인 뒤로 갈 수 있게.
        # 파이썬 참조는 self._settings_dialog에 보관해 GC 방지.
        dlg = getattr(self, "_settings_dialog", None)
        if dlg is None or not dlg.isVisible():
            dlg = SettingsDialog(parent=None)
            dlg.setMainWindow(self)
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

    def _on_zscale_toggle(self, _mode: str) -> None:
        """Z scale 콤보 변경 — z_range 갱신 후 2D/3D 양쪽 재렌더.

        z_range는 2D ImageItem levels(+colorbar)와 3D surface colors 모두에
        영향. 양쪽 렌더 캐시 reset 필요 (보간 캐시는 유지되므로 빠름).
        """
        # Z-Margin 스핀박스 활성/비활성 + 값 토글 (개별 모드 → 0 회색, 공통 복귀 → 저장값)
        is_common = self.cb_zscale.currentText() == "공통"
        self.sp_z_range.blockSignals(True)
        self.sp_z_range.setEnabled(is_common)
        self.lbl_z_range.setEnabled(is_common)
        self.sp_z_range.setValue(self._z_range_pct_stored if is_common else 0)
        self.sp_z_range.blockSignals(False)

        cells = self._result_panel.cells
        if not cells:
            return
        view_mode = self.cb_view.currentText() or "2D"
        displays = [c.display for c in cells]
        self._apply_z_scale_mode(displays, view_mode)
        self._result_panel.refresh_all()

    def _on_z_range_changed(self, value: int) -> None:
        """Z-Margin 스핀박스 변경 — 저장값 갱신 + 재렌더. 공통 모드에서만 호출됨."""
        if self.cb_zscale.currentText() != "공통":
            return
        self._z_range_pct_stored = int(value)
        # settings.json 즉시 반영 (Settings 다이얼로그 경유 없이 직접 저장)
        from core.settings import load_settings as _ls, save_settings as _ss
        s = _ls()
        s.setdefault("chart_common", {})["z_range_expand_pct"] = int(value)
        _ss(s)
        cells = self._result_panel.cells
        if not cells:
            return
        view_mode = self.cb_view.currentText() or "2D"
        displays = [c.display for c in cells]
        self._apply_z_scale_mode(displays, view_mode)
        self._result_panel.refresh_all()
