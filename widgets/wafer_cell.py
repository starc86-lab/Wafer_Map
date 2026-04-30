"""
한 웨이퍼(또는 한 DELTA) 결과 = 2D heatmap + Summary 4행×2열 표 묶음.

`WaferDisplay` 를 받아 렌더. 단일 시각화와 DELTA 시각화가 공통 사용.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import pyqtgraph as pg
import pyqtgraph.opengl as gl
from PySide6.QtCore import QMimeData, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QDoubleValidator, QFont, QFontMetrics, QImage, QLinearGradient,
    QPainter, QPalette, QPen, QPixmap,
)
from PySide6.QtOpenGL import (
    QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMenu, QStackedLayout, QVBoxLayout, QWidget,
)

from OpenGL import GL as _GL

from core import settings as settings_io
from core.coords import WAFER_RADIUS_MM, filter_in_wafer
from core.metrics import summary_metrics


BOUNDARY_SEGMENTS = 361

# 300mm 웨이퍼 notch — 실제 스펙은 ~3mm 폭/~1mm 깊이지만 화면에서 잘 보이도록 과장.
# 방향은 6시(하단, 3π/2) 고정. 깊이는 settings(chart_common.notch_depth_mm)에서 주입.
_NOTCH_ANGLE = 3 * np.pi / 2
_NOTCH_HALF_RAD = np.radians(3.0)
_NOTCH_DEFAULT_DEPTH_MM = 5.0


def _boundary_xy(
    show_notch: bool,
    depth: float = _NOTCH_DEFAULT_DEPTH_MM,
    R: float = WAFER_RADIUS_MM,
):
    """웨이퍼 경계 좌표. notch 옵션 시 6시 방향에 V자 홈 반영.

    R: 경계 원의 반지름 (기본 WAFER_RADIUS_MM=150). Settings 의 boundary_r_mm
    로 살짝 확장 가능 (150~160).
    """
    theta = np.linspace(0, 2 * np.pi, BOUNDARY_SEGMENTS)
    r = np.full_like(theta, R)
    if show_notch:
        d = np.abs(((theta - _NOTCH_ANGLE + np.pi) % (2 * np.pi)) - np.pi)
        in_notch = d < _NOTCH_HALF_RAD
        r[in_notch] = R - depth * (1 - d[in_notch] / _NOTCH_HALF_RAD)
    return r * np.cos(theta), r * np.sin(theta)


# ── 커스텀 컬러맵 — pyqtgraph 기본 목록에 없는 것 ──────
# 이름은 core.themes.HEATMAP_COLORMAPS에 함께 등록.
def _reversed_pg_cmap(name: str) -> pg.ColorMap:
    """pyqtgraph 기본 컬러맵을 min↔max 뒤집어 새 ColorMap 반환.

    pg 기본은 color가 float64(0~1). 새 ColorMap 생성자는 float 입력을 정상
    처리 못 해 uint8(0~255)로 변환 후 넘긴다.
    """
    cm = pg.colormap.get(name)
    color_u8 = (cm.color[::-1] * 255).astype(np.uint8)
    return pg.ColorMap(pos=cm.pos, color=color_u8)


_CUSTOM_CMAPS: dict[str, pg.ColorMap] = {
    # 2-stop gradient (min=White)
    "Red-White":      pg.ColorMap([0.0, 1.0], [(255, 255, 255), (220,  30,  30)]),
    "Blue-White":     pg.ColorMap([0.0, 1.0], [(255, 255, 255), ( 30,  70, 220)]),
    "Black-White":    pg.ColorMap([0.0, 1.0], [(255, 255, 255), ( 20,  20,  20)]),
    "Navy-White":     pg.ColorMap([0.0, 1.0], [(255, 255, 255), ( 20,  35, 110)]),
    "Pink-White":     pg.ColorMap([0.0, 1.0], [(255, 255, 255), (230,  70, 150)]),
    "Brown-White":    pg.ColorMap([0.0, 1.0], [(255, 255, 255), (130,  75,  40)]),
    "Charcoal-White": pg.ColorMap([0.0, 1.0], [(255, 255, 255), ( 65,  70,  80)]),
    # 뒤집힌 변형 (Turbo 제외)
    "Reverse-Viridis": _reversed_pg_cmap("viridis"),
    "Reverse-Plasma":  _reversed_pg_cmap("plasma"),
    "Reverse-Inferno": _reversed_pg_cmap("inferno"),
    "Reverse-Magma":   _reversed_pg_cmap("magma"),
    "Reverse-Cividis": _reversed_pg_cmap("cividis"),
}


def _compute_smooth_vertex_normals(vertexes: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """smooth vertex normals — numpy vectorized.

    pyqtgraph `MeshData.vertexNormals()`는 vertex 수만큼 Python for loop을 돌아
    62,500 vertex 기준 cell당 500ms 이상 소요. 같은 결과를 numpy로 5ms 내외에
    계산한 뒤 `_meshdata._vertexNormals`에 직접 주입해 lazy 경로를 우회.
    """
    v0 = vertexes[faces[:, 0]]
    v1 = vertexes[faces[:, 1]]
    v2 = vertexes[faces[:, 2]]
    face_n = np.cross(v1 - v0, v2 - v0)
    fl = np.linalg.norm(face_n, axis=1, keepdims=True)
    fl[fl < 1e-9] = 1.0
    face_n /= fl

    vert_n = np.zeros_like(vertexes, dtype=np.float32)
    np.add.at(vert_n, faces[:, 0], face_n)
    np.add.at(vert_n, faces[:, 1], face_n)
    np.add.at(vert_n, faces[:, 2], face_n)
    vl = np.linalg.norm(vert_n, axis=1, keepdims=True)
    vl[vl < 1e-9] = 1.0
    vert_n /= vl
    return vert_n.astype(np.float32)


def _build_radial_surface_mesh(
    xs: np.ndarray, ys: np.ndarray, z_raw: np.ndarray,
    rings: int, seg: int,
    vmin_h: float, factor: float,
    vmin_c: float, z_range_c: float,
    cmap: pg.ColorMap,
    *, cut_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """원형 radial mesh — pre-evaluated (xs, ys, z_raw) 로 정점 구성.

    (rings+1) × seg 정점 순서: i*seg + j (ring i, angle j)
    - 높이 스케일: `(z_raw - vmin_h) * factor` (vmin_h / factor 는 공통 / 개별 모드에 따라
      render 에서 결정).
    - 색 스케일: `vmin_c` + `z_range_c` 로 normalize (공통 모드 반영).
    - face: 인접 링 사이 사각형을 2 삼각형으로.
    - cut_mask: True 인 정점은 z=0 + 흰색 (edge_cut shelf / notch V 영역 제거용).
    """
    # RBF 외삽으로 vmin 아래 값이 나올 수 있음 → 바닥(z=0) 뚫지 않도록 clamp.
    z_disp = np.clip((z_raw - vmin_h) * factor, 0.0, None).astype(np.float32)

    # 잘려야 할 정점 z=0 으로 강제
    if cut_mask is not None:
        z_disp[cut_mask] = 0.0

    verts = np.column_stack([xs.astype(np.float32), ys.astype(np.float32), z_disp])

    # Faces — 각 (i,j) 사각형: a=(i,j), b=(i,j+1), c=(i+1,j+1), d=(i+1,j)
    N = rings * seg  # 사각형 개수
    a = np.empty(N, dtype=np.uint32)
    b = np.empty(N, dtype=np.uint32)
    c = np.empty(N, dtype=np.uint32)
    d = np.empty(N, dtype=np.uint32)
    k = 0
    for i in range(rings):
        for j in range(seg):
            j_next = (j + 1) % seg
            a[k] = i * seg + j
            b[k] = i * seg + j_next
            c[k] = (i + 1) * seg + j_next
            d[k] = (i + 1) * seg + j
            k += 1
    # 각 쿼드를 2 trig 으로
    faces = np.empty((2 * N, 3), dtype=np.uint32)
    faces[0::2, 0] = a; faces[0::2, 1] = b; faces[0::2, 2] = c
    faces[1::2, 0] = a; faces[1::2, 1] = c; faces[1::2, 2] = d

    # Colors — 공통 스케일 범위 기준 normalize
    rng = max(z_range_c, 1e-9)
    norm = np.clip((z_raw - vmin_c) / rng, 0.0, 1.0)
    lut = cmap.getLookupTable(0.0, 1.0, 256)
    idx = np.clip((norm * 255).astype(int), 0, 255)
    rgb = lut[idx, :3].astype(np.float32) / 255.0
    colors = np.concatenate([rgb, np.ones((rgb.shape[0], 1), dtype=np.float32)], axis=1)

    # cut 영역 정점은 흰색 (배경 매치)
    if cut_mask is not None and cut_mask.any():
        colors[cut_mask] = (1.0, 1.0, 1.0, 1.0)

    return verts, faces, colors


def _build_smooth_cylinder_wall(
    xs: np.ndarray, ys: np.ndarray, z_raw: np.ndarray,
    seg: int,
    vmin_h: float, factor: float,
    vmin_c: float, z_range_c: float,
    cmap: pg.ColorMap,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """매끈 원통 벽 — pre-evaluated (xs, ys, z_raw) 외곽 링 기반, bottom z=0.

    - 높이: `(z_raw - vmin_h) * factor` top z, bottom 은 z=0.
    - 색: `vmin_c` + `z_range_c` 로 normalize (공통 스케일 반영).
    """
    xs32 = xs.astype(np.float32)
    ys32 = ys.astype(np.float32)
    # 음수 clamp — 바닥 아래로 뚫고 내려가는 문제 방지
    z_top = np.clip((z_raw - vmin_h) * factor, 0.0, None).astype(np.float32)

    top = np.column_stack([xs32, ys32, z_top])
    bot = np.column_stack([xs32, ys32, np.zeros(seg, dtype=np.float32)])
    verts = np.vstack([top, bot])

    # faces: 각 세그먼트별 (top_i, top_nxt, bot_nxt) / (top_i, bot_nxt, bot_i)
    idx = np.arange(seg, dtype=np.uint32)
    nxt = ((idx + 1) % seg).astype(np.uint32)
    top_i, top_n = idx, nxt
    bot_i, bot_n = idx + seg, nxt + seg
    face_a = np.stack([top_i, top_n, bot_n], axis=1)
    face_b = np.stack([top_i, bot_n, bot_i], axis=1)
    faces = np.concatenate([face_a, face_b], axis=0)

    # 색: top 은 data z 기반(공통 스케일), bottom 은 colormap 가장 밑
    rng = max(z_range_c, 1e-9)
    norm_top = np.clip((z_raw - vmin_c) / rng, 0.0, 1.0)
    lut = cmap.getLookupTable(0.0, 1.0, 256)
    idx_top = np.clip((norm_top * 255).astype(int), 0, 255)
    rgb_top = lut[idx_top, :3].astype(np.float32) / 255.0
    rgb_bot = np.tile(lut[0:1, :3].astype(np.float32) / 255.0, (seg, 1))
    rgb = np.vstack([rgb_top, rgb_bot])
    alpha = np.ones((rgb.shape[0], 1), dtype=np.float32)
    colors = np.concatenate([rgb, alpha], axis=1)
    return verts, faces, colors


def _capture_gl_offscreen(gl_view: gl.GLViewWidget, scale: int = 1) -> QImage:
    """GLViewWidget 을 offscreen FBO 에 렌더 → QImage.

    - FBO format: MSAA 4x + CombinedDepthStencil
    - 크기: `widget_size * scale` (scale=1 기본 — GLScatterPlotItem / GLTextItem
      의 pxMode size 가 supersampling 시 상대적으로 작아지는 문제 회피)
    - `paint(region, viewport)` 로 viewport override (pyqtgraph 0.14+ 공개 API)
    - **GLTextItem 후처리**: pyqtgraph GLTextItem.paint 는 `QPainter(self.view())`
      로 widget 본체에 직접 그림 → FBO 에 반영 안 됨. paint() 직후 GL state 가
      FBO 기준으로 설정된 상태에서 GLTextItem 들을 QPainter 로 QImage 에 수동 재그림.

    화면 표시 상태와 무관하게 paintGL 로직을 offscreen FBO 에 찍음.
    스크롤에 가려지거나 다른 창이 덮어도 완전한 렌더 결과 확보.

    실패 시 빈 QImage 반환 (호출자가 폴백 처리).
    """
    if gl_view is None:
        return QImage()
    try:
        gl_view.makeCurrent()
        try:
            fmt = QOpenGLFramebufferObjectFormat()
            fmt.setSamples(4)  # MSAA 4x (FBO 레벨 강제)
            fmt.setAttachment(
                QOpenGLFramebufferObject.Attachment.CombinedDepthStencil,
            )
            w = max(1, int(gl_view.width()) * scale)
            h = max(1, int(gl_view.height()) * scale)
            fbo = QOpenGLFramebufferObject(QSize(w, h), fmt)
            if not fbo.bind():
                return QImage()
            _GL.glViewport(0, 0, w, h)
            gl_view.paint(region=(0, 0, w, h), viewport=(0, 0, w, h))
            img = fbo.toImage()  # MSAA auto-resolve → single-sample
            fbo.release()

            # GLTextItem 재그림 — scale=1 전제 (widget.rect == FBO size)
            text_items = [
                it for it in gl_view.items
                if isinstance(it, gl.GLTextItem) and getattr(it, "text", "")
            ]
            if text_items and scale == 1:
                from PySide6.QtGui import QFont, QVector3D
                painter = QPainter(img)
                painter.setRenderHints(
                    QPainter.RenderHint.Antialiasing
                    | QPainter.RenderHint.TextAntialiasing
                )
                # QSS 로 resolve 된 widget font family 를 FBO painter 에 전파.
                # QImage painter 는 QApplication.font() 만 상속하고 widget font 는
                # 모르므로, item.font 의 family 를 widget 기준으로 교체.
                widget_family = gl_view.font().family()
                for item in text_items:
                    project = item.compute_projection()
                    vec3 = QVector3D(*item.pos)
                    text_pos = item.align_text(project.map(vec3).toPointF())
                    font = QFont(item.font)
                    if widget_family:
                        font.setFamily(widget_family)
                    painter.setPen(item.color)
                    painter.setFont(font)
                    painter.drawText(text_pos, item.text)
                painter.end()

            return img
        finally:
            gl_view.doneCurrent()
    except Exception:
        return QImage()


class _LockedGLView(gl.GLViewWidget):
    """Shift+드래그 카메라 동기화 지원 GLViewWidget.

    - 휠 줌: GLViewWidget 기본 동작 사용 (카메라 distance 조정)
    - 좌 드래그: orbit (회전)
    - Ctrl+좌 드래그: pan (위치 이동) — GLViewWidget 기본
    - Shift+좌클릭: 클릭 순간 전 셀 카메라 스냅 동기. 이어서 Shift 유지 드래그 → 실시간 전파
    - 4x MSAA — surface edge·GLLinePlotItem(경계원·grid) 계단 제거
    """
    import weakref
    _instances: "weakref.WeakSet[_LockedGLView]" = weakref.WeakSet()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from PySide6.QtGui import QSurfaceFormat
        fmt = self.format()
        fmt.setSamples(4)
        self.setFormat(fmt)
        _LockedGLView._instances.add(self)
        self._sync_active: bool = False

    def _broadcast_camera(self) -> None:
        """자신의 카메라 opts를 다른 살아있는 _LockedGLView 인스턴스에 복사 + update."""
        keys = ("elevation", "azimuth", "distance", "center", "fov")
        my = {k: self.opts.get(k) for k in keys if k in self.opts}
        for other in list(_LockedGLView._instances):
            if other is self:
                continue
            try:
                if not other.isVisible():
                    continue
                other.opts.update(my)
                other.update()
            except RuntimeError:
                # widget deleted
                continue

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and (ev.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            # 즉시 전 셀을 현재 카메라와 동일 각도로 스냅 (회전 시작 전 정렬)
            self._sync_active = True
            self._broadcast_camera()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        super().mouseMoveEvent(ev)
        if self._sync_active and (ev.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._broadcast_camera()

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        self._sync_active = False


class _ColorBar(QWidget):
    """QWidget + QPainter 기반 경량 컬러맵 스케일바.

    pg.PlotWidget 버전은 cell당 ~18ms 생성 비용. 이 구현은 ~0.1ms.
    20-stop QLinearGradient(GPU 가속)로 충분히 부드러운 그라데이션 + tick 라벨 5개.
    """

    _BAR_RIGHT = 5  # 색상바 우측 margin (bar는 우측, 라벨은 좌측)
    _BAR_W = 17     # 색상바 폭 (14 × 1.2)
    _LABEL_GAP = 4  # bar와 라벨 사이 간격
    _MARGIN_V = 12  # 상하 여유 (라벨 잘림 방지)
    _N_STOPS = 20   # QLinearGradient stop 수
    _N_TICKS = 5    # 라벨 수

    _MIN_WIDTH = 60   # 기본 폭 (텍스트 짧을 때)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(self._MIN_WIDTH)
        # 전역 QSS 의 QWidget { background-color } 규칙이 child 에도 적용돼 회색
        # 배경이 되므로 인라인 QSS 로 투명 강제. WA_TranslucentBackground 는
        # top-level 전용이라 child widget 에선 효과 없음.
        self.setStyleSheet("background: transparent;")
        self._cmap: pg.ColorMap | None = None
        self._vmin: float = 0.0
        self._vmax: float = 1.0
        self._has_data: bool = False

    def update_bar(self, cmap: pg.ColorMap, vmin: float, vmax: float) -> None:
        if (vmin is None or vmax is None
                or not np.isfinite(vmin) or not np.isfinite(vmax)
                or vmin == vmax):
            return
        self._cmap = cmap
        self._vmin = float(vmin)
        self._vmax = float(vmax)
        self._has_data = True
        # 텍스트 최대 폭 실측 후 widget 폭 동적 조정 — 자릿수 많아지면 왼쪽으로
        # 확장. parent (chart_box) 기준 오른쪽 정렬은 _reposition 이 처리.
        decimals = _dynamic_decimals(self._vmin, self._vmax, self._N_TICKS)
        fmt = f"{{:.{decimals}f}}"
        font = QFont("Arial")
        font.setPixelSize(12)
        fm = QFontMetrics(font)
        max_text_w = 0
        for i in range(self._N_TICKS):
            t = i / (self._N_TICKS - 1)
            val = self._vmax - t * (self._vmax - self._vmin)
            max_text_w = max(max_text_w, fm.horizontalAdvance(fmt.format(val)))
        needed_w = (self._BAR_RIGHT + self._BAR_W + self._LABEL_GAP
                    + max_text_w + 4)
        needed_w = max(self._MIN_WIDTH, needed_w)
        if self.width() != needed_w:
            self.setFixedWidth(needed_w)
            self._reposition()
        self.update()

    _RIGHT_PAD = 4   # 오른쪽 여유 4px

    def _reposition(self) -> None:
        """parent(chart_box) 오른쪽 정렬 + raise_ (chart 위 overlay).

        y 좌표는 기존 값 유지 — cell 이 title_h 만큼 아래로 배치한 경우 그대로.
        x 는 right padding 적용.
        """
        p = self.parent()
        if p is None:
            return
        self.move(p.width() - self.width() - self._RIGHT_PAD, self.y())
        self.raise_()

    def paintEvent(self, ev) -> None:
        if not self._has_data or self._cmap is None:
            return
        p = QPainter(self)
        try:
            # 배경 투명 — chart_box 의 child overlay 라 chart 가 뒤에서 비침.
            # (WA_TranslucentBackground + fillRect 생략)
            w = self.width()
            h = self.height()
            bar_top = self._MARGIN_V
            bar_bottom = h - self._MARGIN_V
            bar_h = bar_bottom - bar_top
            if bar_h <= 0:
                return
            bar_x = w - self._BAR_RIGHT - self._BAR_W
            # 세로 gradient — top=max 색, bottom=min 색
            grad = QLinearGradient(0, bar_top, 0, bar_bottom)
            lut = self._cmap.getLookupTable(0.0, 1.0, self._N_STOPS)
            for i in range(self._N_STOPS):
                t = i / (self._N_STOPS - 1)     # 0=top, 1=bottom
                idx = self._N_STOPS - 1 - i     # top=LUT 마지막(max)
                rgb = lut[idx]
                grad.setColorAt(t, QColor(int(rgb[0]), int(rgb[1]), int(rgb[2])))
            bar_rect = QRect(bar_x, bar_top, self._BAR_W, bar_h)
            p.fillRect(bar_rect, grad)
            # White 계열 컬러맵일 때 배경과 안 구분되는 것 방지 — 연한 회색 테두리
            p.setPen(QPen(QColor(220, 220, 220)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(bar_rect)
            # tick 라벨 (5개, top=max) — bar 좌측에 우측 정렬
            # tick 간격(range / (N-1))에 맞춰 decimals 동적 결정 —
            # 예: range 0.02 → tick_step 0.005 → 3 decimals, range 20 → 5 → 0.
            # 절대 cap 4 (`_dynamic_decimals`) — 무한정 길어지는 출력 방지.
            decimals = _dynamic_decimals(self._vmin, self._vmax, self._N_TICKS)
            fmt = f"{{:.{decimals}f}}"
            # 폰트 12px 하드코딩 — font_scale 무관 (컬러바 폭 고정이라 큰 폰트 시 숫자 잘림 방지)
            font = QFont("Arial")
            font.setPixelSize(12)
            p.setFont(font)
            p.setPen(QPen(QColor("#111")))
            fm = QFontMetrics(font)
            text_right = bar_x - self._LABEL_GAP
            for i in range(self._N_TICKS):
                t = i / (self._N_TICKS - 1)
                val = self._vmax - t * (self._vmax - self._vmin)
                y = bar_top + t * bar_h
                text = fmt.format(val)
                tw = fm.horizontalAdvance(text)
                p.drawText(text_right - tw, int(y + fm.height() / 3), text)
        finally:
            p.end()


def resolve_colormap(name: str) -> pg.ColorMap:
    """이름 → pg.ColorMap. 커스텀 먼저, pyqtgraph는 대소문자 무관 lookup. fallback: viridis."""
    if name in _CUSTOM_CMAPS:
        return _CUSTOM_CMAPS[name]
    # pyqtgraph 기본(plasma/turbo 등)은 소문자라, 대문자 표기도 받아들이도록 소문자 재시도
    for candidate in (name, name.lower()):
        try:
            cm = pg.colormap.get(candidate)
            if cm is not None:
                return cm
        except Exception:
            continue
    return pg.colormap.get("viridis")


@dataclass
class WaferDisplay:
    """WaferCell 에 넘기는 표시 데이터.

    좌표(`x_mm`, `y_mm`)는 **이미 mm 환산된** 상태여야 함.
    반경 필터는 `WaferCell` 내부에서 수행.
    `z_range` 가 주어지면 3D 렌더 시 colormap 정규화 기준으로 사용 (다중 웨이퍼 공통 스케일).
    """
    title: str
    meta_label: str
    x_mm: np.ndarray
    y_mm: np.ndarray
    values: np.ndarray
    z_range: tuple[float, float] | None = None          # 2D/3D map Y range (rendered RBF 값 기반)
    z_range_1d: tuple[float, float] | None = None       # 1D radial graph Y range (실측 v 값 기반)
    is_radial: bool = False                             # 직선/방사 스캔 자동 감지 여부 (badge 표시용)
    is_delta: bool = False                              # DELTA 모드(A-B) 여부 — ER Time 입력 가시성용
    er_time_sec: float | None = None                    # ER/RR 변환용 time (초). None/0 = 변환 안 함


def _dynamic_decimals(vmin: float, vmax: float, n_ticks: int = 5) -> int:
    """tick 간격 + range bucket 기반 자릿수 (cap 3).

    두 항의 max:
      - needed: tick distinct 보장 — `-log10(tick_step)`
      - bucket: range 크기별 고정 decimals — 다중 wafer 일관성 + Z-margin 가시성

    bucket 룰 (사용자 정책 2026-04-30 갱신, 이전 log10 ceil 은 100 boundary 에서
    인접 wafer 간 자릿수 갈리는 inconsistency 있음):
      - range < 1     → 3 (GOF, K)
      - range < 10    → 2 (작은 스케일, NK)
      - range < 1000  → 1 (thickness, 일반 다중 wafer)
      - range >= 1000 → 0

    cap 3 — 매우 narrow range 에서도 무한정 길어지지 않음.
    """
    import math as _math
    if vmax <= vmin:
        return 0
    tick_step = (vmax - vmin) / max(n_ticks - 1, 1)
    range_val = vmax - vmin
    if tick_step <= 0 or range_val <= 0:
        return 2
    needed = max(0, -int(_math.floor(_math.log10(tick_step))))
    # range bucket — discrete, log10 ceil 의 boundary 미스매치 회피
    if range_val < 1.0:
        bucket = 3
    elif range_val < 10.0:
        bucket = 2
    elif range_val < 1000.0:
        bucket = 1
    else:
        bucket = 0
    return min(max(needed, bucket), 3)


class WaferCell(QFrame):
    """2D heatmap + 4행×2열 Summary 표. 컨테이너 grab → Copy Graph 합성 이미지.

    title + chart_box + table 전체가 하나의 패널 (border 박스)로 묶임.
    """

    # ER Map 변환 Time 변경 — MainWindow 가 연결해서 Z-Scale 모드에 맞춰 재렌더 결정.
    er_time_changed = Signal(object)   # emit: float | None
    # "전체 적용" 체크박스 토글 (master 에서만 emit). slave cell enable/disable 용.
    apply_all_toggled = Signal(bool)

    def __init__(
        self,
        display: WaferDisplay,
        value_name: str,
        view_mode: str = "2D",
        parent: QWidget | None = None,
        defer_render: bool = False,
        is_master: bool = False,
    ) -> None:
        super().__init__(parent)
        self._display = display
        self._value_name = value_name
        self._view_mode = view_mode  # "2D" | "3D"
        self._deferred = defer_render
        self._is_master = is_master

        # outer — border 없는 투명 컨테이너. er_row(캡처 밖) + _capture_container(캡처 대상)
        # 를 세로로 묶음. Copy Graph 는 _capture_container 만 crop 대상.
        outer_lay = QVBoxLayout(self)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(2)

        # ───── _capture_container (Copy Graph 대상) ─────
        # 기존 WaferCell 이 갖던 border/배경/내용을 이 컨테이너로 이동.
        self._capture_container = QFrame()
        self._capture_container.setObjectName("waferCell")
        self._capture_container.setStyleSheet(
            "#waferCell { background: white; border: 1px solid #bfbfbf; }"
        )
        outer_lay.addWidget(self._capture_container)

        # ───── er_row (캡처 영역 밖, 셀 하단) — 2 row ─────
        # Row 1: Time: [___]  전체 적용 [체크]  (slave 는 체크 없음)
        # Row 2: *입력 시 ΔTHK/Time 값으로 변환 (ER, RR 계산용도).  (slave 는 빈 placeholder)
        # 폰트는 전역 QWidget body 상속 (Settings 글자크기 연동). QCheckBox 만 전역
        # QSS 에서 small 이라 인라인 body 강제 (refresh 시 재적용).
        from core.themes import FONT_SIZES
        _body_px = FONT_SIZES.get("body", 14)

        # parent=self 명시 — 미명시 시 잠시 top-level 로 native window 승격 위험
        self._er_row = QWidget(self)
        er_outer = QVBoxLayout(self._er_row)
        er_outer.setContentsMargins(8, 2, 8, 2)
        er_outer.setSpacing(0)

        # Row 1
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(6)
        self.lbl_time = QLabel("Time:")
        row1.addWidget(self.lbl_time)
        self.le_time = QLineEdit()
        _v = QDoubleValidator(0.0, 99999.0, 2)
        _v.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.le_time.setValidator(_v)
        self.le_time.setFixedWidth(60)
        self.le_time.setPlaceholderText("sec")
        row1.addWidget(self.le_time)
        if is_master:
            self.chk_apply_all = QCheckBox("전체 적용")
            self.chk_apply_all.setChecked(True)  # default: 전체 적용 ON
            self.chk_apply_all.setStyleSheet(
                f"QCheckBox {{ font-size: {_body_px}px; }}"
            )
            row1.addWidget(self.chk_apply_all)
        else:
            self.chk_apply_all = None
        row1.addStretch(1)
        er_outer.addLayout(row1)

        # Row 2 — master 는 부연설명, slave 는 빈 placeholder (높이 맞춤)
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(0)
        _small_px = FONT_SIZES.get("small", 12)
        if is_master:
            self.lbl_desc = QLabel("*입력 시 ΔTHK/Time 값으로 변환 (ER, RR 계산용도).")
            self.lbl_desc.setStyleSheet(
                f"color: #888; font-size: {_small_px}px;"
            )
        else:
            self.lbl_desc = QLabel(" ")  # placeholder — Row 2 높이 유지
            self.lbl_desc.setStyleSheet(f"font-size: {_small_px}px;")
        row2.addWidget(self.lbl_desc)
        row2.addStretch(1)
        er_outer.addLayout(row2)

        # addWidget 먼저 (parent 확정) → 그 후 setVisible.
        # 순서 반대면 _er_row 가 잠시 top-level QWidget 으로 native window 표시 →
        # 팝업 깜빡임 (사용자 보고 2026-04-28). is_delta=True 시 setVisible(True) 가
        # promotion 트리거.
        outer_lay.addWidget(self._er_row)
        self._er_row.setVisible(bool(getattr(display, "is_delta", False)))

        # signal 연결 — editingFinished (엔터/포커스 아웃) 만 emit (textChanged 는
        # 타이핑 매 키마다라 과함)
        self.le_time.editingFinished.connect(self._on_time_edit_finished)
        if self.chk_apply_all is not None:
            self.chk_apply_all.toggled.connect(self.apply_all_toggled)

        # 기존 "lay" 이름 유지 — 아래 모든 addWidget 이 이 레이아웃 참조. 단, 부모가
        # self(기존) 에서 self._capture_container 로 변경됨.
        lay = QVBoxLayout(self._capture_container)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        # title_stack — title + chart_box 를 같은 영역 absolute overlay. chart 가
        # title 영역 침범 가능 (원이 title 뒤로 침투), title 은 raise_() 로 항상 위.
        self._title_stack = QWidget()
        self._title_stack.setStyleSheet("background: transparent;")
        lay.addWidget(self._title_stack)

        from core.themes import FONT_SIZES
        self._title = QLabel(display.title, self._title_stack)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 전역 QSS의 QWidget { font-size } 가 setFont()를 이기므로 인라인 CSS로 강제.
        # FONT_SIZES['body']는 font_scale 반영된 값이라 +4도 스케일 따라감.
        title_px = FONT_SIZES.get("body", 14) + 3
        self._title.setStyleSheet(
            f"font-weight: bold; color: #111; font-size: {title_px}px;"
            "background: transparent;"
        )
        self._title.move(0, 0)  # title_stack 내 상단 pin

        # 차트 컨테이너 — chart_area + colorbar 를 **absolute 배치**. chart_box 는
        # title_stack 의 자식 (title 과 동일 영역) → chart 가 title 위로 침범 가능.
        # colorbar 는 chart_box 오른쪽 끝 pin, 숫자 길면 왼쪽으로 확장 (overlay).
        self._chart_box = QWidget(self._title_stack)
        # chart_box 자체 투명 — 전역 QSS QWidget { background-color: bg } 가 회색
        # 으로 보이는 걸 방지. capture_container 흰 배경이 뒤로 비침.
        self._chart_box.setStyleSheet("background: transparent;")
        self._chart_box.move(0, 0)   # title_stack 내 상단 pin (title 과 같은 y)
        self._chart_area = QWidget(self._chart_box)
        self._chart_area.move(0, 0)
        self._chart_box_layout = QStackedLayout(self._chart_area)
        self._chart_box_layout.setContentsMargins(0, 0, 0, 0)

        self._colorbar = _ColorBar(self._chart_box)   # chart_box 의 overlay 자식

        # chart_box 는 title_stack 의 자식 → capture_container layout 에 별도 추가 안 함.
        # title_stack 이 이미 lay 에 있으므로 chart_box 도 자동 포함.

        _sfull = settings_io.load_settings()
        _scommon = _sfull.get("chart_common", {})
        _s3d = _sfull.get("chart_3d", {})
        cam_dist = float(_scommon.get("camera_distance", 620))
        elev_3d = float(_s3d.get("elevation", 28))
        azim_3d = float(_s3d.get("azimuth", -135))

        # 2D top-view (radial) — plain GLViewWidget (Shift 동기 없음, 2D 는 의미 X).
        # 카메라는 3D 와 동일 파라미터 (distance, fov) — elevation 만 90 (top-down),
        # azimuth=-90 으로 notch 를 6시(화면 하단)로 정렬.
        # → 3D 를 top 각도로 돌려 봤을 때와 동일 크기.
        self._gl_2d = gl.GLViewWidget()
        self._gl_2d.setBackgroundColor("w")
        self._gl_2d.setCameraPosition(distance=cam_dist, elevation=90, azimuth=-90)
        self._gl_2d.opts["fov"] = 45
        self._gl_2d.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._gl_2d.customContextMenuRequested.connect(self._show_plot_menu)
        self._chart_box_layout.addWidget(self._gl_2d)    # index 0

        # 3D radial view
        self._gl_3d = _LockedGLView()
        self._gl_3d.setBackgroundColor("w")
        self._gl_3d.setCameraPosition(distance=cam_dist, elevation=elev_3d, azimuth=azim_3d)
        self._gl_3d.opts["fov"] = 45
        self._gl_3d.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._gl_3d.customContextMenuRequested.connect(self._show_plot_menu)
        self._chart_box_layout.addWidget(self._gl_3d)    # index 1

        # 마지막으로 settings 에서 적용한 값 — Settings 변경 감지용 tracker.
        # render 시 opts['distance'] 와 비교하면 사용자 zoom 때마다 초기화 되는 버그
        # 있어 별도 추적. 3D view angle 도 같이 추적 (Settings elevation/azimuth 변경
        # 시 3D 카메라 재설정).
        self._applied_cam_dist: float = cam_dist
        self._applied_elev_3d: float = elev_3d
        self._applied_azim_3d: float = azim_3d

        self._chart_widget: QWidget = self._gl_2d  # 활성 위젯 추적

        # r-symmetry 모드 배지 — 직선 스캔 자동 감지 시 좌상단에 표시.
        # 각 GL 위젯의 자식으로 두 개 배치 (stacked layout 토글 시 각자 보임).
        # GL native surface 위에 QLabel 이지만 Windows + AA_ShareOpenGLContexts
        # 조합에서는 합성 정상. 카드 2D/3D 토글 시 자식 배지가 각각 활성.
        def _make_badge(parent: QWidget) -> QLabel:
            b = QLabel("r-symmetry mode", parent)
            b.setStyleSheet(
                "background: rgba(255,255,255,210); color: #555; "
                "padding: 2px 6px; border: 1px solid #bbb; border-radius: 4px; "
                "font-size: 11px;"
            )
            b.hide()
            b.move(8, 8)
            b.adjustSize()
            return b
        self._badge_2d = _make_badge(self._gl_2d)
        self._badge_3d = _make_badge(self._gl_3d)

        # 1D Radial Graph — 2D/3D 그래프와 Summary 표 사이. 체크 시에만 보임.
        # X: r (-5~155 표시, 눈금 0/50/100/150), Y: 실측 min/max 기반.
        # 상/우 테두리는 숨겨진 축(showAxis) 로 표현. 좌/하 축은 라벨 있음.
        self._radial_graph = pg.PlotWidget()
        self._radial_graph.setBackground("w")
        self._radial_graph.setMouseEnabled(False, False)
        self._radial_graph.setMenuEnabled(False)
        self._radial_graph.hideButtons()
        _ax_left = self._radial_graph.getAxis("left")
        _ax_bot = self._radial_graph.getAxis("bottom")
        # 상/우 축 모두 투명 padding (플롯 영역 좁게 + 위쪽 여백 확보)
        self._radial_graph.showAxis("top", show=True)
        self._radial_graph.showAxis("right", show=True)
        _ax_top = self._radial_graph.getAxis("top")
        _ax_right = self._radial_graph.getAxis("right")
        # 좌/하 축 pen — 연한 회색 #888888 1px, 숫자 #111, 폰트 12px 하드코딩
        from PySide6.QtGui import QPen, QColor, QFont
        _border_pen = QPen(QColor("#888888"))
        _border_pen.setWidth(1)
        _ax_font = QFont("Arial")
        _ax_font.setPixelSize(12)
        for _ax in (_ax_left, _ax_bot):
            _ax.setPen(_border_pen)
            _ax.setTextPen("#111111")
            _ax.setStyle(tickFont=_ax_font)
        # 하단 — 주눈금 0/50/100/150 만
        _ax_bot.setTicks([
            [(0, "0"), (50, "50"), (100, "100"), (150, "150")],
            [],
        ])
        _ax_left.setWidth(48)
        _ax_bot.setHeight(22)
        # 우축 투명 (선/눈금/라벨 off) + 폭 48 → 플롯 영역 좁아지고 widget 중앙 위치
        _ax_right.setStyle(showValues=False, tickLength=0)
        _ax_right.setTicks([[], []])
        _ax_right.setPen(QPen(QColor(0, 0, 0, 0)))
        _ax_right.setTextPen(QPen(QColor(0, 0, 0, 0)))
        _ax_right.setWidth(48)
        # 상축 투명 padding (widget 상단 ~ 플롯 상단 간격 확보, 2D/3D 와 거리감)
        _ax_top.setStyle(showValues=False, tickLength=0)
        _ax_top.setTicks([[], []])
        _ax_top.setPen(QPen(QColor(0, 0, 0, 0)))
        _ax_top.setTextPen(QPen(QColor(0, 0, 0, 0)))
        _ax_top.setHeight(16)
        # X range — 0~150 기준 양끝 10mm 균등 여유 (-10~160). 라벨 cull 방지 + 대칭.
        self._radial_graph.setXRange(-10, 160, padding=0)
        self._radial_graph.setVisible(False)
        lay.addWidget(self._radial_graph)

        # Summary 위젯 — Settings 의 table.style 에 따라 dispatch (기본
        # ppt_basic = 기존 QTableWidget). 사용자 정책 2026-04-30, table style
        # 카탈로그 인프라 도입.
        from widgets.summary import build_summary
        _table_style = settings_io.load_settings().get("table", {}).get("style", "ppt_basic")
        self._summary = build_summary(_table_style, parent=self)
        # 기존 코드 호환 — _table 별칭 (Copy Graph .grab(), context menu 등 유지).
        # ppt_basic 의 _table 속성 우선, 없으면 _summary 자체.
        self._table = getattr(self._summary, "_table", self._summary)
        # 우클릭 메뉴 — style 의 context_menu_target 우선, 없으면 _summary 자체
        ctx_target = (self._summary.context_menu_target()
                      if hasattr(self._summary, "context_menu_target")
                      else self._summary)
        ctx_target.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        ctx_target.customContextMenuRequested.connect(self._show_table_menu)
        # Table — 폭은 _apply_chart_size 에서 cell 기준으로 설정, layout 에서 가운데 정렬
        lay.addWidget(self._summary, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._x_in = np.array([])
        self._y_in = np.array([])
        self._v_in = np.array([])    # effective (ER time 적용 후 — render 경로가 이 값 사용)
        self._v_raw = np.array([])   # 원본 delta — ER time 변경 시 재계산 기준
        # 렌더 캐시 — 한 번 그려진 모드는 재계산 없이 인덱스 토글만
        self._rendered_2d = False
        self._rendered_3d = False
        # 3D radial mesh slot — GLMeshItem (surface + cylinder wall)
        self._gl_surface = None      # radial surface mesh
        self._gl_wall = None         # smooth cylinder wall
        self._gl_boundary = None     # 경계 원 (notch 포함)
        self._gl_grid = None         # 바닥 grid
        # 데이터 필터는 즉시 (가벼움) — 렌더는 defer면 ResultPanel이 병렬 prefetch 후 호출
        self._load_data()
        if not defer_render:
            self.render_initial()

    def _load_data(self) -> None:
        """display → filter_in_wafer → _x_in/_y_in/_v_in 설정. 가벼움(<1ms)."""
        d = self._display
        n = min(len(d.x_mm), len(d.y_mm), len(d.values))
        if n == 0:
            return
        x_mm = np.asarray(d.x_mm[:n], dtype=float)
        y_mm = np.asarray(d.y_mm[:n], dtype=float)
        v = np.asarray(d.values[:n], dtype=float)
        x_in, y_in, v_in, _ = filter_in_wafer(x_mm, y_mm, v)
        self._x_in, self._y_in, self._v_raw = x_in, y_in, v_in
        self._recompute_v_eff()

    def render_initial(self) -> None:
        """defer된 초기 렌더를 수행. ResultPanel이 병렬 prefetch 후 호출."""
        if self._v_in.size == 0:
            return
        settings = settings_io.load_settings()
        self._apply_chart_size(settings.get("chart_common", {}))
        self._update_table(self._v_in, settings)
        self._activate_current_view()
        self._deferred = False

    def _apply_chart_size(self, common: dict) -> None:
        """cell 전체를 컨텐츠에 딱 맞춘 고정 크기로 — 리사이즈 시 간격 stretch 없음.

        스케일바 유무와 **무관하게 cell 전체 폭도, chart_area 크기도 동일** —
        3D 크기는 카메라 distance로만 변함. 스케일바 해제 시 chart_area가
        좌우로 중앙 정렬만 될 뿐(좌우 margin 대칭).
        """
        w = int(common.get("chart_width", 360))
        h = int(common.get("chart_height", 280))
        bar_w = 60  # colorbar 기본 폭
        # title_stack 은 title + chart_box overlap container. chart_box 높이를
        # title_h 만큼 위로 확장 → chart 원이 title 영역까지 침범 가능.
        # title 은 raise_() 로 z-order 최상 (항상 chart 위).
        # title 위에 padding_top 여백 — capture_container layout margin 6 위에 추가.
        # 총 6 + 1 = 7px.
        padding_top = 1
        title_h = self._title.sizeHint().height()
        stack_w = w + bar_w
        stack_h = padding_top + title_h + h

        self._title_stack.setFixedSize(stack_w, stack_h)
        self._title.setFixedSize(stack_w, title_h)
        self._title.move(0, padding_top)   # 상단 padding 만큼 아래로

        self._chart_box.setFixedSize(stack_w, stack_h)
        self._chart_box.move(0, 0)
        # chart_area = (w + bar_w/2, stack_h) — chart_box 왼쪽 ¾ 차지. 세로는
        # padding + title + chart 전체. 원 중심이 chart_area 세로 중앙.
        self._chart_area.setFixedSize(w + bar_w // 2, stack_h)
        self._chart_area.move(0, 0)

        # colorbar: y=padding+title_h (title 아래 시작). 높이는 원 하단까지 축소.
        # 원 하단 y = stack_h/2 + h/2. colorbar 시작 = padding+title_h.
        # colorbar height = (stack_h + h)/2 - (padding+title_h) = h - (padding+title_h)/2.
        cb_height = h - (padding_top + title_h) // 2
        self._colorbar.setFixedHeight(cb_height)
        self._colorbar.move(self._colorbar.x(), padding_top + title_h)
        self._colorbar._reposition()  # x 오른쪽 정렬 (y 는 유지)

        # title 이 chart_box / colorbar 위에 z-order 최상
        self._title.raise_()

        # r-symmetry 배지 — 좌측 하단. chart_area 의 자식 GL widget 기준 pos.
        bh = self._badge_2d.sizeHint().height()
        badge_y = stack_h - bh - 4
        for b in (self._badge_2d, self._badge_3d):
            b.move(8, badge_y)
        # 1D Radial Graph — show_1d_radial 체크 시 보이고, 높이 135px
        # 위젯은 cell content 꽉 채움. 플롯 centering 은 내부 좌/우 축 대칭으로.
        show_radial = bool(common.get("show_1d_radial", False))
        self._radial_graph.setVisible(show_radial)
        radial_h_px = 135
        if show_radial:
            self._radial_graph.setFixedWidth(w + bar_w)
            self._radial_graph.setFixedHeight(radial_h_px)
        radial_h = radial_h_px if show_radial else 0
        # Summary 위젯 폭 — cell 컨텐츠 폭에서 좌우 8px 씩 축소, layout 에서 가운데 정렬.
        # 모든 style 이 동일 폭 수용 (사용자 정책 2026-04-30, 크기 align 보장).
        self._summary.set_target_width(w + bar_w - 16)
        # _capture_container (QFrame, border) 만 고정 크기 — 그래프 영역 보존.
        # cell outer (self) 는 layout 이 자동 합산 (_capture_container + er_row).
        # 이전에 self.setFixedSize 로 total_h 를 계산했는데 inner layout 의 spacing 수
        # (radial 숨김 여부 등) 가 동적이라 계산이 어긋나 chart 가 잘리는 버그.
        # title_h + padding_top 은 위 title_stack 과 일관. title 위 6px 여백 포함.
        title_h = self._title.sizeHint().height()
        table_h = self._summary.height()
        cap_w = w + bar_w + 6 * 2              # inner margin 6+6
        cap_h = padding_top + title_h + h + radial_h + table_h + 6 * 2 + 4 * 2
        self._capture_container.setFixedSize(cap_w, cap_h)
        # cell outer — 폭은 capture 와 동일, 높이는 자유 (layout 이 capture + er_row 합산)
        self.setFixedWidth(cap_w)
        self.setMaximumHeight(16777215)        # 이전 setFixedSize 로 생긴 height 제약 해제
        self.adjustSize()

    # ── 외부 API ───────────────────────────────────
    @property
    def display(self) -> WaferDisplay:
        return self._display

    def set_view_mode(self, mode: str) -> None:
        """View 토글 — 첫 진입이면 그리고 캐시, 캐시 있으면 인덱스만 토글(0ms)."""
        if mode == self._view_mode:
            return
        self._view_mode = mode
        self._activate_current_view()

    def invalidate_3d(self) -> None:
        """3D 캐시만 무효화 — z_range 변경 등 3D만 영향받을 때.

        현재 view가 3D면 즉시 재렌더, 2D면 다음 3D 진입 시 그림.
        """
        self._rendered_3d = False
        self._hide_3d_items()
        if self._view_mode == "3D":
            self._activate_current_view()

    def refresh(self) -> None:
        """Settings(컬러맵·보간·mesh 옵션 등) 변경 시 호출 — 양쪽 view 재렌더."""
        self._rendered_2d = False
        self._rendered_3d = False
        self._hide_3d_items()
        settings = settings_io.load_settings()
        # 제목 폰트 크기 재적용 — font_scale 변경 즉시 반영
        from core.themes import FONT_SIZES
        _title_px = FONT_SIZES.get("body", 14) + 3
        self._title.setStyleSheet(
            f"font-weight: bold; color: #111; font-size: {_title_px}px;"
        )
        # er_row 내 위젯 폰트 재적용 — Settings 글자크기 변경 시 따라감.
        # - chk_apply_all: 전역 QSS 가 small 이라 body 강제
        # - lbl_desc: 부연설명은 body 한 단계 아래 small (한국어 긴 문장 우측 잘림 방지)
        _body_px = FONT_SIZES.get("body", 14)
        _small_px = FONT_SIZES.get("small", 12)
        if self.chk_apply_all is not None:
            self.chk_apply_all.setStyleSheet(
                f"QCheckBox {{ font-size: {_body_px}px; }}"
            )
        if self.lbl_desc is not None:
            if self._is_master:
                self.lbl_desc.setStyleSheet(
                    f"color: #888; font-size: {_small_px}px;"
                )
            else:
                self.lbl_desc.setStyleSheet(f"font-size: {_small_px}px;")
        self._apply_chart_size(settings.get("chart_common", {}))
        # Summary 표 재계산 — v_in 변경 (ER time 적용 등) 반영. 빠뜨리면 map/1D 만
        # 갱신되고 표만 stale.
        if self._v_in.size > 0:
            self._update_table(self._v_in, settings)
        self._activate_current_view()

    def prefetch_interp(self) -> None:
        """호환 유지용 — radial 경로에선 별도 캐시 없이 렌더 시 직접 RBF.

        이전 rect 경로의 _ensure_interp 병렬화를 위해 ResultPanel 이 호출했던 훅.
        radial 은 RBF fit 자체가 ~1ms 로 충분히 빨라 병렬화 이득 미미. no-op.
        """
        return

    def prefetch_inactive_view(self) -> None:
        """현재 view_mode와 반대 view를 미리 렌더 (캐시만 채움).

        Run Analysis 완료 후 다음 이벤트 tick에 호출 → 사용자가 2D 보는 사이
        3D도 미리 준비 → 콤보 토글 시 setCurrentIndex만으로 즉시 전환.

        3D prefetch 시 `grabFramebuffer()`로 **hidden 상태에서도 GL 컨텍스트
        초기화 + 첫 paint**를 강제. 덕분에 깜빡임 없이 GPU 업로드 비용을 이
        시점에 흡수 → 이후 show 시 0 딜레이.
        """
        if self._v_in.size == 0:
            return
        settings = settings_io.load_settings()
        if self._view_mode == "2D" and not self._rendered_3d:
            self._render_3d(self._x_in, self._y_in, self._v_in, settings)
            self._rendered_3d = True
            # hidden 상태에서 GL 초기화 + 한 번 paint — 깜빡임 없음
            try:
                self._gl_3d.grabFramebuffer()
            except Exception:
                pass
        elif self._view_mode == "3D" and not self._rendered_2d:
            self._render_2d(self._x_in, self._y_in, self._v_in, settings)
            self._rendered_2d = True

    # ── 렌더 ────────────────────────────────────────
    def _render(self) -> None:
        d = self._display
        n = min(len(d.x_mm), len(d.y_mm), len(d.values))
        if n == 0:
            self._hide_3d_items()
            return
        x_mm = np.asarray(d.x_mm[:n], dtype=float)
        y_mm = np.asarray(d.y_mm[:n], dtype=float)
        v = np.asarray(d.values[:n], dtype=float)

        x_in, y_in, v_in, _ = filter_in_wafer(x_mm, y_mm, v)
        self._x_in, self._y_in, self._v_raw = x_in, y_in, v_in
        self._recompute_v_eff()

        # 새 데이터 — 렌더 캐시 무효화
        self._rendered_2d = False
        self._rendered_3d = False
        self._hide_3d_items()

        settings = settings_io.load_settings()
        self._update_table(v_in, settings.get("table", {}))
        self._activate_current_view()

    def _hide_3d_items(self) -> None:
        """3D items 숨김 (widget 자체는 유지, setData 로 다음 렌더 시 즉시 재사용)."""
        for it in (self._gl_surface, self._gl_wall,
                    self._gl_boundary, self._gl_grid):
            if it is not None:
                it.setVisible(False)

    # ── ER Time 제어 ────────────────────────────────
    def _recompute_v_eff(self) -> None:
        """_v_raw → _v_in 계산. display.er_time_sec 이 있으면 `v / t` 적용."""
        t = getattr(self._display, "er_time_sec", None)
        if t and t > 0 and self._v_raw.size > 0:
            self._v_in = self._v_raw / float(t)
        else:
            self._v_in = self._v_raw.copy()

    def set_er_time(self, t: float | None) -> None:
        """외부 (master → slave 동기화 / MainWindow) 에서 ER time 주입.

        값 갱신 + LineEdit 텍스트 동기 + v_eff 재계산. 재렌더는 호출자 책임
        (공통 Z-Scale 에선 전체 재렌더 필요해 개별 cell refresh 트리거 안 함).
        signal emit 하지 않음 (재진입 방지).
        """
        self._display.er_time_sec = t if (t and t > 0) else None
        txt = "" if self._display.er_time_sec is None else f"{self._display.er_time_sec:g}"
        if self.le_time.text() != txt:
            self.le_time.blockSignals(True)
            self.le_time.setText(txt)
            self.le_time.blockSignals(False)
        self._recompute_v_eff()

    def _on_time_edit_finished(self) -> None:
        """QLineEdit editingFinished → time 파싱 + display 반영 + er_time_changed emit.

        빈 문자열 / 0 / 음수 → None (변환 off). 값 변경 없으면 emit 안 함.
        실제 재렌더는 MainWindow 가 Z-Scale 모드 보고 개별 / 전체 결정.
        """
        txt = self.le_time.text().strip()
        new_t: float | None = None
        if txt:
            try:
                val = float(txt)
                if val > 0:
                    new_t = val
            except ValueError:
                pass
        prev = getattr(self._display, "er_time_sec", None)
        if new_t == prev:
            return
        self._display.er_time_sec = new_t
        self._recompute_v_eff()
        self.er_time_changed.emit(new_t)

    def set_delta_mode(self, is_delta: bool) -> None:
        """DELTA 모드 여부 외부 주입 — er_row visibility 제어 + cell 높이 재계산."""
        self._display.is_delta = bool(is_delta)
        self._er_row.setVisible(bool(is_delta))
        # setFixedSize 재계산 — er_row 높이 변화 반영
        common = settings_io.load_settings().get("chart_common", {})
        self._apply_chart_size(common)

    def _activate_current_view(self) -> None:
        """현재 _view_mode 인덱스로 stack 토글, 캐시 없으면 그때 한 번 그림."""
        settings = settings_io.load_settings()
        if self._view_mode == "3D":
            self._chart_box_layout.setCurrentIndex(1)
            self._chart_widget = self._gl_3d
            if not self._rendered_3d and self._v_in.size > 0:
                self._render_3d(self._x_in, self._y_in, self._v_in, settings)
                self._rendered_3d = True
        else:
            self._chart_box_layout.setCurrentIndex(0)
            self._chart_widget = self._gl_2d
            if not self._rendered_2d and self._v_in.size > 0:
                self._render_2d(self._x_in, self._y_in, self._v_in, settings)
                self._rendered_2d = True

    def _render_2d(self, x_in, y_in, v_in, settings) -> None:
        """2D top-view radial mesh — RBF 1회 평가, _gl_2d 위젯 사용.

        3D radial 과 동일한 mesh 데이터를 z=0 평면으로 깔아서 위에서 내려다 본 모습.
        측정점/값 라벨/경계 원 모두 GL 객체로 그림.
        """
        from core.interp import make_interp

        common = settings.get("chart_common", {})
        chart = settings.get("chart_2d", {})

        # r-symmetry mode 배지 — auto-detect (is_radial) 또는 force (r_symmetry_mode).
        is_rad = bool(getattr(self._display, "is_radial", False)) or \
                 bool(settings.get("r_symmetry_mode", False))
        self._badge_2d.setVisible(is_rad)
        if is_rad:
            self._badge_2d.raise_()
        rings = max(5, int(common.get("radial_rings", 20)))
        seg = max(60, int(common.get("radial_seg", 180)))
        edge_cut_mm = float(common.get("edge_cut_mm", 0.0))
        R = float(WAFER_RADIUS_MM)
        effective_R = max(R - edge_cut_mm, 1.0) if edge_cut_mm > 0 else R
        apply_cut = edge_cut_mm > 0 and effective_R < R

        gview = self._gl_2d

        # Map Size (camera_distance) — 2D/3D 공통. Settings 값이 **바뀔 때만** 리셋
        # (사용자의 zoom 상태 보존).
        dist = float(common.get("camera_distance", 620))
        if dist != self._applied_cam_dist:
            gview.setCameraPosition(distance=dist)
            self._gl_3d.setCameraPosition(distance=dist)
            self._applied_cam_dist = dist

        # 기존 모든 item 제거 (top view 는 매 렌더 깨끗이 다시 그림 — overhead 작음)
        for it in list(gview.items):
            gview.removeItem(it)

        # RBF fit — settings 의 interp_method 반영
        pts = np.column_stack([np.asarray(x_in, dtype=float), np.asarray(y_in, dtype=float)])
        vals = np.asarray(v_in, dtype=float)
        m = ~np.isnan(vals) & ~np.isnan(pts[:, 0]) & ~np.isnan(pts[:, 1])
        if m.sum() < 2:
            return
        method = str(common.get("interp_method", "RBF-ThinPlate"))
        radial_width = float(common.get("radial_line_width_mm", 45.0))
        try:
            rbf = make_interp(
                pts[m, 0], pts[m, 1], vals[m], method=method,
                radial_line_width_mm=radial_width,
                radial_method=str(common.get("radial_method", "Univariate Spline")),
                radial_smoothing_factor=float(common.get("radial_smoothing_factor", 5.0)),
                savgol_window=int(common.get("savgol_window", 11)),
                savgol_polyorder=int(common.get("savgol_polyorder", 3)),
                lowess_frac=float(common.get("lowess_frac", 0.3)),
                polyfit_degree=int(common.get("polyfit_degree", 3)),
                radial_bin_size_mm=float(common.get("radial_bin_size_mm", 0)),
                force_radial=bool(settings.get("r_symmetry_mode", False)),
            )
        except Exception:
            return

        # 링 배치 (3D radial 과 동일 — edge_cut shelf 1 ring 추가)
        if apply_cut:
            r_arr = np.concatenate([np.linspace(0.0, effective_R, rings + 1), [R]])
        else:
            r_arr = np.linspace(0.0, R, rings + 1)
        n_rings = len(r_arr) - 1

        theta = np.linspace(0.0, 2.0 * np.pi, seg, endpoint=False)
        Rm, Tm = np.meshgrid(r_arr, theta, indexing="ij")
        xs_all = (Rm * np.cos(Tm)).ravel()
        ys_all = (Rm * np.sin(Tm)).ravel()
        z_raw_all = rbf(np.column_stack([xs_all, ys_all]))

        # vmin/vmax — 공통 스케일 모드 우선, 아니면 radial 평가값 기반
        if self._display.z_range is not None:
            vmin, vmax = self._display.z_range
        else:
            finite = z_raw_all[np.isfinite(z_raw_all)]
            if finite.size == 0:
                return
            vmin = float(finite.min())
            vmax = float(finite.max())
        z_range = vmax - vmin if vmax > vmin else 1.0

        # 2D top view: z=0 평면 (높이 표현 없음, 색만)
        # cut mask — edge_cut 만 (notch 는 boundary 원에만 표시)
        eff_r_seg = np.full(seg, effective_R, dtype=float)
        vert_theta_idx = np.arange(xs_all.size) % seg
        r_flat = np.sqrt(xs_all ** 2 + ys_all ** 2)
        cut_mask_all = r_flat > eff_r_seg[vert_theta_idx] + 1e-6

        cmap = resolve_colormap(common.get("colormap", "Turbo"))
        # 정점 색 — z_raw 기반 normalize
        rng = max(z_range, 1e-9)
        norm = np.clip((z_raw_all - vmin) / rng, 0.0, 1.0)
        lut = cmap.getLookupTable(0.0, 1.0, 256)
        idx_arr = np.clip((norm * 255).astype(int), 0, 255)
        rgb = lut[idx_arr, :3].astype(np.float32) / 255.0
        colors = np.concatenate([rgb, np.ones((rgb.shape[0], 1), dtype=np.float32)], axis=1)
        if cut_mask_all.any():
            colors[cut_mask_all] = (1.0, 1.0, 1.0, 1.0)

        # Faces
        N = n_rings * seg
        a = np.empty(N, dtype=np.uint32); b = np.empty(N, dtype=np.uint32)
        c = np.empty(N, dtype=np.uint32); d = np.empty(N, dtype=np.uint32)
        k = 0
        for i in range(n_rings):
            for j in range(seg):
                jn = (j + 1) % seg
                a[k] = i * seg + j
                b[k] = i * seg + jn
                c[k] = (i + 1) * seg + jn
                d[k] = (i + 1) * seg + j
                k += 1
        faces = np.empty((2 * N, 3), dtype=np.uint32)
        faces[0::2, 0] = a; faces[0::2, 1] = b; faces[0::2, 2] = c
        faces[1::2, 0] = a; faces[1::2, 1] = c; faces[1::2, 2] = d

        # 정점 — z=0 평면
        verts = np.column_stack([
            xs_all.astype(np.float32),
            ys_all.astype(np.float32),
            np.zeros(xs_all.size, dtype=np.float32),
        ])
        mesh = gl.GLMeshItem(
            vertexes=verts, faces=faces, vertexColors=colors,
            smooth=True, drawEdges=False, glOptions="opaque",
        )
        gview.addItem(mesh)

        # 경계 원 (notch 표시) — mesh 위에 살짝 띄움
        if common.get("show_circle", True):
            bx, by = _boundary_xy(
                common.get("show_notch", True),
                float(common.get("notch_depth_mm", _NOTCH_DEFAULT_DEPTH_MM)),
                R=float(common.get("boundary_r_mm", WAFER_RADIUS_MM)),
            )
            circ = np.column_stack([bx, by, np.full_like(bx, 0.5)])
            line = gl.GLLinePlotItem(
                pos=circ, color=(0, 0, 0, 1), width=2,
                antialias=True, glOptions="opaque",
            )
            gview.addItem(line)

        # 측정점
        if chart.get("show_points", True):
            pts3d = np.column_stack([
                np.asarray(x_in, dtype=np.float32),
                np.asarray(y_in, dtype=np.float32),
                np.full(len(x_in), 0.7, dtype=np.float32),
            ])
            scatter = gl.GLScatterPlotItem(
                pos=pts3d, color=(0.0, 0.0, 0.0, 0.85),
                size=float(chart.get("point_size", 4)),
                pxMode=True, glOptions="opaque",
            )
            gview.addItem(scatter)

        # 값 라벨
        if chart.get("show_value_labels", False):
            tbl = settings.get("table", {})
            decimals = int(common.get("decimals", tbl.get("decimals", 2)))
            # 라벨 폰트 크기 — chart_2d.label_font_scale (0.85 / 1.0 / 1.15) × base 9pt
            scale = float(chart.get("label_font_scale", 0.85))
            from PySide6.QtGui import QFont
            label_font = QFont()
            label_font.setPointSize(max(5, int(round(9 * scale))))
            for x, y, val in zip(x_in, y_in, v_in):
                if np.isnan(val):
                    continue
                try:
                    ti = gl.GLTextItem(
                        pos=(float(x), float(y), 1.0),
                        text=f"{val:.{decimals}f}",
                        color=(40, 40, 40, 255),
                        font=label_font,
                    )
                    gview.addItem(ti)
                except Exception:
                    pass

        # colorbar
        self._update_colorbar(common, None, vmin=vmin, vmax=vmax)
        self._update_radial_graph(common)

    def _render_3d(self, x_in, y_in, v_in, settings) -> None:
        """radial 원형 fan mesh 기반 3D 렌더 — (r, θ) mesh + 매끈 원통 벽.

        비용: RBF 정점 (rings+1)×seg + seg 개 재평가.
        """
        from core.interp import make_interp

        common = settings.get("chart_common", {})
        chart3d = settings.get("chart_3d", {})

        # r-symmetry mode 배지 — 2D 와 동일 로직.
        is_rad = bool(getattr(self._display, "is_radial", False)) or \
                 bool(settings.get("r_symmetry_mode", False))
        self._badge_3d.setVisible(is_rad)
        if is_rad:
            self._badge_3d.raise_()

        # 카메라 distance / elevation / azimuth — Settings 값이 **바뀔 때만** 반영
        # (사용자의 휠 zoom / 드래그 회전 보존). opts 대신 _applied_* 트래커와 비교.
        dist = float(common.get("camera_distance", 620))
        if dist != self._applied_cam_dist:
            self._gl_3d.setCameraPosition(distance=dist)
            self._gl_2d.setCameraPosition(distance=dist)
            self._applied_cam_dist = dist
            self._gl_3d.update()

        elev_3d = float(chart3d.get("elevation", 28))
        azim_3d = float(chart3d.get("azimuth", -135))
        if elev_3d != self._applied_elev_3d or azim_3d != self._applied_azim_3d:
            self._gl_3d.setCameraPosition(elevation=elev_3d, azimuth=azim_3d)
            self._applied_elev_3d = elev_3d
            self._applied_azim_3d = azim_3d
            self._gl_3d.update()

        rings = max(5, int(common.get("radial_rings", 20)))
        seg = max(60, int(common.get("radial_seg", 180)))

        # RBF fit — settings 의 interp_method 반영
        pts = np.column_stack([np.asarray(x_in, dtype=float), np.asarray(y_in, dtype=float)])
        vals = np.asarray(v_in, dtype=float)
        mask = ~np.isnan(vals) & ~np.isnan(pts[:, 0]) & ~np.isnan(pts[:, 1])
        if mask.sum() < 2:
            return
        method = str(common.get("interp_method", "RBF-ThinPlate"))
        radial_width = float(common.get("radial_line_width_mm", 45.0))
        try:
            rbf = make_interp(
                pts[mask, 0], pts[mask, 1], vals[mask], method=method,
                radial_line_width_mm=radial_width,
                radial_method=str(common.get("radial_method", "Univariate Spline")),
                radial_smoothing_factor=float(common.get("radial_smoothing_factor", 5.0)),
                savgol_window=int(common.get("savgol_window", 11)),
                savgol_polyorder=int(common.get("savgol_polyorder", 3)),
                lowess_frac=float(common.get("lowess_frac", 0.3)),
                polyfit_degree=int(common.get("polyfit_degree", 3)),
                radial_bin_size_mm=float(common.get("radial_bin_size_mm", 0)),
                force_radial=bool(settings.get("r_symmetry_mode", False)),
            )
        except Exception:
            return

        R = float(WAFER_RADIUS_MM)

        # edge_cut 먼저 결정 (링 배치에 영향)
        edge_cut_mm = float(common.get("edge_cut_mm", 0.0))
        effective_R = max(R - edge_cut_mm, 1.0) if edge_cut_mm > 0 else R
        apply_cut = edge_cut_mm > 0 and effective_R < R

        # Radial 링 배치:
        # - edge_cut 없음: 0 ~ R 균등 (rings+1 개 링)
        # - edge_cut 적용: 0 ~ effective_R 균등 (rings+1 개 interior 링) + R (shelf 링 1개)
        #   → shelf 영역이 하나의 얇은 band 로 렌더됨
        if apply_cut:
            r_arr = np.concatenate([
                np.linspace(0.0, effective_R, rings + 1),
                [R],
            ])
        else:
            r_arr = np.linspace(0.0, R, rings + 1)
        n_rings = len(r_arr) - 1   # face rings 수

        theta = np.linspace(0.0, 2.0 * np.pi, seg, endpoint=False)
        Rm, Tm = np.meshgrid(r_arr, theta, indexing="ij")
        xs_all = (Rm * np.cos(Tm)).ravel()
        ys_all = (Rm * np.sin(Tm)).ravel()
        z_raw_all = rbf(np.column_stack([xs_all, ys_all]))

        # Z 범위 — 공통 모드면 display.z_range (높이·색 모두 공통), 아니면 개별.
        # 공통 모드 = 모든 wafer 가 동일 vmin~vmax 로 매핑 → 내부 변동이 공통 범위
        # 대비 작으면 dome 이 상대적으로 납작하게 보이는 것은 정상 (physical truth).
        if self._display.z_range is not None:
            vmin_c, vmax_c = self._display.z_range
        else:
            finite = z_raw_all[np.isfinite(z_raw_all)]
            if finite.size == 0:
                return
            vmin_c = float(finite.min())
            vmax_c = float(finite.max())
        z_range_c = vmax_c - vmin_c if vmax_c > vmin_c else 1.0
        vmin_h = vmin_c
        z_range_h = z_range_c
        vmin, vmax, z_range = vmin_c, vmax_c, z_range_c

        # Z 과장 배율
        z_exag = chart3d.get("z_exaggeration", None)
        target_height = WAFER_RADIUS_MM * 0.4
        factor = (target_height / z_range_h) * (float(z_exag) if z_exag is not None else 1.0)

        cmap = resolve_colormap(common.get("colormap", "Turbo"))

        gview = self._gl_3d

        # 바닥 grid — 재사용.
        # size 는 spacing 의 **짝수 배수** 여야 원점(0,0) 대칭 + 0 통과 선 생성.
        # pyqtgraph GLGridItem 은 np.arange(-x/2, x/2, xs) 로 선을 찍음.
        # 320/40 → [-160, -120, -80, -40, 0, 40, 80, 120, 160] 대칭 + 0 통과.
        # 웨이퍼 R=150 대비 10mm 여유.
        if chart3d.get("show_grid", True):
            if self._gl_grid is None:
                # glOptions='opaque' → depth write on → surface 가 grid 위 덮을 때
                # grid 가 숨음. default 'translucent' 는 depth write off 라서 항상 뚫림.
                self._gl_grid = gl.GLGridItem(glOptions='opaque')
                self._gl_grid.setSize(x=320, y=320)
                self._gl_grid.setSpacing(x=40, y=40)
                self._gl_grid.setColor((210, 210, 210, 255))
                # Surface 의 z_disp = (z_raw - vmin_h) * factor 라 Min 지점이 z=0.
                # grid 도 z=0 평면이라 정확히 겹쳐 z-fighting 으로 grid 가 뚫려 보임.
                # grid 를 2mm 아래로 translate → surface 최저점이 grid 위에 확실히 위치.
                self._gl_grid.translate(0, 0, -2.0)
                gview.addItem(self._gl_grid)
            self._gl_grid.setVisible(True)
        elif self._gl_grid is not None:
            self._gl_grid.setVisible(False)

        # radial mode 는 notch 를 mesh 에 반영하지 않음 (반경 분해능 부족으로 계단 모양).
        # notch 는 boundary line 에만 표시 (아래 _boundary_xy 참고).
        # per-angle effective r = R (notch 없음) - edge_cut
        eff_r_seg = np.full(seg, max(R - (edge_cut_mm if apply_cut else 0.0), 1.0), dtype=float)

        # Per-vertex cut mask — edge_cut 만 반영
        vert_theta_idx = np.arange(xs_all.size) % seg
        r_flat = np.sqrt(xs_all ** 2 + ys_all ** 2)
        cut_mask_all = r_flat > eff_r_seg[vert_theta_idx] + 1e-6

        # Radial surface mesh — pre-evaluated (xs_all, ys_all, z_raw_all) 재사용
        smooth = bool(chart3d.get("smooth", True))
        v_s, f_s, c_s = _build_radial_surface_mesh(
            xs_all, ys_all, z_raw_all, n_rings, seg,
            vmin_h, factor, vmin_c, z_range_c, cmap,
            cut_mask=cut_mask_all if cut_mask_all.any() else None,
        )
        # shader="shaded" — lighting 적용으로 smooth=True/False 차이 시각화
        # (shader 없으면 vertex color 그대로 → smooth 차이 안 보임)
        if self._gl_surface is None:
            self._gl_surface = gl.GLMeshItem(
                vertexes=v_s, faces=f_s, vertexColors=c_s,
                smooth=smooth, shader="shaded",
                drawEdges=False, glOptions="opaque",
            )
            gview.addItem(self._gl_surface)
        else:
            self._gl_surface.setMeshData(
                vertexes=v_s, faces=f_s, vertexColors=c_s, smooth=smooth,
            )
        self._gl_surface.setVisible(True)

        # Smooth cylinder wall — 각 angle 별 eff_r 에 배치 → notch 영역 안쪽으로 dip.
        wall_xs = eff_r_seg * np.cos(theta)
        wall_ys = eff_r_seg * np.sin(theta)
        wall_z_raw = rbf(np.column_stack([wall_xs, wall_ys]))
        v_w, f_w, c_w = _build_smooth_cylinder_wall(
            wall_xs, wall_ys, wall_z_raw, seg,
            vmin_h, factor, vmin_c, z_range_c, cmap,
        )
        if self._gl_wall is None:
            self._gl_wall = gl.GLMeshItem(
                vertexes=v_w, faces=f_w, vertexColors=c_w,
                smooth=True, shader="shaded",
                drawEdges=False, glOptions="opaque",
            )
            gview.addItem(self._gl_wall)
        else:
            self._gl_wall.setMeshData(
                vertexes=v_w, faces=f_w, vertexColors=c_w, smooth=True,
            )
        self._gl_wall.setVisible(True)

        # boundary line (재사용)
        if common.get("show_circle", True):
            bx, by = _boundary_xy(
                common.get("show_notch", True),
                float(common.get("notch_depth_mm", _NOTCH_DEFAULT_DEPTH_MM)),
                R=float(common.get("boundary_r_mm", WAFER_RADIUS_MM)),
            )
            circ = np.column_stack([bx, by, np.zeros_like(bx)])
            if self._gl_boundary is None:
                self._gl_boundary = gl.GLLinePlotItem(
                    pos=circ, color=(0, 0, 0, 1), width=2,
                    antialias=True, glOptions="opaque",
                )
                gview.addItem(self._gl_boundary)
            else:
                self._gl_boundary.setData(pos=circ)
            self._gl_boundary.setVisible(True)
        elif self._gl_boundary is not None:
            self._gl_boundary.setVisible(False)

        self._update_colorbar(common, None, vmin=vmin, vmax=vmax)
        self._update_radial_graph(common)

    def _update_radial_graph(self, common: dict) -> None:
        """1D Radial Graph 데이터 갱신 — (r, v) 산점도 + 스플라인 실선.

        visibility 와 size 는 `_apply_chart_size` 에서 통합 관리 (이 메서드는 데이터만).
        X 축: 0~150mm 고정. Y 축: 2D/3D 와 독립 — `display.z_range_1d` (공통 모드)
        또는 실측 min/max (개별 모드). Z-Margin 은 main_window 에서 z_range_1d 에
        이미 적용된 상태라 그대로 사용.
        """
        if not bool(common.get("show_1d_radial", False)):
            return

        self._radial_graph.clear()
        x = np.asarray(self._x_in, dtype=float)
        y = np.asarray(self._y_in, dtype=float)
        v = np.asarray(self._v_in, dtype=float)
        m = ~np.isnan(v) & ~np.isnan(x) & ~np.isnan(y)
        if m.sum() < 2:
            return
        xm, ym, vm = x[m], y[m], v[m]
        r = np.sqrt(xm * xm + ym * ym)

        # Y range: display.z_range_1d 있으면 공통, 없으면 개별 실측 min/max
        if self._display.z_range_1d is not None:
            y_min, y_max = self._display.z_range_1d
        else:
            y_min = float(vm.min())
            y_max = float(vm.max())
            if y_max <= y_min:
                y_max = y_min + 1e-9
        # 1D 전용 추가 여백 — 산점도가 경계에 붙지 않도록 양쪽 8% 확장.
        # z_range_1d 자체 (개별/공통/Z-Margin 공유 값) 는 유지, 뷰만 시각적으로 확장.
        self._radial_graph.setYRange(y_min, y_max, padding=0.08)
        self._radial_graph.setXRange(-10, 160, padding=0)

        # Y 축 주눈금 — min / midpoint / max 3개 고정. 개별/공통 모드 모두 동일 로직
        # (y_min, y_max 가 이미 모드에 맞게 계산됨).
        # 소수점 자릿수는 colorbar 와 동일 기준 (`_dynamic_decimals`): 5 ticks 기준
        # tick_step 의 log10 + 절대 cap 4. (1D 축은 3 ticks 표시지만 colorbar 와
        # 자릿수 일관 유지하기 위해 colorbar 의 z_range 와 5 ticks 가정으로 계산.)
        cbar_range = self._display.z_range if self._display.z_range is not None else (y_min, y_max)
        decimals = _dynamic_decimals(cbar_range[0], cbar_range[1], 5)
        fmt = f"{{:.{decimals}f}}"
        mid = (y_min + y_max) / 2.0
        y_ticks_maj = [
            (float(y_min), fmt.format(y_min)),
            (float(mid),   fmt.format(mid)),
            (float(y_max), fmt.format(y_max)),
        ]
        self._radial_graph.getAxis("left").setTicks([y_ticks_maj, []])

        # 축 tick 폰트 — 12px 하드코딩 (font_scale 무관, 축 폭 고정이라 큰 폰트 시 잘림 방지)
        from PySide6.QtGui import QFont as _QFont
        _fn = _QFont("Arial")
        _fn.setPixelSize(12)
        for _ax_name in ("left", "bottom"):
            self._radial_graph.getAxis(_ax_name).setStyle(tickFont=_fn)

        # 스플라인 실선 — RadialInterp 로 (r, v) 1D spline. 정석 방식대로 **측정된
        # r 범위 (r_min ~ r_max) 안에서만** 곡선 그림. r<r_min / r>r_max 는 공백
        # (데이터 없는 구간을 flat 또는 외삽으로 표시하지 않음 = 과학 시각화 관례).
        from core.interp import RadialInterp
        try:
            ri = RadialInterp(
                xm, ym, vm,
                method=str(common.get("radial_method", "Univariate Spline")),
                smoothing_factor=float(common.get("radial_smoothing_factor", 5.0)),
                savgol_window=int(common.get("savgol_window", 11)),
                savgol_polyorder=int(common.get("savgol_polyorder", 3)),
                lowess_frac=float(common.get("lowess_frac", 0.3)),
                polyfit_degree=int(common.get("polyfit_degree", 3)),
                bin_size_mm=float(common.get("radial_bin_size_mm", 0)),
            )
            r_min = float(r.min())
            r_max = float(r.max())
            r_q = np.linspace(r_min, r_max, 200)
            v_q = ri(np.column_stack([r_q, np.zeros_like(r_q)]))
            # spline 색 — 진한 회색 (#777). 연한 회색 테두리/표 border (#888888)
            # 보다 확실히 진해 시각 구분. scatter (검정) 보다는 약해 scatter 가 주인공.
            self._radial_graph.plot(r_q, v_q, pen=pg.mkPen("#777777", width=2))
        except Exception:
            pass
        # 실측 산점도
        self._radial_graph.plot(
            r, vm, pen=None,
            symbol="o", symbolSize=4,
            symbolBrush="#202020", symbolPen=pg.mkPen("#202020"),
        )

    def _update_colorbar(self, common: dict, values=None, vmin=None, vmax=None) -> None:
        """show_scale_bar 옵션 반영 + 컬러맵/범위로 스케일바 갱신."""
        if not bool(common.get("show_scale_bar", True)):
            self._colorbar.setVisible(False)
            return
        self._colorbar.setVisible(True)
        if vmin is None or vmax is None:
            if values is None or values.size == 0:
                return
            valid = values[~np.isnan(values)]
            if valid.size == 0:
                return
            vmin = float(valid.min())
            vmax = float(valid.max())
        cmap = resolve_colormap(common.get("colormap", "Turbo"))
        self._colorbar.update_bar(cmap, vmin, vmax)

    def _update_table(self, v: np.ndarray, settings: dict) -> None:
        """Summary 위젯에 metrics 위임 (사용자 정책 2026-04-30, table style 추상화).

        모든 style 이 동일 입력 (metrics dict, decimals, percent_suffix) 받음.
        update 후 cell 전체 크기 재계산 (style 따라 높이 약간 다를 수 있어 대응).
        """
        common = settings.get("chart_common", {})
        tbl_cfg = settings.get("table", {})
        decimals = int(common.get("decimals", tbl_cfg.get("decimals", 2)))
        percent_suffix = bool(tbl_cfg.get("nu_percent_suffix", True))
        m = summary_metrics(v)
        self._summary.update_metrics(m, decimals, percent_suffix)
        # 테이블 높이가 바뀌었으니 cell 전체 크기 재계산 (chart_area 는 그대로, 전체 높이만)
        self._apply_chart_size(common)

    # ── 우클릭 메뉴 ────────────────────────────────
    def _show_plot_menu(self, pos: QPoint) -> None:
        chart = self._chart_widget
        if chart is None:
            return
        menu = QMenu(self)
        a_reset = menu.addAction("Reset")
        a_graph = menu.addAction("Copy Graph")
        a_data = menu.addAction("Copy Data")
        chosen = menu.exec(chart.mapToGlobal(pos))
        if chosen is a_reset:
            sall = settings_io.load_settings()
            scom = sall.get("chart_common", {})
            s3d = sall.get("chart_3d", {})
            dist = float(scom.get("camera_distance", 620))
            elev_3d = float(s3d.get("elevation", 28))
            azim_3d = float(s3d.get("azimuth", -135))
            from pyqtgraph import Vector
            if chart is self._gl_2d:
                chart.setCameraPosition(
                    pos=Vector(0, 0, 0),
                    distance=dist, elevation=90, azimuth=-90,
                )
            else:  # _gl_3d
                chart.setCameraPosition(
                    pos=Vector(0, 0, 0),
                    distance=dist, elevation=elev_3d, azimuth=azim_3d,
                )
            chart.opts["fov"] = 45
            chart.update()
            # Reset 시 applied 값도 동기 — 이후 render 에서 또 리셋 안 걸리게.
            self._applied_cam_dist = dist
            if chart is self._gl_3d:
                self._applied_elev_3d = elev_3d
                self._applied_azim_3d = azim_3d
        elif chosen is a_graph:
            self._copy_graph()
        elif chosen is a_data:
            self._copy_data()

    def _show_table_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        a_table = menu.addAction("Copy Table")
        chosen = menu.exec(self._table.mapToGlobal(pos))
        if chosen is a_table:
            self._copy_table()

    # ── Copy ──────────────────────────────────────
    def _copy_graph(self) -> None:
        """_capture_container 합성 이미지를 클립보드로.

        - non-GL 부분 (QFrame border, 제목, 컬러바, 1D 라디얼, Summary 표):
          `_capture_container.grab()` 으로 한 번에 캡처.
        - GL 부분 (`_chart_widget` = _gl_2d 또는 _gl_3d):
          `_capture_gl_offscreen(scale=2)` 로 MSAA 4x + 2x supersampling 렌더
          → widget 크기로 downscale → QPainter 로 non-GL 픽맵 위에 덮어씌움.

        장점:
          - 화면 표시 상태 무관 (스크롤에 가려지거나 다른 창이 덮어도 정상)
          - MSAA 4x 강제 (화면 widget 은 samples=0 인 환경도 FBO 는 4 확보)
          - 2x supersampling 으로 edge 품질 개선

        실패 시 기존 화면 캡처 경로 (grabWindow + crop) 로 폴백.
        """
        cap = self._capture_container
        dpr = float(cap.devicePixelRatioF())

        # 1. non-GL 부분 grab — GL widget 영역은 검정/최근 framebuffer 로 남지만
        #    아래에서 FBO 이미지로 덮어씀. title/colorbar/badge 도 여기서 찍힘 (z-order)
        #    이지만 drawImage 로 GL 영역 덮을 때 overlap 된 overlay 가 함께 지워지므로
        #    마지막에 재그림.
        pm = cap.grab()

        # 2. GL widget FBO offscreen 렌더 (MSAA 4x, scale=1)
        chart = self._chart_widget
        gl_img = _capture_gl_offscreen(chart, scale=1) if chart is not None else QImage()

        if gl_img.isNull():
            # FBO 실패 — 기존 화면 캡처 방식 폴백
            screen = self.screen() or QApplication.primaryScreen()
            if screen is None:
                QApplication.clipboard().setPixmap(pm)
                return
            full_pm = screen.grabWindow(0)
            dpr2 = full_pm.devicePixelRatio()
            tl_global = cap.mapToGlobal(QPoint(0, 0))
            screen_tl = screen.geometry().topLeft()
            x = int((tl_global.x() - screen_tl.x()) * dpr2)
            y = int((tl_global.y() - screen_tl.y()) * dpr2)
            w = int(cap.width() * dpr2)
            h = int(cap.height() * dpr2)
            cropped = full_pm.copy(x, y, w, h)
            cropped.setDevicePixelRatio(dpr2)
            QApplication.clipboard().setPixmap(cropped)
            return

        # 3. GL 이미지를 chart 위치에 덮음 (chart_area 크기 = title 영역 포함 overlap)
        gl_pos = chart.mapTo(cap, QPoint(0, 0))
        painter = QPainter(pm)
        painter.drawImage(
            QPoint(int(gl_pos.x() * dpr), int(gl_pos.y() * dpr)),
            gl_img,
        )

        # 4. Overlay 복원 — GL 이미지에 덮여 사라진 title/colorbar/badge 를 다시 그림
        #    (z-order 의 "GL 위에 Qt widget overlay" 순서 보존)
        overlays: list[QWidget] = []
        if getattr(self, "_title", None) is not None:
            overlays.append(self._title)
        if getattr(self, "_colorbar", None) is not None:
            overlays.append(self._colorbar)
        for badge_attr in ("_badge_2d", "_badge_3d"):
            b = getattr(self, badge_attr, None)
            if b is not None and b.isVisible():
                overlays.append(b)

        for w in overlays:
            if not w.isVisible():
                continue
            pos = w.mapTo(cap, QPoint(0, 0))
            w_pm = w.grab()
            painter.drawPixmap(
                QPoint(int(pos.x() * dpr), int(pos.y() * dpr)),
                w_pm,
            )

        painter.end()
        QApplication.clipboard().setPixmap(pm)

    def _copy_data(self) -> None:
        lines = [f"X\tY\t{self._value_name}"]
        for x, y, v in zip(self._x_in, self._y_in, self._v_in):
            lines.append(f"{x}\t{y}\t{v}")
        QApplication.clipboard().setText("\n".join(lines))

    def _copy_table(self) -> None:
        rows: list[list[str]] = []
        for r in range(self._table.rowCount()):
            row_cells: list[str] = []
            for c in range(self._table.columnCount()):
                it = self._table.item(r, c)
                row_cells.append(it.text() if it else "")
            rows.append(row_cells)
        tsv = "\n".join("\t".join(r) for r in rows)
        html_rows = "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
        )
        html = (
            "<table border='1' cellpadding='4' cellspacing='0'>"
            f"<tbody>{html_rows}</tbody></table>"
        )
        mime = QMimeData()
        mime.setText(tsv)
        mime.setHtml(html)
        QApplication.clipboard().setMimeData(mime)
