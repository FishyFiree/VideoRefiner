"""PySide6 桌面外壳（S5 单文件 + S6 串行批量队列 + 对比播放 + v2 超分）。

结构（PRD 决策）：核心管线独立库 + CLI 薄壳 + GUI 外壳。
处理在 QThread 中执行（不卡界面）；进度/状态经信号回传（排队连接）。

v2（V2-4）：分辨率动态预设下拉（不超分/2K/4K/8K，过滤 ≥ 源长边）、超分模型选择
（通用/动漫）、实时校验（帧率与分辨率都等于源值 → 红字提示 + 禁用开始）、
分阶段进度提示（阶段：插帧 → 超分）+ 4K/8K 警告。
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QSizeF, QThread, Qt, Signal, QUrl
from PySide6.QtGui import QIcon, QPainter
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtMultimediaWidgets import QGraphicsVideoItem

from . import av_io
from .pipeline import Cancelled
from .scale import compute_target_size
from .pipeline import plan_pipeline_stages

VIDEO_EXTS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v",
    ".ts", ".flv", ".wmv", ".mpg", ".mpeg",
}
QUALITY_NAMES = {"均衡": "balanced", "高质量": "high", "小体积": "small"}
CODEC_NAMES = {"H.265（推荐）": "h265", "H.264": "h264"}

# 分辨率预设（"档位长边"）：None = 不超分（= 源分辨率）
RES_PRESETS = [
    ("不超分（= 源分辨率）", None),
    ("2K（2560）", 2560),
    ("4K（3840）", 3840),
    ("8K（7680）", 7680),
]
# 超分模型预设
SR_MODEL_NAMES = {"通用（默认）": "realesr-general-wdn-x4v3", "动漫": "RealESRGAN_x4plus_anime_6B"}

PROJECT_URL = "https://github.com/FishyFiree/VideoRefiner"


def _fmt_seconds(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def _long_edge(w: int, h: int) -> int:
    return max(int(w), int(h))


def _res_presets_for(source_edge: int | None) -> list[tuple[str, int | None]]:
    """针对源长边过滤分辨率预设：不超分 + 只保留 > 源长边的档位（PRD/03）。

    ``source_edge`` 为 None（未知）时返回全部。
    """
    out: list[tuple[str, int | None]] = [("不超分（= 源分辨率）", None)]
    for label, edge in RES_PRESETS[1:]:
        if source_edge is None or edge > source_edge:
            out.append((label, edge))
    return out


def _item_is_noop(target_fps: float, target_edge: int | None, src_fps: float, src_w: int, src_h: int) -> bool:
    """判断该文件在给定目标下是否"无任何操作"（插帧与超分都会被跳过）。"""
    effective = None
    if target_edge is not None:
        res = compute_target_size(src_w, src_h, target_edge)
        if res != (src_w, src_h):
            effective = res
    try:
        stages = plan_pipeline_stages(target_fps, src_fps, effective, (src_w, src_h))
    except ValueError:
        return True  # 两者都等于源值 → 无操作
    return not stages


class QueueItem:
    """队列中的一个文件项。"""

    def __init__(self, path: str, label: str, output: str):
        self.path = path
        self.label = label       # 列表显示文本（名称+信息）
        self.output = output
        self.status = "等待"     # 等待/处理中/完成/失败/已取消
        self.src_fps: float | None = None   # 源帧率
        self.src_w: int | None = None       # 源宽
        self.src_h: int | None = None       # 源高


class BatchWorker(QObject):
    """在 QThread 中串行执行整个队列；模型只加载一次、常驻。"""

    status = Signal(str)              # 模型下载/加载等状态
    item_started = Signal(int, str)   # (index, 显示名)
    item_progress = Signal(int, int, int)  # (index, done, total)
    item_done = Signal(int, str)      # (index, 输出路径)
    item_failed = Signal(int, str)    # (index, 错误信息)
    item_cancelled = Signal(int)      # (index)
    queue_finished = Signal(dict)     # {"ok": n, "fail": n, "cancelled": n, "skipped": n}

    def __init__(
        self,
        items: list[QueueItem],
        target_fps: int,
        codec: str,
        quality: str,
        scene_threshold: float,
        target_edge: int | None = None,
        sr_model: str = "realesr-general-wdn-x4v3",
        parent=None,
    ):
        super().__init__(parent)
        self.items = items
        self.target_fps = target_fps
        self.codec = codec
        self.quality = quality
        self.scene_threshold = scene_threshold
        self.target_edge = target_edge
        self.sr_model = sr_model
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def _load_engines(self, need_interp: bool, need_upscale: bool):
        """按需加载插帧/超分引擎（各一次、常驻；不同时驻留多个超分权重）。"""
        from .rife import RifeEngine
        from .upscaler import RealESRGANUpscaler

        if need_interp and self._engine is None:
            self.status.emit("正在加载插帧模型…")
            self._engine = RifeEngine(download_progress_cb=self._on_model_progress)
            self._engine.load()
        if need_upscale and self._upscaler is None:
            self.status.emit("正在加载超分模型…")
            self._upscaler = RealESRGANUpscaler(
                model_name=self.sr_model, download_progress_cb=self._on_model_progress
            )
            self._upscaler.load()
        return need_interp, need_upscale

    def run(self) -> None:
        import av  # PyAV（判断源信息）

        from .pipeline import run as pipeline_run

        self._engine = None
        self._upscaler = None
        stats = {"ok": 0, "fail": 0, "cancelled": 0, "skipped": 0}
        try:
            for i, item in enumerate(self.items):
                if self._cancel.is_set():
                    item.status = "等待"
                    stats["skipped"] += 1
                    continue
                self.item_started.emit(i, item.label)
                item.status = "处理中"
                try:
                    # 探测源信息 + 计算阶段
                    sess = av.open(item.path)
                    v = next((s for s in sess.streams if s.type == "video"), None)
                    if v is None:
                        raise ValueError("输入文件没有视频流")
                    src_fps = float(v.average_rate) if v.average_rate else 30.0
                    src_w, src_h = v.codec_context.width, v.codec_context.height
                    sess.close()

                    effective_res = None
                    if self.target_edge is not None:
                        res = compute_target_size(src_w, src_h, self.target_edge)
                        if res != (src_w, src_h):
                            effective_res = res
                    try:
                        stages = plan_pipeline_stages(self.target_fps, src_fps, effective_res, (src_w, src_h))
                    except ValueError:
                        item.status = "跳过（参数与原视频一致）"
                        stats["skipped"] += 1
                        continue
                    if not stages:
                        item.status = "跳过（参数与原视频一致）"
                        stats["skipped"] += 1
                        continue

                    need_interp = "interpolate" in stages
                    need_upscale = "upscale" in stages
                    self._load_engines(need_interp, need_upscale)

                    stage_desc = "插帧 → 超分" if (need_interp and need_upscale) else ("插帧" if need_interp else "超分")
                    self.status.emit(f"阶段：{stage_desc}")

                    result = pipeline_run(
                        item.path,
                        item.output,
                        self.target_fps,
                        codec=self.codec,
                        quality=self.quality,
                        engine=self._engine if need_interp else None,
                        upscaler=self._upscaler if need_upscale else None,
                        progress_cb=lambda d, t, _i=i: self.item_progress.emit(_i, d, t),
                        should_cancel=self._cancel.is_set,
                        scene_threshold=self.scene_threshold,
                        target_resolution=effective_res,
                        unload_engine=False,
                    )
                    item.status = "完成"
                    stats["ok"] += 1
                    self.item_done.emit(i, result.output_path)
                except Cancelled:
                    item.status = "已取消"
                    stats["cancelled"] += 1
                    self.item_cancelled.emit(i)
                    break  # 取消当前项后停止队列
                except Exception as exc:  # noqa: BLE001 —— 单文件失败继续下一个
                    item.status = "失败"
                    stats["fail"] += 1
                    self.item_failed.emit(i, f"{type(exc).__name__}: {exc}")
        finally:
            if self._engine is not None:
                self._engine.unload()
            if self._upscaler is not None:
                self._upscaler.unload()
        self.queue_finished.emit(stats)

    def _on_model_progress(self, done: int, total: int) -> None:
        if total:
            self.status.emit(f"正在下载模型… {done / total * 100:.0f}%")
        else:
            self.status.emit(f"正在下载模型… {done // (1024 * 1024)} MB")


class VideoView(QGraphicsView):
    """QGraphicsVideoItem 渲染路径（QVideoWidget 在本机 D3D11 下黑屏，此路径已验证可渲染）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._item = None
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing)
        self.setFrameShape(QFrame.Shape.StyledPanel)

    def attach_item(self, item: QGraphicsVideoItem) -> None:
        self._item = item
        self._scene.addItem(item)
        item.setSize(QSizeF(640, 360))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._item is not None:
            self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)


