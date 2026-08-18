"""PyAV 输入/输出：解码、编码、封装、音频直通。

PRD 决策：核心管线用 PyAV 进程内解码/编码/封装（wheel 自带 FFmpeg 库）；
内置 ffmpeg 二进制保留给 GUI 播放对比用。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

import av
import numpy as np

# 质量预设 → (preset, crf 表)。PRD：默认软件编码，CRF 20/22（均衡档）。
QUALITY_PRESETS = {
    "high":     {"preset": "slow",   "crf": {"h264": 18, "h265": 20}},
    "balanced": {"preset": "medium", "crf": {"h264": 20, "h265": 22}},
    "small":    {"preset": "fast",   "crf": {"h264": 24, "h265": 26}},
}
CODECS = {"h264": "libx264", "h265": "libx265"}
# 注：NVENC 硬件编码（h264_nvenc / hevc_nvenc）在实测环境中驱动层不可用，
# 作为可选加速项留待后续（见 S7 报告）；实现时按 codec.endswith("_nvenc")
# 走 {'preset': 'p4', 'cq': '24'} 参数路径即可。


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    frame_count: int  # 估算（部分容器实际帧数未知时按时长推算）
    has_audio: bool


@dataclass
class InputSession:
    container: av.container.InputContainer
    video_stream: av.VideoStream
    audio_stream: Optional[av.AudioStream]
    info: VideoInfo

    def close(self) -> None:
        self.container.close()


def open_input(path: str) -> InputSession:
    container = av.open(path)
    video = next((s for s in container.streams if s.type == "video"), None)
    if video is None:
        container.close()
        raise ValueError(f"输入文件没有视频流: {path}")
    audio = next((s for s in container.streams if s.type == "audio"), None)

    fps = float(video.average_rate) if video.average_rate else 30.0
    frame_count = int(video.frames) if video.frames else 0
    if frame_count <= 0:
        # 部分容器未知总帧数：按时长（微秒）推算
        duration_us = container.duration
        if duration_us:
            frame_count = max(1, round(duration_us / 1_000_000 * fps))

    info = VideoInfo(
        width=video.codec_context.width,
        height=video.codec_context.height,
        fps=fps,
        frame_count=frame_count,
        has_audio=audio is not None,
    )
    return InputSession(container, video, audio, info)


class OutputSession:
    """输出封装：写视频帧 + 音频直通 + .part 原子收尾。"""

    def __init__(
        self,
        path: str,
        fps: float,
        width: int,
        height: int,
        codec: str = "h265",
        quality: str = "balanced",
        audio_template: Optional[av.AudioStream] = None,
    ):
        self.final_path = path
        self.part_path = path + ".part"
        self.container = av.open(self.part_path, "w", format="mp4")
        params = QUALITY_PRESETS[quality]
        codec_name = CODECS[codec]

        self.video_stream = self.container.add_stream(
            codec_name, rate=Fraction(str(fps)).limit_denominator(10000)
        )
        self.video_stream.width = width
        self.video_stream.height = height
        self.video_stream.codec_context.pix_fmt = "yuv420p"
        self.video_stream.codec_context.options = {
            "preset": params["preset"],
            "crf": str(params["crf"][codec]),
        }

        self.audio_stream = None
        if audio_template is not None:
            self.audio_stream = self.container.add_stream_from_template(audio_template)

        self._frame_index = 0
        self._started = False

    def _ensure_started(self) -> None:
        if not self._started:
            start = getattr(self.container, "start_encoding", None)
            if start is not None:
                start()
            self._started = True

    def write_frame(self, frame_rgb: np.ndarray) -> None:
        """写入一帧 RGB uint8 (H, W, 3)。"""
        self._ensure_started()
        frame = av.VideoFrame.from_ndarray(frame_rgb, format="rgb24")
        frame.pts = self._frame_index
        self._frame_index += 1
        for packet in self.video_stream.encode(frame):
            self.container.mux(packet)

    def mux_audio_packet(self, packet: av.Packet) -> None:
        """音频直通：把输入音频包改指向输出音频流后 mux（不重编码）。"""
        if self.audio_stream is None:
            return
        self._ensure_started()
        packet.stream = self.audio_stream
        self.container.mux(packet)

    def finish(self) -> str:
        """冲刷编码器、关闭容器、原子改名为最终文件。返回最终路径。"""
        self._ensure_started()
        for packet in self.video_stream.encode():
            self.container.mux(packet)
        self.container.close()
        if os.path.exists(self.final_path):
            os.remove(self.final_path)
        os.replace(self.part_path, self.final_path)
        return self.final_path

    def abort(self) -> None:
        """取消/失败：清理临时文件。"""
        try:
            self.container.close()
        except Exception:
            pass
        if os.path.exists(self.part_path):
            os.remove(self.part_path)
