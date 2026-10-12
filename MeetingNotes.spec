# Directory build keeps shared libraries replaceable and avoids extracting to temp on every launch.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

a = Analysis(
    ['app.py'], pathex=[],
    binaries=[],
    datas=collect_data_files('docx') + collect_data_files('openai') + collect_data_files('opencc')
        + [('assets/department-template.docx', 'assets')]
        + collect_data_files('PySide6', includes=['translations/qtbase_zh_TW.qm']),
    hiddenimports=[],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
              'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtPdf', 'tkinter', 'IPython', 'pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MeetingNotes',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='MeetingNotes')
