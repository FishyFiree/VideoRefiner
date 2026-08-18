"""RIFE 模型管理与自动下载。

06/PRD 决策：模型首次运行自动下载到用户数据目录（%APPDATA%/VideoRefiner/models/），
带进度提示与失败重试；下载源可配置（环境变量 VIDEOREFINER_MODELS_DIR 重定向目录）。

模型源：官方 hzwer/RIFE HF 镜像的 RIFEv4.26_0921.zip（内含 flownet.pkl，v4.26，
与 vendored RIFE-v4.26 代码匹配）。下载后解出 pkl 存为 rife4.26.pkl。
离线兜底：用户手动放置的 pkl / safetensors / pt 文件直接可用。
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

DEFAULT_MODEL = "rife4.26.pkl"

# 官方 v4.26 模型压缩包（hzwer/RIFE HF 镜像）
MODEL_ZIP_URL = (
    "https://huggingface.co/hzwer/RIFE/resolve/main/RIFEv4.26_0921.zip"
)
MODEL_ZIP_SHA256 = "1FA9B9CDA3D9B8C3E301359E2595960902F97BF926C08598B0E9957A3F3F760E"
MODEL_ZIP_MEMBER = "RIFEv4.26_0921/flownet.pkl"

# 本地模型目录兜底时认可的文件名（含用户手动放置的）
_LOCAL_PATTERNS = ("flownet.pkl", DEFAULT_MODEL, "rife4.26.pkl", "*.pkl", "*.safetensors", "*.pt")


def models_dir() -> Path:
    env = os.environ.get("VIDEOREFINER_MODELS_DIR")
    if env:
        return Path(env)
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "VideoRefiner" / "models"


def find_local_model(model_name: Optional[str] = None) -> Optional[Path]:
    """在模型目录里找可用模型文件；找不到返回 None。"""
    d = models_dir()
    if not d.exists():
        return None
    candidates: list[Path] = []
    if model_name:
        candidates.append(d / model_name)
    for pat in _LOCAL_PATTERNS:
        candidates.extend(d.glob(pat))
    for c in candidates:
        if c.is_file():
            return c
    return None


def ensure_model(
    progress_cb: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Path:
    """确保默认模型可用：已有则返回本地路径，否则下载官方 zip 并解出 pkl。"""
    existing = find_local_model(DEFAULT_MODEL)
    if existing:
        return existing

    d = models_dir()
    d.mkdir(parents=True, exist_ok=True)
    dest = d / DEFAULT_MODEL
    tmp_zip = d / (DEFAULT_MODEL + ".zip.part")

    last_err: Optional[Exception] = None
    for _attempt in range(3):
        try:
            _download(MODEL_ZIP_URL, tmp_zip, progress_cb, cancel_check)
            _verify_sha256(tmp_zip, MODEL_ZIP_SHA256)
            with zipfile.ZipFile(tmp_zip) as z:
                with z.open(MODEL_ZIP_MEMBER) as src, open(dest, "wb") as out:
                    out.write(src.read())
            tmp_zip.unlink(missing_ok=True)
            return dest
        except Exception as exc:  # noqa: BLE001 —— 重试
            last_err = exc
            try:
                tmp_zip.unlink(missing_ok=True)
            except Exception:
                pass
    raise RuntimeError(f"模型下载失败（已重试 3 次）: {last_err}")


def _verify_sha256(path: Path, expected: str) -> None:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
    actual = sha.hexdigest().upper()
    if actual != expected.upper():
        raise RuntimeError(f"模型压缩包校验失败: {actual[:16]}…")


def _download(
    url: str,
    dest: Path,
    progress_cb: Optional[Callable[[int, int], None]],
    cancel_check: Optional[Callable[[], bool]],
) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "videorefiner/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress_cb:
                    progress_cb(done, total)
                if cancel_check and cancel_check():
                    raise RuntimeError("下载已取消")
    if total and done < total:
        raise RuntimeError(f"下载不完整: {done}/{total}")
