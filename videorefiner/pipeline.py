"""核心管线：编排 解码 → 重映射 → 插帧 → 编码 → 音频直通。

流式处理：边解码边插帧边编码，内存只保留当前帧对；输出先写 <output>.part，
成功完成后原子改名为最终文件（取消/失败时清理临时文件）。

S4 增强：
- 轻量场景切换保护（默认开启，阈值可配）：相邻源帧差异超阈值时，该帧对的插值
  帧直接拷贝新场景帧（避免跨场景插值鬼影）
- 60→120（精确 2x）快速路径：交替 copy/interp 专用循环 + 分批 interpolate_batch，
  顺序保证、省去通用路径的逐帧计划开销
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np

from . import av_io
from .engine import BlendEngine, FrameInterpolator, Upscaler
from .remapper import is_scene_cut, plan_output_frames
from .scale import compute_target_size

# 帧率比较容差（浮点源帧率；目标需要 ≥ 源帧率）
_FPS_EPS = 1e-9


class Cancelled(Exception):
    """处理被用户取消。"""


@dataclass
class PipelineResult:
    input_path: str
    output_path: str
    source_fps: float
    target_fps: float
    source_frames: int
    output_frames: int


ProgressCallback = Callable[[int, int], None]  # (done, total)
CancelCheck = Callable[[], bool]

DEFAULT_SCENE_THRESHOLD = 30.0  # 平均绝对像素差阈值（0-255）


def _is_exact_2x(src_fps: float, dst_fps: float) -> bool:
    return abs(dst_fps - 2.0 * src_fps) <= 1e-6 * max(1.0, abs(dst_fps))


def plan_pipeline_stages(
    target_fps: float,
    src_fps: float,
    target_resolution: Optional[Tuple[int, int]],
    src_resolution: Tuple[int, int],
) -> List[str]:
    """按两个目标生成阶段序列 ``[interpolate?, upscale?]``。

    - 帧率目标 > 源帧率 → 含 ``interpolate``
    - 分辨率目标 != 源分辨率 → 含 ``upscale``
    - 两者都等于源值 → 抛 ``ValueError("参数与原视频一致，请修改")``
    - 顺序恒为 ``interpolate`` → ``upscale``（先插帧原生分辨率，再超分）
    """
    target_resolution = target_resolution or src_resolution
    needs_interp = target_fps > src_fps + _FPS_EPS
    needs_upscale = tuple(target_resolution) != tuple(src_resolution)
    if not needs_interp and not needs_upscale:
        raise ValueError("参数与原视频一致，请修改")
    stages: List[str] = []
    if needs_interp:
        stages.append("interpolate")
    if needs_upscale:
        stages.append("upscale")
    return stages


def run(
    input_path: str,
    output_path: str,
    target_fps: float,
    codec: str = "h265",
    quality: str = "balanced",
    engine: Optional[FrameInterpolator] = None,
    progress_cb: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCheck] = None,
    scene_threshold: Optional[float] = DEFAULT_SCENE_THRESHOLD,
    use_fast_path: bool = True,
    unload_engine: bool = True,
    *,
    target_resolution: Optional[Tuple[int, int]] = None,
    target_edge: Optional[int] = None,
    upscaler: Optional[Upscaler] = None,
) -> PipelineResult:
    """端到端处理管线（v2 可组合：插帧 / 超分 / 两者）。

    ``target_resolution`` 为 (out_w, out_h)；``target_edge`` 为"档位长边"
    （二选一，``target_edge`` 优先内部调用 :func:`compute_target_size`）。
    只插帧完全复用 v1 路径；两者都等于源值时抛 ``ValueError``。
    输出先写 <output>.part，完成后原子改名。
    """
    from .upscaler import RealESRGANUpscaler  # 迟到导入：避免无超分使用时引入 torch 推理栈开销

    if engine is None:
        engine = BlendEngine()

    session = av_io.open_input(input_path)
    info = session.info
    source_fps = info.fps
    src_w, src_h = info.width, info.height

    if target_fps < source_fps - _FPS_EPS:
        session.close()
        raise ValueError(f"目标帧率 {target_fps:g} 必须大于等于源帧率 {source_fps:g}")

    # 解析目标分辨率：显式 (out_w,out_h) 或目标长边（内部等比计算）
    if target_resolution is not None:
        target_resolution = (int(target_resolution[0]), int(target_resolution[1]))
    elif target_edge is not None:
        target_resolution = compute_target_size(src_w, src_h, target_edge)

    effective_res = None
    if target_resolution is not None and target_resolution != (src_w, src_h):
        effective_res = target_resolution

    stages = plan_pipeline_stages(target_fps, source_fps, effective_res, (src_w, src_h))
    needs_interp = "interpolate" in stages
    needs_up = "upscale" in stages
    out_w, out_h = effective_res or (src_w, src_h)

    if needs_interp:
        engine.load()
    if needs_up:
        if upscaler is None:
            upscaler = RealESRGANUpscaler(progress_cb=getattr(engine, "download_progress_cb", None))
        upscaler.load()

    def write(frame: np.ndarray) -> None:
        if needs_up:
            frame = upscaler.upscale(frame, out_w, out_h)
        out.write_frame(frame)

    out = av_io.OutputSession(
        output_path,
        target_fps,
        out_w,
        out_h,
        codec=codec,
        quality=quality,
        audio_template=session.audio_stream,
    )

    try:
        if needs_interp and use_fast_path and _is_exact_2x(source_fps, target_fps):
            batch_size = getattr(engine, "batch_limit", 8)
            plan = list(plan_output_frames(source_fps, target_fps, info.frame_count))
            _run_2x_streaming(
                session, out, engine, info.frame_count, len(plan),
                write, progress_cb, should_cancel, scene_threshold, batch_size,
            )
        else:
            # 只超分：目标帧率 == 源帧率 → 1:1 复制源帧，逐帧超分
            plan = list(
                plan_output_frames(source_fps, target_fps, info.frame_count)
                if needs_interp
                else plan_output_frames(source_fps, source_fps, info.frame_count)
            )
            _run_streaming(
                session, out, engine, plan, len(plan),
                write, progress_cb, should_cancel, scene_threshold,
            )
        result_path = out.finish()
    except Cancelled:
        out.abort()
        raise
    except Exception:
        out.abort()
        raise
    finally:
        session.close()
        if unload_engine and needs_interp:
            engine.unload()
        if unload_engine and needs_up:
            upscaler.unload()

    return PipelineResult(
        input_path=input_path,
        output_path=result_path,
        source_fps=source_fps,
        target_fps=target_fps,
        source_frames=info.frame_count,
        output_frames=len(plan),
    )


def _run_streaming(
    session: av_io.InputSession,
    out: av_io.OutputSession,
    engine: FrameInterpolator,
    plan: List,
    total: int,
    write: Callable[[np.ndarray], None],
    progress_cb: Optional[ProgressCallback],
    should_cancel: Optional[CancelCheck],
    scene_threshold: Optional[float],
) -> None:
    """通用路径：按源帧顺序解码并尽可能早地生成输出帧；内存仅缓存最近 1~2 帧。

    每个即将写出的帧先经过 ``write``（可能做超分变换），再交给编码器。
    """
    decoded: List[np.ndarray] = []
    base = 0
    next_emit = 0

    def emit_all_possible() -> None:
        nonlocal next_emit, base
        while next_emit < total:
            e = plan[next_emit]
            need = e.k if e.copy else e.k + 1
            if need > base + len(decoded) - 1:
                break
            if e.copy:
                write(decoded[e.k - base])
            else:
                fa = decoded[e.k - base]
                fb = decoded[e.k + 1 - base]
                if scene_threshold is not None and is_scene_cut(fa, fb, scene_threshold):
                    # 场景切换：直接拷贝新场景帧，避免跨场景插值鬼影
                    write(fb.copy())
                else:
                    write(engine.interpolate(fa, fb, e.alpha))
            next_emit += 1
            if progress_cb:
                progress_cb(next_emit, total)
            if should_cancel and should_cancel():
                raise Cancelled()
        if next_emit < total:
            keep_from = plan[next_emit].k
            drop = keep_from - base
            if drop > 0:
                del decoded[:drop]
                base = keep_from

    try:
        for packet in session.container.demux():
            if packet.stream.type == "audio":
                out.mux_audio_packet(packet)
            elif packet.stream.type == "video":
                for frame in packet.decode():
                    nd = frame.to_ndarray(format="rgb24")
                    decoded.append(nd)
                    emit_all_possible()
    finally:
        emit_all_possible()  # 末帧保持条目在此补齐


def _run_2x_streaming(
    session: av_io.InputSession,
    out: av_io.OutputSession,
    engine: FrameInterpolator,
    est_frames: int,
    total: int,
    write: Callable[[np.ndarray], None],
    progress_cb: Optional[ProgressCallback],
    should_cancel: Optional[CancelCheck],
    scene_threshold: Optional[float],
    batch_size: int,
) -> None:
    """2x 快速路径。

    输出序列（N 源帧 → 2N 输出）：c0,i0,c1,i1,…,c_{N-2},i_{N-2},c_{N-1},c_{N-1}。
    interp 帧按 batch_size 分批走 ``interpolate_batch``（顺序保证：输出序号决定
    取 copies/interps 字典中的哪一帧，谁先就绪谁先出）。
    """
    copies: dict[int, np.ndarray] = {}
    interps: dict[int, np.ndarray] = {}
    pending: list[tuple[int, np.ndarray, np.ndarray]] = []
    emitted = 0
    frame_count = 0
    finished = False
    last: Optional[np.ndarray] = None

    def emit_all() -> None:
        nonlocal emitted
        while True:
            n = emitted
            if n >= 2 * frame_count:
                break
            if n % 2 == 0:
                k = n // 2
                if k >= frame_count:
                    break
                f = copies.get(k)
            else:
                k = (n - 1) // 2
                if k <= frame_count - 2:
                    f = interps.get(k)
                elif finished:
                    f = copies.get(frame_count - 1)  # 末帧保持（流已结束）
                else:
                    f = None
            if f is None:
                break
            write(f)
            emitted += 1
            if progress_cb:
                progress_cb(emitted, total)
            if should_cancel and should_cancel():
                raise Cancelled()

    def flush_batch() -> None:
        nonlocal pending
        if not pending:
            return
        pairs = [(fa, fb) for _, fa, fb in pending]
        results = engine.interpolate_batch(pairs, [0.5] * len(pending))
        for (k, _, _), res in zip(pending, results):
            interps[k] = res
        pending = []
        emit_all()

    try:
        for packet in session.container.demux():
            if packet.stream.type == "audio":
                out.mux_audio_packet(packet)
            elif packet.stream.type == "video":
                for frame in packet.decode():
                    nd = frame.to_ndarray(format="rgb24")
                    k = frame_count
                    frame_count += 1
                    copies[k] = nd
                    if last is not None:
                        pk = k - 1
                        if scene_threshold is not None and is_scene_cut(last, nd, scene_threshold):
                            interps[pk] = nd  # 场景切换：中间帧 = 新场景帧
                        else:
                            pending.append((pk, last, nd))
                            if len(pending) >= batch_size:
                                flush_batch()
                    last = nd
                    emit_all()
    finally:
        finished = True
        flush_batch()
        emit_all()  # 末帧保持依赖 copies[frame_count-1]，此时已就绪
