"""
PARA 조합 다이얼로그 — 두 PARA + 두 좌표 페어를 합쳐 시각화.

use case: T1 (inner 0~145mm) + T1_A (edge 145~150mm) → 풀 wafer 한 장.

DELTA 모드: A∩B 의 PARA / 좌표 (이름 기준 교집합) 만 콤보에 노출.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from core.auto_select import _is_coord_name, select_xy_pairs
from core.settings import load_settings
from main import ParseResult


# ── 후보 추출 헬퍼 ─────────────────────────────────────────────
def _gather_paras(result: ParseResult | None) -> dict[str, int]:
    """ParseResult 에서 plain PARA → n. 입력 순서 보존.

    합성 친화 키 (` + ` 또는 ` ∪ ` 포함) 는 모두 제외 — 합성 항목은 별도로
    `combined_state` 에서 가져와 콤보에 추가 (사용자 정책 2026-04-29). 좌표 합성 키
    (`X ∪ X_A`, sum 의 X 는 plain 과 동일하므로 통과) 도 동일 정책.
    """
    if result is None:
        return {}
    out: dict[str, int] = {}
    for w in result.wafers.values():
        for name, rec in w.parameters.items():
            if name in out:
                continue
            if " + " in name or " ∪ " in name:
                continue
            out[name] = rec.n
    return out


def _value_paras(all_ns: dict[str, int]) -> list[str]:
    """좌표 PARA 제외 + n>=2 만 (단일 PARA 콤보 정책과 동일).

    n=0 (빈 측정), n=1 (단일값 _AVG 류) 은 맵 시각화 불가라 제외.
    """
    return [name for name, n in all_ns.items()
            if not _is_coord_name(name) and n >= 2]


def _coord_pairs(all_ns: dict[str, int]) -> list[tuple[str, str, int]]:
    """X/Y suffix 매칭 페어 — (x_name, y_name, pair_n) 리스트."""
    auto = load_settings().get("auto_select", {})
    xpat = auto.get("x_patterns", ["X", "X*"])
    ypat = auto.get("y_patterns", ["Y", "Y*"])
    _, _, x_ord, y_ord = select_xy_pairs(all_ns, xpat, ypat)
    pairs: list[tuple[str, str, int]] = []
    for x, y in zip(x_ord, y_ord):
        n = min(all_ns.get(x, 0), all_ns.get(y, 0))
        pairs.append((x, y, n))
    return pairs


def _intersect_dict(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    """이름 기준 교집합 — A 의 순서 유지, n 은 A 값."""
    return {k: v for k, v in a.items() if k in b}


def _wrap(name: str) -> str:
    """미리보기용 — 합성 operand 자동 괄호. main_window._wrap_if_composite 와 동일 규칙."""
    return f"({name})" if (" + " in name or " ∪ " in name) else name


# ── 다이얼로그 ────────────────────────────────────────────────
class ParaCombineDialog(QDialog):
    """PARA 조합 다이얼로그.

    사용자 흐름:
      1. PARA 1 (자동 선택) + 좌표 1 (suffix 매칭 자동 선택)
      2. PARA 2 (사용자 선택) + 좌표 2 (suffix 매칭 자동)
      3. 합성 미리보기 한 줄 표시
      4. Apply (둘 다 선택 시 활성)
    """

    def __init__(
        self,
        result_a: ParseResult | None,
        result_b: ParseResult | None,
        parent: QWidget | None = None,
        combined_state=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Para 조합")
        self.setModal(True)
        self.resize(540, 280)

        # 미리보기 flatten 용 — main_window 의 CombinedState. dialog 는 외부 모듈
        # import 안 하고 duck typing (items 속성 + mode/v_key/operands 만 사용).
        self._combined_state = combined_state

        # 후보 추출 — DELTA 모드면 A∩B 교집합 (이름 기준).
        # _gather_paras 가 ` ∪ ` 포함 키만 제외 (concat 합성 결과). sum 합성 결과
        # (` + ` 패턴) 는 통과 → sum recursive 가능.
        # 사용된 PARA 도 그대로 유지 (T1+T1_A 만들고 T1+T1_B 도 가능).
        a_paras = _gather_paras(result_a)
        b_paras = _gather_paras(result_b)
        if a_paras and b_paras:
            paras = _intersect_dict(a_paras, b_paras)
        elif a_paras:
            paras = a_paras
        else:
            paras = b_paras

        # 좌표 페어 (DELTA 면 교집합 — pair 의 (x,y) 이름 같은 것만)
        a_coord_pairs = _coord_pairs(a_paras) if a_paras else []
        b_coord_pairs = _coord_pairs(b_paras) if b_paras else []
        if a_coord_pairs and b_coord_pairs:
            b_set = {(x, y) for x, y, _ in b_coord_pairs}
            self._coord_pairs = [t for t in a_coord_pairs if (t[0], t[1]) in b_set]
        else:
            self._coord_pairs = a_coord_pairs or b_coord_pairs

        self._value_paras = _value_paras(paras)
        self._para_n = paras  # PARA → n 조회용

        # 합성 항목 — combined_state 에서 직접 빌드. wafer.parameters 에 Apply 시점에
        # 등록된 친화 키들이 있어 거기서 n 조회 가능 (없으면 0).
        # composites_v: list[(v_key, n)] / composites_coord: list[(x_key, y_key, n)]
        self._composites_v: list[tuple[str, int]] = []
        self._composites_coord: list[tuple[str, str, int]] = []
        # composite v_key 별 (x_key, y_key) 매핑 — auto-pick 용
        self._composite_v_to_coord: dict[str, tuple[str, str]] = {}
        if combined_state is not None:
            # n 조회 — 첫 wafer 의 wafer.parameters[v_key].n (Apply inject 됨)
            first_w = None
            for r in (result_a, result_b):
                if r and r.wafers:
                    first_w = next(iter(r.wafers.values()))
                    break

            def _n_of(name: str) -> int:
                if first_w is None or name not in first_w.parameters:
                    return 0
                return first_w.parameters[name].n

            for it in getattr(combined_state, "items", []):
                v_n = _n_of(it.v_key)
                self._composites_v.append((it.v_key, v_n))
                self._composite_v_to_coord[it.v_key] = (it.x_key, it.y_key)
                # sum 좌표는 plain (이미 _coord_pairs 에 있음) — concat 만 추가
                if it.mode == "concat":
                    self._composites_coord.append(
                        (it.x_key, it.y_key, _n_of(it.x_key)),
                    )

        # ── UI ────────────────────────────────────────
        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        # PARA 1 + 좌표 1
        sec1 = QGroupBox("PARA 1")
        f1 = QFormLayout(sec1)
        self.cb_p1 = QComboBox()
        self.cb_c1 = QComboBox()
        f1.addRow("PARA:", self.cb_p1)
        f1.addRow("좌표:", self.cb_c1)
        lay.addWidget(sec1)

        # PARA 2 + 좌표 2
        sec2 = QGroupBox("PARA 2")
        f2 = QFormLayout(sec2)
        self.cb_p2 = QComboBox()
        self.cb_c2 = QComboBox()
        f2.addRow("PARA:", self.cb_p2)
        f2.addRow("좌표:", self.cb_c2)
        lay.addWidget(sec2)

        # 합성 미리보기
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        lay.addWidget(line)

        prev_box = QHBoxLayout()
        prev_box.addWidget(QLabel("조합:"))
        self._lbl_preview = QLabel("—")
        self._lbl_preview.setStyleSheet("font-weight: bold; color: #1a4d6e;")
        prev_box.addWidget(self._lbl_preview)
        prev_box.addStretch(1)
        lay.addLayout(prev_box)

        # Apply / Close
        bb = QDialogButtonBox()
        self.btn_apply = bb.addButton("Apply", QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_close = bb.addButton("Close", QDialogButtonBox.ButtonRole.RejectRole)
        self.btn_apply.clicked.connect(self.accept)
        self.btn_close.clicked.connect(self.reject)
        for b in (self.btn_apply, self.btn_close):
            b.setDefault(False)
            b.setAutoDefault(False)
        lay.addWidget(bb)

        # 콤보 채우기
        self._fill_para_combos()
        self._fill_coord_combos()

        # PARA 변경 시 좌표 자동 매칭 + preview 갱신
        self.cb_p1.currentIndexChanged.connect(self._on_p1_changed)
        self.cb_p2.currentIndexChanged.connect(self._on_p2_changed)
        self.cb_c1.currentIndexChanged.connect(self._refresh_preview)
        self.cb_c2.currentIndexChanged.connect(self._refresh_preview)

        # 초기 자동 선택 — PARA 1 은 첫 후보, PARA 2 는 미선택
        self._on_p1_changed()  # 좌표 1 자동 매칭
        self._refresh_preview()

        # 다이얼로그를 부모 (메인 윈도우) 의 중앙에 배치
        if parent is not None:
            geo = self.frameGeometry()
            geo.moveCenter(parent.frameGeometry().center())
            self.move(geo.topLeft())

    # ── 콤보 채우기 ───────────────────────────────────
    def _fill_para_combos(self) -> None:
        for cb in (self.cb_p1, self.cb_p2):
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("— 선택 —", None)
            for name in self._value_paras:
                n = self._para_n.get(name, 0)
                cb.addItem(f"{name}  [{n} pt]", name)
            # 합성 항목 — 🔗 prefix 로 시각 구분
            for v_key, n in self._composites_v:
                cb.addItem(f"🔗 {v_key}  [{n} pt]", v_key)
            cb.blockSignals(False)
        # PARA 1 자동 선택 (첫 후보)
        if self._value_paras or self._composites_v:
            self.cb_p1.setCurrentIndex(1)  # 0 은 placeholder

    def _fill_coord_combos(self) -> None:
        for cb in (self.cb_c1, self.cb_c2):
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("— 선택 —", None)
            for x, y, n in self._coord_pairs:
                cb.addItem(f"{x} / {y}  [{n} pt]", (x, y))
            # composite 좌표 (concat 결과만 — sum 좌표는 plain 과 동일)
            for x, y, n in self._composites_coord:
                cb.addItem(f"🔗 {x} / {y}  [{n} pt]", (x, y))
            cb.blockSignals(False)

    # ── 좌표 자동 매칭 (suffix + n 일치) ─────────────────
    def _auto_pick_coord(self, para_name: str | None) -> tuple[str, str] | None:
        if not para_name:
            return None
        # composite operand → state 의 매핑으로 즉시 결정 (suffix 매칭 X)
        if para_name in self._composite_v_to_coord:
            return self._composite_v_to_coord[para_name]
        para_n = self._para_n.get(para_name)
        # 1순위: PARA 의 suffix 와 같은 X/Y 페어 (예: T1_A → X_A/Y_A)
        para_suffix = self._suffix_of(para_name)
        # n 일치 우선
        candidates_n_match = [(x, y) for x, y, n in self._coord_pairs if n == para_n]
        if para_suffix:
            for x, y in candidates_n_match:
                if self._suffix_of(x) == para_suffix:
                    return (x, y)
        # 2순위: n 만 일치
        if candidates_n_match:
            return candidates_n_match[0]
        # 3순위: 첫 후보
        if self._coord_pairs:
            x, y, _ = self._coord_pairs[0]
            return (x, y)
        return None

    @staticmethod
    def _suffix_of(name: str) -> str:
        """이름의 suffix (마지막 `_xx` 토큰) — 1~2자 알파벳만 인정. 없으면 빈 string."""
        if "_" not in name:
            return ""
        last = name.rsplit("_", 1)[-1]
        return last if 1 <= len(last) <= 2 and last.isalpha() else ""

    def _select_coord_in_combo(self, cb: QComboBox, target: tuple[str, str] | None) -> None:
        if target is None:
            cb.setCurrentIndex(0)
            return
        for i in range(cb.count()):
            if cb.itemData(i) == target:
                cb.setCurrentIndex(i)
                return
        cb.setCurrentIndex(0)

    # ── 콤보 변경 핸들러 ───────────────────────────────
    def _on_p1_changed(self) -> None:
        para = self.cb_p1.currentData()
        target = self._auto_pick_coord(para)
        self.cb_c1.blockSignals(True)
        self._select_coord_in_combo(self.cb_c1, target)
        self.cb_c1.blockSignals(False)
        self._refresh_preview()

    def _on_p2_changed(self) -> None:
        para = self.cb_p2.currentData()
        target = self._auto_pick_coord(para)
        self.cb_c2.blockSignals(True)
        self._select_coord_in_combo(self.cb_c2, target)
        self.cb_c2.blockSignals(False)
        self._refresh_preview()

    # ── 미리보기 + Apply 활성 ──────────────────────────
    def _refresh_preview(self) -> None:
        r = self._extract()
        if r is None:
            self._lbl_preview.setText("—")
            self.btn_apply.setEnabled(False)
            return
        p1, p2 = r["value"]
        x1, y1 = r["coord1"]
        x2, y2 = r["coord2"]
        if r["mode"] == "sum":
            # sum recursive flatten 미리 반영 + 합성 operand 자동 괄호 (사용자 정책 2026-04-29)
            ops = self._flatten_sum(p1) + self._flatten_sum(p2)
            v_text = " + ".join(_wrap(op) for op in ops)
            self._lbl_preview.setText(f"{v_text}    {x1}/{y1}")
        else:
            v_text = f"{_wrap(p1)} ∪ {_wrap(p2)}"
            x_text = f"{_wrap(x1)} ∪ {_wrap(x2)}"
            y_text = f"{_wrap(y1)} ∪ {_wrap(y2)}"
            self._lbl_preview.setText(f"{v_text}    {x_text}/{y_text}")
        self.btn_apply.setEnabled(True)

    def _flatten_sum(self, name: str) -> list[str]:
        """operand 가 기존 sum CombinedItem 의 v_key 면 그 operands 로 펼침."""
        st = self._combined_state
        if st is None:
            return [name]
        for it in getattr(st, "items", []):
            if getattr(it, "mode", None) == "sum" and getattr(it, "v_key", None) == name:
                return list(it.operands)
        return [name]

    def _extract(self) -> dict | None:
        """콤보 4개 모두 선택됐고 PARA 가 서로 다르면 dict 반환, 아니면 None.

        mode 자동 판정: 두 좌표 페어가 같으면 "sum", 다르면 "concat".
        """
        p1 = self.cb_p1.currentData()
        p2 = self.cb_p2.currentData()
        c1 = self.cb_c1.currentData()
        c2 = self.cb_c2.currentData()
        if not (p1 and p2 and c1 and c2):
            return None
        if p1 == p2:
            return None  # 같은 PARA 두 번 의미 없음
        mode = "sum" if c1 == c2 else "concat"
        return {"value": (p1, p2), "coord1": c1, "coord2": c2, "mode": mode}

    # ── 외부 API ────────────────────────────────────
    def result(self) -> dict | None:
        return self._extract()
