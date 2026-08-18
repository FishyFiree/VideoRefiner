"""CLI 薄壳：videorefiner <输入> --fps <目标帧率> -o <输出>"""

from __future__ import annotations

import argparse
import sys

from .pipeline import Cancelled, run


def _progress_to_stderr(done: int, total: int) -> None:
    pct = done / total * 100
    sys.stderr.write(f"\r进度: {pct:5.1f}% ({done}/{total} 帧)")
    sys.stderr.flush()
    if done >= total:
        sys.stderr.write("\n")


def _make_engine(name: str):
    if name == "rife":
        from . import models as models_mod
        from .rife import RifeEngine

        if models_mod.find_local_model() is None:
            print("首次运行将自动下载 RIFE 模型（约 15MB，HuggingFace 镜像）……", file=sys.stderr)
        return RifeEngine()
    from .engine import BlendEngine

    return BlendEngine()


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="videorefiner",
        description="AI 视频插帧：输入任意帧率视频，输出更高帧率（默认 60→120fps），只插帧不改画面内容。",
    )
    parser.add_argument("input", help="输入视频路径")
    parser.add_argument("--fps", type=float, required=True, help="目标帧率（如 120）")
    parser.add_argument("-o", "--output", required=True, help="输出视频路径")
    parser.add_argument(
        "--codec", choices=["h264", "h265"], default="h265",
        help="输出编码（默认 h265；NVENC 硬件加速待后续版本）",
    )
    parser.add_argument(
        "--quality", choices=["high", "balanced", "small"], default="balanced",
        help="质量预设：high / balanced / small（默认 balanced）",
    )
    parser.add_argument(
        "--engine", choices=["blend", "rife"], default="rife",
        help="插帧引擎：rife（AI 光流，默认）/ blend（帧混合，调试用）",
    )
    parser.add_argument(
        "--scene-threshold", type=float, default=30.0, metavar="FLOAT",
        help="场景切换检测阈值（平均绝对像素差，0-255；设 0 关闭保护）",
    )
    args = parser.parse_args(argv)

    try:
        result = run(
            args.input,
            args.output,
            args.fps,
            codec=args.codec,
            quality=args.quality,
            engine=_make_engine(args.engine),
            progress_cb=_progress_to_stderr,
            scene_threshold=args.scene_threshold or None,
        )
    except Cancelled:
        print("已取消。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    print(
        f"完成: {result.input_path} ({result.source_fps:g}fps, {result.source_frames} 帧) "
        f"→ {result.output_path} ({result.target_fps:g}fps, {result.output_frames} 帧)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