class CompareDialog(QDialog):
    """简版对比播放：双窗口对齐播放原视频与输出视频（共享进度条）。"""

    def __init__(self, original: str, output: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("对比播放 — 原视频 vs 处理结果")
        self.resize(1000, 620)
        self._seeking = False

        root = QVBoxLayout(self)
        row = QHBoxLayout()
        self.players: list[QMediaPlayer] = []
        self._views: list[VideoView] = []
        for path in (original, output):
            box = QVBoxLayout()
            box.addWidget(QLabel(Path(path).name))
            view = VideoView()
            item = QGraphicsVideoItem()
            view.attach_item(item)
            player = QMediaPlayer(self)
            audio = QAudioOutput(self)
            audio.setMuted(True)  # 对比以视觉为主，音频静音
            player.setAudioOutput(audio)
            player.setVideoOutput(item)
            player.setSource(QUrl.fromLocalFile(str(path)))
            self.players.append(player)
            self._views.append(view)
            box.addWidget(view)
            row.addLayout(box)
        root.addLayout(row)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.slider.sliderReleased.connect(self._seek_to)
        root.addWidget(self.slider)

        btn_row = QHBoxLayout()
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.clicked.connect(self._toggle_play)
        btn_row.addWidget(self.play_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        self._media_error = False
        self._ended = False
        for player in self.players:
            player.positionChanged.connect(self._sync_slider)
            player.errorOccurred.connect(self._on_media_error)
            player.mediaStatusChanged.connect(self._on_media_status)

    def _sync_slider(self, _pos: int) -> None:
        if self._seeking:
            return
        durs = [p.duration() for p in self.players if p.duration() > 0]
        dur = max(durs) if durs else 1
        pos = max(p.position() for p in self.players)
        self.slider.setValue(int(pos / dur * 1000))

    def _seek_to(self) -> None:
        durs = [p.duration() for p in self.players if p.duration() > 0]
        dur = max(durs) if durs else 1
        pos = int(self.slider.value() / 1000 * dur)
        for p in self.players:
            p.setPosition(pos)
        self._seeking = False

    def _toggle_play(self) -> None:
        if any(p.playbackState() == QMediaPlayer.PlaybackState.PlayingState for p in self.players):
            for p in self.players:
                p.pause()
            self.play_btn.setText("▶ 播放")
        else:
            self._ended = False
            for p in self.players:
                p.play()
            self.play_btn.setText("⏸ 暂停")

    def _on_media_status(self, status) -> None:
        """任一播放器播放到结尾：先暂停所有、再统一回卷到开头（只处理一次）。"""
        if status == QMediaPlayer.MediaStatus.EndOfMedia and not self._ended:
            self._ended = True
            for p in self.players:
                p.pause()
                p.setPosition(0)
            self.play_btn.setText("▶ 播放")
            self._sync_slider(0)

    def _on_media_error(self, _err, error_str: str) -> None:
        if not self._media_error:
            self._media_error = True
            QMessageBox.warning(
                self,
                "播放提示",
                f"有视频无法播放（{error_str}）。\n"
                "若为 H.265 输出，可改用 H.264 编码再处理（Windows 可能缺少 HEVC 解码）。",
            )


def _app_icon() -> QIcon:
    """应用图标（assets/icon.ico；打包产物中位于 _MEIPASS/assets/）。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    icon_path = base / "assets" / "icon.ico"
    icon = QIcon(str(icon_path))
    return icon if not icon.isNull() else QIcon()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoRefiner — AI 视频插帧 + 超分")
        self.setWindowIcon(_app_icon())
        self.setAcceptDrops(True)
        self.setMinimumWidth(600)

        self._thread: QThread | None = None
        self._worker: BatchWorker | None = None
        self._items: list[QueueItem] = []
        self._start_time = 0.0
        self._out_dir: str | None = None
        self._params_invalid = False

        self._build_ui()
        self._refresh_res_combo(None)  # 初始：全部档位
        self._validate_params()
        self._check_gpu()
        self._update_buttons()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # 队列
        queue_group = QGroupBox("处理队列")
        qg = QVBoxLayout(queue_group)
        self.queue_list = QListWidget()
        self.queue_list.itemDoubleClicked.connect(self._on_double_click)
        qg.addWidget(self.queue_list)
        q_row = QHBoxLayout()
        add_btn = QPushButton("添加文件…")
        add_btn.clicked.connect(self._browse)
        rm_btn = QPushButton("移除选中")
        rm_btn.clicked.connect(self._remove_selected)
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._clear_queue)
        self.compare_btn = QPushButton("对比播放")
        self.compare_btn.clicked.connect(self._compare_selected)
        q_row.addWidget(add_btn)
        q_row.addWidget(rm_btn)
        q_row.addWidget(clear_btn)
        q_row.addStretch(1)
        q_row.addWidget(self.compare_btn)
        qg.addLayout(q_row)
        root.addWidget(queue_group)

        # 参数
        param_group = QGroupBox("处理参数")
        form = QFormLayout(param_group)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(2, 1000)
        self.fps_spin.setValue(120)
        self.fps_spin.setSuffix(" fps")
        self.res_combo = QComboBox()
        self.res_combo.setToolTip("目标分辨率（档位长边）；选择「不超分」则保持源分辨率不变")
        self.sr_model_combo = _combo(SR_MODEL_NAMES)
        self.sr_model_combo.setToolTip(
            "超分模型：通用（写实视频/照片，默认）｜动漫（动漫/插画/线稿风格更贴合）。\n"
            "写实素材用「通用」、动漫素材用「动漫」，效果最佳；不确定就用默认。"
        )
        self.codec_combo = _combo(CODEC_NAMES)
        self.quality_combo = _combo(QUALITY_NAMES)
        out_row = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setReadOnly(True)
        self.out_edit.setPlaceholderText("留空 = 输出到各文件同目录")
        out_btn = QPushButton("选择目录…")
        out_btn.clicked.connect(self._choose_out_dir)
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(out_btn)
        form.addRow("目标帧率：", self.fps_spin)
        form.addRow("目标分辨率：", self.res_combo)
        form.addRow("超分模型：", self.sr_model_combo)
        form.addRow("输出编码：", self.codec_combo)
        form.addRow("质量预设：", self.quality_combo)
        form.addRow("输出目录：", out_row)
        # 实时校验提示（红字）
        self.param_hint = QLabel("")
        self.param_hint.setWordWrap(True)
        form.addRow("", self.param_hint)
        root.addWidget(param_group)

        # 参数变更 / 队列选择 → 更新提示与允许开始
        self.fps_spin.valueChanged.connect(self._on_param_changed)
        self.res_combo.currentIndexChanged.connect(self._on_param_changed)
        self.sr_model_combo.currentIndexChanged.connect(self._on_param_changed)
        self.queue_list.currentRowChanged.connect(self._on_selection_changed)

        # 进度
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_label = QLabel("就绪")
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        root.addWidget(self.progress_bar)
        root.addWidget(self.progress_label)
        root.addWidget(self.status_label)

        # 按钮
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("开始处理")
        self.start_btn.clicked.connect(self._start)
        self.cancel_btn = QPushButton("取消当前项")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setEnabled(False)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.cancel_btn)
        root.addLayout(btn_row)

        # 开源地址（可点击）
        footer = QLabel(
            f'<a href="{PROJECT_URL}" style="color:#9ca3af; text-decoration:none;">'
            f'本项目已开源：{PROJECT_URL.replace("https://", "")} ｜ 有问题欢迎提 Issue</a>'
        )
        footer.setOpenExternalLinks(True)
        root.addWidget(footer)

    # ---------- 队列操作 ----------

    def _current_edge(self) -> int | None:
        """读取目标分辨率下拉当前值（长边；None=不超分）。"""
        return self.res_combo.currentData() if self.res_combo.count() else None

    def _default_output(self, src_path: str, src_w: int | None = None, src_h: int | None = None) -> str:
        src = Path(src_path)
        edge = self._current_edge()
        name = f"{src.stem}_{self.fps_spin.value()}fps"
        if edge and (src_w is None or edge > _long_edge(src_w, src_h)):
            name += f"_{edge}px"
        name += ".mp4"
        if self._out_dir:
            return str(Path(self._out_dir) / name)
        return str(src.with_name(name))

    def _add_file(self, path: str) -> None:
        if Path(path).suffix.lower() not in VIDEO_EXTS:
            return
        item = QueueItem(path, "", "")
        try:
            sess = av_io.open_input(path)
            info = sess.info
            sess.close()
            dur = info.frame_count / info.fps if info.fps else 0
            label = f"{Path(path).name} ｜ {info.width}×{info.height} ｜ {info.fps:.3g}fps ｜ 约 {_fmt_seconds(dur)}"
            if info.width >= 3840 or info.height >= 2160:
                label += " ｜ ⚠4K（建议 RTX 3080/4070+）"
            item.src_fps = info.fps
            item.src_w = info.width
            item.src_h = info.height
        except Exception:
            label = f"{Path(path).name} ｜ 无法读取"
        item.label = label
        item.output = self._default_output(path, item.src_w, item.src_h)
        self._items.append(item)
        self._refresh_list()
        self._validate_params()

    def _refresh_list(self) -> None:
        self.queue_list.clear()
        for item in self._items:
            self.queue_list.addItem(QListWidgetItem(f"{item.status} ｜ {item.label}"))
        self._update_buttons()

    def _browse(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择视频（可多选）", "",
            "视频 (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.ts *.flv *.wmv)",
        )
        for f in files:
            self._add_file(f)

    def _remove_selected(self) -> None:
        for row in sorted({i.row() for i in self.queue_list.selectedItems()}, reverse=True):
            del self._items[row]
        self._refresh_list()
        self._validate_params()

    def _clear_queue(self) -> None:
        self._items.clear()
        self._refresh_list()
        self._reset_progress()
        self._validate_params()

    def _choose_out_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self._out_dir = d
            self.out_edit.setText(d)
            for item in self._items:
                item.output = self._default_output(item.path, item.src_w, item.src_h)

    # ---------- 参数提示 / 校验 ----------

    def _reference_item(self) -> QueueItem | None:
        """校验参考项：优先当前选中项，否则第一个待处理项。"""
        row = self.queue_list.currentRow()
        if 0 <= row < len(self._items):
            return self._items[row]
        for item in self._items:
            if item.status in ("等待", "失败", "已取消"):
                return item
        return None

    def _refresh_res_combo(self, reference: QueueItem | None) -> None:
        source_edge = _long_edge(reference.src_w, reference.src_h) if reference and reference.src_w else None
        presets = _res_presets_for(source_edge)
        current = self._current_edge()
        self.res_combo.blockSignals(True)
        self.res_combo.clear()
        for label, edge in presets:
            self.res_combo.addItem(label, edge)
        # 恢复原选择；若该档位不再可用（≤源长边）则回落到"不超分"
        idx = self.res_combo.findData(current)
        self.res_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.res_combo.blockSignals(False)

    def _validate_params(self) -> None:
        ref = self._reference_item()
        edge = self._current_edge()
        msg = ""
        invalid = False
        warn = False
        if ref is not None and ref.src_fps is not None:
            if self.fps_spin.value() < ref.src_fps - 1e-6:
                msg = f"目标帧率（{self.fps_spin.value()}）低于源帧率（{ref.src_fps:.3g}），请修改"
                invalid = True
            elif _item_is_noop(self.fps_spin.value(), edge, ref.src_fps, ref.src_w, ref.src_h):
                msg = "参数与原视频一致，请修改（帧率与分辨率都等于源值）"
                invalid = True
            elif edge is not None and edge >= 3840:
                msg = "⚠ 4K/8K 目标分辨率很吃显存与时间，建议 RTX 3080/4070+"
                warn = True
            elif _long_edge(ref.src_w, ref.src_h) >= 3840:
                msg = "⚠ 源为 4K，处理较慢，建议 RTX 3080/4070+"
                warn = True
        self._params_invalid = invalid
        if invalid:
            self.param_hint.setStyleSheet("color: #c00000;")
        elif warn:
            self.param_hint.setStyleSheet("color: #b06000;")
        else:
            self.param_hint.setStyleSheet("")
        self.param_hint.setText(msg)
        self._update_buttons()

    def _on_param_changed(self) -> None:
        # 参数变化：刷新待处理项的输出路径 + 校验
        for item in self._items:
            if item.status in ("等待", "失败", "已取消"):
                item.output = self._default_output(item.path, item.src_w, item.src_h)
        self._validate_params()

    def _on_selection_changed(self) -> None:
        self._refresh_res_combo(self._reference_item())
        self._validate_params()

    def _on_double_click(self, item) -> None:
        row = self.queue_list.row(item)
        if 0 <= row < len(self._items) and self._items[row].status == "完成":
            self._open_compare(row)

    def _compare_selected(self) -> None:
        rows = [self.queue_list.row(i) for i in self.queue_list.selectedItems()]
        if rows:
            self._open_compare(rows[0])

    def _open_compare(self, row: int) -> None:
        item = self._items[row]
        if not Path(item.output).is_file():
            QMessageBox.warning(self, "提示", "输出文件不存在")
            return
        try:
            dlg = CompareDialog(item.path, item.output, self)
        except RuntimeError as exc:
            QMessageBox.warning(self, "提示", str(exc))
            return
        dlg.exec()

    # ---------- 处理控制 ----------

    def _start(self) -> None:
        if not self._items:
            QMessageBox.warning(self, "提示", "请先添加视频文件")
            return
        if self._params_invalid:
            QMessageBox.warning(self, "提示", self.param_hint.text() or "参数无效，请修改后再开始")
            return
        if not any(i.status in ("等待", "失败", "已取消") for i in self._items):
            QMessageBox.information(self, "提示", "队列中没有待处理项目")
            return
        # 更新输出路径（用户可能改过帧率/目录）
        for item in self._items:
            if item.status in ("等待", "失败", "已取消"):
                item.output = self._default_output(item.path, item.src_w, item.src_h)

        self._thread = QThread(self)
        self._worker = BatchWorker(
            self._items,
            self.fps_spin.value(),
            codec=CODEC_NAMES[self.codec_combo.currentText()],
            quality=QUALITY_NAMES[self.quality_combo.currentText()],
            scene_threshold=30.0,
            target_edge=self._current_edge(),
            sr_model=SR_MODEL_NAMES[self.sr_model_combo.currentText()],
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.status.connect(self.status_label.setText)
        self._worker.item_started.connect(self._on_item_started)
        self._worker.item_progress.connect(self._on_item_progress)
        self._worker.item_done.connect(self._on_item_done)
        self._worker.item_failed.connect(self._on_item_failed)
        self._worker.item_cancelled.connect(self._on_item_cancelled)
        self._worker.queue_finished.connect(self._on_queue_finished)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._start_time = time.time()
        self.status_label.setText("")
        self._thread.start()
        self._update_buttons()

    def _cancel(self) -> None:
        if self._worker is not None:
            self.status_label.setText("正在取消当前项…")
            self._worker.cancel()

    def _on_item_started(self, idx: int, _label: str) -> None:
        self._items[idx].status = "处理中"
        self._refresh_list()
        self.progress_label.setText(f"处理第 {idx + 1}/{len(self._items)} 个：{Path(self._items[idx].path).name}")
        self.progress_bar.setValue(0)

    def _on_item_progress(self, idx: int, done: int, total: int) -> None:
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(done)
        pct = done / total * 100 if total else 0
        eta = ""
        if done > 0:
            elapsed = time.time() - self._start_time
            eta = f" ｜ 剩余约 {_fmt_seconds(elapsed * (total - done) / done)}"
        self.progress_label.setText(f"第 {idx + 1}/{len(self._items)} 个 ｜ {pct:.1f}% ｜ {done}/{total} 帧{eta}")

    def _on_item_done(self, idx: int, out_path: str) -> None:
        self._items[idx].status = "完成"
        self._refresh_list()

    def _on_item_failed(self, idx: int, msg: str) -> None:
        self._items[idx].status = "失败"
        self._refresh_list()
        self.status_label.setText(f"第 {idx + 1} 个失败：{msg}")

    def _on_item_cancelled(self, idx: int) -> None:
        self._items[idx].status = "已取消"
        self._refresh_list()

    def _on_queue_finished(self, stats: dict) -> None:
        self._stop_thread()
        self._reset_progress()
        self.progress_label.setText(
            f"完成 {stats['ok']} ｜ 失败 {stats['fail']} ｜ 取消 {stats['cancelled']}"
            + (f" ｜ 跳过 {stats['skipped']}" if stats["skipped"] else "")
        )
        self.status_label.setText("队列处理结束")
        if stats["ok"]:
            box = QMessageBox(self)
            box.setWindowTitle("处理完成")
            box.setText(
                f"队列处理完成：成功 {stats['ok']} 个，失败 {stats['fail']} 个。\n"
                "双击列表中的「完成」项可对比播放原视频与结果。"
            )
            box.addButton("确定", QMessageBox.ButtonRole.AcceptRole)
            box.exec()
        self._update_buttons()

    def _stop_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(5000)
            self._thread = None
        self._worker = None

    def _reset_progress(self) -> None:
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)

    def _update_buttons(self) -> None:
        running = self._thread is not None and self._thread.isRunning()
        self.start_btn.setEnabled(not running and not self._params_invalid)
        self.cancel_btn.setEnabled(running)
        has_done = any(i.status == "完成" for i in self._items)
        self.compare_btn.setEnabled(not running and has_done)

    # ---------- 环境 ----------

    def _check_gpu(self) -> None:
        try:
            import torch

            if not torch.cuda.is_available():
                self.status_label.setText(
                    "⚠ 未检测到 NVIDIA GPU（CUDA）——v1 需要 NVIDIA GPU 才能使用 AI 插帧引擎（RIFE）"
                )
                self.status_label.setStyleSheet("color: #b06000;")
        except ImportError:
            pass

    # ---------- 拖拽 ----------

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            self._add_file(url.toLocalFile())

    def closeEvent(self, event) -> None:
        if self._thread is not None and self._thread.isRunning():
            ans = QMessageBox.question(self, "确认", "正在处理中，确定退出？")
            if ans != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._worker.cancel()
            self._thread.quit()
            self._thread.wait(5000)
        event.accept()


def _combo(mapping: dict) -> QComboBox:
    combo = QComboBox()
    combo.addItems(list(mapping.keys()))
    return combo


def main(argv: list | None = None) -> int:
    """GUI 入口；隐藏模式 ``--selftest <输入> <输出>``：无头跑一次真实插帧
    （打包产物自检用：windowed exe 无控制台，以退出码 + 输出文件验证）。"""
    argv = argv if argv is not None else sys.argv[1:]
    if argv[:1] == ["--selftest"] and len(argv) == 3:
        from .pipeline import run as _pipeline_run
        from .rife import RifeEngine

        try:
            _pipeline_run(argv[1], argv[2], 120, engine=RifeEngine())
            return 0
        except Exception:
            return 1

    app = QApplication(argv)
    app.setWindowIcon(_app_icon())
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
