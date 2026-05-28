"""智能标点修正模块 - 对 CT-Transformer 恢复的标点进行二次修正

职责：
- 英文标点转中文标点
- 语气修正（句号→问号/感叹号）
- 重复标点修正
- 标点前后空格修正
- (可选) 自动分段

注意：标点插入（逗号、句号等）由 PunctuationRestorer (CT-Transformer) 负责，
本模块只负责对标点恢复结果进行修正和优化。
"""

import re
from typing import Optional


class PunctuationProcessor:
    """中文标点修正处理器"""

    # 英文标点到中文标点的映射
    EN_TO_ZH_PUNCT = {
        ".": "。",
        ",": "，",
        "!": "！",
        "?": "？",
        ";": "；",
        ":": "：",
        "(": "（",
        ")": "）",
    }

    # 中文疑问词列表（用于智能判断问号）
    QUESTION_WORDS = [
        "吗",
        "呢",
        "什么",
        "怎么",
        "为什么",
        "哪里",
        "哪个",
        "谁",
        "几",
        "多少",
        "是否",
        "能不能",
        "可以吗",
        "好不好",
        "对不对",
        "是不是",
        "有没有",
        "行不行",
    ]

    # 反问句式（需要改为问号）
    RHETORICAL_PATTERNS = [
        r"不是.*吗",
        r"难道.*",
        r"岂.*",
        r"何必.*",
        r"何不.*",
        r"怎么会.*",
        r"怎么能.*",
    ]

    # 中文感叹词（用于智能判断感叹号）
    EXCLAMATION_WORDS = [
        "啊",
        "呀",
        "哇",
        "哦",
        "嗯",
        "嘿",
        "哎",
        "唉",
        "太棒了",
        "太好了",
        "厉害",
        "不错",
        "真好",
        "加油",
        "恭喜",
        "谢谢",
        "感谢",
    ]

    def __init__(
        self,
        auto_paragraph: bool = False,
        paragraph_threshold: int = 50,
    ):
        """
        初始化标点处理器

        Args:
            auto_paragraph: 是否自动分段
            paragraph_threshold: 自动分段字数阈值
        """
        self.auto_paragraph = auto_paragraph
        self.paragraph_threshold = paragraph_threshold

    def process(self, text: str, language: Optional[str] = "zh") -> str:
        """
        处理文本标点

        Args:
            text: 原始识别文本（已经过 CT-Transformer 标点恢复）
            language: 语言 (zh/en)

        Returns:
            处理后的文本
        """
        if not text:
            return text

        if language == "zh" or language is None:
            text = self._process_chinese(text)

        return text

    def _process_chinese(self, text: str) -> str:
        """处理中文标点（CT-Transformer 输出的后处理）"""
        # 1. 英文标点转中文标点
        text = self._convert_punctuation(text)

        # 2. 语气修正（句号→问号/感叹号，基于疑问词/感叹词/反问句式）
        text = self._adjust_sentence_ending(text)

        # 3. 修正重复标点
        text = self._fix_duplicate_punctuation(text)

        # 4. 修正标点前后空格
        text = self._fix_spacing(text)

        # 5. 自动分段
        if self.auto_paragraph:
            text = self._auto_paragraph(text)

        return text

    def _convert_punctuation(self, text: str) -> str:
        """将中文语境中的英文标点转换为中文标点"""
        result = []
        chars = list(text)

        for i, char in enumerate(chars):
            if char in self.EN_TO_ZH_PUNCT:
                if self._is_chinese_context(chars, i):
                    result.append(self.EN_TO_ZH_PUNCT[char])
                else:
                    result.append(char)
            else:
                result.append(char)

        return "".join(result)

    def _is_chinese_context(self, chars: list, pos: int) -> bool:
        """判断标点位置是否处于中文语境中"""

        def is_chinese(c):
            return "\u4e00" <= c <= "\u9fff" or c in "，。！？；：''（）"

        prev_chinese = False
        next_chinese = False

        if pos > 0:
            prev_chinese = is_chinese(chars[pos - 1])
        if pos < len(chars) - 1:
            next_chinese = is_chinese(chars[pos + 1])

        return prev_chinese or next_chinese

    def _adjust_sentence_ending(self, text: str) -> str:
        """
        语气修正：根据语义将句号改为问号或感叹号

        处理策略：
        1. 按句号分割文本
        2. 对每个以句号结尾的句子，检查是否应为问号或感叹号
        3. 替换对应的句末标点
        """
        # 按句号分割（保留句号）
        sentences = re.split(r"(?<=。)", text)
        result = []

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # 只处理以句号结尾的句子
            if not sentence.endswith("。"):
                result.append(sentence)
                continue

            # 检查反问句式（优先级最高）
            is_rhetorical = False
            for pattern in self.RHETORICAL_PATTERNS:
                if re.search(pattern, sentence):
                    is_rhetorical = True
                    break

            if is_rhetorical:
                sentence = sentence[:-1] + "？"
                result.append(sentence)
                continue

            # 检查疑问词
            is_question = False
            for word in self.QUESTION_WORDS:
                if word in sentence:
                    is_question = True
                    break

            if is_question:
                sentence = sentence[:-1] + "？"
                result.append(sentence)
                continue

            # 检查感叹词
            is_exclamation = False
            for word in self.EXCLAMATION_WORDS:
                if word in sentence:
                    is_exclamation = True
                    break

            if is_exclamation:
                sentence = sentence[:-1] + "！"
                result.append(sentence)
                continue

            result.append(sentence)

        return "".join(result)

    def _fix_duplicate_punctuation(self, text: str) -> str:
        """修正重复标点符号"""
        text = re.sub(r"[。]{2,}", "。", text)
        text = re.sub(r"[，]{2,}", "，", text)
        text = re.sub(r"[！]{2,}", "！", text)
        text = re.sub(r"[？]{2,}", "？", text)
        return text

    def _fix_spacing(self, text: str) -> str:
        """修正标点前后的空格"""
        text = re.sub(r"([，。！？；：])\s+", r"\1", text)
        text = re.sub(r"\s+([，。！？；：])", r"\1", text)
        return text

    def _auto_paragraph(self, text: str) -> str:
        """根据句子长度自动分段"""
        sentences = re.split(r"(?<=[。！？])", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) <= 1:
            return text

        result = []
        current_paragraph = []
        char_count = 0

        for sentence in sentences:
            current_paragraph.append(sentence)
            char_count += len(sentence)

            if char_count >= self.paragraph_threshold:
                result.append("".join(current_paragraph))
                current_paragraph = []
                char_count = 0

        if current_paragraph:
            result.append("".join(current_paragraph))

        return "\n\n".join(result)
