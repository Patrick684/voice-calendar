"""混合指令解析器 - 规则引擎优先，LLM 兜底

解析流程:
1. RuleEngine 正则匹配 → 高置信度结果直接返回
2. 匹配失败 → LLMFallback 解析（如已启用）
3. LLM 也失败 → 返回 UNKNOWN，提示用户换种说法
"""

import logging
from typing import Optional

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
