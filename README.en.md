# VideoRefiner — AI Video Frame Interpolation

<p align="center">
  <img src="assets/icon.png" width="120" alt="VideoRefiner">
</p>

**Convert videos to higher frame rates (e.g. 60fps → 120fps) using AI frame interpolation. Only AI-generated new frames are inserted — the original visual content stays unchanged, making motion look smoother.**

Built on [RIFE](https://github.com/hzwer/ECCV2022-RIFE) (optical-flow frame interpolation, MIT licensed) with a PySide6 desktop GUI. Supports any source → any target frame rate, including non-integer multiples (e.g. 24→60).

## ✨ Features

- **AI optical-flow interpolation** (RIFE v4.26): naturally generated in-between frames; content-preserving (semantics unchanged, output fully re-encoded)
- **Arbitrary target frame rate**: 60→120 by default; also 24→60, 30→120, or any combination (up to 1000fps)
- **Desktop GUI (Chinese)**: drag & drop / batch queue, parameters, live progress + ETA, cancellable, and a side-by-side comparison player (original vs result, synchronized)
- **CLI**: `videorefiner <input> --fps 120 -o <output>` for scripting
- **Automatic model management**: model (~15MB) auto-downloaded on first run from HuggingFace mirror; offline placement supported
- **Scene-change protection**: source frames are reused at cuts to avoid ghosting artifacts
- **Audio passthrough**: original audio track preserved untouched
- Quality: PSNR ≥ 32dB / SSIM ≥ 0.95 on synthetic test sets (measured 48.6dB / 0.998 with RIFE fp16)

## ❓ Why this project?

Many short-video creators face the same problem: **their recorded footage doesn't have an ideal frame rate** —
device limits (phones/cameras stuck at 30fps or 60fps) or shooting conditions make the motion look choppy instead of silky-smooth.

Traditional workarounds all have pain points:

- Recording at a high frame rate → limited by hardware, huge files
- Speeding up / slowing down in an editor → changes playback speed but adds no frames; motion gets *worse*
- Professional post tools → steep learning curve and high cost (e.g. Topaz Video AI costs hundreds of dollars)

**VideoRefiner exists to fix exactly this**: drop in your footage, pick a target frame rate, press start, and the AI
generates in-between frames to turn "not smooth enough" into "silky smooth" — **your visual content is untouched, only
the motion gets smoother**. Free, open source, and ready to use out of the box — built for creators who want smoother videos.

## 🆚 Comparison with similar tools

| Tool | Price | Algorithm | Arbitrary fps | Scene protection | Batch | Model management | UI | Best for |
|---|---|---|---|---|---|---|---|---|
| **VideoRefiner (this project)** | **Free · OSS (MIT)** | RIFE v4.26 | ✅ (incl. 24→60) | ✅ automatic | ✅ serial queue | ✅ auto-download + offline | ✅ Chinese GUI | Short-video creators |
| CapCut / Douyin etc. | Free | built-in (only when slow-mo) | ❌ no standalone upscaling | no | no | n/a | mobile app | Light casual use |
| [Topaz Video AI](https://costbench.com/software/ai-video-generators/topaz-video-ai/) | $299 + $99/yr updates | proprietary (upscale+interp) | ✅ | yes | ✅ | built-in | English GUI | Professionals with budget |
| [SVFI](https://store.steampowered.com/app/1692080/SVFI/) (Steam) | Paid (Steam) | RIFE family | ✅ | yes | ✅ | built-in | mostly English | Power users willing to pay |
| [Flowframes](https://github.com/stefanpinson/flowframes) | Free · OSS | RIFE/DAIN multi | ✅ | partial | yes | ❌ manual model download | dated GUI | Tinkerers |
| [Squirrel-RIFE](https://doc.svfi.group/#%F0%9F%8C%8E-%E6%95%99%E7%A8%8B%E6%BC%94%E7%A4%BA-tutorial-on-bilibili) | Free · OSS | RIFE | ✅ | no | yes | built-in | ❌ CLI only | Command-line users |
| FFmpeg `minterpolate` | Free | traditional block matching (non-AI) | ✅ | no | yes | n/a | CLI | Poor on fast motion |

**Our advantages**:

1. **Free + open source + out-of-the-box**: MIT licensed, unzip and run `VideoRefiner.exe` on Windows — versus paid
   Topaz/SVFI, fiddly Flowframes, or CLI-only Squirrel-RIFE
2. **Arbitrary target frame rate**: non-integer multiples (24→60, 30→120, …) are supported; most tools only do fixed 2x/4x/8x
3. **Scene-change protection**: source frames are reused at cuts automatically — no cross-scene ghosting
4. **Zero model setup**: auto-downloaded on first run, offline placement supported (Flowframes requires manual model downloads)
5. **Built-in comparison player**: side-by-side synchronized playback of original vs result
6. **Chinese UI**: friendly for Chinese-speaking creators

**Honest gaps**: Topaz has a higher quality ceiling (upscaling + interpolation) but costs hundreds of dollars;
SVFI/Flowframes have longer track records and more mature batch/GPU optimization (TensorRT etc.); CapCut-class mobile
apps are free and handy for light use. Our v1 supports NVIDIA GPUs only, the bundle is large (~5GB, mostly the PyTorch
CUDA runtime), and there is no upscaling — all on the roadmap.

## 💻 System Requirements

- **Windows 10/11** (x64)
- **NVIDIA GPU** (required in v1, CUDA):
  - Minimum: GTX 1660 6GB (1080p usable, slow)
  - Recommended: RTX 3060 8GB+ (near-real-time 1080p)
  - High-end: RTX 3080/4070+ (smooth 4K)
- Non-NVIDIA (AMD/Intel) is not supported yet

## 📦 Installation

### Option 1: Installer (recommended)

Download **`VideoRefiner-setup.exe`** (~1.7GB, single file) from [GitHub Releases](https://github.com/Yuh-Hypnotized/VideoRefiner/releases),
run it (no admin rights needed — installs to the current user's folder), then launch `VideoRefiner` from the
desktop / Start menu.

> The AI model (~15MB) is auto-downloaded on first run. If your antivirus flags the executable, that's a common
> PyInstaller false positive — add an exclusion or report the false positive.

### Option 2: Portable zip

Download `VideoRefiner-windows.zip`, unzip it and run `VideoRefiner.exe` (no installation needed).

### Option 2: Run from source

```bash
git clone https://github.com/Yuh-Hypnotized/VideoRefiner.git
cd VideoRefiner
pip install -e .
python -m videorefiner.gui        # launch GUI
# or CLI:
python -m videorefiner.cli in.mp4 --fps 120 -o out.mp4
```

Requires Python 3.11+ and a CUDA-enabled PyTorch
(`pip install torch --index-url https://download.pytorch.org/whl/cu128`).

## 🎬 Usage

**GUI**: add one or more videos → set target frame rate (default 120), codec and quality → start →
the serial queue processes them one by one → double-click a "done" item to compare original vs result.

**CLI**:

```bash
videorefiner input.mp4 --fps 120 -o output.mp4              # 60→120
videorefiner input.mp4 --fps 60 --codec h264 -o out.mp4     # specify codec
videorefiner input.mp4 --fps 240 --quality high -o out.mp4  # high quality preset
```

## ⚡ Performance (measured on RTX 4060 Laptop 8GB)

| Resolution | Per-frame interpolation (fp16) | Processing speed |
|---|---|---|
| 640×360 | 27 ms | 37 fps |
| 1280×720 | 36 ms | 28 fps |
| 1920×1080 | 70 ms | 14.4 fps |
| 3840×2160 | 320 ms | 3.1 fps |

1080p60 → 120fps end-to-end (incl. software encoding): ~2 hours for a 10-minute source
(~42 min interpolation + ~80 min x265 encoding).

## 🔧 How It Works

1. Decode the source (PyAV); map every output frame to a source frame pair and in-between position (`alpha`) by timestamps
2. Call RIFE single-step interpolation per pair (arbitrary `alpha` ⇒ arbitrary rate multiplier)
3. When consecutive source frames differ beyond a threshold (scene cut), reuse the source frame directly to avoid ghosting
4. Re-encode the output (x264/x265, audio passthrough) with atomic temp-file finalization

## 🛠️ Building

```bash
python build.py              # PyInstaller one-dir + zip
python build.py --installer  # also compile the Inno Setup installer (VideoRefiner-setup.exe, ~1.7GB, single file <2GB)
```

> The app dir is ~4.5GB (mostly the PyTorch CUDA runtime); the zip is ~2.7GB (GitHub Releases caps single files at 2GB,
> so the installer is the recommended artifact). The installer wizard is currently English (the app UI is Chinese);
> a Simplified-Chinese wizard language file can be added later.

## 📄 License & Credits

- This project: **MIT License** (see `LICENSE`)
- Interpolation engine [RIFE](https://github.com/hzwer/ECCV2022-RIFE) ([Practical-RIFE](https://github.com/hzwer/Practical-RIFE)): MIT, by hzwer et al.; vendored under `third_party/` (see [third_party/README.md](third_party/README.md))
- Pretrained model `rife4.26.pkl`: from [hzwer/RIFE](https://huggingface.co/hzwer/RIFE) (HuggingFace); distributed loosely by upstream — commercial products (SVP, SVFI) use it at scale. **When distributing commercially, keep the model attribution.**

## 🚧 Limitations & Roadmap

- v1 requires an NVIDIA GPU; non-NVIDIA support (ncnn backend) planned
- 4K interpolation needs a high-end GPU (RTX 3080/4070+)
- Scrolling-text scenes may occasionally flicker (de-flicker post-processing planned)
- Performance roadmap: NVENC hardware encoding, TensorRT engine, batch optimization
- No resume for interrupted jobs yet

Questions or suggestions? Open an [Issue](https://github.com/Yuh-Hypnotized/VideoRefiner/issues)!
