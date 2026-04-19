# Changelog

Wafer Map 버전 이력. SemVer(Major.Minor.Patch) 기준.
- **Major**: settings.json 스키마·입력 포맷 등 breaking 변경
- **Minor**: 기능 추가 / UI 변경
- **Patch**: 버그 수정

## [0.1.0] — 2026-04-20
첫 사용 가능 배포 (사내 베타).

### 기능
- 클립보드 페이스트 기반 long-form CSV 파서 (헤더 대소문자/공백/언더바 무관).
- 3-패널 세로 스택 UI (Input A/B · Control · Result).
- 2D Heatmap + 3D Surface MAP — `QStackedLayout`으로 즉시 토글.
- VALUE/X/Y 자동 선택 (`auto_select.py`) + X 변경 시 Y suffix 동기화 + VALUE 변경 즉시 재시각화.
- 다중 웨이퍼 가로 나열. DELTA 시각화 (A-B WAFERID 교집합 · 좌표 일치점).
- Summary 표 (Average / Non Unif. / Range, 3Sig) — 테마 무관 흰색 고정.
- Copy Graph (화면 픽셀 캡처, PPT paste 호환) / Copy Data (TSV) / Copy Table (HTML+TSV dual MIME).
- 좌표 프리셋 라이브러리 (`coord_library.json`) — RECIPE 기반 자동 조회 + 수동 추가.
  - 4 포맷 자동 감지 (row+라벨 / row / col+header / col) + y-first 허용.
  - 노이즈 허용 (BOM/NBSP/quote/leading·trailing 비데이터).
- 자동 정리 정책 (max_count / max_days, last_used 기준, 0=무제한, 기본 1000).
- 보간: RBF 4종 (ThinPlate / Multiquadric / Gaussian / Quintic).
- 컬러맵 28종 + 컬러 스케일바 (Turbo 기본). Reverse·Custom White 포함.
- 테마 14종 + font_scale + Segoe UI 기본.
- 무설치 포터블 배포 (PyInstaller `--onedir`) — settings.json·coord_library.json 실행 폴더 기준.

### UI 인터랙션
- 3D 카메라: 좌드래그=회전, Ctrl+드래그=이동, 휠=비활성.
- **Shift+좌클릭**: 전체 3D 셀 카메라 스냅 동기 + 이어 드래그하면 실시간 전파.
- 우클릭 메뉴: Reset / Copy Graph / Copy Data / Copy Table.
- 윈도우 크기·splitter·최대화 상태 자동 복원.

### 제한사항 / 알려진 이슈
- Copy Graph가 화면 픽셀 캡처 방식이라 **다른 창이 위에 있으면 그 내용이 포함됨** — Settings 창을 `parent=None` 처리로 뒤로 갈 수 있게 workaround. 추후 offscreen FBO 방식으로 전환 예정.
- 3D surface edge에 MSAA가 일부 드라이버에서 적용 안 될 수 있음 (jaggies).
