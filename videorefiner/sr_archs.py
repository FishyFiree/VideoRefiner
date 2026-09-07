"""Real-ESRGAN 神经网络结构（vendored，BSD-3-Clause）。

来源：xinntao/Real-ESRGAN（v0.3.x，BSD-3-Clause）与 xinntao/BasicSR。
为规避 basicsr/realesrgan 在 Python 3.14 下的依赖与兼容问题，此处仅提权
（复制、按需裁剪）RRDBNet 与 SRVGGNetCompact 两个结构定义，权重仍从官方
预训练 .pth 加载（对齐 v1 的 vendored RIFE 模式）。许可：BSD-3-Clause。

模型对应关系（见 ``videorefiner/upscaler.py`` 的模型目录）：
- SRVGGNetCompact —— ``realesr-general-wdn-x4v3``（默认，x4，无降噪卷积）
- RRDBNet —— ``RealESRGAN_x4plus_anime_6B``（x4，6 块）、``RealESRGAN_x2plus``（x2）
"""

from __future__ import annotations

import math
from typing import Optional

import torch
from torch import nn
from torch.nn import functional as F


# ---------------------------------------------------------------------------
# 通用
# ---------------------------------------------------------------------------


def make_layer(basic_block, num_basic_block, **kwarg):
    """堆叠 num_basic_block 个 basic_block。"""
    layers = []
    for _ in range(num_basic_block):
        layers.append(basic_block(**kwarg))
    return nn.Sequential(*layers)


def pixel_unshuffle(x: torch.Tensor, scale: int) -> torch.Tensor:
    """PixelUnshuffle：把空间下采样 scale 倍、通道上采样 scale^2 倍。"""
    b, c, hh, hw = x.size()
    out_channel = c * (scale**2)
    if hh % scale != 0 or hw % scale != 0:
        raise ValueError(f"pixel_unshuffle 需要 H/W 可被 {scale} 整除，got {hh}x{hw}")
    h = hh // scale
    w = hw // scale
    x_view = x.view(b, c, h, scale, w, scale)
    return x_view.permute(0, 1, 3, 5, 2, 4).reshape(b, out_channel, h, w)


# ---------------------------------------------------------------------------
# RRDBNet（x4plus / x4plus_anime_6B / x2plus）
# ---------------------------------------------------------------------------


class ResidualDenseBlock(nn.Module):
    """残差稠密块（RRDB 的基本单元）。"""

    def __init__(self, num_feat: int = 64, num_grow_ch: int = 32):
        super().__init__()
        self.conv1 = nn.Conv2d(num_feat, num_grow_ch, 3, 1, 1)
        self.conv2 = nn.Conv2d(num_feat + num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv3 = nn.Conv2d(num_feat + 2 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv4 = nn.Conv2d(num_feat + 3 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv5 = nn.Conv2d(num_feat + 4 * num_grow_ch, num_feat, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x


class RRDB(nn.Module):
    """RRDB 块：三个 RDB 的残差。"""

    def __init__(self, num_feat: int, num_grow_ch: int = 32):
        super().__init__()
        self.rdb1 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb2 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb3 = ResidualDenseBlock(num_feat, num_grow_ch)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.rdb1(x)
        out = self.rdb2(out)
        out = self.rdb3(out)
        return out * 0.2 + x


class RRDBNet(nn.Module):
    """Real-ESRGAN 主干（RRDB）。scale ∈ {1, 2, 4}。"""

    def __init__(
        self,
        num_in_ch: int = 3,
        num_out_ch: int = 3,
        scale: int = 4,
        num_feat: int = 64,
        num_block: int = 23,
        num_grow_ch: int = 32,
    ):
        super().__init__()
        self.scale = scale
        if scale == 2:
            num_in_ch = num_in_ch * 4
        elif scale == 1:
            num_in_ch = num_in_ch * 16
        self.conv_first = nn.Conv2d(num_in_ch, num_feat, 3, 1, 1)
        self.body = make_layer(
            RRDB, num_block, num_feat=num_feat, num_grow_ch=num_grow_ch
        )
        self.conv_body = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        # 上采样头（scale=1 时跳过，无 up1/up2）
        if scale > 1:
            self.conv_up1 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_up2 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        else:
            self.conv_up1 = nn.Identity()
            self.conv_up2 = nn.Identity()
        self.conv_hr = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_last = nn.Conv2d(num_feat, num_out_ch, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.scale == 2:
            feat = pixel_unshuffle(x, scale=2)
        elif self.scale == 1:
            feat = pixel_unshuffle(x, scale=4)
        else:
            feat = x
        feat = self.conv_first(feat)
        body_feat = self.conv_body(self.body(feat))
        feat = feat + body_feat
        if self.scale > 1:
            feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
            feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
        feat = self.lrelu(self.conv_hr(feat))
        return self.conv_last(feat)


# ---------------------------------------------------------------------------
# SRVGGNetCompact（realesr-general-x4v3 / wdn-x4v3）
# ---------------------------------------------------------------------------


class SRVGGNetCompact(nn.Module):
    """紧凑 VGG 风格超分网络（realesr-general 系列）。"""

    def __init__(
        self,
        num_in_ch: int = 3,
        num_out_ch: int = 3,
        num_feat: int = 64,
        num_conv: int = 32,
        upscale: int = 4,
        act_type: str = "prelu",
    ):
        super().__init__()
        self.num_in_ch = num_in_ch
        self.num_out_ch = num_out_ch
        self.num_feat = num_feat
        self.num_conv = num_conv
        self.upscale = upscale
        self.act_type = act_type

        self.body = nn.ModuleList()
        self.body.append(nn.Conv2d(num_in_ch, num_feat, 3, 1, 1))
        self.body.append(self._act())
        for _ in range(num_conv):
            self.body.append(nn.Conv2d(num_feat, num_feat, 3, 1, 1))
            self.body.append(self._act())
        self.body.append(nn.Conv2d(num_feat, num_out_ch * upscale * upscale, 3, 1, 1))
        self.upsampler = nn.PixelShuffle(upscale)

    def _act(self) -> nn.Module:
        if self.act_type == "prelu":
            return nn.PReLU(num_parameters=self.num_feat)
        return nn.LeakyReLU(negative_slope=0.1, inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = x
        for layer in self.body:
            out = layer(out)
        out = self.upsampler(out)
        # 残差：近邻上采样加上，保持高频锐度
        base = F.interpolate(x, scale_factor=self.upscale, mode="nearest")
        return out + base


# ---------------------------------------------------------------------------
# 加载辅助
# ---------------------------------------------------------------------------


def build_model(
    name: str,
    *,
    arch: str,
    num_feat: int = 64,
    num_block: int = 23,
    num_grow_ch: int = 32,
    num_conv: int = 32,
    upscale: Optional[int] = None,
    act_type: str = "prelu",
) -> "torch.nn.Module":
    """按名字构建对应结构（``upscaler`` 模型目录调用）。

    ``upscale`` 未显式给出时，按结构推断：RRDBNet 用 4、SRVGG 用 4。
    """
    if arch == "rrdb":
        scale = upscale if upscale is not None else 4
        return RRDBNet(
            num_in_ch=3, num_out_ch=3, scale=scale,
            num_feat=num_feat, num_block=num_block, num_grow_ch=num_grow_ch,
        )
    # srvgg
    scale = upscale if upscale is not None else 4
    return SRVGGNetCompact(
        num_in_ch=3, num_out_ch=3, num_feat=num_feat,
        num_conv=num_conv, upscale=scale, act_type=act_type,
    )
