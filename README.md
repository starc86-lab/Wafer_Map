# Wafer Map

PySide6 + pyqtgraph 기반 반도체 웨이퍼 측정 데이터 시각화 데스크톱 앱.

> 회사 사내 사용 (반도체 계측 엔지니어). 한국어 commit / 주석 / 문서.

## 핵심 워크플로

1. 계측 장비 / Excel 에서 long-form CSV 를 **Ctrl+C**
2. 앱의 **Input A** (또는 B) 에 **Ctrl+V**
3. **▶ Run** → 결과 패널에 cell (차트 + 1D radial + Summary 표) 가로 나열
4. cell 우클릭 → **Copy Image** → PPT / Excel 에 **Ctrl+V** 로 사진 paste

> 입력이 클립보드면 **출력도 클립보드**. 파일 I/O 최소화.

## 주요 기능

- **단일 / DELTA / 다중 wafer** 시각화 (WAFERID 매칭, A−B 부호 고정)
- **2D heatmap + 3D radial mesh** — `QStackedLayout` 으로 0ms 토글, MSAA 4x
- **Summary 표 11종 카탈로그** (`widgets/summary/`) — Settings 에서 즉시 swap
- **좌표 프리셋 라이브러리** — RECIPE 기반 자동 매칭 + 수동 추가 (4 포맷 자동 감지)
- **Copy Image** — Cell 전체 합성 이미지. PPT / Excel 둘 다 지원 (RGB32 + PNG/DIB 듀얼 MIME)
- **Copy Table / Copy Data** — TSV+HTML 듀얼 / TSV
- **ER Map** (Etch Rate) — DELTA cell 에 Time 입력 → `ΔTHK / Time` 자동 변환
- **r-symmetry mode / Δ-Interp mode** — radial 강제 / DELTA 보간 fallback
- **PARA 조합** — sum / concat recursive (예 `T1 + T2 ∪ T3_A`)
- **UI 해상도** — auto / FHD / QHD / UHD (`QT_SCALE_FACTOR`)

## 기술 스택

- Python 3.14
- PySide6 (Qt 6)
- pyqtgraph (2D heatmap + 3D `pyqtgraph.opengl`)
- numpy / scipy (RBF / SVD radial 자동 감지)
- pandas (long-form CSV)
- 배포: PyInstaller `--onedir` 무설치 포터블 zip

## 실행 (개발)

```bash
python -m venv venv
venv\Scripts\activate     # Windows
pip install -r requirements.txt
python app.py
```

`python app.py --selftest` — 1.5초 후 자동 종료 (import / QSS 검증용).

## 코드 구조

```
app.py              ─ 엔트리포인트 (UI scale + warmup)
main.py             ─ long-form CSV 파서 (ParseResult / WaferData / parse_wafer_csv)
core/
  ├── settings.py / themes.py / stylesheet.py / runtime.py
  ├── auto_select.py / coords.py / coord_library.py
  ├── interp.py             ─ RBF + Radial spline + SVD 자동 감지
  ├── delta.py              ─ DELTA 매칭 (union_match + NaN 룰)
  ├── combine.py            ─ PARA 조합 (sum / concat recursive)
  ├── integrity.py          ─ 입력 무결성 6종 검사
  ├── recipe_util.py        ─ RECIPE PRE/POST 호환 판정
  └── ...
widgets/
  ├── main_window.py        ─ 3-패널 메인 윈도우
  ├── wafer_cell.py         ─ Cell 렌더링 (2D/3D + 1D radial + 표)
  ├── settings_dialog.py    ─ non-modal Save/Close
  ├── summary/              ─ 11종 Table Style 카탈로그
  ├── reason_bar.py         ─ 입력 검증 단일 채널
  ├── paste_area.py / result_panel.py / preset_*.py / ...
docs/
  ├── policies/             ─ 3대 정책 (input_parsing / coords / reason_bar)
  └── rendering_optimizations.md ─ 최적화 이력 + 실패 / 롤백 사례
tests/                      ─ pytest 형식 + 단위 회귀 (auto_select / clipboard alpha 등)
```

## 정책 / 아키텍처 문서

본 repo 의 **single source of truth** 는 [`CLAUDE.md`](CLAUDE.md) (~700 라인).
프로젝트 철학 / 정책 / 디자인 결정 / tech debt / 묵시적 invariant 모두 정리됨.

- [`USER_GUIDE.md`](USER_GUIDE.md) — 사용자 워크플로
- [`CHANGELOG.md`](CHANGELOG.md) — 버전 이력 (SemVer)
- [`docs/policies/`](docs/policies/) — 입력 / 좌표 / ReasonBar 3대 정책
- [`docs/rendering_optimizations.md`](docs/rendering_optimizations.md) — 렌더 최적화 이력 (실패 사례 포함)
- [`TODO.md`](TODO.md) — 알려진 한계 / 향후 작업

## 라이선스 / 사용

회사 내부 사용 목적. 외부 배포 / 재사용 시 작성자 (Jihwan Park, SK hynix) 와 협의 필요.

## 개발

[`CLAUDE.md`](CLAUDE.md) 의 "개발자 정보" 섹션 참고. 한국어 commit / 협의 후 변경 / 정책 카탈로그 동반 갱신 등 워크플로 명시.
