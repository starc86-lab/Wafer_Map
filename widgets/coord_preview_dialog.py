"""좌표 프리셋 프리뷰 다이얼로그 — 웨이퍼 맵(좌) + 좌표 표(우).

좌표 라이브러리(Settings 탭) / 불러오기 다이얼로그(PresetDialog) 양쪽에서
행 더블클릭 시 띄움. read-only view — 편집/저장은 추후 과제.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)


_BOUNDARY_R = 153.0          # 경계 원 반지름 (mm) — WaferCell 과 동일 (notch 포함 여유)
_NOTCH_DEPTH = 3.0           # notch V자 깊이 (mm)
_NOTCH_ANGLE = 3 * np.pi / 2  # 6시 방향
_NOTCH_HALF_RAD = 3 * np.pi / 180   # ±3°
_BOUNDARY_SEGMENTS = 361


def _boundary_xy(R: float = _BOUNDARY_R, depth: float = _NOTCH_DEPTH) -> tuple[np.ndarray, np.ndarray]:
    """경계 원 + 6시 notch V자 좌표. wafer_cell 의 동일 함수를 단순화."""
    theta = np.linspace(0, 2 * np.pi, _BOUNDARY_SEGMENTS)
    r = np.full_like(theta, R)
    d = np.abs(((theta - _NOTCH_ANGLE + np.pi) % (2 * np.pi)) - np.pi)
    in_notch = d < _NOTCH_HALF_RAD
    r[in_notch] = R - depth * (1 - d[in_notch] / _NOTCH_HALF_RAD)
    return r * np.cos(theta), r * np.sin(theta)


class CoordPreviewDialog(QDialog):
    """좌표 프리셋 프리뷰 — 좌(웨이퍼 맵) + 우(좌표 표).

    x_mm, y_mm 는 mm 단위 1D numpy array (또는 list). 둘 다 동일 길이.
    title 은 다이얼로그 title bar 에 표기 (preset name · recipe 등).
    """

    def __init__(
        self,
        x_mm, y_mm,
        title: str = "좌표 프리뷰",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        x = np.asarray(x_mm, dtype=float)
        y = np.asarray(y_mm, dtype=float)
        n = min(x.size, y.size)
        x = x[:n]
        y = y[:n]

        # 3-row QGridLayout 로 좌/우 영역 행 정렬 — plot(좌) 과 table(우) 이 같은
        # row 1 에 있어 세로 높이 자동 동일. row 0 = info 라벨, row 2 = Close 버튼.
        # 테마 색상 — 다이얼로그 생성 시 1회 snapshot. 재오픈 시 갱신 반영.
        from core import settings as settings_io
        from core.themes import THEMES
        _s = settings_io.load_settings()
        _t = THEMES.get(_s.get("theme", "Light"), THEMES["Light"])
        _border = _t.get("border", "#888")
        _header_bg = _t.get("header_bg", "#f0f0f0")
        _text_sub = _t.get("text_sub", "#555")
        # 테마 밝기 판정 — 다크 테마에서만 맵 배경 연회색 (밝은 테마는 흰색 유지).
        _bg = _t.get("bg", "#ffffff").lstrip("#")
        try:
            _lum = (int(_bg[0:2], 16) + int(_bg[2:4], 16) + int(_bg[4:6], 16)) / 3
            _is_dark = _lum < 128
        except Exception:
            _is_dark = False
        _map_bg = "#f0f0f0" if _is_dark else "white"

        lay = QGridLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setHorizontalSpacing(10)
        lay.setVerticalSpacing(6)

        # ── 좌: 웨이퍼 맵 ─────────────────────────
        self._plot = pg.PlotWidget()
        # 배경 — 밝은 테마: 흰색 / 다크 테마: 연회색 (다크 dialog 배경과 대비 확보)
        self._plot.setBackground(_map_bg)
        self._plot.setMouseEnabled(False, False)
        self._plot.setMenuEnabled(False)
        self._plot.hideButtons()
        self._plot.setAspectLocked(True)
        self._plot.showGrid(x=False, y=False)
        vb = self._plot.getViewBox()
        # ViewBox range ±170 → boundary R=153 이 영역의 ~0.9 비율 차지.
        # (이전 ±160 은 꽉 차서 답답)
        vb.setRange(xRange=(-170, 170), yRange=(-170, 170), padding=0)
        # 축 완전 제거 — hideAxis 는 공간까지 제거해서 ViewBox 가 plot widget
        # 중앙에 정렬됨 (setVisible(False) 는 공간 남김).
        pi = self._plot.getPlotItem()
        for ax_name in ("left", "bottom", "top", "right"):
            pi.hideAxis(ax_name)
        pi.layout.setContentsMargins(0, 0, 0, 0)
        # 외곽 테두리 — 표 전체 테두리와 동일 굵기/색 (테마 border 연동, 1px)
        self._plot.setStyleSheet(f"border: 1px solid {_border};")

        # 경계 원 + notch
        bx, by = _boundary_xy()
        self._plot.plot(bx, by, pen=pg.mkPen("#666", width=1.5))

        # 좌표점 — 검정 점 (기존 대비 2/3 크기)
        self._plot.plot(
            x, y,
            pen=None,
            symbol="o",
            symbolBrush=pg.mkBrush("#111"),
            symbolPen=pg.mkPen("#111"),
            symbolSize=4,
        )

        # 각 좌표점 옆에 Point 번호 텍스트 (오른쪽 위 방향으로 살짝 offset).
        # TextItem 들을 _num_items 에 모아 체크박스로 일괄 토글.
        self._num_items: list = []
        _pt_font = QFont()
        _pt_font.setPixelSize(10)
        for i in range(n):
            txt = pg.TextItem(text=str(i + 1), color="#444", anchor=(-0.1, 1.1))
            txt.setFont(_pt_font)
            txt.setPos(float(x[i]), float(y[i]))
            self._plot.addItem(txt, ignoreBounds=True)
            self._num_items.append(txt)

        # 공통 body 폰트 크기 — 체크박스/라벨 모두 동일 (전역 QSS 의 QCheckBox small
        # override 해서 표 위 "총 N 포인트" QLabel 과 동일 크기/체로 통일).
        from core.themes import FONT_SIZES
        _body_px = FONT_SIZES.get("body", 14)

        # ── 맵 상단 체크박스: 좌표번호 표시 on/off ─────
        self.chk_show_numbers = QCheckBox("좌표번호 표시")
        self.chk_show_numbers.setChecked(True)
        self.chk_show_numbers.setStyleSheet(
            f"QCheckBox {{ font-size: {_body_px}px; }}"
        )
        self.chk_show_numbers.toggled.connect(self._on_show_numbers_toggled)

        # ── 우: 좌표 표 ─────────────────────────
        info = QLabel(f"총 {n} 포인트")
        info.setStyleSheet(f"color: {_text_sub}; font-size: {_body_px}px;")

        self._table = QTableWidget(n, 3)
        self._table.setHorizontalHeaderLabels(["Point", "X (mm)", "Y (mm)"])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().hide()
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hh = self._table.horizontalHeader()
        # Point 은 좁게 고정, X/Y 는 Stretch — 남는 공간 균등 분배 (내용 최소 폭
        # 보장은 resizeToContents 불필요. X/Y 자릿수 짧아 stretch 로 충분히 여유).
        _col_xy_w = 90                # X/Y 칼럼 기준 폭 (표 minimum 폭 계산용)
        _col_pt_w = int(_col_xy_w * 0.7)  # Point 칼럼 = X/Y 의 0.7배 (=63px)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(0, _col_pt_w)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for i in range(n):
            it_p = QTableWidgetItem(str(i + 1))
            it_x = QTableWidgetItem(f"{float(x[i]):.3f}")
            it_y = QTableWidgetItem(f"{float(y[i]):.3f}")
            for it in (it_p, it_x, it_y):
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, 0, it_p)
            self._table.setItem(i, 1, it_x)
            self._table.setItem(i, 2, it_y)
        # 표 폭 = 맵과 동일한 정사각형 변 길이로 고정 (아래 _table_h 계산 후 조정).

        # 표 스타일 — 외곽/gridline 만 테마 border 연동. 배경·텍스트·헤더는
        # **라이트 고정** (wafer_cell summary 표 관례와 일관, PPT paste 호환).
        # 다크 테마에서 body 가 흰색이라 cell 글자 (#111) 와 대비 확보.
        self._table.setStyleSheet(f"""
            QTableWidget {{
                border: 1px solid {_border};
                gridline-color: {_border};
                background-color: white;
                color: #111;
            }}
            QTableWidget::item {{
                color: #111;
            }}
            QHeaderView::section {{
                background-color: #f0f0f0;
                color: #111;
                border: none;
                border-right: 1px solid {_border};
                border-bottom: 1px solid {_border};
                padding: 4px;
                font-weight: bold;
            }}
            QHeaderView::section:last {{
                border-right: none;
            }}
        """)

        # 표 높이 — 8.5 행 + header 로 고정 (마지막 행이 반만 보여 "스크롤 가능"
        # 을 사용자가 직관적으로 인지). 실제 스크롤바는 필요 시 자동.
        _row_h = 24
        self._table.verticalHeader().setDefaultSectionSize(_row_h)
        _hdr_h = self._table.horizontalHeader().sizeHint().height()
        _table_h = int(_row_h * 8.5) + _hdr_h + 2   # +2 frame
        self._table.setFixedHeight(_table_h)
        # 표 폭도 _table_h 로 정사각형. Point 고정 폭은 유지, X/Y 는 Stretch 로
        # 남는 공간 균등 분배.
        self._table.setFixedWidth(_table_h)
        # Plot widget 정사각형
        self._plot.setFixedSize(_table_h, _table_h)

        # 닫기 버튼
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)

        # ── 배치 ─────────────────────────────────
        # row 0: 좌표번호 체크박스 | info                — 같은 높이
        # row 1: plot              | table               — 같은 높이
        # row 2: (좌 빈)           | Close btn           — 같은 높이
        lay.addWidget(self.chk_show_numbers, 0, 0)
        lay.addWidget(info, 0, 1)
        lay.addWidget(self._plot, 1, 0)
        lay.addWidget(self._table, 1, 1)
        lay.addWidget(QWidget(), 2, 0)
        lay.addLayout(btn_row, 2, 1)
        # 세로로 row 1(plot/table) 이 늘어나도록
        lay.setRowStretch(0, 0)
        lay.setRowStretch(1, 1)
        lay.setRowStretch(2, 0)
        lay.setColumnStretch(0, 1)
        lay.setColumnStretch(1, 0)

        # 고정 크기 구성이라 dialog 도 자연 크기에 맞춤
        self.adjustSize()

    # ── slots ─────────────────────────────────
    def _on_show_numbers_toggled(self, checked: bool) -> None:
        """좌표번호 표시 체크박스 토글 → 모든 TextItem setVisible."""
        for it in self._num_items:
            it.setVisible(bool(checked))
