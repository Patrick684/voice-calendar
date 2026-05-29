"""混合指令解析器 - 规则引擎优先，LLM 兜底

解析流程:
1. RuleEngine 正则匹配 → 高置信度结果直接返回
2. 匹配失败 → LLMFallback 解析（如已启用）
3. LLM 也失败 → 返回 UNKNOWN，提示用户换种说法
"""

import logging
import re
from typing import Optional, List

from command.rule_engine import RuleEngine, CommandType, ParsedCommand
from command.llm_fallback import LLMFallback

logger = logging.getLogger(__name__)


class CommandParser:
    """混合指令解析器

    优先使用规则引擎快速解析，失败时降级到 LLM 兜底。
    """

    # 规则引擎置信度阈值，低于此值触发 LLM 兜底
    CONFIDENCE_THRESHOLD = 0.5

    def __init__(
        self,
        llm_enabled: bool = False,
        llm_provider: str = "ollama",
        llm_model: str = "qwen2.5:7b",
        llm_base_url: str = "http://localhost:11434",
    ):
        """
        初始化指令解析器

        Args:
            llm_enabled: 是否启用 LLM 兜底
            llm_provider: LLM 提供商
            llm_model: 模型名称
            llm_base_url: API 地址
        """
        self._rule_engine = RuleEngine()
        self._llm_fallback: Optional[LLMFallback] = None
        self._llm_enabled = llm_enabled

        if llm_enabled:
            self._llm_fallback = LLMFallback(
                provider=llm_provider,
                model=llm_model,
                base_url=llm_base_url,
            )
            logger.info(f"LLM 兜底已启用: {llm_provider}/{llm_model}")

    def parse(self, text: str) -> ParsedCommand:
        """解析语音指令

        Args:
            text: 语音识别后的文本

        Returns:
            ParsedCommand 解析结果
        """
        text = text.strip()
        if not text:
            return ParsedCommand(
                command_type=CommandType.UNKNOWN,
                original_text=text,
                confidence=0.0,
            )

        logger.info(f"开始解析指令: '{text}'")

        # 1. 规则引擎解析
        rule_result = self._rule_engine.parse(text)
        logger.info(
            f"规则引擎结果: type={rule_result.command_type.value}, "
            f"confidence={rule_result.confidence}, title='{rule_result.title}'"
        )

        # 高置信度直接返回
        if rule_result.confidence >= self.CONFIDENCE_THRESHOLD:
            return rule_result

        # 2. LLM 兜底
        if self._llm_enabled and self._llm_fallback is not None:
            logger.info("规则引擎置信度不足，触发 LLM 兜底...")
            llm_result = self._llm_fallback.parse(text)
            if llm_result is not None and llm_result.confidence > 0:
                logger.info(
                    f"LLM 结果: type={llm_result.command_type.value}, "
                    f"confidence={llm_result.confidence}"
                )
                return llm_result

        # 3. 均失败
        logger.info("指令解析失败：无法识别意图")
        return ParsedCommand(
            command_type=CommandType.UNKNOWN,
            original_text=text,
            confidence=0.0,
        )

    @property
    def llm_enabled(self) -> bool:
        """LLM 兜底是否启用"""
        return self._llm_enabled

    def enable_llm(self, enabled: bool):
        """动态开关 LLM 兜底"""
        self._llm_enabled = enabled

    # 多指令拆分连接词（按长度降序，长词优先匹配）
    _SPLIT_DELIMITERS = re.compile(
        r"(?:还有|以及|另外|然后|同时|再者|接着|其次|最后|再|[\uff0c\u3002])"
    )

    def parse_multiple(self, text: str) -> List[ParsedCommand]:
        """解析可能包含多个指令的文本

        按连接词分句后逐句解析，返回所有非 UNKNOWN 的指令。

        Args:
            text: 语音识别后的完整文本

        Returns:
            ParsedCommand 列表（仅包含可识别的指令）
        """
        # 拆分文本
        segments = self._SPLIT_DELIMITERS.split(text)
        segments = [s.strip() for s in segments if s.strip()]

        # 如果拆分后只有一段，直接走单次解析
        if len(segments) <= 1:
            result = self.parse(text)
            return [result] if result.command_type != CommandType.UNKNOWN else []

        # 逐段解析
        results: List[ParsedCommand] = []
        for segment in segments:
            cmd = self.parse(segment)
            if cmd.command_type != CommandType.UNKNOWN:
                results.append(cmd)
                logger.info(
                    f"多指令解析: '{segment}' -> {cmd.command_type.value}"
                )
            else:
                logger.debug(f"多指令解析: 忽略无法识别的片段 '{segment}'")

        return results
