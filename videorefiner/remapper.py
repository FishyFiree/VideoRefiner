"""时间戳驱动的帧生成器：任意源帧率 → 任意目标帧率。

对每个输出帧 i，源时间戳 t_out = i / Ft（秒），定位源帧对 (k, k+1) 与帧内步长 alpha：
- alpha ≈ 0 → 直接拷贝源帧 k（零开销）
- k 为最后一帧（末帧保持区间）→ 拷贝源帧 k
- 否则 → 引擎单步插值 (k, k+1, alpha)

S4 将在此加入场景切换保护与 60→120 快速路径。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np

_EPS = 1e-9


def is_scene_cut(frame_a: np.ndarray, frame_b: np.ndarray, threshold: float = 30.0) -> bool:
    """轻量场景切换检测：两帧平均绝对像素差超过阈值视为场景切换。

    S4 将接入时间戳驱动帧生成器——场景切换处直接拷贝源帧，避免跨场景插值鬼影。
    阈值单位与像素值一致（0-255）。
    """
    if frame_a.shape != frame_b.shape:
        return True
    diff = float(np.abs(frame_a.astype(np.int16) - frame_b.astype(np.int16)).mean())
    return diff > threshold


@dataclass(frozen=True)
class OutputFrame:
    """一个输出帧的生成计划。"""

    k: int          # 源帧对起始索引（floor(src_time)）
    alpha: float    # 帧内时间步 [0,1]
    copy: bool      # True → 直接拷贝源帧 k（alpha≈0 或末帧保持）

    def __repr__(self) -> str:
        kind = "copy" if self.copy else f"interp(t={self.alpha:.4f})"
        return f"<OutputFrame k={self.k} {kind}>"


def plan_output_frames(src_fps: float, dst_fps: float, num_src_frames: int) -> Iterator[OutputFrame]:
    """生成输出帧计划。

    输出帧数 M = round(N * Ft / Fs)（至少 1）；第 i 帧位于源时间 i/Ft 秒。
    """
    if dst_fps <= 0 or src_fps <= 0:
        raise ValueError("帧率必须为正数")
    if num_src_frames <= 0:
        raise ValueError("源帧数必须为正数")

    num_out = max(1, round(num_src_frames * dst_fps / src_fps))
    ratio = src_fps / dst_fps  # 每个输出帧跨越的源帧数
    last = num_src_frames - 1
    for i in range(num_out):
        src_time = i * ratio
        k = int(src_time)
        alpha = src_time - k
        if k >= last:
            yield OutputFrame(k=last, alpha=0.0, copy=True)
        elif alpha <= _EPS:
            yield OutputFrame(k=k, alpha=0.0, copy=True)
        else:
            yield OutputFrame(k=k, alpha=alpha, copy=False)
