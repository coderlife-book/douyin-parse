from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules


root = Path(SPECPATH).parents[1]
hiddenimports = []
for package in ("faster_whisper", "ctranslate2", "av", "opencc", "playwright", "uvicorn"):
    hiddenimports.extend(collect_submodules(package))

binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("av")
datas = collect_data_files("faster_whisper") + collect_data_files("opencc")

analysis = Analysis(
    [str(root / "desktop_launcher.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="抖音视频工具",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory="_internal",
)
bundle = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="抖音视频工具",
)
