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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import __version__

DEFAULT_MODEL = "rife4.26.pkl"

# Real-ESRGAN 模型源（BSD-3-Clause 许可，官方锚定于 GitHub Releases；此处走
# HuggingFace 镜像以便自动下载 + SHA 校验，策略与 v1 的 RIFE HF 镜像一致）。
_REALESRGAN_HF = "https://huggingface.co/leonelhs/realesrgan/resolve/main/"


@dataclass(frozen=True)
class SuperResModel:
    """超分模型规格：下载元数据 + 结构构建参数。"""

    key: str                      # 模型键（如 realesr-general-wdn-x4v3）
    filename: str                 # 落盘的 .pth 文件名
    url: str                      # 下载 URL（已拼接）
    sha256: str                   # 大写 SHA256 校验值
    scale: int                    # 原生倍率（x2 / x4）
    arch_settings: dict = field(default_factory=dict)  # 传给 sr_archs.build_model


SUPERRES_MODELS: dict[str, SuperResModel] = {
    "realesr-general-wdn-x4v3": SuperResModel(
        key="realesr-general-wdn-x4v3",
        filename="realesr-general-wdn-x4v3.pth",
        url=_REALESRGAN_HF + "realesr-general-wdn-x4v3.pth",
        sha256="1641F8C4464B9F097C9FDDA5589273713F67CF59F3D909E0BD688F0CEE269DCA",
        scale=4,
        arch_settings=dict(
            arch="srvgg", num_feat=64, num_conv=32, upscale=4, act_type="prelu"
        ),
    ),
    "RealESRGAN_x4plus_anime_6B": SuperResModel(
        key="RealESRGAN_x4plus_anime_6B",
        filename="RealESRGAN_x4plus_anime_6B.pth",
        url=_REALESRGAN_HF + "RealESRGAN_x4plus_anime_6B.pth",
        sha256="F872D837D3C90ED2E05227BED711AF5671A6FD1C9F7D7E91C911A61F155E99DA",
        scale=4,
        arch_settings=dict(
            arch="rrdb", num_feat=64, num_block=6, num_grow_ch=32, upscale=4
        ),
    ),
    "RealESRGAN_x2plus": SuperResModel(
        key="RealESRGAN_x2plus",
        filename="RealESRGAN_x2plus.pth",
        url=_REALESRGAN_HF + "RealESRGAN_x2plus.pth",
        sha256="49FAFD45F8FD7AA8D31AB2A22D14D91B536C34494A5CFE31EB5D89C2FA266ABB",
        scale=2,
        arch_settings=dict(
            arch="rrdb", num_feat=64, num_block=23, num_grow_ch=32, upscale=2
        ),
    ),
    "RealESRGAN_x4plus": SuperResModel(
        key="RealESRGAN_x4plus",
        filename="RealESRGAN_x4plus.pth",
        url=_REALESRGAN_HF + "RealESRGAN_x4plus.pth",
        sha256="4FA0D38905F75AC06EB49A7951B426670021BE3018265FD191D2125DF9D682F1",
        scale=4,
        arch_settings=dict(
            arch="rrdb", num_feat=64, num_block=23, num_grow_ch=32, upscale=4
        ),
    ),
}

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


def find_local_superres_model(model_key: str) -> Optional[Path]:
    """在模型目录里找指定超分模型文件（离线兜底）。

    离线兜底优先级高于在线下载：用户手动放置对应文件名到模型目录即直接用。
    """
    spec = SUPERRES_MODELS.get(model_key)
    if spec is None:
        return None
    p = models_dir() / spec.filename
    return p if p.is_file() else None


def ensure_superres_model(
    model_key: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Path:
    """确保指定的 Real-ESRGAN 模型可用：已有则返回本地路径，否则下载并 SHA 校验。"""
    spec = SUPERRES_MODELS[model_key]
    existing = find_local_superres_model(model_key)
    if existing:
        return existing

    d = models_dir()
    d.mkdir(parents=True, exist_ok=True)
    dest = d / spec.filename
    tmp = d / (spec.filename + ".part")

    last_err: Optional[Exception] = None
    for _attempt in range(3):
        try:
            _download(spec.url, tmp, progress_cb, cancel_check)
            _verify_sha256(tmp, spec.sha256)
            os.replace(tmp, dest)
            return dest
        except Exception as exc:  # noqa: BLE001 —— 重试
            last_err = exc
            try:
                tmp.unlink(missing_ok=True)
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
    req = urllib.request.Request(url, headers={"User-Agent": f"videorefiner/{__version__}"})
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
