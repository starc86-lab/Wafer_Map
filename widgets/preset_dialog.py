"""
좌표 추가 다이얼로그 — 라이브러리에서 좌표 페어 1개+ 선택 후 가족 좌표 list 에
추가 (사용자 정책 2026-04-30, preset_override 강제 1순위 폐지).

- 필터: 현재 VALUE PARAMETER의 DATA 개수(`n_points`)가 일치하는 프리셋만
- 개별 레코드 행 표시 (레시피 그룹 병합 없음)
- 정렬: RECIPE 유사도 → `last_used` 최근순
- ExtendedSelection — 여러 행 동시 선택 후 Add
- 더블클릭 / Add → accept (선택된 행들 모두 반환)
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
    QLabel, QMenu, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from core.coord_library import CoordLibrary, CoordPreset, format_dt_display, recipe_similarity


class PresetSelectDialog(QDialog):
    """n_points 필터 + RECIPE 유사도 정렬. 레코드 개별 행 표시."""

    def __init__(
        self,
        library: CoordLibrary,
        current_recipe: str,
        current_n: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("좌표 추가")
        self.resize(720, 500)

        # n_points 필터
        filtered = library.filter_by_n(current_n)
        # RECIPE 유사도 → last_used 최신 순
        filtered.sort(
            key=lambda p: (recipe_similarity(p.recipe, current_recipe), p.last_used),
            reverse=True,
        )
        self._presets: list[CoordPreset] = filtered

        lay = QVBoxLayout(self)

        info = QLabel(
            f"현재 입력: n_points = {current_n}  ·  "
            f"recipe = \"{current_recipe or '-'}\""
            f"   →   {len(filtered)}개 레코드 후보"
        )
        info.setStyleSheet("color: #495057; padding: 4px 0;")
        lay.addWidget(info)

        self._table = QTableWidget(len(filtered), 5)
        self._table.setHorizontalHeaderLabels(
            ["RECIPE", "X / Y", "유사도", "Point", "마지막 사용"],
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # ExtendedSelection — Ctrl/Shift 로 다중 행 선택 후 Add (사용자 정책 2026-04-30)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setStretchLastSection(True)
        # 행 더블클릭 → 적용 (accept). 미리보기는 우클릭 메뉴 또는 좌측 하단
        # '좌표 미리보기' 버튼 (사용자 정책 2026-04-30).
        self._table.doubleClicked.connect(self.accept)
        # 우클릭 → 컨텍스트 메뉴 (좌표 미리보기)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)

        for i, p in enumerate(filtered):
            sim = recipe_similarity(p.recipe, current_recipe)
            sim_text = self._format_similarity(sim, p.recipe, current_recipe)
            for col, text in enumerate([
                p.recipe,
                f"{p.x_name} / {p.y_name}",
                sim_text,
                str(p.n_points),
                format_dt_display(p.last_used),
            ]):
                item = QTableWidgetItem(text)
                if col in (2, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(i, col, item)

        if filtered:
            self._table.selectRow(0)

        lay.addWidget(self._table, stretch=1)

        # 좌측: 좌표 미리보기 버튼 / 우측: Apply / Cancel
        btn_row = QHBoxLayout()
        self.btn_preview = QPushButton("좌표 미리보기")
        self.btn_preview.clicked.connect(self._on_preview_clicked)
        btn_row.addWidget(self.btn_preview)
        btn_row.addStretch(1)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("추가")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btn_row.addWidget(btns)
        lay.addLayout(btn_row)

    @staticmethod
    def _format_similarity(sim: int, preset_recipe: str, current: str) -> str:
        if not current or not preset_recipe:
            return "—"
        if sim >= 10_000:
            return "완전 일치"
        if sim > 0:
            return f"토큰 {sim}개"
        return "—"

    def _on_table_context_menu(self, pos) -> None:
        """우클릭 → 컨텍스트 메뉴 (좌표 미리보기)."""
        idx = self._table.indexAt(pos)
        if idx.row() < 0:
            return
        # 우클릭 시 해당 행 자동 선택
        self._table.selectRow(idx.row())
        menu = QMenu(self._table)
        act_preview = QAction("좌표 미리보기", menu)
        act_preview.triggered.connect(self._on_preview_clicked)
        menu.addAction(act_preview)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _on_preview_clicked(self) -> None:
        """선택된 첫 프리셋의 좌표를 별도 다이얼로그에 표시 (다중 선택이어도 1개 미리보기)."""
        presets = self.selected_presets()
        if not presets:
            return
        p = presets[0]
        from widgets.coord_preview_dialog import CoordPreviewDialog
        dlg = CoordPreviewDialog(
            p.x_mm, p.y_mm,
            title=f"{p.recipe} · {p.x_name}/{p.y_name} · {p.n_points}pt",
            parent=self,
        )
        dlg.exec()

    def selected_presets(self) -> list[CoordPreset]:
        """선택된 모든 행의 preset (행 순서대로). 빈 리스트 = 선택 없음."""
        rows = sorted({i.row() for i in self._table.selectedIndexes()})
        return [self._presets[r] for r in rows
                if 0 <= r < len(self._presets)]

    def selected_preset(self) -> CoordPreset | None:
        """첫 선택 preset (호환성 유지 — F3 에서 호출자가 selected_presets 로 전환)."""
        ps = self.selected_presets()
        return ps[0] if ps else None
