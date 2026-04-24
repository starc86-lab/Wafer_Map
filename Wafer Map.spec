# -*- mode: python ; coding: utf-8 -*-
"""
Wafer Map PyInstaller spec.

0.2.0 용량 최적화:
- matplotlib / PIL (완전 미사용)
- scipy 불필요 submodule (optimize / sparse / stats / fft / ndimage / integrate)
- PySide6 불필요 모듈 (QtQml / QtQuick / QtPdf / QtNetwork / QtMultimedia / 웹 관련 / DBus)
- 개발/테스트 모듈 (pytest / IPython 등)

scipy.interpolate / scipy.signal / scipy.linalg / scipy.spatial / scipy.special 은
RBFInterpolator / UnivariateSpline / savgol_filter 등에 직·간접 의존이라 유지.

출력 폴더/실행 파일 이름에 `app.py::VERSION` 자동 반영.
"""
import re

with open('app.py', encoding='utf-8') as _f:
    _m = re.search(r'VERSION\s*=\s*"([^"]+)"', _f.read())
    _VERSION = _m.group(1) if _m else '0.0.0'

_BUILD_NAME = f'Wafer_Map_{_VERSION}'


excludes = [
    # 완전 미사용
    'matplotlib',
    'matplotlib.pyplot',
    'PIL',
    'PIL.Image',
    'tkinter',
    # scipy submodule 은 서로 transitive import 가 많아 개별 exclude 시 체인 깨짐
    # (optimize ← interpolate._bsplines / special ← _array_api / stats ← signal 등).
    # scipy 전체 포함 유지. 추가 감축이 필요하면 빌드 후 scipy/<미사용> 하위 디렉토리
    # 수동 삭제 스크립트를 별도로 운영.
    # PySide6 미사용 모듈
    'PySide6.QtQml',
    'PySide6.QtQuick',
    'PySide6.QtQuick3D',
    'PySide6.QtQuickWidgets',
    'PySide6.QtPdf',
    'PySide6.QtPdfWidgets',
    'PySide6.QtNetwork',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineQuick',
    'PySide6.QtWebChannel',
    'PySide6.QtWebSockets',
    'PySide6.QtBluetooth',
    'PySide6.QtDBus',
    'PySide6.QtNfc',
    'PySide6.QtPositioning',
    'PySide6.QtLocation',
    'PySide6.QtSerialBus',
    'PySide6.QtSerialPort',
    'PySide6.QtTest',
    'PySide6.QtSql',
    # PySide6.QtSvg / QtSvgWidgets 는 Fusion style 의 체크박스/라디오 버튼
    # indicator 렌더에 사용 → 제거 시 체크마크 미표시. 유지.
    'PySide6.QtCharts',
    'PySide6.QtDataVisualization',
    'PySide6.Qt3DCore',
    'PySide6.Qt3DRender',
    'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic',
    'PySide6.Qt3DAnimation',
    'PySide6.Qt3DExtras',
    # 개발/테스트 (stdlib 의 unittest / doctest / pydoc 은 numpy.testing 이
    # lazy import 하므로 exclude 하면 scipy 체인 깨짐 → 제외하지 않음)
    'pytest',
    'IPython',
    'jupyter',
    'notebook',
]


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

# ─────────────────────────────────────────────────────────
# Qt DLL / translations 수동 정리
# PyInstaller excludes 는 Python 모듈만 제거하고 Qt DLL 은 모두 포함되므로,
# Analysis 결과의 binaries / datas 를 후처리로 필터링.
# ─────────────────────────────────────────────────────────
_QT_DLL_EXCLUDES = {
    # QML / Quick (사용 안 함)
    'Qt6Qml.dll', 'Qt6QmlModels.dll', 'Qt6QmlMeta.dll',
    'Qt6QmlWorkerScript.dll',
    'Qt6Quick.dll', 'Qt6QuickParticles.dll', 'Qt6QuickShapes.dll',
    'Qt6QuickTest.dll', 'Qt6QuickWidgets.dll', 'Qt6QuickTemplates2.dll',
    'Qt6QuickControls2.dll', 'Qt6QuickControls2Impl.dll',
    'Qt6QuickDialogs2.dll', 'Qt6QuickDialogs2QuickImpl.dll',
    'Qt6QuickDialogs2Utils.dll',
    # PDF / Network (사용 안 함)
    'Qt6Pdf.dll',
    'Qt6Network.dll',
    # 기타 (미사용 확실)
    'Qt6Multimedia.dll', 'Qt6MultimediaWidgets.dll', 'Qt6MultimediaQuick.dll',
    'Qt6WebChannel.dll', 'Qt6WebEngineCore.dll',
    'Qt6WebSockets.dll', 'Qt6WebView.dll',
    'Qt6Sensors.dll', 'Qt6Positioning.dll', 'Qt6Location.dll',
    'Qt6Bluetooth.dll', 'Qt6Nfc.dll',
    'Qt6SerialPort.dll', 'Qt6SerialBus.dll',
    'Qt6Sql.dll', 'Qt6Test.dll',
    # Qt6Svg / Qt6SvgWidgets — Fusion 체크박스/라디오 indicator 용. 유지.
    'Qt6Charts.dll', 'Qt6DataVisualization.dll',
    'Qt63DCore.dll', 'Qt63DRender.dll', 'Qt63DInput.dll',
    'Qt63DLogic.dll', 'Qt63DAnimation.dll', 'Qt63DExtras.dll',
    'Qt63DQuickRender.dll', 'Qt63DQuickInput.dll',
    'Qt63DQuickAnimation.dll', 'Qt63DQuickExtras.dll',
    'Qt63DQuickScene2D.dll',
}

def _skip_binary(entry):
    dest = entry[0].replace('\\', '/')
    name = dest.rsplit('/', 1)[-1]
    return name in _QT_DLL_EXCLUDES

def _skip_data(entry):
    dest = entry[0].replace('\\', '/')
    # Qt 번역 파일 (Qt 내부 error message 번역 — 없어도 영어로 표시, 앱 동작 영향 없음)
    if '/translations/' in dest or dest.endswith('.qm'):
        return True
    return False

a.binaries = [b for b in a.binaries if not _skip_binary(b)]
a.datas = [d for d in a.datas if not _skip_data(d)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Wafer Map',  # 실행 파일명은 버전 미포함 (탐색기 표시 간결)
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=_BUILD_NAME,   # 출력 폴더 = Wafer_Map_<VERSION> (예: Wafer_Map_0.2.0)
)
