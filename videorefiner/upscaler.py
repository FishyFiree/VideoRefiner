"""Real-ESRGAN 超分引擎实现（v2，V2-1）：实现 :class:`Upscaler` 契约。

集中说明（参考 .scratch/video-interpolation-v2/research/01-super-res-engine.md）：
- 主引擎 Real-ESRGAN（v0.3.x，BSD-3），结构 vendored 于 ``videorefiner/sr_archs.py``
  （不引入 basicsr/realesrgan，规避 Python 3.14 依赖与打包体积问题）。
- 模型目录见 ``videorefiner/models.py`` 的 ``SUPERRES_MODELS``：
  默认 ``realesr-general-wdn-x4v3``（x4、SRVGGNetCompact、无降噪卷积，契合纯提升）。
- 契约 ``upscale(frame_rgb, out_w, out_h)``：整数倍走模型原生倍率，非整数倍先模型
  原生倍率放大再 bicubic 缩放回目标（"往返"，见 research ① 做法一）。
- tile 自动分块（按显存自适应）+ pre-pad overlap 去接缝；fp16；OOM 时自动降 tile 重试。
- ``BicubicUpscaler`` 为轻量占位（测试/调试用，无模型），类比 v1 的 BlendEngine。
"""

from __future__ import annotations

from typing import List, Optional, Union

import numpy as np
import torch
from torch.nn import functional as F

from . import models as models_mod
from . import sr_archs
from .engine import Upscaler


def _unwrap_state_dict(sd: dict) -> dict:
    """剥离官方的 ``params`` / ``params_ema`` 包装层。"""
    for key in ("params_ema", "params"):
        if key in sd and isinstance(sd[key], dict):
            return sd[key]
    return sd


def _load_state_dict(path, map_location: str = "cpu") -> dict:
    sd = torch.load(path, map_location=map_location, weights_only=True)
    return _unwrap_state_dict(sd)


def _to_tensor(img: np.ndarray, device: str) -> torch.Tensor:
    """RGB uint8 HWC → (1,3,H,W) float32 [0,1]。"""
    t = torch.from_numpy(np.ascontiguousarray(img.transpose(2, 0, 1)))
    return t.to(device, dtype=torch.float32).unsqueeze(0) / 255.0


def _from_tensor(t: torch.Tensor) -> np.ndarray:
    """(1,3,H,W) float [0,1] → RGB uint8 HWC。"""
    out = (t[0].clamp(0, 1) * 255).round().to(torch.uint8)
    return out.cpu().numpy().transpose(1, 2, 0)


def _run_model(
    img: torch.Tensor,
    model: torch.nn.Module,
    scale: int,
) -> torch.Tensor:
    """对整幅张量跑一次模型；先 pad 到 scale 的整数倍，返回裁剪回原尺寸的输出。"""
    h, w = img.shape[2], img.shape[3]
    ph = (scale - h % scale) % scale if h % scale else 0
    pw = (scale - w % scale) % scale if w % scale else 0
    if ph or pw:
        # reflect 要求 pad < 尺寸；极小图时退化为复制边
        mode = "reflect" if (ph < h and pw < w) else "replicate"
        img = F.pad(img, (0, pw, 0, ph), mode=mode)
    with torch.no_grad():
        out = model(img)
    return out[:, :, : h * scale, : w * scale]


def _tile_upscale(
    x: torch.Tensor,
    model: torch.nn.Module,
    scale: int,
    tile: int,
    overlap: int,
) -> torch.Tensor:
    """对 (1,3,H,W) 张量按 tile 分块推理，输出 (1,3,H*scale,W*scale)。

    每个 tile 取 overlap 边界上下文放大后裁剪回对应输出区域，从而在 tile 交界处
    无接缝；输入先 pad 到 tile 的整数倍（reflect），最后裁剪回原尺寸。
    """
    b, c, h, w = x.shape
    pad_h = (tile - h % tile) % tile if h % tile else 0
    pad_w = (tile - w % tile) % tile if w % tile else 0
    if pad_h or pad_w:
        xp = F.pad(x, (0, pad_w, 0, pad_h), mode="reflect")
    else:
        xp = x
    H, W = xp.shape[2], xp.shape[3]
    out = torch.zeros((b, c, H * scale, W * scale), dtype=xp.dtype, device=xp.device)
    for ty in range(0, H, tile):
        for tx in range(0, W, tile):
            iy0 = max(0, ty - overlap)
            iy1 = min(H, ty + tile + overlap)
            ix0 = max(0, tx - overlap)
            ix1 = min(W, tx + tile + overlap)
            t = xp[:, :, iy0:iy1, ix0:ix1]
            with torch.no_grad():
                ot = model(t)
            oy0_in = (ty - iy0) * scale
            ox0_in = (tx - ix0) * scale
            out[:, :, ty * scale : (ty + tile) * scale, tx * scale : (tx + tile) * scale] = (
                ot[:, :, oy0_in : oy0_in + tile * scale, ox0_in : ox0_in + tile * scale]
            )
    return out[:, :, : h * scale, : w * scale]


