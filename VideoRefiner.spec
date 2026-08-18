# -*- mode: python ; coding: utf-8 -*-
"""VideoRefiner PyInstaller spec：单目录 GUI 包（标准单入口模式）。

- 依赖收集用官方标准 hook（av / torch / PySide6）
- nvidia.* CUDA 动态库：torch 运行时经 ctypes 加载、import 图不可见 → 显式收集
- vendored RIFE 代码（third_party/）作为数据打入（运行时经 sys.path 加载）
- 模型文件不打包（首次运行自动下载，PRD 决策）
- 隐藏自检：VideoRefiner.exe --selftest <输入> <输出>（无头跑一次真实插帧）
- excludes：剔除 hook 顺带拖入的无关重量级依赖（scipy/pandas/sklearn/nltk/lxml/
  matplotlib/numba/faiss/transformers/cv2/torchvision/PIL 等）——torch 推理用不到，
  vendored model/loss.py 已把 torchvision 改为惰性导入（仅训练用），可安全排除
"""

import pkgutil
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH)  # PyInstaller 提供的 spec 所在目录

datas = [
    (str(ROOT / "third_party"), "third_party"),
    (str(ROOT / "assets" / "icon.ico"), "assets"),
]
binaries = []
hiddenimports = []

# CUDA 运行时库：nvidia-*-cu128 各包的 DLL（torch 在运行时按包路径 ctypes 加载）
for m in pkgutil.iter_modules():
    if m.name.startswith("nvidia."):
        binaries += collect_dynamic_libs(m.name)
        hiddenimports += collect_submodules(m.name)

_EXCLUDES = [
    # 推理不需要的重量级依赖（hook 顺带拖入）
    "scipy", "pandas", "sklearn", "nltk", "lxml", "matplotlib", "numba",
    "llvmlite", "faiss", "faiss_cpu", "transformers", "openpyxl", "regex",
    "anyio", "rich", "pygments", "fsspec", "tzdata", "pydantic",
    "cryptography", "win32com", "dateutil", "six", "pytest",
    # torchvision 及其依赖链（vendored loss.py 已惰性导入，仅训练用）
    "torchvision", "cv2", "PIL", "pillow", "opencv-python",
]

a = Analysis(
    [str(ROOT / "entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VideoRefiner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI 无控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="VideoRefiner",
)
