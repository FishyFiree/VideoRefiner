"""插帧引擎契约与占位实现。

契约（PRD Implementation Decisions）：
- ``interpolate(frame_a, frame_b, t) -> frame``：单帧对插值，t∈[0,1]
- ``interpolate_batch(pairs, ts) -> frames``：批处理（S3 实现显存自适应与 OOM 降批）

S1 使用帧混合（blend）占位引擎——只保证管线形状正确，画质为混合级；
S3 将替换为 RIFE 真引擎，上层只依赖本契约，不直接碰引擎内部。
"""

from __future__ import annotations

from typing import List, Protocol, Tuple

import numpy as np


class FrameInterpolator(Protocol):
    """插帧引擎契约。帧为 RGB uint8 numpy 数组 (H, W, 3)。"""

    def interpolate(self, frame_a: np.ndarray, frame_b: np.ndarray, t: float) -> np.ndarray:
        """对单帧对 (a, b) 插值；t=0 → a，t=1 → b。"""
        ...

    def interpolate_batch(
        self, pairs: List[Tuple[np.ndarray, np.ndarray]], ts: List[float]
    ) -> List[np.ndarray]:
        """批量插值；实现方负责显存自适应。"""
        ...

    def load(self) -> None:
        """加载模型（S1 占位为空操作；S3 加载并常驻 GPU）。"""
        ...

    def unload(self) -> None:
        """释放模型资源。"""
        ...


class BlendEngine:
    """帧混合占位引擎（S1）：result = (1-t)*a + t*b。"""

    name = "blend"

    def interpolate(self, frame_a: np.ndarray, frame_b: np.ndarray, t: float) -> np.ndarray:
        if t <= 0:
            return frame_a.copy()
        if t >= 1:
            return frame_b.copy()
        a = frame_a.astype(np.uint16)
        b = frame_b.astype(np.uint16)
        out = (a * (1.0 - t) + b * t + 0.5).astype(np.uint8)
        return out

    def interpolate_batch(
        self, pairs: List[Tuple[np.ndarray, np.ndarray]], ts: List[float]
    ) -> List[np.ndarray]:
        return [self.interpolate(a, b, t) for (a, b), t in zip(pairs, ts)]

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass
