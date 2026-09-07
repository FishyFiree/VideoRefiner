"""等比缩放纯函数（v2，V2-2）。

分辨率目标以"档位长边"表达：输出 = 源分辨率**等比放大**到该长边，两维同倍率，
长宽比严格不变（竖屏 / 4:3 / 方形源都不变形）；非整数倍由超分引擎做"bicubic
往返 + 模型精修"（见 ``videorefiner/upscaler.py``）。
"""

from __future__ import annotations

from typing import Tuple


def _nearest_even(n: int) -> int:
    """取最近偶数（编码 yuv420p 需要偶数宽高）。"""
    return max(2, int(round(n / 2) * 2))


def compute_target_size(src_w: int, src_h: int, target_edge: int) -> Tuple[int, int]:
    """返回等比放大后的 (out_w, out_h)，其**长边**恰为 ``target_edge``。

    - 长宽比严格不变（仅做等比缩放，不拉伸）。
    - 长边（横向源的宽 / 纵向源的高）恰好等于 ``target_edge``；短边按同倍率取整到偶数。
    - ``target_edge`` 等于源长边时返回源尺寸（=源分辨率，即"不超分"）。
    """
    src_w = int(src_w)
    src_h = int(src_h)
    target_edge = int(target_edge)
    if src_w <= 0 or src_h <= 0:
        raise ValueError(f"源宽高必须为正数: {src_w}x{src_h}")
    if target_edge <= 0:
        raise ValueError(f"目标长边必须为正数: {target_edge}")

    if src_w >= src_h:
        out_w = _nearest_even(target_edge)
        out_h = _nearest_even(round(src_h * target_edge / src_w))
    else:
        out_h = _nearest_even(target_edge)
        out_w = _nearest_even(round(src_w * target_edge / src_h))
    return (out_w, out_h)


def aspect_ratio_ok(src_w: int, src_h: int, out_w: int, out_h: int) -> bool:
    """断言长宽比是否近似不变（用于测试）。

    短边会因偶数取整而偏移最多 ~2px，故容差按短边相对误差（≈3px/短边）放宽；
    真正的拉伸（如 4:3 → 16:9）会远超此容差而被拒绝。
    """
    if src_w <= 0 or src_h <= 0 or out_w <= 0 or out_h <= 0:
        return False
    src_ratio = src_w / src_h
    out_ratio = out_w / out_h
    tol = 3.0 / min(out_w, out_h)
    return abs(src_ratio - out_ratio) <= tol * max(1.0, src_ratio)
