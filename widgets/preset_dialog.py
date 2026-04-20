"""
좌표 프리셋 불러오기 다이얼로그.

- 필터: 현재 VALUE PARAMETER의 DATA 개수(`n_points`)가 일치하는 프리셋만
- 병합 표시: 좌표 배열(tolerance 내)이 같은 프리셋들은 대표 1개 + "외 N" 표기
- 정렬: RECIPE 유사도 (완전 일치 → 토큰 공유 → 기타) → `last_used` 최근순
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
    """n_points 필터 + RECIPE 유사도 정렬 + 좌표 중복 병합 표시."""

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
        # **레시피 기준** 그룹핑 — 같은 recipe 의 모든 pair 를 1 행으로 표시
        from collections import defaultdict
        recipe_groups: dict[str, list[CoordPreset]] = defaultdict(list)
        for p in filtered:
            recipe_groups[p.recipe.lower()].append(p)
        groups = list(recipe_groups.values())
        # RECIPE 유사도 + 그룹 내 last_used 최신 기준 정렬 (내림차순)
        groups.sort(
            key=lambda g: (
                recipe_similarity(g[0].recipe, current_recipe),
                max(p.last_used for p in g),
            ),
            reverse=True,
        )
        self._groups: list[list[CoordPreset]] = groups

        lay = QVBoxLayout(self)

        info = QLabel(
            f"현재 입력: n_points = {current_n}  ·  "
            f"recipe = \"{current_recipe or '-'}\""
            f"   →   {len(groups)}개 레시피 후보"
        )
        info.setStyleSheet("color: #495057; padding: 4px 0;")
        lay.addWidget(info)

        self._table = QTableWidget(len(groups), 5)
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
        self._table.doubleClicked.connect(self.accept)

        from core.auto_select import _has_group_suffix
        def pick_primary(pairs: list[CoordPreset]) -> CoordPreset:
            """그룹 내 대표 — non-suffix 우선, 같으면 last_used 최신."""
            return max(
                pairs,
                key=lambda p: (0 if not _has_group_suffix(p.x_name) else -1, p.last_used),
            )

        for i, grp in enumerate(groups):
            rep = pick_primary(grp)
            extra = len(grp) - 1
            xy_text = f"{rep.x_name} / {rep.y_name}"
            if extra > 0:
                xy_text += f"   외 {extra}개"
            sim = recipe_similarity(rep.recipe, current_recipe)
            sim_text = self._format_similarity(sim, rep.recipe, current_recipe)
            latest_used = max(p.last_used for p in grp)

            for col, text in enumerate([
                rep.recipe,
                xy_text,
                sim_text,
                str(rep.n_points),
                format_dt_display(latest_used),
            ]):
                item = QTableWidgetItem(text)
                if col in (2, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(i, col, item)

        if groups:
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

    def selected_preset(self) -> CoordPreset | None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._groups):
            return None
        from core.auto_select import _has_group_suffix
        grp = self._groups[row]
        # primary = non-suffix 우선 + last_used 최신 — 이걸 override 로 반환
        # (main_window 의 _apply_preset_indicator 가 recipe 의 모든 pair 를 콤보에 표시)
        return max(
            grp,
            key=lambda p: (0 if not _has_group_suffix(p.x_name) else -1, p.last_used),
        )
