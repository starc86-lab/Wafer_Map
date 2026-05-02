# Wafer Map

PySide6 + pyqtgraph 기반 반도체 웨이퍼 측정 데이터 시각화 데스크톱 앱.

> 회사 사내 사용 (반도체 계측 엔지니어). 한국어 commit / 주석 / 문서.

## 핵심 워크플로

1. **MES-DCOL Data** 를 **Ctrl+C** (계측 장비 측정값이 사내 MES 시스템에 업로드된 long-form CSV)
2. 앱의 **Input A** (또는 B) 에 **Ctrl+V**
3. **▶ Run** → 결과 패널에 cell (차트 + 1D radial + Summary 표) 가로 나열
4. cell 우클릭 → **Copy Image** → PPT / Excel 에 **Ctrl+V** 로 사진 paste

> 입력이 클립보드면 **출력도 클립보드**. 파일 I/O 최소화.

## 주요 기능 (요약)

단일 / DELTA / 다중 wafer · 2D heatmap + 3D radial mesh · Summary 표 11종 · 좌표 프리셋 라이브러리 (RECIPE 자동 매칭) · PARA 조합 (sum / concat recursive) · ER Map · r-symmetry mode · UI 해상도 자동 (FHD/QHD/UHD).

자세한 기능·사용법은 [`USER_GUIDE.md`](USER_GUIDE.md).

## 기술 스택

Python 3.14 · PySide6 (Qt 6) · pyqtgraph · numpy / scipy · pandas. 배포: PyInstaller `--onedir` 무설치 포터블 zip.

## 실행 (개발)

```bash
python -m venv venv
venv\Scripts\activate     # Windows
pip install -r requirements.txt
python app.py
```

`python app.py --selftest` — 1.5초 후 자동 종료 (import / QSS 검증용).

## 문서 구조

| 파일 | 시청자 | 내용 |
|---|---|---|
| [`USER_GUIDE.md`](USER_GUIDE.md) | 사내 사용자 | 워크플로 / 단축키 / Settings / ReasonBar 메시지 카탈로그 |
| [`CLAUDE.md`](CLAUDE.md) | 개발자 + AI 협업 | 정책 / 아키텍처 / tech debt / 묵시적 invariant |
| [`CHANGELOG.md`](CHANGELOG.md) | 모두 | 버전 이력 (SemVer) |
| [`docs/policies/`](docs/policies/) | 개발자 | 입력 / 좌표 / ReasonBar 3대 정책 |
| [`docs/rendering_optimizations.md`](docs/rendering_optimizations.md) | 개발자 | 렌더 최적화 이력 (실패 사례 포함) |

## 라이선스 / 사용

회사 내부 사용 목적. 외부 배포 / 재사용 시 작성자 (Jihwan Park, SK hynix) 와 협의 필요.