class RealESRGANUpscaler(Upscaler):
    """Real-ESRGAN 超分引擎（tile 分块 + fp16 + OOM 降级）。"""

    name = "realesrgan"

    def __init__(
        self,
        model_name: str = "realesr-general-wdn-x4v3",
        device: Optional[str] = None,
        tile: Optional[int] = None,
        tile_overlap: int = 10,
        fp16: bool = True,
        download_progress_cb=None,
    ):
        if model_name not in models_mod.SUPERRES_MODELS:
            raise ValueError(f"未知超分模型: {model_name}")
        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tile = tile
        self.tile_overlap = max(0, tile_overlap)
        self.fp16 = fp16
        self.download_progress_cb = download_progress_cb
        self._model: Optional[torch.nn.Module] = None
        self._scale: int = 4
        self._use_fp16 = bool(fp16 and torch.cuda.is_available() and device != "cpu")

    # ---------- Upscaler 契约 ----------

    def load(self) -> None:
        if self._model is not None:
            return
        spec = models_mod.SUPERRES_MODELS[self.model_name]
        path = models_mod.ensure_superres_model(
            self.model_name, progress_cb=self.download_progress_cb
        )
        self._scale = spec.scale
        model = sr_archs.build_model(self.model_name, **spec.arch_settings)
        model.load_state_dict(_load_state_dict(path), strict=False)
        model.eval()
        model.to(self.device)
        if self._use_fp16:
            model.half()
        self._model = model
        if self.tile is None:
            self.tile = self._auto_tile_size()

        # 预热：触发 kernel 编译，避免首次推理额外延迟
        with torch.no_grad():
            dummy = torch.zeros(1, 3, 64, 64, device=self.device)
            if self._use_fp16:
                dummy = dummy.half()
            model(dummy)

    def upscale(self, frame: np.ndarray, out_w: int, out_h: int) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("RealESRGANUpscaler 未加载（调用 load()）")
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError(f"期望 RGB uint8 (H,W,3)，got {frame.shape}")
        x = _to_tensor(frame, self.device)
        if self._use_fp16:
            x = x.half()
        out = self._tile_process(x)
        if self._use_fp16:
            out = out.float()
        if out.shape[3] != out_w or out.shape[2] != out_h:
            out = F.interpolate(out, size=(out_h, out_w), mode="bicubic", align_corners=False)
        return _from_tensor(out)

    def unload(self) -> None:
        if self._model is not None:
            del self._model
            self._model = None
            torch.cuda.empty_cache()

    # ---------- 内部 ----------

    def _auto_tile_size(self) -> int:
        """按可用显存粗选 tile（384/256/192/128/64）。

        本机实测 1080p→4K 用 tile=384 最快（384>512 因 tile 过大徒增单块计算且
        显存压力大）；选 384 起步、OOM 时自动降级。显存未知时保守回 256。
        """
        if not self.device.startswith("cuda"):
            return 256
        try:
            free, _total = torch.cuda.mem_get_info(self.device)
        except Exception:
            return 256
        # 粗估每个 tile 的激活内存（bytes）：比纯输入留更多余量以规避 OOM
        for t in (384, 256, 192, 128, 64):
            if t * t * 3 * 8 * 8 < free * 0.4:
                return t
        return 64

    def _tile_process(self, x: torch.Tensor) -> torch.Tensor:
        tile = self.tile or 256
        # 图像不超出单 tile：直接整幅推理（无需分块，避免对小图 reflect 越界）
        if x.shape[2] <= tile and x.shape[3] <= tile:
            return _run_model(x, self._model, self._scale)
        while True:
            try:
                return _tile_upscale(x, self._model, self._scale, tile, self.tile_overlap)
            except torch.cuda.OutOfMemoryError:
                if tile <= 64 or tile >= max(x.shape[2], x.shape[3]):
                    raise
                tile = max(64, tile // 2)
                torch.cuda.empty_cache()


class BicubicUpscaler(Upscaler):
    """轻量占位超分（测试/调试用）：纯 bicubic 缩放，无模型。

    类比 v1 的 BlendEngine：只保证管线形状与输出尺寸正确，不产出真实 AI 画质。
    """

    name = "bicubic"

    def __init__(self, device: Optional[str] = None):
        self.device = device or "cpu"

    def upscale(self, frame: np.ndarray, out_w: int, out_h: int) -> np.ndarray:
        if frame.shape[1] == out_w and frame.shape[0] == out_h:
            return frame.copy()
        t = _to_tensor(frame, self.device)
        with torch.no_grad():
            resized = F.interpolate(t, size=(out_h, out_w), mode="bicubic", align_corners=False)
        return _from_tensor(resized)

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass
