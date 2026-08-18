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
from typing import Callable, List, Optional

import numpy as np

from . import av_io
from .engine import BlendEngine, FrameInterpolator
from .remapper import is_scene_cut, plan_output_frames


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
) -> PipelineResult:
    """端到端插帧。输出先写 <output>.part，完成后原子改名。

    unload_engine=False 时模型保持常驻（批量队列复用同一引擎，避免重复加载）。
    """
    if engine is None:
        engine = BlendEngine()
    engine.load()

    session = av_io.open_input(input_path)
    info = session.info
    source_fps = info.fps
    if target_fps <= source_fps:
        session.close()
        engine.unload()
        raise ValueError(f"目标帧率 {target_fps:g} 必须大于源帧率 {source_fps:g}")

    plan = list(plan_output_frames(source_fps, target_fps, info.frame_count))
    total = len(plan)

    out = av_io.OutputSession(
        output_path,
        target_fps,
        info.width,
        info.height,
        codec=codec,
        quality=quality,
        audio_template=session.audio_stream,
    )

    try:
        if use_fast_path and _is_exact_2x(source_fps, target_fps):
            batch_size = getattr(engine, "batch_limit", 8)
            _run_2x_streaming(
                session, out, engine, info.frame_count, total,
                progress_cb, should_cancel, scene_threshold, batch_size,
            )
        else:
            _run_streaming(
                session, out, engine, plan, total,
                progress_cb, should_cancel, scene_threshold,
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
        if unload_engine:
            engine.unload()

    return PipelineResult(
        input_path=input_path,
        output_path=result_path,
        source_fps=source_fps,
        target_fps=target_fps,
        source_frames=info.frame_count,
        output_frames=total,
    )


def _run_streaming(
    session: av_io.InputSession,
    out: av_io.OutputSession,
    engine: FrameInterpolator,
    plan: List,
    total: int,
    progress_cb: Optional[ProgressCallback],
    should_cancel: Optional[CancelCheck],
    scene_threshold: Optional[float],
) -> None:
    """通用路径：按源帧顺序解码并尽可能早地生成输出帧；内存仅缓存最近 1~2 帧。"""
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
                out.write_frame(decoded[e.k - base])
            else:
                fa = decoded[e.k - base]
                fb = decoded[e.k + 1 - base]
                if scene_threshold is not None and is_scene_cut(fa, fb, scene_threshold):
                    # 场景切换：直接拷贝新场景帧，避免跨场景插值鬼影
                    out.write_frame(fb.copy())
                else:
                    out.write_frame(engine.interpolate(fa, fb, e.alpha))
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
            out.write_frame(f)
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
