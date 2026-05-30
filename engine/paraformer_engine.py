"""Paraformer 语音识别引擎 - 基于 FunASR 实现本地中文语音转文字

相比 Whisper，Paraformer 在中文场景下具有显著优势：
- 准确率：100% vs 60%（日历指令场景测试）
- 速度：GPU 0.23s/条 vs CPU 1.72s/条（快 7.5 倍）
- 中文数字保持汉字输出（不会转为阿拉伯数字）
- 无同音字混淆问题（跑步不会变成泡布）

注意事项：
- 必须在 CTranslate2 (faster-whisper) 之前加载，否则 cuDNN 符号冲突
- ct-punc 标点子模型与 Paraformer 同进程加载会崩溃，标点由项目独立的 PunctuationRestorer 处理
"""

import logging
import threading
import numpy as np
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class ParaformerEngine:
    """FunASR Paraformer 中文语音识别引擎

    接口与 WhisperEngine 兼容，可作为即插即用的替代方案。
    """

    def __init__(
        self,
        device: str = "cuda:0",
        vad_model: str = "fsmn-vad",
        cache_dir: Optional[str] = None,
        audio_preprocessor=None,
    ):
        """
        初始化 Paraformer 引擎

        Args:
            device: 计算设备 (cuda:0/cpu)
            vad_model: VAD 模型名称（默认 fsmn-vad），设为 None 可禁用
            cache_dir: 模型缓存目录（暂未使用，ModelScope 自动管理缓存）
            audio_preprocessor: 音频预处理器（高通滤波+降噪），可选
        """
        self.device = device
        self.vad_model = vad_model
        self.cache_dir = cache_dir
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
        加载 Paraformer 模型（首次调用时自动从 ModelScope 下载）

        Args:
            on_progress: 进度回调函数
        """
        if self._model is not None:
            return

        if on_progress:
            on_progress("正在加载 Paraformer 语音识别模型...")

        try:
            from funasr import AutoModel

            model_kwargs = {
                "model": "paraformer-zh",
                "device": self.device,
                "disable_update": True,
            }

            # 添加 VAD 模型（用于长音频端点检测）
            if self.vad_model:
                model_kwargs["vad_model"] = self.vad_model

            self._model = AutoModel(**model_kwargs)

            if on_progress:
                on_progress("Paraformer 模型加载完成")

            logger.info(f"ParaformerEngine: 模型加载成功 (device={self.device}, vad={self.vad_model})")

        except ImportError:
            error_msg = "funasr 未安装，请运行: pip install funasr"
            if on_progress:
                on_progress(f"模型加载失败: {error_msg}")
            raise RuntimeError(error_msg)

        except Exception as e:
            error_msg = str(e)
            if on_progress:
                on_progress(f"模型加载失败: {error_msg}")

            # 如果 CUDA 失败，尝试 CPU 回退
            if "cuda" in self.device.lower() and "cuda" in error_msg.lower():
                logger.warning("ParaformerEngine: CUDA 加载失败，尝试 CPU 回退...")
                try:
                    from funasr import AutoModel

                    model_kwargs = {
                        "model": "paraformer-zh",
                        "device": "cpu",
                        "disable_update": True,
                    }
                    if self.vad_model:
                        model_kwargs["vad_model"] = self.vad_model

                    self._model = AutoModel(**model_kwargs)
                    self.device = "cpu"
                    logger.info("ParaformerEngine: CPU 回退成功")

                    if on_progress:
                        on_progress("Paraformer 模型加载完成（CPU 模式）")
                    return
                except Exception as e2:
                    logger.error(f"ParaformerEngine: CPU 回退也失败: {e2}")

            raise RuntimeError(f"无法加载 Paraformer 模型: {error_msg}")

    def unload_model(self):
        """卸载模型，释放显存/内存"""
        with self._lock:
            if self._model is not None:
                del self._model
                self._model = None
                logger.info("ParaformerEngine: 模型已卸载")

                # 尝试释放 GPU 显存
                try:
                    import torch

                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass

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
            language: 语言代码（Paraformer 仅支持中文，此参数保留兼容性）
            initial_prompt: 初始提示词（Paraformer 不使用，保留兼容性）
            beam_size: 束搜索大小（Paraformer 不使用，保留兼容性）
            vad_filter: 是否启用 VAD 过滤（由模型自带 VAD 处理）
            vad_threshold: VAD 阈值（保留兼容性）

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

            # 归一化音频电平
            audio = self._normalize_audio(audio)

            # FunASR 推理
            result = self._model.generate(input=audio)

            if not result or len(result) == 0:
                return None

            # 提取识别文本
            text = result[0].get("text", "") if isinstance(result[0], dict) else str(result[0])

            # Paraformer 输出带空格分隔的字符，去除空格
            text = text.replace(" ", "").strip()

            # 去除标点符号（与 WhisperEngine 行为一致，输出纯文本）
            if text:
                text = self._strip_punctuation(text)

            return text if text else None

        except Exception as e:
            logger.error(f"ParaformerEngine 语音识别错误: {e}")
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
            on_complete: 识别完成回调
            **kwargs: 传递给 transcribe 的额外参数
        """

        def _worker():
            result = self.transcribe(audio, **kwargs)
            on_complete(result)

        thread = threading.Thread(target=_worker, daemon=True, name="ParaformerWorker")
        thread.start()

    @staticmethod
    def _normalize_audio(audio: np.ndarray, target_peak: float = 0.8, max_gain: float = 10.0) -> np.ndarray:
        """
        归一化音频电平

        Args:
            audio: 原始音频数据
            target_peak: 目标峰值电平 (0.0~1.0)
            max_gain: 最大增益倍数

        Returns:
            归一化后的音频
        """
        peak = np.max(np.abs(audio))
        if peak < 0.001:
            return audio

        if peak < target_peak * 0.5:
            gain = min(target_peak / peak, max_gain)
            audio = audio * gain
            logger.debug(f"音频增益: {gain:.1f}x (原始峰值={peak:.4f})")

        return audio

    @staticmethod
    def _strip_punctuation(text: str) -> str:
        """
        移除所有标点符号，保留纯文本

        Args:
            text: 原始文本

        Returns:
            去除标点后的纯文本
        """
        import unicodedata

        result = []
        for ch in text:
            cat = unicodedata.category(ch)
            if cat.startswith("P"):
                continue
            if ch in "·\u00b7\u2027\u30fb":
                continue
            result.append(ch)
        return "".join(result).strip()
