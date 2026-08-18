"""VideoRefiner — AI 视频插帧工具核心库。

输入任意帧率视频，输出更高帧率（如 60→120fps）；只插入新帧、不改动画面内容
（语义不变，输出整体重编码）。详见 PRD（.scratch/video-interpolation/PRD.md）。
"""

__version__ = "0.1.0"
