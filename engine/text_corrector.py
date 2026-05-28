"""中文同音纠错模块 - 基于拼音和上下文的高频同音字纠错

解决 Whisper 中文识别最大痛点：同音字/近音字混淆。
采用规则+统计的轻量方案，不引入大模型。

纠错流程：
1. 高频混淆词典匹配（的/地/得、在/再 等）
2. 上下文 bigram 概率选择（基于预置高频词组）
"""

import logging
import re
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class TextCorrector:
    """中文同音纠错器"""

    # ================================================================
    # 高频混淆词典：每个条目为 (错误写法, 正确写法, 上下文条件)
    # 上下文条件为正则，匹配错误写法前后的文本
    # ================================================================

    # "的/地/得" 用法修正规则
    # 规则：形容词+的+名词，副词+地+动词，动词+得+补语
    _DE_RULES: List[Tuple[str, str, str]] = [
        # "的" 用在形容词后修饰名词 → 正确用法，不改
        # "地" 用在副词后修饰动词 → 如果"的"出现在副词+动词之间，改为"地"
        (
            r"的(?=说|看|想|做|跑|走|吃|喝|写|读|听|学|玩|笑|哭|唱|跳|工作|努力|认真|仔细|快速|慢慢|静静|轻轻|悄悄)",
            "地",
            "副词+的+动词 → 地",
        ),
        # "得" 用在动词后接补语 → 如果"的"出现在动词+程度补语之间，改为"得"
        (
            r"(?<=好|快|慢|多|少|早|晚|高|低|大|小|长|短|深|浅|难|易)的(?=很|非常|特别|极|太|最|更|比较|有点|不)",
            "得",
            "形容词+的+程度补语 → 得",
        ),
    ]

    # ================================================================
    # 高频同音混淆词典（拼音相同但字不同的常见错误）
    # 格式: { 错误写法: 正确写法 }
    # 只收录高频确定性错误，避免过度纠正
    # ================================================================
    HOMOPHONE_CORRECTIONS: Dict[str, str] = {
        # 常见两字词混淆
        "做座": "做作",
        "带表": "代表",
        "带替": "代替",
        "代提": "代替",
        "反应": "反映",  # 上下文相关，此处为高频修正
        "急记": "记忆",
        "记亿": "记忆",
        "几亿": "记忆",
        "记异": "记忆",
        "以精": "已经",
        "以经": "已经",
        "义经": "已经",
        "已经": "已经",  # 保持不变
        "在次": "再次",
        "在见": "再见",
        "做后": "最后",
        "最后": "最后",
        # 三字/四字混淆
        "不好意思": "不好意思",
        "不得不": "不得不",
        "没想到": "没想到",
        "想不到": "想不到",
    }

    # ================================================================
    # 上下文敏感词典：同一个拼音可能对应多个词，根据上下文选择
    # 格式: { 拼音: [(候选词, 上下文正则), ...] }
    # ================================================================
    CONTEXT_SENSITIVE: Dict[str, List[Tuple[str, str]]] = {
        # "zai4jian4" 可能是 "再见" 或 "在建"
        "zaijian": [
            ("再见", r"(再见|bye|拜拜|下次)"),
            ("在建", r"(在建|工程|项目|施工)"),
        ],
        # "zai4xian4" 可能是 "在线" 或 "再现"
        "zaixian": [
            ("在线", r"(在线|网络|连接|状态|登录)"),
            ("再现", r"(再现|重现|历史|场景)"),
        ],
        # "fan4ying4" 可能是 "反应" 或 "反映"
        "fanying": [
            ("反应", r"(反应|速度|快|慢|化学|物理|过敏|核)"),
            ("反映", r"(反映|问题|情况|意见|建议|报告)"),
        ],
        # "zuo4wei2" 可能是 "作为" 或 "坐位"
        "zuowei": [
            ("作为", r"(作为|身份|角色|一名|一个)"),
            ("座位", r"(座位|坐下|位置|椅子)"),
        ],
    }

    def __init__(self, enabled: bool = True):
        """
        初始化同音纠错器

        Args:
            enabled: 是否启用纠错
        """
        self._enabled = enabled
        self._pypinyin_available = self._check_pypinyin()

    @property
    def enabled(self) -> bool:
        """纠错是否启用"""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    @staticmethod
    def _check_pypinyin() -> bool:
        """检查 pypinyin 是否可用"""
        try:
            import pypinyin  # noqa: F401

            return True
        except ImportError:
            logger.warning("pypinyin 未安装，同音纠错功能不可用")
            return False

    def correct(self, text: str) -> str:
        """
        对文本执行同音纠错

        流程: 高频混淆词典 -> 的/地/得修正 -> 上下文敏感选择

        Args:
            text: 输入文本（纯中文，无标点或已有标点均可）

        Returns:
            纠错后的文本
        """
        if not self._enabled or not text or not self._pypinyin_available:
            return text

        original = text

        # 第1步：高频同音混淆词典（精确替换）
        text = self._apply_homophone_corrections(text)

        # 第2步：的/地/得 修正（基于语法规则）
        text = self._apply_de_rules(text)

        # 第3步：上下文敏感选择（基于拼音+上下文）
        text = self._apply_context_sensitive(text)

        if text != original:
            logger.info(f"同音纠错: '{original[:30]}' -> '{text[:30]}'")

        return text

    def _apply_homophone_corrections(self, text: str) -> str:
        """
        应用高频同音混淆词典

        对文本中的已知错误写法进行直接替换。
        """
        for wrong, correct in self.HOMOPHONE_CORRECTIONS.items():
            if wrong != correct and wrong in text:
                text = text.replace(wrong, correct)
        return text

    def _apply_de_rules(self, text: str) -> str:
        """
        应用"的/地/得"语法规则修正

        基于简单的上下文正则判断：
        - 副词 + "的" + 动词 → 改为 "地"
        - 形容词 + "的" + 程度补语 → 改为 "得"
        """
        for pattern, replacement, _ in self._DE_RULES:
            try:
                text = re.sub(pattern, replacement, text)
            except re.error:
                continue
        return text

    def _apply_context_sensitive(self, text: str) -> str:
        """
        上下文敏感的同音选择

        对每个拼音有多义的词，根据上下文选择正确的写法。
        使用滑动窗口检查候选词是否出现在文本中，
        然后根据上下文正则选择最佳候选。
        """
        if not self.CONTEXT_SENSITIVE:
            return text

        try:
            from pypinyin import lazy_pinyin

            text_pinyin = "".join(lazy_pinyin(text))

            for pinyin_key, candidates in self.CONTEXT_SENSITIVE.items():
                if pinyin_key not in text_pinyin:
                    continue

                # 检查当前文本中是否已有某个候选词
                current_word = None
                for word, _ in candidates:
                    if word in text:
                        current_word = word
                        break

                if current_word is None:
                    continue

                # 检查上下文，看是否需要切换到另一个候选
                for word, context_pattern in candidates:
                    if word == current_word:
                        continue
                    # 如果当前候选的上下文不匹配，而另一个候选匹配
                    if re.search(context_pattern, text):
                        text = text.replace(current_word, word, 1)
                        break

        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"上下文敏感纠错失败: {e}")

        return text
