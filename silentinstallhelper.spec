# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH)
icon_path = project_root / "assets" / "app.ico"
version_file = project_root / "windows-version-info.txt"
datas = [
    (str(project_root / "example-config.json"), "."),
    (str(project_root / "config-7zip-extract.jsonc"), "."),
    (str(project_root / "config-example-7z-icacls.jsonc"), "."),
    (str(project_root / "config-template.jsonc"), "."),
    (str(project_root / "config-template-basic.jsonc"), "."),
    (str(project_root / "config-template-full.jsonc"), "."),
    (str(project_root / "config-template-silent.jsonc"), "."),
    (str(project_root / "readme.md"), "."),
]

a = Analysis(
    ["run.py"],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SilentInstallHelper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
    version=str(version_file),
)
