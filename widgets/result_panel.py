"""
결과 패널 — 가로 스크롤 Cell 나열. 사유/경고 메시지는 ReasonBar 가 별도 표시.

외부 API:
    panel.set_displays(displays, value_name, view_mode="2D")
    panel.clear()
"""
from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from widgets.wafer_cell import WaferCell, WaferDisplay


class ResultPanel(QWidget):
    """가로 스크롤 Cells. 사유/경고 메시지는 ReasonBar 가 처리."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self._container = QWidget()
        self._layout = QHBoxLayout(self._container)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(8)
        self._scroll.setWidget(self._container)
        root.addWidget(self._scroll, stretch=1)

        # 첫 Run Analysis 시 GLViewWidget이 추가되며 ancestor가 native window로
        # 일괄 승격되는 시점의 윈도우 깜빡임 제거 — startup에 미리 영구 자식 1개 두기
        import pyqtgraph.opengl as gl
        self._gl_anchor = gl.GLViewWidget(self._container)
        self._gl_anchor.resize(1, 1)
        self._gl_anchor.hide()

        self._cells: list[WaferCell] = []
        self._show_placeholder()

    def _show_placeholder(self) -> None:
        self._clear_layout()
        ph = QLabel(
            "그래프를 우클릭하여 그래프 이미지나 데이터를 Clipboard로 Copy할 수 있습니다.\n"
            "\n"
            "3D 그래프 Tips\n"
            "- Ctrl + 드래그 : 그래프 이동\n"
            "- Shift + 드래그 : 전체 그래프 앵글 변경\n"
            "- Shift + Ctrl + 드래그 : 전체 그래프 위치 변경"
        )
        ph.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        ph.setStyleSheet("color: gray; padding: 40px;")
        self._layout.addWidget(ph)

    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._cells.clear()

    def clear(self) -> None:
        self._show_placeholder()

    def set_displays(
        self,
        displays: Iterable[WaferDisplay],
        value_name: str,
        view_mode: str = "2D",
    ) -> None:
        displays = list(displays)
        self._clear_layout()
        if not displays:
            self._show_placeholder()
            return

        # container 전체를 hide한 채 cells 생성·렌더·layout 완료 → 최종 show.
        # hide 동안은 paint/layout activate가 deferred라 "중첩→펼쳐짐" 현상 제거.
        self._container.hide()
        try:
            new_cells = []
            for i, d in enumerate(displays):
                cell = WaferCell(
                    d, value_name, view_mode=view_mode, defer_render=True,
                    is_master=(i == 0),
                )
                new_cells.append(cell)
                self._cells.append(cell)

            # 병렬 보간 prefetch
            if len(new_cells) > 1:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=len(new_cells)) as ex:
                    list(ex.map(lambda c: c.prefetch_interp(), new_cells))

            # 초기 렌더 (container hidden이라 paint 없음)
            for c in new_cells:
                c.render_initial()

            # layout에 add — AlignTop 없으면 scroll viewport > content 높이일 때
            # QHBoxLayout 기본(세로 중앙)이라, 윈도우 리사이즈 시 셀들이 중앙으로 내려감
            for c in new_cells:
                self._layout.addWidget(c, 0, Qt.AlignmentFlag.AlignTop)
            self._layout.addStretch(1)

            # hidden 상태에서 layout을 강제 activate → 자식 geometry 확정
            # 이걸 빼면 show() 직후 (0,0)에 쌓였다가 HBoxLayout이 펼쳐지는 1프레임이 보임
            self._layout.activate()
            self._container.adjustSize()
        finally:
            self._container.show()

        # 비활성 view(주로 3D) 백그라운드 prefetch
        QTimer.singleShot(50, self._prefetch_inactive_views)

    def _prefetch_inactive_views(self) -> None:
        for c in self._cells:
            c.prefetch_inactive_view()

    def set_view_mode(self, mode: str) -> None:
        """View 토글 — 모든 cell에 forward (cell이 캐시 보유, 재계산 없음)."""
        for c in self._cells:
            c.set_view_mode(mode)

    @property
    def cells(self) -> list[WaferCell]:
        return self._cells

    def invalidate_3d(self) -> None:
        """3D 캐시 무효화 — z_range 변경 시. 2D 캐시는 그대로."""
        for c in self._cells:
            c.invalidate_3d()

    def set_table_style(self, style: str) -> None:
        """Settings table.style 변경 — 모든 cell 의 _summary 위젯 교체.
        RBF / GL 캐시 유지 (사용자 정책 2026-04-30).
        """
        for c in self._cells:
            c.swap_summary_style(style)

    def apply_fonts_all(self) -> None:
        """font_scale 변경 시 — swap 없이 _summary.apply_fonts + cell layout reflow.
        set_table_style 의 위젯 재 init 비용 회피 (사용자 정책 2026-05-01,
        scope 2 fix #2).
        """
        from core import settings as settings_io
        common = settings_io.load_settings().get("chart_common", {})
        for c in self._cells:
            c._summary.apply_fonts()
            c._apply_chart_size(common)

    def refresh_all(self) -> None:
        """Settings 변경 시 — 모든 cell 렌더 캐시 reset + 보간 병렬 prefetch.

        보간 캐시는 각 cell이 (method, grid) 비교로 알아서 재사용/재계산 결정.
        grid 큰 값 + RBF일 때 cell별 보간이 cell당 80~130ms까지 나가서, GIL 해제되는
        scipy RBF를 ThreadPoolExecutor로 동시에 돌림. 렌더는 메인 스레드에서 순차.
        """
        if len(self._cells) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=len(self._cells)) as ex:
                list(ex.map(lambda c: c.prefetch_interp(), self._cells))
        for c in self._cells:
            c.refresh()
