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
    QMessageBox, QPushButton, QSizePolicy, QSplitter, QToolBar, QToolButton,
    QVBoxLayout, QWidget,
)

import numpy as np

from core import runtime
from core.auto_select import select_value, select_y_with_suffix
from core.coord_library import CoordLibrary, CoordPreset
from core.coords import normalize_to_mm
from core.delta import compute_delta
from core.settings import load_settings
from main import ParseResult

from widgets.paste_area import PasteArea
from widgets.preset_dialog import PresetSelectDialog
from widgets.result_panel import ResultPanel
from widgets.wafer_cell import WaferDisplay


PRESET_BUTTON_DEFAULT_TEXT = "좌표 불러오기"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Wafer Map")

        # 저장된 윈도우 크기가 있으면 우선, 없으면 해상도 티어 기반
        s = load_settings()
        saved_main = (s.get("window", {}) or {}).get("main")
        if isinstance(saved_main, (list, tuple)) and len(saved_main) == 2:
            self.resize(int(saved_main[0]), int(saved_main[1]))
        else:
            w, h = runtime.default_window_size("main")
            self.resize(w, h)

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
        s = load_settings()
        if s.get("window_save_enabled", True):
            s.setdefault("window", {})
            s["window"]["main"] = [self.width(), self.height()]
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

        self.cb_value = QComboBox(); self.cb_value.setFixedWidth(84)
        self.cb_x = QComboBox();     self.cb_x.setFixedWidth(84)
        self.cb_y = QComboBox();     self.cb_y.setFixedWidth(84)

        self.btn_load_preset = QPushButton(PRESET_BUTTON_DEFAULT_TEXT)
        self.btn_load_preset.setEnabled(False)
        self.btn_load_preset.clicked.connect(self._open_preset_dialog)

        self.cb_view = QComboBox(); self.cb_view.addItems(["2D", "3D"])
        self.cb_zscale = QComboBox(); self.cb_zscale.addItems(["공통", "개별"])
        self.cb_zscale.setCurrentText("개별")  # 세션 디폴트 (저장 X)

        self.btn_visualize = QPushButton("▶  Run Analysis")
        self.btn_visualize.setProperty("class", "primary")
        # Input B 헤더 Text+Table+Clear 폭 합과 동일 (시작/끝 X가 일치하도록)
        from widgets.paste_area import HEADER_BUTTON_WIDTH, HEADER_BUTTON_SPACING
        self.btn_visualize.setFixedWidth(
            HEADER_BUTTON_WIDTH * 3 + HEADER_BUTTON_SPACING * 2
        )
        self.btn_visualize.setEnabled(False)
        self.btn_visualize.clicked.connect(self._on_visualize)

        # X 콤보 변경 시 Y suffix 동기화
        self.cb_x.currentTextChanged.connect(self._on_x_changed)
        # View(2D/3D) 변경 — cell 재생성 없이 stack 인덱스만 토글 (캐시 활용)
        self.cb_view.currentTextChanged.connect(self._on_view_toggle)
        # Z scale 변경 — z_range만 갈아끼우고 3D 캐시 무효화 (2D 캐시 유지)
        self.cb_zscale.currentTextChanged.connect(self._on_zscale_toggle)

        for label, widget in [
            ("VALUE:", self.cb_value),
            ("X:", self.cb_x),
            ("Y:", self.cb_y),
        ]:
            lay.addWidget(QLabel(label))
            lay.addWidget(widget)
        lay.addWidget(self.btn_load_preset)
        lay.addSpacing(16)
        lay.addWidget(QLabel("View:"))
        lay.addWidget(self.cb_view)
        lay.addWidget(QLabel("Z-Scale:"))
        lay.addWidget(self.cb_zscale)
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
        """입력 결과를 바탕으로 콤보 리스트·기본값 갱신."""
        available_ns, data_cols_n = self._build_selection_context()

        auto = load_settings().get("auto_select", {})
        vpat = auto.get("value_patterns", ["T*"])
        xpat = auto.get("x_patterns", ["X", "X*"])
        ypat = auto.get("y_patterns", ["Y", "Y*"])

        value_sel, value_ordered = select_value(available_ns, vpat, data_cols_n)
        x_sel, x_ordered = select_value(available_ns, xpat, data_cols_n)
        y_sel, y_ordered = select_y_with_suffix(x_sel, available_ns, ypat, data_cols_n)

        self._fill_combo(self.cb_value, value_ordered, value_sel)
        self._fill_combo(self.cb_x, x_ordered, x_sel)
        self._fill_combo(self.cb_y, y_ordered, y_sel)

        any_input = bool(self._result_a or self._result_b)
        self.btn_visualize.setEnabled(any_input and bool(available_ns))
        self.btn_load_preset.setEnabled(any_input)

    def _build_selection_context(self) -> tuple[dict[str, int], int]:
        """현재 양측 결과로부터 (available_ns, data_cols_n) 계산.

        available_ns: 모든 웨이퍼에 공통 존재하는 PARAMETER → 대표 n (첫 웨이퍼 기준).
        data_cols_n: DATA 컬럼 총 개수. 양쪽 모두 있으면 A 기준(동일해야 정상).
        """
        a, b = self._result_a, self._result_b
        results = [r for r in (a, b) if r is not None]
        if not results:
            return {}, 0

        # 공통 PARAMETER 집합
        param_sets: list[set[str]] = []
        for r in results:
            per_result = [set(w.parameters) for w in r.wafers.values()]
            if per_result:
                param_sets.append(set.intersection(*per_result))
        common = set.intersection(*param_sets) if param_sets else set()

        # 대표 n (첫 웨이퍼 기준)
        first_result = results[0]
        first_wafer = next(iter(first_result.wafers.values())) if first_result.wafers else None
        if first_wafer is None:
            return {}, 0
        available_ns = {
            name: first_wafer.parameters[name].n
            for name in common if name in first_wafer.parameters
        }
        return available_ns, len(first_result.data_columns)

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

    def _on_x_changed(self, new_x: str) -> None:
        """X 변경 시 Y를 X의 suffix에 맞춰 자동 재선택. 사용자 수동 변경 시 프리셋 override 해제."""
        if not new_x:
            return
        self._reset_preset_override()
        available_ns, data_cols_n = self._build_selection_context()
        if not available_ns:
            return
        ypat = load_settings().get("auto_select", {}).get("y_patterns", ["Y", "Y*"])
        y_sel, y_ordered = select_y_with_suffix(new_x, available_ns, ypat, data_cols_n)
        self._fill_combo(self.cb_y, y_ordered, y_sel)

    # ── 프리셋 override ───────────────────────────────
    def _open_preset_dialog(self) -> None:
        result = self._result_a or self._result_b
        if result is None or not result.wafers:
            return
        v = self.cb_value.currentText()
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
        self.btn_load_preset.setText(f"프리셋: {preset.name}")

    def _reset_preset_override(self) -> None:
        if self._preset_override is None:
            return
        self._preset_override = None
        self.btn_load_preset.setText(PRESET_BUTTON_DEFAULT_TEXT)

    def _on_visualize(self) -> None:
        v = self.cb_value.currentText()
        x = self.cb_x.currentText()
        y = self.cb_y.currentText()
        if not (v and x and y):
            return

        a, b = self._result_a, self._result_b
        if a and b:
            self._visualize_delta(a, b, v, x, y)
        elif a or b:
            self._visualize_single(a or b, v, x, y)
        else:
            self._result_panel.clear()

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
                x_mm = np.asarray(override.x_mm, dtype=float)
                y_mm = np.asarray(override.y_mm, dtype=float)
                from_preset = True
            elif coord_valid and x in w.parameters and y in w.parameters:
                xr, _ = normalize_to_mm(w.parameters[x].values)
                yr, _ = normalize_to_mm(w.parameters[y].values)
                if len(xr) > 0 and len(yr) > 0:
                    x_mm, y_mm = xr, yr

            if x_mm is None and w.recipe:
                hits = library.find_by_recipe(w.recipe)
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

            # 사용자 콤보 좌표일 때만 새 레코드 저장 (override / library 경로는 이미 touch 됨)
            if not (from_preset or from_lib):
                try:
                    library.add_or_touch(w.recipe, x_mm, y_mm, save=False)
                except ValueError:
                    pass

            title = f"{w.wafer_id}  —  {v}"
            if from_preset or from_lib:
                title += "  📁"
            displays.append(WaferDisplay(
                title=title,
                meta_label=f"{w.lot_id} / {w.slot_id}",
                x_mm=x_mm, y_mm=y_mm, values=val_n,
            ))

        library.save()
        self._apply_z_scale_mode(displays, view_mode)
        self._result_panel.set_displays(displays, v, view_mode=view_mode, summary_line="")

    def _visualize_delta(
        self, a: ParseResult, b: ParseResult, v: str, x: str, y: str,
    ) -> None:
        # DELTA 모드의 자동 저장 — A/B 각 웨이퍼의 (recipe, 좌표) 조합을 라이브러리에 반영
        coord_valid = bool(v and x and y and v != x and v != y and x != y)
        if coord_valid:
            library = CoordLibrary()
            for result in (a, b):
                for w in result.wafers.values():
                    if not all(n in w.parameters for n in (v, x, y)):
                        continue
                    x_mm, _ = normalize_to_mm(w.parameters[x].values)
                    y_mm, _ = normalize_to_mm(w.parameters[y].values)
                    nn = min(len(x_mm), len(y_mm))
                    if nn == 0:
                        continue
                    try:
                        library.add_or_touch(
                            w.recipe, x_mm[:nn], y_mm[:nn], save=False,
                        )
                    except ValueError:
                        pass
            library.save()

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

        displays = [
            WaferDisplay(
                title=f"{d.wafer_id}  —  Δ {v}",
                meta_label=f"{d.lot_a} / {d.slot_a}  ←  {d.lot_b} / {d.slot_b}",
                x_mm=d.x_mm, y_mm=d.y_mm, values=d.delta_v,
            )
            for d in dr.deltas
        ]
        summary = (
            f"매칭 {dr.matched} / A {dr.count_a} vs B {dr.count_b}  "
            f"·  DELTA (A − B)"
        )
        view_mode = self.cb_view.currentText() or "2D"
        self._apply_z_scale_mode(displays, view_mode)
        self._result_panel.set_displays(displays, v, view_mode=view_mode, summary_line=summary)

    def _apply_z_scale_mode(self, displays: list[WaferDisplay], view_mode: str) -> None:
        """cb_zscale을 ground truth로 모든 display의 z_range 세팅.

        공통: 모든 display에 동일 (vmin, vmax) 주입.
        개별: 모두 None reset (cell이 자체 데이터로 vmin/vmax 계산).
        view_mode 무관 — 2D 상태에서 토글해도 다음 3D 진입 시 정합 보장.
        """
        if self.cb_zscale.currentText() != "공통":
            for d in displays:
                d.z_range = None
            return
        all_v: list[float] = []
        for d in displays:
            arr = np.asarray(d.values, dtype=float)
            valid = arr[~np.isnan(arr)]
            if valid.size > 0:
                all_v.extend(valid.tolist())
        if not all_v:
            return
        vmin = float(min(all_v))
        vmax = float(max(all_v))
        for d in displays:
            d.z_range = (vmin, vmax)

    def _open_settings(self) -> None:
        from widgets.settings_dialog import SettingsDialog
        # 논모달 — 한 인스턴스만 유지, 이미 열려있으면 앞으로 가져오기
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

        보간 캐시는 cell 내부에서 (interp_method, grid_resolution) 비교로 재사용 판단.
        컬러맵·shading 등 대부분의 변경에서 RBF 50~100ms 비용 생략.
        """
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
        cells = self._result_panel.cells
        if not cells:
            return
        view_mode = self.cb_view.currentText() or "2D"
        displays = [c.display for c in cells]
        self._apply_z_scale_mode(displays, view_mode)
        self._result_panel.refresh_all()
