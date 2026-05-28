"""音频录制模块 - 使用 sounddevice 实现麦克风录音"""

import logging
import threading
import queue
import numpy as np
from typing import Callable, Optional

import sounddevice as sd

logger = logging.getLogger(__name__)


class AudioRecorder:
    """麦克风录音器，支持按住录音模式"""

    def __init__(
        self,
        sample_rate: int = 16000,
        device: Optional[int] = None,
        on_audio_chunk: Optional[Callable[[np.ndarray], None]] = None,
        on_volume: Optional[Callable[[float], None]] = None,
    ):
        """
        初始化录音器

        Args:
            sample_rate: 采样率，Whisper 要求 16000
            device: 音频设备索引，None 为默认设备
            on_audio_chunk: 音频数据回调（用于实时处理）
            on_volume: 音量指示回调 (0.0 ~ 1.0)
        """
        self.sample_rate = sample_rate
        self.device = device
        self.on_audio_chunk = on_audio_chunk
        self.on_volume = on_volume

        self._audio_queue: queue.Queue = queue.Queue()
        self._recording = False
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()
        self._block_count: int = 0  # 录音块计数器，用于跳过初始暖机块

    @property
    def is_recording(self) -> bool:
        return self._recording

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status: sd.CallbackFlags,
    ):
        """音频回调"""
        if status:
            logger.warning(f"音频流状态警告: {status}")

        if self._recording:
            # 跳过第 1 个块（暖机期，避免音频流初始化时的杂音）
            self._block_count += 1
            if self._block_count <= 1:
                return

            # 复制音频数据放入队列
            audio_data = indata.copy().flatten()
            self._audio_queue.put(audio_data)

            # 计算音量 (RMS)
            if self.on_volume:
                rms = np.sqrt(np.mean(audio_data**2))
                # 归一化到 0-1 范围
                volume = min(1.0, rms * 10)
                self.on_volume(volume)

            # 实时音频块回调
            if self.on_audio_chunk:
                self.on_audio_chunk(audio_data)

    def start_recording(self) -> bool:
        """
        开始录音

        Returns:
            True 如果成功开始录音
        """
        with self._lock:
            if self._recording:
                return False

            # 清空队列
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    break

            # 重置块计数器
            self._block_count = 0

            # 明确获取输入设备（避免 Windows 下误用输出设备）
            input_device = self.device
            if input_device is None:
                try:
                    input_device = sd.default.device[0]
                    device_info = sd.query_devices(input_device)
                    logger.info(
                        f"使用默认输入设备: [{input_device}] {device_info['name']}"
                    )
                except Exception:
                    logger.info("使用 sounddevice 默认设备")

            try:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    device=input_device,
                    channels=1,
                    dtype="float32",
                    blocksize=int(
                        self.sample_rate * 0.2
                    ),  # 200ms 块，提高 Windows 稳定性
                    callback=self._audio_callback,
                )
                self._stream.start()
                self._recording = True
                return True
            except sd.PortAudioError as e:
                print(f"无法打开音频流: {e}")
                return False

    def stop_recording(self) -> Optional[np.ndarray]:
        """
        停止录音并返回录制的音频数据

        Returns:
            numpy 数组格式的音频数据 (float32, 单声道)，如果未录音则返回 None
        """
        with self._lock:
            if not self._recording:
                return None

            self._recording = False

        # 停止音频流
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        # 收集所有音频数据
        audio_chunks = []
        while not self._audio_queue.empty():
            try:
                chunk = self._audio_queue.get_nowait()
                audio_chunks.append(chunk)
            except queue.Empty:
                break

        if not audio_chunks:
            return None

        # 拼接音频数据
        audio_data = np.concatenate(audio_chunks)

        # 记录音频质量指标（用于调试识别准确率问题）
        rms = np.sqrt(np.mean(audio_data**2))
        peak = np.max(np.abs(audio_data))
        duration = len(audio_data) / self.sample_rate
        logger.info(
            f"音频统计: 时长={duration:.2f}s, RMS={rms:.4f}, "
            f"峰值={peak:.4f}, 采样点={len(audio_data)}"
        )

        return audio_data

    def cancel_recording(self):
        """取消录音，丢弃所有数据"""
        with self._lock:
            if not self._recording:
                return
            self._recording = False

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        # 清空队列
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    @staticmethod
    def list_devices() -> list:
        """列出可用的音频输入设备"""
        devices = sd.query_devices()
        input_devices = []
        for i, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                input_devices.append(
                    {
                        "index": i,
                        "name": dev["name"],
                        "channels": dev["max_input_channels"],
                        "sample_rate": int(dev["default_samplerate"]),
                    }
                )
        return input_devices

    def get_audio_duration(self, audio_data: np.ndarray) -> float:
        """获取音频时长（秒）"""
        return len(audio_data) / self.sample_rate
