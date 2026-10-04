# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path.cwd().resolve()
ENTRY = ROOT / "desktop" / "vox_rescue_studio.py"
ICON = ROOT / "desktop" / "vox_rescue_icon.ico"
VERSION = ROOT / "desktop" / "version_info.txt"

datas = [
    (
        str(ROOT / "models" / "DeepFilterNet3" / "config.ini"),
        "models/DeepFilterNet3",
    ),
    (
        str(
            ROOT
            / "models"
            / "DeepFilterNet3"
            / "checkpoints"
            / "model_120.ckpt.best"
        ),
        "models/DeepFilterNet3/checkpoints",
    ),
    (
        str(
            ROOT
            / "models"
            / "protected"
            / "vox_rescue_engine.vrm"
        ),
        "models/protected",
    ),
    (str(ROOT / "desktop" / "VOX RESCUE  LOGO.png"), "desktop"),
    (str(ROOT / "desktop" / "VOX RESCUE.png"), "desktop"),
    (str(ROOT / "desktop" / "RELEASE_README.txt"), "."),
    (str(ROOT / "website"), "help"),
]

a = Analysis(
    [str(ENTRY)],
    pathex=[str(ROOT), str(ROOT / "desktop")],
    binaries=[
        (
            str(
                ROOT
                / "desktop"
                / "native_model_guard"
                / "x64"
                / "Release"
                / "model_guard.pyd"
            ),
            ".",
        )
    ],
    datas=datas,
    hiddenimports=["df.deepfilternet3", "libdf.libdf", "pystray._win32"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VoxRescue",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="x86_64",
    icon=str(ICON),
    version=str(VERSION),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="VoxRescue",
)
