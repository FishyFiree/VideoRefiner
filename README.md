# VideoRefiner — AI 视频插帧 + 超分工具

<p align="center">
  <img src="assets/icon.png" width="120" alt="VideoRefiner">
</p>

**输入任意帧率/分辨率的视频，输出更高帧率（如 60fps → 120fps）且/或更高分辨率（如 1080p → 4K）。全程只做 AI 生成/重建，不改动画面语义：插帧用 [RIFE](https://github.com/hzwer/ECCV2022-RIFE)，超分用 [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)。**

基于 RIFE（光流插帧）、Real-ESRGAN（超分，代码与预训练权重均可商用，BSD-3/MIT）与 PySide6 桌面界面。支持任意源帧率 → 任意目标帧率（含 24→60 这类非整数倍），分辨率**等比不拉伸**放大（竖屏 / 4:3 / 方形源不变形）。免费、开源、中文界面。

---

## ✨ 功能

### AI 光流插帧（RIFE v4.26）
- 在帧与帧之间生成自然过渡的中间帧，画面内容不变（语义不变，输出整体重编码）
- **任意目标帧率**：默认 60→120，也可 24→60 / 30→120 / 任意组合（最高 1000fps）
- **场景切换保护**：剪辑点处直接沿用源帧，避免跨场景插值的"鬼影"
- 精确 2× 快速路径：交替 copy/interp，性能与通用路径字节级一致

### AI 超分 / 画质优化（Real-ESRGAN v0.3.x）
- 逐帧提升分辨率（如 1080p→4K），**等比不拉伸**——按"档位长边"等比放大，长宽比严格不变
- **整数倍**走模型原生倍率（x2/x4），**非整数倍**用"bicubic 往返 + 模型精修"
- **自动 tile 分块**（按显存自适应 384/256/128…）+ pre-pad 去接缝 + fp16；显存不足自动降 tile 重试，避免爆显存
- 多模型：通用（默认）/ 动漫（`RealESRGAN_x4plus_anime_6B`）/ 1080p→4K 精确 2×（`RealESRGAN_x2plus`）/ 对照（`RealESRGAN_x4plus`）

### 双功能可组合（本产品核心）
- 帧率、分辨率两个目标都接受 `≥` 源值；**等于源值时跳过该功能**
- 帧率 = 源帧率 → 只超分；分辨率 = 源分辨率 → 只插帧；两者都 = 源值 → 提示"参数与原视频一致，请修改"
- **先插帧（原生分辨率）→ 再超分**（RIFE 原生分辨率又快又准，超分放最后、分辨率倍增成本最低）
- 全程**帧级内存流式**，不中途落盘/重编码；最后统一编码 + 音频直通 + 临时文件原子收尾

### 体验
- **桌面 GUI（中文）**：拖拽/串行批量队列、目标帧率 + 目标分辨率下拉（只显示 ≥ 源档位）、超分模型选择、实时校验（不可用时红字 + 禁用开始）、分阶段进度 + 剩余时间、随时取消、完成后一键**对比播放**（原视频 vs 结果，双窗口同步）、4K/8K 性能警告
- **命令行入口**：`videorefiner <输入> --fps 120 --resolution 3840 -o <输出>`，便于脚本化
- **自动管理模型**：首次运行自动下载（HuggingFace 镜像，支持离线放置）；插帧约 24MB、超分约 5MB 起
- **音频直通**：原音轨原样保留

### 质量保障（实测校准）
- 插帧：合成真值集 PSNR ≥ 32dB / SSIM ≥ 0.95（RIFE fp16 实测 48.6dB / 0.998）
- 超分：x2 实测 PSNR≈38.4 / SSIM≈0.955（验收线 34/0.94）；x4 实测 PSNR≈42.5 / SSIM≈0.973（验收线 34/0.93）

---

## ❓ 为什么要有这个产品？

很多短视频创作者会遇到**两个**常见痛点：

**① 视频卡顿 / 帧率不理想。** 手机、摄像头常只能录 30fps / 60fps，或拍摄环境不佳，播放时动作"一顿一顿"不够丝滑。

**② 素材不够清晰 / 分辨率不够高。** 拍摄或下载的 1080p（甚至更低）视频，在大屏或 4K 显示器上清晰度不足，画面发糊、细节看不清。

而且这两个问题**经常同时出现**：视频又卡又糊。传统方法的痛点：

- 拍摄强行拉高帧率/分辨率 → 受设备限制，文件巨大
- 剪辑软件"变速" → 只改播放速度、不补帧，画面更卡
- 上专业后期工具 → 学习成本高、价格贵（如 Topaz Video AI 需数百美元）

**VideoRefiner 就是为了同时解决这两点**：把视频拖进来，选目标帧率 + 目标分辨率，点开始——AI 自动补帧让动作**丝滑**，同时超分让画面**更清晰**。**不改动你的画面内容，只让运动更流畅、画面更清晰**。免费、开源、开箱即用（仅需 NVIDIA GPU 加速），特别适合想"又顺滑又高清"的短视频创作者、二次元/游戏录像爱好者。

---

## 🆚 同类产品对比

| 工具 | 价格 | 插帧算法 | 超分算法 | 任意帧率 | 等比超分 | 场景保护 | 批量 | 模型管理 | 界面 | 适合人群 |
|---|---|---|---|---|---|---|---|---|---|---|
| **VideoRefiner（本项目）** | **免费 · 开源(MIT)** | RIFE v4.26 | Real-ESRGAN | ✅（含 24→60） | ✅ 不拉伸 | ✅ 自动 | ✅ 串行队列 | ✅ 自动下载+离线 | ✅ 中文 GUI | 短视频创作者、二次元/游戏录像 |
| [Topaz Video AI](https://costbench.com/software/ai-video-generators/topaz-video-ai/) | $299 + $99/年更新 | 自研 | 自研 | ✅ | ✅ | 有 | ✅ | 内置 | 英文 | 专业后期、预算充足 |
| [SVFI](https://store.steampowered.com/app/1692080/SVFI/)（Steam） | 付费 | RIFE 系+多种 | 有 | ✅ | ✅ | 有 | ✅ | 内置 | 英文为主 | 愿付费的重度用户 |
| [Flowframes](https://github.com/stefanpinson/flowframes) | 免费 · 开源 | RIFE/DAIN 多算法 | 部分 | ✅ | 部分 | 部分 | 有 | ❌ 手动下载 | 老旧 GUI | 有折腾经验的玩家 |
| [Squirrel-RIFE](https://doc.svfi.group/) | 免费 · 开源 | RIFE | ❌ | ✅ | ❌ | 无 | 有 | 内置 | ❌ 纯命令行 | 命令行用户 |
| 独立超分（[Real-ESRGAN-ncnn-vulkan](https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan)/[Upscayl](https://upscayl.org/)） | 免费 · 开源 | ❌ | ✅ | ❌ | ✅ | 无 | 有 | 内置/自带 | 图形/CLI | 只想超分、低配/跨卡 |
| [剪映/抖音](https://www.douyin.com/shipin/7300910419244386343)等手机剪辑 | 免费 | 内置（仅慢放补帧） | 弱 | 仅慢放 | ❌ | 无 | 无 | 无 | 手机 App | 随手轻量场景 |
| FFmpeg `minterpolate` | 免费 | 传统块匹配（非 AI） | 无 | ✅ | — | 无 | 有 | 无 | CLI | 快速运动场景效果差 |

**我们的优势**：
1. **免费 + 开源 + 开箱即用**：MIT 许可——对比付费的 Topaz/SVFI，或配置繁琐的 Flowframes、纯命令行的 Squirrel-RIFE
2. **插帧 + 超分二合一**：一次处理同时提升帧率与分辨率，还能单独做其中一个（= 源值时自动跳过）
3. **等比不拉伸**：竖屏 / 4:3 / 方形源按档位长边等比放大，长宽比严格不变
4. **任意目标帧率（含非整数倍）** + **任意目标分辨率（2K/4K/8K）**：多数工具只做固定 2x/4x/8x
5. **场景切换保护**：剪辑点自动沿用源帧，不产生跨场景鬼影
6. **模型零配置 + 离线可用**：首次运行自动下载、支持离线放置
7. **内置对比播放 + 分阶段进度**：双窗口同步对比，清晰看到插帧与超分各自进度
8. **中文界面**：面向中文创作者的友好体验

**诚实的差距**：Topaz 的超分+插帧上限更高（但数百美元）；SVFI/Flowframes 生态更久、批处理与 GPU 优化（TensorRT 等）更成熟；独立超分工具在低配/跨卡上更快；剪映等手机 App 免费且随手可用。我们目前**仅支持 NVIDIA GPU**，打包体积较大（应用目录约 4.6GB，主要是 PyTorch CUDA 运行时）——非 NVIDIA 支持与超分速度优化在后续计划中。

---

## 💻 系统要求

- **Windows 10 / 11**（x64）
- **NVIDIA GPU**（必需，CUDA）：
  - 最低：GTX 1660 6GB（1080p 可用，较慢）
  - 推荐：RTX 3060 8GB 及以上（1080p 流畅）
  - 高性能：RTX 3080 / 4070+（4K / 8K 顺畅）
- 非 NVIDIA（AMD/Intel）暂不支持
- （源码运行需 Python 3.11+，CUDA 版 PyTorch）

---

## 📦 安装

### 方式一：安装程序（推荐）
从 [GitHub Releases](https://github.com/FishyFiree/VideoRefiner/releases) 下载 **`VideoRefiner-setup.exe`**（约 1.8GB，单文件 <2GB），双击安装（无需管理员权限，安装到当前用户目录），完成后从桌面/开始菜单启动 `VideoRefiner`。

> 首次运行会自动下载 AI 模型：插帧约 24MB、超分约 5MB 起（HuggingFace 镜像）。若杀毒软件误报，属 PyInstaller 产物常见情况，可添加信任或提交误报申诉。
> 若已装旧版：AppId 相同，可直接升级（1.0.0 → 2.0.0）；下载的模型在 `%APPDATA%\VideoRefiner\models`，卸载不会删除、无需重下。

### 方式二：绿色免安装版
下载 `VideoRefiner-windows.zip`（约 2.9GB）并解压，双击 `VideoRefiner.exe`（无需安装）。

### 方式三：源码运行
```bash
git clone https://github.com/FishyFiree/VideoRefiner.git
cd VideoRefiner
pip install -e .
python -m videorefiner.gui        # 启动 GUI
# 或命令行：
python -m videorefiner.cli in.mp4 --fps 120 -o out.mp4
```
需要 Python 3.11+，以及 CUDA 版 PyTorch（`pip install torch --index-url https://download.pytorch.org/whl/cu128`）。

---

## 🎬 使用方法

**GUI**：拖入或添加一个/多个视频 → 设置 **目标帧率**（默认 120）与 **目标分辨率**（默认"不超分 = 源分辨率"，可选 2K/4K/8K）→ 选超分模型（通用/动漫）与编码/质量 → 开始处理 → 串行队列逐个完成（状态栏显示"阶段：插帧 → 超分"+ 进度与剩余时间）→ 双击"完成"项对比播放原视频与结果。

**CLI**：
```bash
# 只插帧（60→120）
videorefiner input.mp4 --fps 120 -o output.mp4

# 只超分到 4K（--fps 设为源帧率）
videorefiner input.mp4 --fps 60 --resolution 3840 -o output.mp4

# 先插帧到 120，再超分到 4K（组合，等比不拉伸）
videorefiner input.mp4 --fps 120 --resolution 3840 -o output.mp4

# 指定编码 / 质量 / 场景阈值 / 超分模型
videorefiner input.mp4 --fps 240 --codec h264 --quality high -o output.mp4
videorefiner input.mp4 --fps 120 --resolution 2560 --model realesrgan -o output.mp4
```

> 说明：`--resolution` 以"档位长边"表示（2560=2K / 3840=4K / 7680=8K）。分辨率目标 `≥` 源尺寸、帧率目标 `≥` 源帧率；等于源值时仅跳过该功能。目标分辨率会**按源长宽比等比放大**（不拉伸），输出宽高取偶数（yuv420p 编码需要）。GUI 会自动过滤出 `≥` 源的分辨率档位并实时校验参数，避免产生无意义的处理。

---

## ⚡ 性能（RTX 4060 Laptop 8GB 实测，torch 2.11+cu128）

### 插帧（RIFE，fp16）
| 分辨率 | 单帧插值耗时 | 处理速度 |
|---|---|---|
| 640×360 | 27 ms | 37 fps |
| 1280×720 | 36 ms | 28 fps |
| 1920×1080 | 70 ms | 14.4 fps |
| 3840×2160 | 320 ms | 3.1 fps |

### 超分（Real-ESRGAN，逐帧；超分是组合管线的主要耗时项）
| 目标 | 模型 | `tile` | 单帧耗时 | 速率 |
|---|---|---|---|---|
| 1080p→4K（精确 2×） | RealESRGAN_x2plus | 384（自动） | ≈4.3 s | ≈0.23 fps |
| 1080p→4K（精确 2×） | RealESRGAN_x2plus | 256 | ≈6.9 s | ≈0.14 fps |
| 4K（x4 模型往返，非整数倍） | realesr-general-wdn-x4v3 | 自动 | 更慢 | — |

### 组合端到端
对 640×360 素材做"插帧 30→60 + 超分到 1280×720"，16 源帧 → 32 帧约 **39s**（同素材只插帧的 v1 基线约 **7.3s**）——**超分占绝对主导**，属离线重活（非实时）。目标达 4K/8K 时显著变慢，建议高端 GPU；`tile` 越大（显存允许时）越快，4K 建议 384。

> 说明：插帧单帧与 v1 一致；超分是瓶颈，1080p→4K 约 0.14–0.23 fps。GUI 的进度/剩余时间会按实测帧率滚动估算。

---

## 🔧 工作原理

1. 解码源视频（PyAV），按时间戳定位每个输出帧对应的源帧对与帧内位置（`alpha`）
2. 对每对源帧调用 RIFE 单步插值（支持任意 `alpha`，即任意倍率）；相邻源帧差异超阈值（场景切换）时直接沿用源帧，避免鬼影
3. **（可选超分）** 对每个输出帧调用 Real-ESRGAN 提升到目标分辨率——自动 tile 分块、fp16、显存不足自动降 tile；整数倍走原生倍率，非整数倍先放大再缩放回目标（"往返"）
4. 输出整体重编码（x264/x265，音频直通），临时文件原子收尾；全程帧级内存流式、不中途落盘

---

## ⚙️ 分辨率与倍率说明（等比不拉伸）

- 分辨率目标用"**档位长边**"表达（不超分 / 2K=2560 / 4K=3840 / 8K=7680）。
- 输出 = 源分辨率**按比例等比放大**到该长边：长宽比严格不变（竖屏 / 4:3 / 方形源都不变形）。
- **整数倍**（如 1080p→4K = 精确 2×）走模型原生倍率（`RealESRGAN_x2plus`），质量最好。
- **非整数倍**（如竖屏 1080×1920→"4K" ≈3.56×、720p→2K ≈1.33×）用"bicubic 往返 + 模型精修"：先让模型按原生 x4 放大、再缩放回目标长边，质量略逊但通用。

---

## 🛠️ 构建打包

```bash
python build.py              # PyInstaller 单目录 + zip
python build.py --installer  # 再编译 Inno Setup 安装程序（VideoRefiner-setup.exe，约 1.8GB，单文件 <2GB）
```

> 应用目录约 4.6GB（主要来自 PyTorch CUDA 运行时）；zip 约 2.9GB（GitHub Release 单文件限 2GB，故推荐以安装程序发布）。安装向导当前为英文（产品界面为中文），简体中文向导语言文件可后续补充。超分结构已 vendored（`videorefiner/sr_archs.py`），**无需额外打包 basicsr/realesrgan/cv2 依赖**。

---

## 📄 许可证与致谢

- 本项目代码：**MIT License**（见 `LICENSE`）
- 插帧引擎 [RIFE](https://github.com/hzwer/ECCV2022-RIFE)（[Practical-RIFE](https://github.com/hzwer/Practical-RIFE)）：MIT，作者黄峥（hzwer）等；vendored 于 `third_party/`（见 [third_party/README.md](third_party/README.md)）
- 超分引擎 [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)（v0.3.x）：BSD-3-Clause（代码 + 预训练权重均可商用）；结构 vendored 于 `videorefiner/sr_archs.py`
- 预训练模型：插帧 `rife4.26.pkl` 来源 [hzwer/RIFE](https://huggingface.co/hzwer/RIFE)（HuggingFace）；超分模型（`realesr-general-wdn-x4v3` 等）来源 [xinntao/Real-ESRGAN Releases](https://github.com/xinntao/Real-ESRGAN/releases)（HuggingFace 镜像）
- **商业分发时建议保留模型出处说明**

---

## 🚧 已知限制与计划

- **超分为离线重活（非实时）**：1080p→4K 约 0.14–0.23 fps；`tile` 调优可提速
- **逐帧超分存在轻微帧间闪烁/抖动**（SISR 固有，尤其细纹/字幕）：计划加入时间一致性后处理
- **仅支持 NVIDIA GPU**：非 NVIDIA（ncnn 后端）支持计划中
- **4K/8K 插帧/超分需高端卡**（RTX 3080/4070+）
- **打包体积大**（应用目录约 4.6GB，主要 PyTorch CUDA）：体积优化计划中
- 提速方向：NVENC 硬件编码、TensorRT 引擎、批处理优化、超分 tile 调优
- 断点续传暂不支持

---

有任何问题或建议，欢迎提 [Issue](https://github.com/FishyFiree/VideoRefiner/issues)！
