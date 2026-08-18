"""S8 构建脚本：PyInstaller 打包 + zip 发布物。

用法：python build.py [--skip-build]
产出：dist/VideoRefiner/（应用目录）+ dist/VideoRefiner-windows.zip
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


if __name__ == "__main__":
    main()
