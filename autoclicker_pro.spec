# -*- mode: python ; coding: utf-8 -*-
"""
连点器 Pro (Auto Clicker Pro) PyInstaller 打包配置
打包命令: pyinstaller autoclicker_pro.spec
"""

import sys
import os

block_cipher = None

a = Analysis(
    ['autoclicker_pro.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('hotkey_settings.json', '.'),
    ],
    hiddenimports=[
        'pyautogui',
        'pynput',
        'pynput.mouse',
        'pynput.keyboard',
        'PIL',
        'PIL._tkinter_finder',
        'cv2',
        'numpy',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.simpledialog',
        'tkinter.colorchooser',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'scipy', 'pandas', 'notebook', 'IPython',
        'pytest', 'unittest', 'doctest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='连点器Pro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,               # 可替换为 .ico 图标文件路径
)
