# VideoRefiner — AI Video Frame Interpolation + Super-Resolution

<p align="center">
  <img src="assets/icon.png" width="120" alt="VideoRefiner">
</p>

**Turn any frame-rate / resolution video into a higher frame rate (e.g. 60fps → 120fps) and/or a higher resolution (e.g. 1080p → 4K) — using only AI generation/reconstruction, keeping the visual semantics unchanged. Interpolation uses [RIFE](https://github.com/hzwer/ECCV2022-RIFE); super-resolution uses [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN).**

Built on RIFE (optical-flow interpolation) and Real-ESRGAN (super-resolution, code + pretrained weights both commercially usable, BSD-3/MIT) with a PySide6 desktop GUI. Supports any source frame rate → any target frame rate (including non-integer multiples like 24→60), with **aspect-preserving** upscaling (vertical / 4:3 / square sources stay undistorted). Free, open source, with a Chinese UI.

---

## ❓ Why this project?

Short-video creators commonly hit **two** problems:

**① Choppy motion / unsatisfying frame rate.** Phones and cameras often only record 30fps or 60fps, or shooting conditions make the motion look "one-frame-at-a-time" instead of silky-smooth.

**② Footage isn't sharp / resolution is too low.** A 1080p (or lower) clip looks soft and loses detail on a large or 4K display.

These two problems **often appear together**: video that is both choppy *and* blurry. Traditional workarounds all have pain points:

- Recording at high frame rate / resolution → limited by hardware, huge files
- "Speed up / slow down" in an editor → changes playback speed but adds no frames; motion gets *worse*
- Professional post tools → steep learning curve and high cost (e.g. Topaz Video AI costs hundreds of dollars)

**VideoRefiner fixes both at once**: drop in your footage, pick a target frame rate + target resolution, press start — the AI adds in-between frames to make motion **silky**, and upscales to make the picture **sharper**. **Your visual content is untouched; only the motion gets smoother and the image gets clearer.** Free, open source, ready out of the box (with NVIDIA GPU acceleration) — built for creators who want videos that are both smooth and sharp, especially short-video makers and anime/game-recording fans.

---

## ✨ Features

### AI optical-flow interpolation (RIFE v4.26)
- Naturally generated in-between frames; content-preserving (semantics unchanged, output re-encoded)
- **Arbitrary target frame rate**: 60→120 by default; also 24→60, 30→120, or any combination (up to 1000fps)
- **Scene-change protection**: source frames are reused at cuts to avoid cross-scene ghosting
- Exact-2× fast path (alternating copy/interp) with byte-identical output to the general path

### AI super-resolution / quality (Real-ESRGAN v0.3.x)
- Per-frame upscaling (e.g. 1080p→4K), **aspect-preserving** — scaled to a "target long edge", aspect ratio strictly unchanged
- **Integer scale** uses the model's native scale (x2/x4); **non-integer scale** uses "bicubic round-trip + model refinement"
- **Auto tiling** (memory-adaptive 384/256/128…) + pre-pad to avoid seams + fp16; auto down-tile retry on OOM to avoid VRAM overflow
- Multiple models: general (default) / anime (`RealESRGAN_x4plus_anime_6B`) / exact 2× 1080p→4K (`RealESRGAN_x2plus`) / reference (`RealESRGAN_x4plus`)

### Composable pipeline (the core value)
- Both the frame-rate and resolution targets accept `≥` the source value; **equal → that stage is skipped**
- frame rate = source → upscale only; resolution = source → interpolate only; both equal → "parameters identical to source, please change"
- **Interpolate (native resolution) → upscale** (RIFE is fast and accurate at native res; upscaling is the resolution-multiplying final step)
- Fully **frame-level in-memory streaming** — no intermediate disk writes / re-encode; final unified encode + audio passthrough + atomic temp-file finalization

### Experience
- **Desktop GUI (Chinese)**: drag & drop / serial batch queue, target frame rate + target resolution dropdown (only shows `≥` source), super-res model choice, real-time validation (red hint + disabled Start when invalid), staged progress + ETA, cancellable, one-click **comparison playback** (original vs result, synchronized), 4K/8K performance warnings
- **CLI**: `videorefiner <input> --fps 120 --resolution 3840 -o <output>` for scripting
- **Automatic model management**: auto-downloaded on first run (HuggingFace mirror, offline placement supported); interpolation ≈24MB, super-res ≈5MB+
- **Audio passthrough**: original audio track preserved untouched

### Quality assurance (measured/calibrated)
- Interpolation: PSNR ≥ 32dB / SSIM ≥ 0.95 on synthetic ground truth (measured 48.6dB / 0.998 with RIFE fp16)
- Super-resolution: x2 measured PSNR≈38.4 / SSIM≈0.955 (acceptance 34/0.94); x4 measured PSNR≈42.5 / SSIM≈0.973 (acceptance 34/0.93)

---

## 🆚 Comparison with similar tools

| Tool | Price | Interpolation | Super-resolution | Arbitrary fps | Aspect-preserving upscale | Scene protect | Batch | Model mgmt | UI | Best for |
|---|---|---|---|---|---|---|---|---|---|---|
| **VideoRefiner (this project)** | **Free · OSS (MIT)** | RIFE v4.26 | Real-ESRGAN | ✅ (incl. 24→60) | ✅ no stretch | ✅ auto | ✅ serial queue | ✅ auto-download + offline | ✅ Chinese GUI | Short-video creators, anime/game recording |
| [Topaz Video AI](https://costbench.com/software/ai-video-generators/topaz-video-ai/) | $299 + $99/yr updates | proprietary | proprietary | ✅ | ✅ | yes | ✅ | built-in | English | Professionals with budget |
| [SVFI](https://store.steampowered.com/app/1692080/SVFI/) (Steam) | Paid | RIFE family + more | yes | ✅ | ✅ | yes | ✅ | built-in | mostly English | Power users willing to pay |
| [Flowframes](https://github.com/stefanpinson/flowframes) | Free · OSS | RIFE/DAIN multi | partial | ✅ | partial | partial | yes | ❌ manual download | dated GUI | Tinkerers |
| [Squirrel-RIFE](https://doc.svfi.group/) | Free · OSS | RIFE | ❌ | ✅ | ❌ | no | yes | built-in | ❌ CLI only | Command-line users |
| Standalone SR ([Real-ESRGAN-ncnn-vulkan](https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan)/[Upscayl](https://upscayl.org/)) | Free · OSS | ❌ | ✅ | ❌ | ✅ | no | yes | built-in/bundled | GUI/CLI | Upscale-only, low-end/cross-vendor |
| CapCut/Douyin etc. | Free | built-in (only when slow-mo) | weak | slow-mo only | ❌ | no | no | n/a | mobile app | Light casual use |
| FFmpeg `minterpolate` | Free | block matching (non-AI) | none | ✅ | — | no | yes | n/a | CLI | Poor on fast motion |

**Our advantages**:
1. **Free + open source + out of the box**: MIT licensed — versus paid Topaz/SVFI, fiddly Flowframes, or CLI-only Squirrel-RIFE
2. **Interpolation + super-resolution in one**: one pass for both higher frame rate and higher resolution, or either one on its own (= source value → auto-skipped)
3. **Aspect-preserving upscaling**: vertical / 4:3 / square sources stay undistorted (target long edge)
4. **Arbitrary target frame rate (non-integer OK)** + **arbitrary target resolution (2K/4K/8K)** — most tools only do fixed 2x/4x/8x
5. **Scene-change protection**: source frames reused at cuts, no cross-scene ghosting
6. **Zero model setup + offline**: auto-downloaded on first run, offline placement supported
7. **Built-in comparison player + staged progress**: side-by-side synchronized playback, clear per-stage progress
8. **Chinese UI** for Chinese-speaking creators

**Honest gaps**: Topaz has a higher quality ceiling (upscaling + interpolation) but costs hundreds of dollars; SVFI/Flowframes have longer track records and more mature batch/GPU optimization (TensorRT etc.); standalone upscalers are faster on low-end/cross-vendor GPUs; CapCut-class mobile apps are free and handy for light use. We currently **support NVIDIA GPUs only**, and the bundle is large (app dir ≈4.6GB, mostly the PyTorch CUDA runtime) — non-NVIDIA support and super-res speed optimization are on the roadmap.

---

## 💻 System Requirements

- **Windows 10 / 11** (x64)
- **NVIDIA GPU** (required, CUDA):
  - Minimum: GTX 1660 6GB (1080p usable, slow)
  - Recommended: RTX 3060 8GB+ (smooth 1080p)
  - High-end: RTX 3080 / 4070+ (smooth 4K / 8K)
- Non-NVIDIA (AMD/Intel) is not supported yet
- (Running from source needs Python 3.11+, CUDA-enabled PyTorch)

---

## 📦 Installation

### Option 1: Installer (recommended)
Download **`VideoRefiner-setup.exe`** (~1.8GB, single file <2GB) from [GitHub Releases](https://github.com/FishyFiree/VideoRefiner/releases), run it (no admin needed — installs to the current user's folder), then launch `VideoRefiner` from the desktop / Start menu.

> AI models (~24MB interpolation, ~5MB+ super-res) are auto-downloaded on first run (HuggingFace mirror). If your antivirus flags the executable, that's a common PyInstaller false positive — add an exclusion or report it.
> Already on an older build? The AppId is the same, so you can upgrade directly (1.0.0 → 2.0.0); downloaded models live in `%APPDATA%\VideoRefiner\models` and survive uninstall (no re-download).

### Option 2: Portable zip
Download `VideoRefiner-windows.zip` (~2.9GB), unzip it and run `VideoRefiner.exe` (no installation needed).

### Option 3: Run from source
```bash
git clone https://github.com/FishyFiree/VideoRefiner.git
cd VideoRefiner
pip install -e .
python -m videorefiner.gui        # launch GUI
# or CLI:
python -m videorefiner.cli in.mp4 --fps 120 -o out.mp4
```
Requires Python 3.11+ and a CUDA-enabled PyTorch (`pip install torch --index-url https://download.pytorch.org/whl/cu128`).

---

## 🎬 Usage

**GUI**: add one or more videos → set **target frame rate** (default 120) and **target resolution** (default "no upscale = source resolution", optionally 2K/4K/8K) → pick a super-res model (general/anime) and codec/quality → start → the serial queue processes them one by one (status shows "stage: interpolate → upscale" + progress + ETA) → double-click a "done" item to compare original vs result.

**CLI**:
```bash
# Interpolation only (60→120)
videorefiner input.mp4 --fps 120 -o output.mp4

# Super-resolution only to 4K (set --fps to the source frame rate)
videorefiner input.mp4 --fps 60 --resolution 3840 -o output.mp4

# Interpolate to 120 then upscale to 4K (composite, aspect-preserving)
videorefiner input.mp4 --fps 120 --resolution 3840 -o output.mp4

# Specify codec / quality / scene threshold / super-res model
videorefiner input.mp4 --fps 240 --codec h264 --quality high -o output.mp4
videorefiner input.mp4 --fps 120 --resolution 2560 --model realesrgan -o output.mp4
```

> Note: `--resolution` uses the "target long edge" (2560=2K / 3840=4K / 7680=8K). The resolution target must be `≥` the source size and the frame-rate target `≥` the source frame rate; equal → that stage is skipped. The target resolution is scaled **proportionally from the source** (no stretch), with even width/height (required by yuv420p). The GUI auto-filters resolution presets to `≥` the source and validates parameters in real time to avoid pointless processed jobs.

---

## ⚡ Performance (measured on RTX 4060 Laptop 8GB, torch 2.11+cu128)

### Interpolation (RIFE, fp16)
| Resolution | Per-frame interpolation | Processing speed |
|---|---|---|
| 640×360 | 27 ms | 37 fps |
| 1280×720 | 36 ms | 28 fps |
| 1920×1080 | 70 ms | 14.4 fps |
| 3840×2160 | 320 ms | 3.1 fps |

### Super-resolution (Real-ESRGAN, per-frame; dominates the composite pipeline)
| Target | Model | `tile` | Per-frame | Rate |
|---|---|---|---|---|
| 1080p→4K (exact 2×) | RealESRGAN_x2plus | 384 (auto) | ≈4.3 s | ≈0.23 fps |
| 1080p→4K (exact 2×) | RealESRGAN_x2plus | 256 | ≈6.9 s | ≈0.14 fps |
| 4K (x4 round-trip, non-integer) | realesr-general-wdn-x4v3 | auto | slower | — |

### Composite end-to-end
For a 640×360 clip doing "interpolate 30→60 + upscale to 1280×720", 16 source frames → 32 frames took ≈**39s** (vs ≈**7.3s** for the interpolate-only v1 baseline) — **super-resolution dominates** and is offline heavy lifting (not real-time). 4K/8K targets are dramatically slower; a high-end GPU is recommended. A larger `tile` (when VRAM allows) is faster; use 384 for 4K.

> Note: interpolation is unchanged from v1; super-resolution is the bottleneck (~0.14–0.23 fps for 1080p→4K). The GUI's progress/ETA is estimated from measured frame rates.

---

## 🔧 How It Works

1. Decode the source (PyAV); map every output frame to a source frame pair and in-between position (`alpha`) by timestamps
2. Run RIFE single-step interpolation per pair (arbitrary `alpha` ⇒ arbitrary rate multiplier); when consecutive source frames differ beyond a threshold (scene cut), reuse the source frame directly to avoid ghosting
3. **(optional super-res)** run Real-ESRGAN on each output frame to the target resolution — auto tiling, fp16, auto tile reduction on OOM; integer scale uses the native scale, non-integer rounds up then resizes back ("round-trip")
4. Re-encode the output (x264/x265, audio passthrough) with atomic temp-file finalization; fully frame-level in-memory streaming (no intermediate re-encode)

---

## ⚙️ Resolution & Scale Notes (aspect-preserving)

- The resolution target is expressed as a "**target long edge**" (no upscale / 2K=2560 / 4K=3840 / 8K=7680).
- The output = source scaled **proportionally** to that long edge: aspect ratio strictly unchanged (vertical / 4:3 / square sources stay undistorted).
- **Integer scale** (e.g. 1080p→4K = exact 2×) uses the model's native scale (`RealESRGAN_x2plus`), best quality.
- **Non-integer scale** (e.g. vertical 1080×1920→"4K" ≈3.56×, 720p→2K ≈1.33×) uses "bicubic round-trip + model refinement": the model first upscales natively (x4), then resizes back to the target long edge — versatile, slightly lower quality.

---

## 🛠️ Building

```bash
python build.py              # PyInstaller one-dir + zip
python build.py --installer  # also compile the Inno Setup installer (~1.8GB, single file <2GB)
```

> The app dir is ≈4.6GB (mostly the PyTorch CUDA runtime); the zip is ≈2.9GB (GitHub Releases caps single files at 2GB, so the installer is the recommended artifact). The installer wizard is currently English (the app UI is Chinese); a Simplified-Chinese wizard language file can be added later. Super-res architectures are vendored (`videorefiner/sr_archs.py`), so **no extra basicsr/realesrgan/cv2 dependencies are bundled**.

---

## 📄 License & Credits

- This project: **MIT License** (see `LICENSE`)
- Interpolation engine [RIFE](https://github.com/hzwer/ECCV2022-RIFE) ([Practical-RIFE](https://github.com/hzwer/Practical-RIFE)): MIT, by hzwer et al.; vendored under `third_party/` (see [third_party/README.md](third_party/README.md))
- Super-resolution engine [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) (v0.3.x): BSD-3-Clause (code + pretrained weights both commercially usable); architectures vendored at `videorefiner/sr_archs.py`
- Pretrained models: interpolation `rife4.26.pkl` from [hzwer/RIFE](https://huggingface.co/hzwer/RIFE) (HuggingFace); super-res models (`realesr-general-wdn-x4v3` etc.) from [xinntao/Real-ESRGAN Releases](https://github.com/xinntao/Real-ESRGAN/releases) (HuggingFace mirror)
- **When distributing commercially, keep the model attributions.**

---

## 🚧 Limitations & Roadmap

- **Super-resolution is offline heavy lifting (not real-time)**: ≈0.14–0.23 fps for 1080p→4K; `tile` tuning can help
- **Per-frame super-resolution can cause slight temporal flicker** (inherent to SISR, especially fine text/subtitles): temporal-consistency post-processing planned
- **NVIDIA GPUs only**: non-NVIDIA support (ncnn backend) planned
- **4K/8K interpolation/upscaling needs a high-end GPU** (RTX 3080/4070+)
- **Large bundle** (app dir ≈4.6GB, mostly PyTorch CUDA): size optimization planned
- Performance roadmap: NVENC hardware encoding, TensorRT engine, batch optimization, super-res tile tuning
- No resume for interrupted jobs yet

---

Questions or suggestions? Open an [Issue](https://github.com/FishyFiree/VideoRefiner/issues)!
