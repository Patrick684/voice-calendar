"""Whisper 语音识别引擎 - 基于 faster-whisper 实现本地语音转文字"""

import logging
import os
import threading
import numpy as np
from typing import Callable, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class WhisperEngine:
    """Whisper 语音识别引擎封装"""

    # 支持的模型大小及其特性
    MODEL_INFO = {
        "tiny": {"size_mb": 75, "speed": "最快", "accuracy": "一般"},
        "base": {"size_mb": 150, "speed": "快", "accuracy": "较好"},
        "small": {"size_mb": 500, "speed": "中等", "accuracy": "好"},
        "medium": {"size_mb": 1500, "speed": "较慢", "accuracy": "很好"},
        "large": {"size_mb": 3000, "speed": "慢", "accuracy": "最佳"},
    }

    def __init__(
        self,
        model_size: str = "base",
        compute_type: str = "int8",
        device: str = "cpu",
        cache_dir: Optional[str] = None,
        audio_preprocessor=None,
    ):
        """
        初始化 Whisper 引擎

        Args:
            model_size: 模型大小 (tiny/base/small/medium/large)
            compute_type: 计算类型 (int8/float16/float32)
            device: 计算设备 (cpu/cuda)
            cache_dir: 模型缓存目录
            audio_preprocessor: 音频预处理器（高通滤波+降噪），可选
        """
        self.model_size = model_size
        self.compute_type = compute_type
        self.device = device
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self._preprocessor = audio_preprocessor
        self._model = None
        self._lock = threading.Lock()
        self._is_processing = False

    @property
    def is_loaded(self) -> bool:
        """模型是否已加载"""
        return self._model is not None

    @property
    def is_processing(self) -> bool:
        """是否正在处理音频"""
        return self._is_processing

    def load_model(self, on_progress: Optional[Callable[[str], None]] = None):
        """
        加载 Whisper 模型（首次调用时会自动下载）

        Args:
            on_progress: 进度回调函数
        """
        if self._model is not None:
            return

        if on_progress:
            on_progress(f"正在加载 {self.model_size} 模型...")

        try:
            from faster_whisper import WhisperModel

            download_root = str(self.cache_dir) if self.cache_dir else None

            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=download_root,
            )

            if on_progress:
                on_progress("模型加载完成")

        except Exception as e:
            error_msg = str(e)
            if on_progress:
                on_progress(f"模型加载失败: {error_msg}")
            # 清理可能不完整的缓存
            self._cleanup_incomplete_cache()
            raise RuntimeError(f"无法加载 Whisper 模型: {error_msg}")

    def _cleanup_incomplete_cache(self):
        """清理不完整的模型缓存文件"""
        if not self.cache_dir or not self.cache_dir.exists():
            return
        import glob

        for pattern in ["**/*.incomplete", "**/*.part"]:
            for f in glob.glob(str(self.cache_dir / pattern), recursive=True):
                try:
                    os.remove(f)
                except OSError:
                    pass

    def unload_model(self):
        """卸载模型以释放内存"""
        with self._lock:
            self._model = None

    # 语言对应的引导提示词（引导 Whisper 输出正确的文字风格和标点习惯）
    # 通过句号暗示模型输出标点，但不能太长，否则在音乐/噪音片段会回显提示词内容
    LANGUAGE_PROMPTS = {
        "zh": "普通话，简体。",
        "en": "English speech.",
        "ja": "日本語の音声。",
    }

    @staticmethod
    def _strip_punctuation(text: str) -> str:
        """
        移除 Whisper 输出中的所有标点符号，保留纯文本

        使用 Unicode 类别匹配所有标点（包括特殊变体如 ﹔U+FE14），
        避免硬编码列表遗漏字符导致标点堆砌。

        Args:
            text: Whisper 原始输出文本

        Returns:
            去除标点后的纯文本
        """
        import unicodedata

        # Unicode 类别以 "P" 开头的都是标点符号
        # Po: 其他标点, Pd: 破折号, Ps/Pe/Pi/Pf: 括号/引号, Pc: 连接符
        result = []
        for ch in text:
            cat = unicodedata.category(ch)
            if cat.startswith("P"):
                continue
            # 额外过滤一些特殊符号（如中点 · 属于 Sm）
            if ch in "·\u00b7\u2027\u30fb":
                continue
            result.append(ch)
        return "".join(result).strip()

    @staticmethod
    def _normalize_audio(
        audio: np.ndarray, target_peak: float = 0.8, max_gain: float = 10.0
    ) -> np.ndarray:
        """
        归一化音频电平，确保 Whisper 获得足够响的输入

        Args:
            audio: 原始音频数据
            target_peak: 目标峰值电平 (0.0~1.0)
            max_gain: 最大增益倍数，防止放大底噪

        Returns:
            归一化后的音频
        """
        peak = np.max(np.abs(audio))
        if peak < 0.001:  # 几乎无声，不处理
            return audio

        if peak < target_peak * 0.5:  # 峰值低于目标的一半时，进行增益补偿
            gain = min(target_peak / peak, max_gain)  # 限制最大增益，防止放大底噪
            audio = audio * gain
            logger.info(
                f"音频增益: {gain:.1f}x (原始峰值={peak:.4f}, 上限={max_gain}x)"
            )

        return audio

    def _build_prompt(
        self, language: Optional[str], user_prompt: Optional[str]
    ) -> Optional[str]:
        """
        构建组合引导提示词，融合语言引导和用户热词

        Args:
            language: 语言代码
            user_prompt: 用户提供的热词 prompt

        Returns:
            组合后的 prompt，或 None
        """
        parts = []

        # 添加语言引导（确保简体中文输出等）
        if language and language in self.LANGUAGE_PROMPTS:
            parts.append(self.LANGUAGE_PROMPTS[language])

        # 添加用户热词
        if user_prompt:
            parts.append(user_prompt)

        if not parts:
            return None

        return " ".join(parts)

    def transcribe(
        self,
        audio: np.ndarray,
        language: Optional[str] = "zh",
        initial_prompt: Optional[str] = None,
        beam_size: int = 5,
        vad_filter: bool = True,
        vad_threshold: float = 0.5,
    ) -> Optional[str]:
        """
        将音频转换为文字

        Args:
            audio: numpy 数组格式的音频数据 (float32, 16kHz, 单声道)
            language: 语言代码 (zh/en/ja 等)，None 为自动检测
            initial_prompt: 初始提示词（用于热词注入）
            beam_size: 束搜索大小
            vad_filter: 是否启用 VAD 过滤
            vad_threshold: VAD 阈值

        Returns:
            识别出的文字，如果处理失败返回 None
        """
        with self._lock:
            if self._model is None:
                raise RuntimeError("模型未加载，请先调用 load_model()")

            self._is_processing = True

        try:
            # 确保音频格式正确
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)

            # 检查音频是否为空或太短
            if len(audio) < 1600:  # 少于 0.1 秒
                return None

            # 音频预处理（高通滤波 + 降噪）
            if self._preprocessor:
                audio = self._preprocessor.process(audio)

            # 归一化音频电平（解决麦克风增益不足导致识别率低的问题）
            audio = self._normalize_audio(audio)

            # 构建引导提示词（用户热词 + 语言引导，确保简体中文输出）
            combined_prompt = self._build_prompt(language, initial_prompt)
            if combined_prompt:
                logger.info(f"识别引导: {combined_prompt[:50]}...")

            # 执行识别
            segments, info = self._model.transcribe(
                audio,
                language=language,
                initial_prompt=combined_prompt,
                beam_size=beam_size,
                vad_filter=vad_filter,
                vad_parameters={"threshold": vad_threshold} if vad_filter else None,
                without_timestamps=True,
            )

            # 拼接所有片段
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)

            text = "".join(text_parts).strip()

            # 清理 Whisper 残余标点，输出纯文本供 CT-Transformer 恢复标点
            if text:
                text = self._strip_punctuation(text)

            return text if text else None

        except Exception as e:
            print(f"语音识别错误: {e}")
            return None

        finally:
            with self._lock:
                self._is_processing = False

    def transcribe_async(
        self,
        audio: np.ndarray,
        on_complete: Callable[[Optional[str]], None],
        **kwargs,
    ):
        """
        异步执行语音识别

        Args:
            audio: 音频数据
            on_complete: 完成回调，参数为识别结果
            **kwargs: 传递给 transcribe 的其他参数
        """

        def _worker():
            try:
                result = self.transcribe(audio, **kwargs)
                on_complete(result)
            except Exception as e:
                print(f"异步识别错误: {e}")
                on_complete(None)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        return thread

    def change_model(self, model_size: str):
        """
        切换模型大小

        Args:
            model_size: 新的模型大小
        """
        if model_size == self.model_size and self._model is not None:
            return

        self.unload_model()
        self.model_size = model_size
