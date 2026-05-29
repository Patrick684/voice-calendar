"""混合指令解析器 - 模型意图优先，规则引擎提取槽位，LLM 兜底

解析流程:
0. IntentClassifier 预测意图 → 高置信度用模型意图 + RuleEngine 提取时间/标题
1. 模型未启用或低置信度 → RuleEngine 正则匹配
2. 规则引擎低置信度 → LLMFallback 解析（如已启用）
3. 均失败 → 返回 UNKNOWN，提示用户换种说法
"""

import logging
import re
from typing import Optional, List

from command.rule_engine import RuleEngine, CommandType, ParsedCommand
from command.llm_fallback import LLMFallback

# IntentClassifier 可选导入（需要 torch + transformers）
try:
    from command.intent_classifier import IntentClassifier
except ImportError:
    IntentClassifier = None  # type: ignore

logger = logging.getLogger(__name__)


class CommandParser:
    """混合指令解析器

    支持三种解析模式：
    - 模型意图分类 + 规则引擎槽位提取（最优）
    - 纯规则引擎（默认）
    - LLM 兜底（可选）
    """

    # 规则引擎置信度阈值，低于此值触发 LLM 兆底
    CONFIDENCE_THRESHOLD = 0.5
    
    # 动态置信度阈值（模型意图分类）
    _CALENDAR_INTENT_THRESHOLD = 0.75  # 日历意图较低阈值，减少漏判
    _OTHER_INTENT_THRESHOLD = 0.90     # other 意图较高阈值，减少误判

    # 模型意图 -> CommandType 映射
    _INTENT_TO_COMMAND = {
        "add_event": CommandType.ADD_EVENT,
        "query_event": CommandType.QUERY_EVENT,
        "delete_event": CommandType.DELETE_EVENT,
        "update_event": CommandType.UPDATE_EVENT,
    }

    def __init__(
        self,
        llm_enabled: bool = False,
        llm_provider: str = "ollama",
        llm_model: str = "qwen2.5:7b",
        llm_base_url: str = "http://localhost:11434",
        intent_model_enabled: bool = False,
        intent_model_path: str = "models/intent_classifier",
        intent_confidence_threshold: float = 0.8,
    ):
        """
        初始化指令解析器

        Args:
            llm_enabled: 是否启用 LLM 兜底
            llm_provider: LLM 提供商
            llm_model: 模型名称
            llm_base_url: API 地址
            intent_model_enabled: 是否启用意图分类模型
            intent_model_path: 意图分类模型路径
            intent_confidence_threshold: 意图分类置信度阈值
        """
        self._rule_engine = RuleEngine()
        self._llm_fallback: Optional[LLMFallback] = None
        self._llm_enabled = llm_enabled
        self._intent_classifier = None
        self._intent_threshold = intent_confidence_threshold

        if llm_enabled:
            self._llm_fallback = LLMFallback(
                provider=llm_provider,
                model=llm_model,
                base_url=llm_base_url,
            )
            logger.info(f"LLM 兜底已启用: {llm_provider}/{llm_model}")

        if intent_model_enabled and IntentClassifier is not None:
            try:
                self._intent_classifier = IntentClassifier(
                    model_path=intent_model_path
                )
                logger.info(f"意图分类模型已启用: {intent_model_path}")
            except FileNotFoundError:
                logger.warning(
                    f"意图模型路径不存在: {intent_model_path}，"
                    f"将回退到规则引擎。请运行 scripts/train_intent_classifier.py"
                )
        elif intent_model_enabled:
            logger.warning(
                "intent_model_enabled=True 但 torch/transformers 未安装，"
                "将回退到规则引擎"
            )

    def parse(self, text: str) -> ParsedCommand:
        """解析语音指令

        解析优先级：
        0. 意图分类模型（如已启用且高置信度）
        1. 规则引擎正则匹配
        2. LLM 兜底（如已启用）
        3. 返回 UNKNOWN

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

        # 0. 意图分类模型预测
        if self._intent_classifier is not None:
            model_result = self._parse_with_model(text)
            if model_result is not None:
                return model_result

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

    def _parse_with_model(self, text: str) -> Optional[ParsedCommand]:
        """使用意图分类模型解析

        采用动态置信度阈值：
        - 日历意图（add/query/delete/update）: 0.75（减少漏判）
        - other 意图: 0.90（减少误判）

        Returns:
            ParsedCommand 如果模型高置信度，否则 None（回退到规则引擎）
        """
        intent_label, confidence = self._intent_classifier.predict(text)
        logger.info(
            f"意图模型结果: intent={intent_label}, confidence={confidence:.3f}"
        )

        # 动态阈值：日历意图用较低阈值，other 用较高阈值
        if intent_label == "other":
            threshold = self._OTHER_INTENT_THRESHOLD
        else:
            threshold = self._CALENDAR_INTENT_THRESHOLD

        if confidence < threshold:
            logger.info(
                f"意图模型置信度不足 ({confidence:.3f} < {threshold})，回退到规则引擎"
            )
            return None

        # 模型判断为非日历指令
        if intent_label == "other":
            logger.info("意图模型判定为非日历指令")
            return ParsedCommand(
                command_type=CommandType.UNKNOWN,
                original_text=text,
                confidence=confidence,
            )

        # 映射为 CommandType
        cmd_type = self._INTENT_TO_COMMAND.get(intent_label)
        if cmd_type is None:
            return None

        # 仍用 RuleEngine 提取时间/标题槽位
        rule_result = self._rule_engine.parse(text)
        return ParsedCommand(
            command_type=cmd_type,
            title=rule_result.title,
            time=rule_result.time,
            end_time=rule_result.end_time,
            original_text=text,
            confidence=confidence,
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

    # 时间边界分割正则（在时间关键词/数字时间前拆分）
    _TIME_BOUNDARY_SPLIT = re.compile(
        r"(?=(?:大后天|后天|明天|今天|今日|今晚|明晚|"
        r"早上|早晨|上午|中午|下午|傍晚|晚上|晚间|凌晨|"
        r"(?<!\d)\d{1,2}点))"
    )

    # 纯日期/时段词（用于合并无标题的时间片段）
    _DATE_PERIOD_WORDS = {
        "大后天", "后天", "明天", "今天", "今日", "今晚", "明晚",
        "早上", "早晨", "上午", "中午", "下午", "傍晚", "晚上", "晚间", "凌晨",
    }

    def _split_by_time_boundaries(self, segment: str) -> list:
        """按时间关键词边界进一步拆分片段

        当 Whisper 输出无标点的多事件文本时，在时间关键词前拆分。
        纯日期/时段片段（如单独的"明天"）会自动与下一片段合并。
        """
        parts = self._TIME_BOUNDARY_SPLIT.split(segment)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) <= 1:
            return parts
        # 合并无标题的纯日期/时段片段到下一段（保持"明天下午"不拆分）
        merged = [parts[0]]
        for part in parts[1:]:
            prev = merged[-1].strip()
            if prev in self._DATE_PERIOD_WORDS:
                merged[-1] = prev + part
            else:
                merged.append(part)
        return merged

    def parse_multiple(self, text: str) -> List[ParsedCommand]:
        """解析可能包含多个指令的文本

        分三层拆分：连接词/标点 → 时间边界 → 逐句解析。

        Args:
            text: 语音识别后的完整文本

        Returns:
            ParsedCommand 列表（仅包含可识别的指令）
        """
        # 第一层：按连接词/标点拆分
        segments = self._SPLIT_DELIMITERS.split(text)
        segments = [s.strip() for s in segments if s.strip()]

        # 第二层：对每个片段按时间边界进一步拆分
        all_segments: List[str] = []
        for segment in segments:
            all_segments.extend(self._split_by_time_boundaries(segment))

        # 如果拆分后只有一段，直接走单次解析
        if len(all_segments) <= 1:
            result = self.parse(text)
            return [result] if result.command_type != CommandType.UNKNOWN else []

        # 第三层：逐段解析
        results: List[ParsedCommand] = []
        for segment in all_segments:
            cmd = self.parse(segment)
            # 过滤无法识别或标题为空的添加事件
            if cmd.command_type == CommandType.UNKNOWN:
                logger.debug(f"多指令解析: 忽略无法识别的片段 '{segment}'")
                continue
            if cmd.command_type == CommandType.ADD_EVENT and not cmd.title:
                logger.debug(f"多指令解析: 忽略空标题片段 '{segment}'")
                continue
            results.append(cmd)
            logger.info(
                f"多指令解析: '{segment}' -> {cmd.command_type.value}"
            )

        return results
