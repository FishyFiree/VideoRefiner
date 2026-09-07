# VideoRefiner — AI 视频插帧 + 超分工具

<p align="center">
  <img src="assets/icon.png" width="120" alt="VideoRefiner">
</p>

**输入任意帧率的视频，输出更高帧率（如 60fps → 120fps）且/或更高分辨率（如 1080p → 4K）。只做 AI 生成/重建，不改动画面语义。插帧用 [RIFE](https://github.com/hzwer/ECCV2022-RIFE)，超分用 [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)。**

基于 RIFE（光流插帧）、Real-ESRGAN（超分，均可商用，BSD-3/MIT）与 PySide6 桌面界面，支持任意源帧率 → 任意目标帧率（含 24→60 这类非整数倍），分辨率**等比不拉伸**放大。

## ✨ 功能

- **AI 光流插帧**（RIFE v4.26）：在帧与帧之间生成自然过渡的中间帧，画面内容不变（语义不变，输出整体重编码）
- **AI 超分/画质优化**（Real-ESRGAN v0.3.x）：逐帧提升分辨率（如 1080p→4K），**等比不拉伸**（竖屏/4:3/方形源不变形）；整数倍走模型原生倍率，非整数倍用"bicubic 往返 + 模型精修"
- **双功能可组合**：帧率、分辨率两个目标都接受 `≥` 源值；等于源值时跳过该功能；都等于源值提示"参数与原视频一致，请修改"。组合时**先插帧（原生分辨率）→ 再超分**
- **任意目标帧率**：默认 60→120，也可 24→60 / 30→120 / 任意组合（最高 1000fps）
- **桌面 GUI（中文）**：拖拽/多文件队列、参数设置、实时进度与剩余时间、可取消、处理完成后一键对比播放（原视频 vs 插帧结果，双窗口同步）
- **命令行入口**：`videorefiner <输入> --fps 120 -o <输出>`，便于脚本化
- **自动管理模型**：首次运行自动下载插帧（约 15MB）与超分（约 5MB 起）模型（HuggingFace 镜像，支持离线放置）
- **场景切换保护**：剪辑点处直接沿用原帧，避免跨场景插值的鬼影
- **音频直通**：原音轨原样保留
- 质量保障：插帧合成测试集 PSNR ≥ 32dB / SSIM ≥ 0.95（RIFE fp16 实测 48.6dB / 0.998）；超分 x2 实测 PSNR≈38.4/SSIM≈0.955、x4 实测 PSNR≈42.5/SSIM≈0.973（验收线见 `PRD.md`）

## ❓ 为什么要有这个产品？

很多短视频创作者会遇到这样的问题：**录制的视频帧率不理想**——可能是设备限制（手机/摄像头只支持 30fps、60fps），也可能是拍摄环境不佳，成片动起来"一顿一顿"的，不够丝滑。

传统解决办法都各有痛点：

- 拍摄时强行拉高帧率 → 受设备限制，且文件巨大
- 用剪辑软件"变速" → 只改播放速度，不补帧，画面更卡
- 上专业后期工具 → 学习成本高、价格贵（如 Topaz Video AI 需数百美元）

**VideoRefiner 就是为了解决这个问题**：录完的视频，拖进来、选个目标帧率、点开始，AI 自动在帧与帧之间生成过渡帧，把"不够丝滑"变成"丝滑"——**不改动你的画面内容，只让动作更流畅**。它免费、开源、开箱即用，特别适合想让视频更流畅的短视频创作者。

## 🆚 同类产品对比

| 产品 | 价格 | 插帧算法 | 任意帧率 | 场景保护 | 批量 | 模型管理 | 界面 | 适合人群 |
|---|---|---|---|---|---|---|---|---|
| **VideoRefiner（本项目）** | **免费·开源(MIT)** | RIFE v4.26 | ✅（含 24→60 非整数倍） | ✅ 自动 | ✅ 串行队列 | ✅ 自动下载+离线 | ✅ 中文 GUI | 短视频创作者、二次元/游戏录像 |
| [剪映 / 抖音](https://www.douyin.com/shipin/7300910419244386343) 等手机剪辑 | 免费 | 内置（仅慢放时补帧） | ❌ 无独立升帧 | 无 | 无 | 无 | 手机 App | 随手轻量场景 |
| [Topaz Video AI](https://costbench.com/software/ai-video-generators/topaz-video-ai/) | $299 永久 + $99/年更新 | 自研（超分+插帧） | ✅ | 有 | ✅ | 内置 | 英文 GUI | 专业后期，预算充足 |
| [SVFI](https://store.steampowered.com/app/1692080/SVFI/)（Steam） | 付费（Steam 销售） | RIFE 系 | ✅ | 有 | ✅ | 内置 | 英文为主 | 愿意付费的重度用户 |
| [Flowframes](https://github.com/stefanpinson/flowframes) | 免费·开源 | RIFE/DAIN 多算法 | ✅ | 部分 | 有 | ❌ 需手动下载模型 | 老旧 GUI | 有折腾经验的玩家 |
| [Squirrel-RIFE](https://doc.svfi.group/#%F0%9F%8C%8E-%E6%95%99%E7%A8%8B%E6%BC%94%E7%A4%BA-tutorial-on-bilibili) | 免费·开源 | RIFE | ✅ | 无 | 有 | 内置 | ❌ 纯命令行 | 命令行用户 |
| FFmpeg `minterpolate` | 免费 | 传统块匹配（非 AI） | ✅ | 无 | 有 | 无 | CLI | 快速运动场景效果差 |

**我们的优势**：

1. **免费 + 开源 + 开箱即用**：MIT 许可，Windows 解压即用（下载 Release zip 双击 `VideoRefiner.exe`）——对比付费的 Topaz/SVFI，或配置繁琐的 Flowframes、纯命令行的 Squirrel-RIFE
2. **任意目标帧率**：支持非整数倍（24→60、30→120 等），多数工具只做固定 2x/4x/8x
3. **场景切换保护**：剪辑点自动沿用原帧，不产生跨场景鬼影
4. **模型零配置**：首次运行自动下载、支持离线放置（Flowframes 需手动下载模型到指定目录）
5. **内置对比播放**：双窗口同步播放原视频与结果，效果一目了然
6. **中文界面**：面向中文创作者的友好体验

**诚实的差距**：Topaz 的超分+插帧上限更高（但数百美元）；SVFI/Flowframes 生态更久、批处理与 GPU 优化（TensorRT 等）更成熟；剪映等手机 App 免费且随手可用，适合轻量场景。我们 v1 仅支持 NVIDIA GPU，打包体积较大（约 5GB，主要来自 PyTorch CUDA 运行时）——非 NVIDIA 支持与体积优化在后续计划中。

## 💻 系统要求

- **Windows 10/11**（x64）
- **NVIDIA GPU**（v1 必需，CUDA）：
  - 最低：GTX 1660 6GB（1080p 可用，较慢）
  - 推荐：RTX 3060 8GB 及以上（1080p 近实时）
  - 高性能：RTX 3080/4070+（4K 顺畅）
- 非 NVIDIA（AMD/Intel）暂不支持

## 📦 安装

### 方式一：下载安装程序（推荐）

从 [GitHub Releases](https://github.com/Yuh-Hypnotized/VideoRefiner/releases) 下载 **`VideoRefiner-setup.exe`**（约 1.7GB，单文件），
双击安装（无需管理员权限，安装到当前用户目录），安装完成后从桌面/开始菜单启动 `VideoRefiner`。

> 首次运行会自动下载 AI 模型（约 15MB）；若杀毒软件误报，属 PyInstaller 产物常见情况，可提交误报申诉或添加信任。

### 方式二：绿色免安装版

下载 `VideoRefiner-windows.zip` 并解压，双击运行 `VideoRefiner.exe`（无需安装）。

### 方式二：源码运行

```bash
git clone https://github.com/Yuh-Hypnotized/VideoRefiner.git
cd VideoRefiner
pip install -e .
python -m videorefiner.gui        # 启动 GUI
# 或命令行：
python -m videorefiner.cli in.mp4 --fps 120 -o out.mp4
```

需要 Python 3.11+，以及 CUDA 版 PyTorch（`pip install torch --index-url https://download.pytorch.org/whl/cu128`）。

## 🎬 使用方法

**GUI**：拖入或添加一个/多个视频 → 设置目标帧率（默认 120）、编码与质量 → 开始处理 →
串行队列逐个完成 → 双击「完成」项对比播放原视频与结果。

**CLI**：

```bash
videorefiner input.mp4 --fps 120 -o output.mp4              # 60→120（只插帧）
videorefiner input.mp4 --fps 60 --codec h264 -o out.mp4     # 指定编码
videorefiner input.mp4 --fps 240 --quality high -o out.mp4  # 高质量预设
videorefiner input.mp4 --resolution 3840 -o out.mp4         # 只超分到 4K（--fps 设为源帧率）
videorefiner input.mp4 --fps 120 --resolution 3840 -o out.mp4  # 先插帧到120，再超分到4K（等比不拉伸）
```

> `--resolution` 以"档位长边"表示（如 2560=2K / 3840=4K / 7680=8K）。分辨率目标 `≥` 源尺寸；等于源值时仅插帧，等于源帧率时仅超分。GUI 同样支持分辨率下拉（自动过滤 ≥ 源档位）、超分模型选择、实时校验与分阶段进度提示。

## ⚡ 性能（RTX 4060 Laptop 8GB 实测）

| 分辨率 | 单帧插值耗时（fp16） | 处理速度 |
|---|---|---|
| 640×360 | 27 ms | 37 fps |
| 1280×720 | 36 ms | 28 fps |
| 1920×1080 | 70 ms | 14.4 fps |
| 3840×2160 | 320 ms | 3.1 fps |

1080p60 → 120fps 端到端（含软件编码）：10 分钟素材约 2 小时（插帧约 42 分钟 + x265 编码约 80 分钟）。

**超分**（Real-ESRGAN，逐帧，RTX 4060 8GB 实测；超分是组合管线的主要耗时项）：

| 目标 | 模型 | `tile` | 单帧耗时 | 速率 |
|---|---|---|---|---|
| 1080p→4K（精确 2×） | RealESRGAN_x2plus | 384（自动） | ≈4.3 s | ≈0.23 fps |
| 1080p→4K（精确 2×） | RealESRGAN_x2plus | 256 | ≈6.9 s | ≈0.14 fps |
| 4K（x4 模型 往返） | realesr-general-wdn-x4v3 | 自动 | 更慢（x4 原生再缩放） | — |

> 组合端到端：对 640×360 素材做"插帧 30→60 + 超分到 1280×720"，16 源帧→32 帧约 **39s**（同素材只插帧 v1 基线约 **7.3s**）——超分占绝对主导，实时性远低于插帧（非实时，属离线重活）。目标达 4K/8K 时显著变慢，建议高端 GPU。

## 🔧 工作原理

1. 解码源视频（PyAV），按时间戳定位每个输出帧对应的源帧对与帧内位置（`alpha`）
2. 对每对源帧调用 RIFE 单步插值（支持任意 `alpha`，即任意倍率）；相邻帧差异超阈值（场景切换）时直接沿用源帧，避免鬼影
3. **（可选超分）** 对每个输出帧调用 Real-ESRGAN 提升到目标分辨率（自动 tile 分块、fp16、显存不足自动降 tile；整数倍走原生倍率，非整数倍先放大再缩放回目标）
4. 输出整体重编码（x264/x265，音频直通），临时文件原子收尾；全程帧级内存流式、不中途落盘

## 🛠️ 构建打包

```bash
python build.py              # PyInstaller 单目录 + zip
python build.py --installer  # 再编译 Inno Setup 安装程序（VideoRefiner-setup.exe，约 1.7GB，单文件 <2GB）
```

> 应用目录约 4.5GB（主要来自 PyTorch CUDA 运行时）；zip 约 2.7GB（GitHub Release 单文件限 2GB，
> 故推荐以安装程序形式发布）。安装向导当前为英文（产品界面为中文），简体中文向导语言文件可后续补充。

## 📄 许可证与致谢

- 本项目代码：**MIT License**（见 `LICENSE`）
- 插帧引擎 [RIFE](https://github.com/hzwer/ECCV2022-RIFE)（[Practical-RIFE](https://github.com/hzwer/Practical-RIFE)）：MIT，作者黄峥（hzwer）等；vendored 于 `third_party/`（见 [third_party/README.md](third_party/README.md)）
- 超分引擎 [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)（v0.3.x）：BSD-3-Clause（代码 + 预训练权重均可商用）；结构 vendored 于 `videorefiner/sr_archs.py`（不引入 basicsr/realesrgan 依赖）
- 预训练模型 `rife4.26.pkl`：来源 [hzwer/RIFE](https://huggingface.co/hzwer/RIFE)（HuggingFace）；超分模型（`realesr-general-wdn-x4v3` 等）来源 [xinntao/Real-ESRGAN Releases](https://github.com/xinntao/Real-ESRGAN/releases)（HuggingFace 镜像）。**商业分发时建议保留模型出处说明**

## 🚧 已知限制与计划

- v2 超分为离线重活（非实时）：1080p→4K 约 0.14–0.23 fps；打包体积优化（V2-6）进行中、Inno Setup 安装程序需重建
- 逐帧超分存在轻微**帧间闪烁/抖动**（SISR 固有，尤其细纹/字幕），计划加入时间一致性后处理
- v1 要求 NVIDIA GPU；非 NVIDIA 支持（ncnn 后端）计划中
- 4K/8K 插帧/超分需高端卡（RTX 3080/4070+）
- 提速方向：NVENC 硬件编码、TensorRT 引擎、批处理优化、超分 tile 调优
- 断点续传暂不支持

有任何问题或建议，欢迎提 [Issue](https://github.com/Yuh-Hypnotized/VideoRefiner/issues)！
