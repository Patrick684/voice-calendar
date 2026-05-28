"""标点恢复引擎 - 基于 CT-Transformer 的语义标点恢复

将 Whisper 输出的纯文本（无标点）通过专门的 NLP 模型恢复标点符号，
实现类似微信语音输入的「先识别文字，后判断语义加标点」的效果。
CT-Transformer 加载失败时自动降级为规则方案。
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class PunctuationRestorer:
    """基于 CT-Transformer 的语义标点恢复引擎"""

    # 规则后备方案：连接词（前面通常需要逗号停顿）
    _COMMA_BEFORE_WORDS = [
        "然后",
        "所以",
        "但是",
        "不过",
        "因为",
        "如果",
        "虽然",
        "而且",
        "另外",
        "同时",
        "因此",
        "然而",
        "否则",
        "也就是说",
        "换句话说",
        "总之",
        "其次",
        "最后",
        "此外",
        "并且",
    ]

    # 长句逗号插入阈值（连续中文字符超过此数量时尝试断句）
    _COMMA_INSERT_THRESHOLD = 12

    # 短文本阈值（少于此字数时跳过模型推理）
    _MIN_TEXT_LENGTH = 3

    def __init__(self, cache_dir: Optional[str] = None):
        """
        初始化标点恢复引擎

        Args:
            cache_dir: 模型缓存目录
        """
        self._cache_dir = cache_dir
        self._model = None
        self._fallback = False  # 是否使用规则后备方案
        self._loaded = False  # 是否已尝试加载

    @property
    def is_loaded(self) -> bool:
        """模型是否已加载"""
        return self._model is not None

    @property
    def is_fallback(self) -> bool:
        """是否正在使用规则后备方案"""
        return self._fallback

    def load_model(self, on_progress=None):
        """
        加载 CT-Transformer 标点恢复模型

        Args:
            on_progress: 进度回调函数
        """
        if self._loaded:
            return

        self._loaded = True

        if on_progress:
            on_progress("正在加载标点恢复模型...")

        try:
            from funasr import AutoModel

            # ct-punc 是达摩院的 CT-Transformer 中文标点恢复模型
            self._model = AutoModel(model="ct-punc")
            self._fallback = False
            logger.info("PunctuationRestorer: CT-Transformer 模型加载成功")

            if on_progress:
                on_progress("标点恢复模型加载完成")

        except ImportError:
            logger.warning(
                "PunctuationRestorer: funasr 未安装，降级为规则标点方案。"
                "请安装: pip install funasr"
            )
            self._fallback = True
        except Exception as e:
            logger.warning(
                f"PunctuationRestorer: CT-Transformer 加载失败 ({e})，"
                "降级为规则标点方案"
            )
            self._fallback = True

    def restore(self, text: str) -> str:
        """
        对纯文本恢复标点符号

        Args:
            text: 无标点的纯文本

        Returns:
            恢复标点后的文本
        """
        if not text or not text.strip():
            return text

        text = text.strip()

        # 短文本跳过推理（如 "嗯"、"好的" 等语气词）
        if len(text) < self._MIN_TEXT_LENGTH:
            return text + "。"

        if self._model and not self._fallback:
            return self._restore_neural(text)

        return self._restore_rule_based(text)

    def _restore_neural(self, text: str) -> str:
        """CT-Transformer 神经网络标点恢复"""
        try:
            result = self._model.generate(input=text)

            if result and len(result) > 0:
                # FunASR 返回格式: [{"text": "恢复标点后的文本"}]
                restored = result[0].get("text", "")
                if restored:
                    logger.debug(f"标点恢复: '{text[:20]}...' -> '{restored[:20]}...'")
                    return restored

            logger.warning("PunctuationRestorer: 模型返回空结果，降级为规则方案")
            return self._restore_rule_based(text)

        except Exception as e:
            logger.error(f"PunctuationRestorer: 推理异常 ({e})，降级为规则方案")
            return self._restore_rule_based(text)

    def _restore_rule_based(self, text: str) -> str:
        """
        规则后备方案：基于语法模式的标点恢复

        当 CT-Transformer 不可用时使用，准确率有限但保证基本可用。
        """
        # 策略 1：在连接词前插入逗号
        for word in self._COMMA_BEFORE_WORDS:
            pattern = rf"(?<=[^\s，。！？；：、])(?={re.escape(word)})"
            text = re.sub(pattern, "，", text)

        # 策略 2：对超长无标点段落插入逗号
        text = self._add_commas_to_long_spans(text)

        # 策略 3：添加句末标点
        text = self._add_ending_punctuation(text)

        return text

    def _add_commas_to_long_spans(self, text: str) -> str:
        """对连续无标点的长中文段落插入逗号"""
        segments = re.split(r"(?<=[，。！？；：、])", text)
        result = []

        # 常见的两字/三字词组（避免在词中间断开）
        common_bigrams = {
            "我们",
            "你们",
            "他们",
            "大家",
            "今天",
            "明天",
            "昨天",
            "觉得",
            "认为",
            "知道",
            "可以",
            "应该",
            "需要",
            "散步",
            "公园",
            "回家",
            "吃饭",
            "工作",
            "学习",
            "时间",
            "方案",
            "讨论",
            "细节",
            "问题",
            "回答",
        }

        for segment in segments:
            chinese_count = sum(1 for c in segment if "\u4e00" <= c <= "\u9fff")

            if chinese_count <= self._COMMA_INSERT_THRESHOLD:
                result.append(segment)
                continue

            # 在中间附近寻找合适的断句点
            mid = len(segment) // 2
            best_pos = -1
            best_dist = len(segment)

            for i in range(1, len(segment)):
                if not ("\u4e00" <= segment[i] <= "\u9fff"):
                    continue

                # 避免在常见词组中间断开
                if i >= 1:
                    bigram = segment[i - 1 : i + 1]
                    if bigram in common_bigrams:
                        continue
                if i >= 1 and i + 1 < len(segment):
                    bigram = segment[i : i + 2]
                    if bigram in common_bigrams:
                        continue

                dist = abs(i - mid)
                if dist < best_dist:
                    best_dist = dist
                    best_pos = i

            if best_pos > 0:
                segment = segment[:best_pos] + "，" + segment[best_pos:]

            result.append(segment)

        return "".join(result)

    @staticmethod
    def _add_ending_punctuation(text: str) -> str:
        """为没有句末标点的文本添加句号"""
        text = text.strip()
        if not text:
            return text

        if text[-1] in "。！？…，、；：":
            return text

        # 简单疑问词检测
        question_words = [
            "吗",
            "呢",
            "什么",
            "怎么",
            "为什么",
            "哪里",
            "是不是",
            "有没有",
        ]
        for word in question_words:
            if text.endswith(word) or word in text[-5:]:
                return text + "？"

        return text + "。"
