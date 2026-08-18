"""S8 构建脚本：PyInstaller 打包 + zip + Inno Setup 安装程序。

用法：
  python build.py                # PyInstaller + zip
  python build.py --installer    # 再编译 Inno Setup 安装程序（dist/VideoRefiner-setup.exe，约 1.7GB，单文件 <2GB）
产出：dist/VideoRefiner/（应用目录）+ dist/VideoRefiner-windows.zip + dist/VideoRefiner-setup.exe
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
APP_DIR = DIST / "VideoRefiner"
ZIP_PATH = DIST / "VideoRefiner-windows.zip"
SETUP_PATH = DIST / "VideoRefiner-setup.exe"


def _find_iscc() -> Path:
    for cand in (
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        Path.home() / r"AppData\Local\Programs\Inno Setup 6\ISCC.exe",
    ):
        if cand.is_file():
            return cand
    return None


def main() -> None:
    if "--skip-build" not in sys.argv:
        cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(ROOT / "VideoRefiner.spec")]
        print(">>>", " ".join(cmd))
        subprocess.run(cmd, check=True)

    if not (APP_DIR / "VideoRefiner.exe").is_file():
        raise SystemExit("打包产物缺失：dist/VideoRefiner/VideoRefiner.exe")

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(APP_DIR.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(DIST))
    size_mb = ZIP_PATH.stat().st_size / 1e6
    app_mb = sum(f.stat().st_size for f in APP_DIR.rglob("*") if f.is_file()) / 1e6
    print(f"OK: {APP_DIR}（{app_mb:.0f} MB，{sum(1 for _ in APP_DIR.rglob('*'))} 个文件）")
    print(f"OK: {ZIP_PATH}（{size_mb:.0f} MB）")

    if "--installer" in sys.argv:
        iscc = _find_iscc()
        if iscc is None:
            raise SystemExit("未找到 ISCC.exe（Inno Setup），跳过安装程序编译")
        cmd = [str(iscc), str(ROOT / "VideoRefiner_installer.iss")]
        print(">>>", " ".join(cmd))
        subprocess.run(cmd, check=True)
        print(f"OK: {SETUP_PATH}（{SETUP_PATH.stat().st_size / 1e6:.0f} MB，单文件 <2GB 可直传 GitHub Release）")


if __name__ == "__main__":
    main()
