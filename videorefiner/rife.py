"""RIFE 引擎实现（S3）：实现 FrameInterpolator 契约。

集成说明（vendored，均锁定）：
- hzwer/ECCV2022-RIFE（third_party/，commit 5d8adbdd40e12c2c8f91930eff838aebe561c086，
  MIT）——提供 model 包（warplayer 等底层算子）
- RIFE-v4.26 官方模型包（third_party/RIFE-v4.26/，zip SHA256
  1FA9B9CDA3D9B8C3E301359E2595960902F97BF926C08598B0E9957A3F3F760E）——
  RIFE_HDv3.Model + IFNet_HDv3，与 flownet.pkl(v4.26) 匹配
- 模型 rife4.26.pkl：官方 HF 镜像自动下载 + 离线目录兜底

要点（PRD/03 决策）：
- 契约 ``interpolate(a, b, t)`` / ``interpolate_batch(pairs, ts)``
- 批处理按 batch_limit 分块；CUDA OOM 时自动减半重试
- 模型加载一次、常驻 GPU（load 后不卸载）
- 输入帧尺寸 pad 到 32 的倍数再推理（RIFE 金字塔下采样需要），推理后裁剪还原
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import torch

from . import models as models_mod
from .engine import FrameInterpolator

_THIRD_PARTY = Path(__file__).resolve().parent.parent / "third_party"
if getattr(sys, "frozen", False):  # PyInstaller 打包产物：资源在 _MEIPASS
    _THIRD_PARTY = Path(getattr(sys, "_MEIPASS", ".")) / "third_party"
_RIFE_REPO = _THIRD_PARTY / "ECCV2022-RIFE"   # 提供 model 包（warplayer 等）
_RIFE_V426 = _THIRD_PARTY / "RIFE-v4.26"       # 提供 RIFE_HDv3 + train_log


def _load_state_dict(model_path: Path, map_location: str = "cpu") -> dict:
    """加载 pkl（torch pickle）或 safetensors 为 state_dict，剥离 module. 前缀。"""
    if model_path.suffix == ".safetensors":
        from safetensors.torch import load_file

        sd = load_file(str(model_path))
    else:
        sd = torch.load(model_path, map_location=map_location, weights_only=True)
    if any(k.startswith("module.") for k in sd):
        sd = {k.replace("module.", ""): v for k, v in sd.items()}
    return sd


def _to_tensor(img: np.ndarray, device: str) -> torch.Tensor:
    """RGB uint8 HWC → (1,3,H,W) float32 [0,1]（CHW，/255）。"""
    t = torch.from_numpy(np.ascontiguousarray(img.transpose(2, 0, 1)))
    return t.to(device, dtype=torch.float32).unsqueeze(0) / 255.0


def _from_tensor(t: torch.Tensor) -> np.ndarray:
    """(1,3,H,W) float [0,1] → RGB uint8 HWC。"""
    out = (t[0].clamp(0, 1) * 255).round().to(torch.uint8)
    return out.cpu().numpy().transpose(1, 2, 0)


class RifeEngine(FrameInterpolator):
    """RIFE v4.26 光流插帧引擎（任意时间步）。"""

    name = "rife"

    def __init__(
        self,
        model_path: Optional[str] = None,
        device: Optional[str] = None,
        batch_limit: int = 8,
        fp16: bool = True,
        download_progress_cb=None,
    ):
        self.model_path = Path(model_path) if model_path else None
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.batch_limit = max(1, batch_limit)
        self.fp16 = fp16
        self.download_progress_cb = download_progress_cb
        self._model = None
        self._loaded_path: Optional[Path] = None

    # ---------- FrameInterpolator 契约 ----------

    def load(self) -> None:
        if self._model is not None:
            return
        for p in (_RIFE_REPO, _RIFE_V426):
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))

        model_path = self.model_path
        if model_path is None:
            model_path = models_mod.find_local_model() or models_mod.ensure_model(
                progress_cb=self.download_progress_cb
            )
        sd = _load_state_dict(model_path)

        from RIFE_HDv3 import Model  # 迟到导入：只在需要时引入 RIFE 代码

        m = Model()
        m.flownet.load_state_dict(sd, strict=False)
        m.flownet.eval()
        m.flownet.to(self.device)
        if self.fp16:
            # 官方 fp16 做法：内部新建张量默认 half，避免与半精度权重 dtype 不匹配。
            # 注意：同一进程内先加载 fp32 引擎再加载 fp16 引擎可能 dtype 冲突
            # （RIFE 内部某些张量在混合场景下残留 float32）；实际使用单引擎不受影响。
            m.flownet.half()
            torch.set_default_dtype(torch.float16)
        self._model = m
        self._loaded_path = model_path

        # 预热：触发 CUDA kernel 编译，避免首次推理的额外延迟
        with torch.no_grad():
            dummy = torch.zeros(1, 3, 64, 64, device=self.device)
            self._infer(dummy, dummy, 0.5)

    def interpolate(self, frame_a: np.ndarray, frame_b: np.ndarray, t: float) -> np.ndarray:
        if t <= 0:
            return frame_a.copy()
        if t >= 1:
            return frame_b.copy()
        img0, img1, _pad = self._prepare(frame_a, frame_b)
        with torch.no_grad():
            out = self._infer(img0, img1, float(t))
        return _from_tensor(out)[: frame_a.shape[0], : frame_a.shape[1]]

    def interpolate_batch(
        self, pairs: List[Tuple[np.ndarray, np.ndarray]], ts: List[float]
    ) -> List[np.ndarray]:
        limit = self.batch_limit
        while True:
            try:
                results: List[np.ndarray] = []
                for i in range(0, len(pairs), limit):
                    results.extend(
                        self.interpolate(a, b, t)
                        for (a, b), t in zip(pairs[i : i + limit], ts[i : i + limit])
                    )
                return results
            except torch.cuda.OutOfMemoryError:
                if limit <= 1:
                    raise
                limit = max(1, limit // 2)
                torch.cuda.empty_cache()

    def unload(self) -> None:
        if self._model is not None:
            del self._model
            self._model = None
            if self.fp16:
                torch.set_default_dtype(torch.float32)
            torch.cuda.empty_cache()

    # ---------- 内部 ----------

    def _prepare(self, frame_a: np.ndarray, frame_b: np.ndarray):
        """pad 到 64 的倍数并转张量；返回 (t_a, t_b, (pad_h, pad_w))。

        RIFE v4.26 五级金字塔（scale 至 16）要求输入尺寸被 64 整除，
        否则 conv 链下采样取整后重建尺寸不匹配（如 736→768）。
        """
        h, w = frame_a.shape[:2]
        ph = (64 - h % 64) % 64
        pw = (64 - w % 64) % 64
        if ph or pw:
            pa = np.pad(frame_a, ((0, ph), (0, pw), (0, 0)), mode="reflect")
            pb = np.pad(frame_b, ((0, ph), (0, pw), (0, 0)), mode="reflect")
        else:
            pa, pb = frame_a, frame_b
        return _to_tensor(pa, self.device), _to_tensor(pb, self.device), (ph, pw)

    def _infer(self, img0: torch.Tensor, img1: torch.Tensor, t: float) -> torch.Tensor:
        if self.fp16:
            img0, img1 = img0.half(), img1.half()
        out = self._model.inference(img0, img1, timestep=t)
        if self.fp16:
            out = out.float()
        return out
