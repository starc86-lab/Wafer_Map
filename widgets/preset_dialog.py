"""
좌표 프리셋 불러오기 다이얼로그.

- 필터: 현재 VALUE PARAMETER의 DATA 개수(`n_points`)가 일치하는 프리셋만
- 개별 레코드 행 표시 (레시피 그룹 병합 없음)
- 정렬: RECIPE 유사도 → `last_used` 최근순
- 더블클릭 / Apply → accept
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
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
        self.setWindowTitle("저장된 좌표 불러오기")
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
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setStretchLastSection(True)
        # 행 더블클릭 → 좌표 프리뷰 다이얼로그 (맵 + 좌표 표).
        # 프리셋 적용(accept) 은 OK 버튼으로만 — 더블클릭은 "내용 보기" 용.
        self._table.doubleClicked.connect(self._on_row_dbl_click)

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

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("적용")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    @staticmethod
    def _format_similarity(sim: int, preset_recipe: str, current: str) -> str:
        if not current or not preset_recipe:
            return "—"
        if sim >= 10_000:
            return "완전 일치"
        if sim > 0:
            return f"토큰 {sim}개"
        return "—"

    def _on_row_dbl_click(self, index) -> None:
        """행 더블클릭 → 좌표 프리뷰. 프리셋 적용은 OK 버튼으로만."""
        row = index.row() if index is not None else -1
        if row < 0 or row >= len(self._presets):
            return
        p = self._presets[row]
        from widgets.coord_preview_dialog import CoordPreviewDialog
        dlg = CoordPreviewDialog(
            p.x_mm, p.y_mm,
            title=f"{p.recipe} · {p.x_name}/{p.y_name} · {p.n_points}pt",
            parent=self,
        )
        dlg.exec()

    def selected_preset(self) -> CoordPreset | None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._presets):
            return None
        return self._presets[row]
