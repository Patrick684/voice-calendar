"""混合指令解析器 - 模型意图优先，规则引擎提取槽位，LLM 兜底

解析流程:
0. IntentClassifier 预测意图 → 高置信度用模型意图 + RuleEngine 提取时间/标题
1. 模型未启用或低置信度 → RuleEngine 正则匹配
2. 规则引擎低置信度 → LLMFallback 解析（如已启用）
3. 均失败 → 返回 UNKNOWN，提示用户换种说法
"""

import logging
import re
from datetime import datetime
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
    _OTHER_INTENT_THRESHOLD = 0.90  # other 意图较高阈值，减少误判

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
                self._intent_classifier = IntentClassifier(model_path=intent_model_path)
                logger.info(f"意图分类模型已启用: {intent_model_path}")
            except FileNotFoundError:
                logger.warning(
                    f"意图模型路径不存在: {intent_model_path}，"
                    f"将回退到规则引擎。请运行 scripts/train_intent_classifier.py"
                )
        elif intent_model_enabled:
            logger.warning("intent_model_enabled=True 但 torch/transformers 未安装，将回退到规则引擎")

    def parse(self, text: str, base_date: Optional[datetime] = None) -> ParsedCommand:
        """解析语音指令

        解析优先级：
        0. 意图分类模型（如已启用且高置信度）
        1. 规则引擎正则匹配
        2. LLM 兜底（如已启用）
        3. 返回 UNKNOWN

        Args:
            text: 语音识别后的文本
            base_date: 基准日期（用于日期上下文继承），默认使用当天

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
            model_result = self._parse_with_model(text, base_date=base_date)
            if model_result is not None:
                return model_result

        # 1. 规则引擎解析
        rule_result = self._rule_engine.parse(text, base_date=base_date)
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
                logger.info(f"LLM 结果: type={llm_result.command_type.value}, confidence={llm_result.confidence}")
                return llm_result

        # 3. 均失败
        logger.info("指令解析失败：无法识别意图")
        return ParsedCommand(
            command_type=CommandType.UNKNOWN,
            original_text=text,
            confidence=0.0,
        )

    def _parse_with_model(self, text: str, base_date: Optional[datetime] = None) -> Optional[ParsedCommand]:
        """使用意图分类模型解析

        采用动态置信度阈值：
        - 日历意图（add/query/delete/update）: 0.75（减少漏判）
        - other 意图: 0.90（减少误判）

        Returns:
            ParsedCommand 如果模型高置信度，否则 None（回退到规则引擎）
        """
        intent_label, confidence = self._intent_classifier.predict(text)
        logger.info(f"意图模型结果: intent={intent_label}, confidence={confidence:.3f}")

        # 动态阈值：日历意图用较低阈值，other 用较高阈值
        if intent_label == "other":
            threshold = self._OTHER_INTENT_THRESHOLD
        else:
            threshold = self._CALENDAR_INTENT_THRESHOLD

        if confidence < threshold:
            logger.info(f"意图模型置信度不足 ({confidence:.3f} < {threshold})，回退到规则引擎")
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
        rule_result = self._rule_engine.parse(text, base_date=base_date)
        return ParsedCommand(
            command_type=cmd_type,
            title=rule_result.title,
            time=rule_result.time,
            end_time=rule_result.end_time,
            priority=rule_result.priority,
            recurrence_rule=rule_result.recurrence_rule,
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
    _SPLIT_DELIMITERS = re.compile(r"(?:还有|以及|另外|然后|同时|再者|接着|其次|最后|再|[\uff0c\u3002])")

    # 时间触发词：匹配到时开启新的分割片段
    # 包含：日期锚点 + 时段 + X月X号/日 + 具体时间(X点) + 中文数字时间
    _COMMAND_TIME_TRIGGERS = re.compile(
        r"(?:大后天|后天|明天|今天|今日|今晚|明晚"
        r"|(?:下|这)?(?:周|星期)[一二三四五六日天]"
        r"|\d{1,2}月\d{1,2}[号日]"
        r"|早上|早晨|上午|中午|下午|傍晚|晚上|晚间|凌晨"
        r"|(?<!\d)\d{1,2}点"
        r"|[一二两三四五六七八九十]+点)"
    )

    # 日期引用检测（用于多指令日期上下文继承）
    # 只匹配日期级关键词，不含时段（上午/下午）和具体时间（X点）
    _DATE_REFERENCE_PATTERN = re.compile(
        r"(?:大后天|后天|明天|今天|今日|今晚|明晚"
        r"|(?:下|这)?(?:周|星期)[一二三四五六日天]"
        r"|\d{1,2}月\d{1,2}[号日]"
        r"|\d+天后)"
    )

    # ASR 标点修复用的已知时间词
    _ASR_TIME_WORDS = {"上午", "下午", "中午", "晚上", "早上", "凌晨", "傍晚"}

    @staticmethod
    def _has_date_reference(text: str) -> bool:
        """检查文本是否含明确日期引用（明天/后天/X月X号等）"""
        return CommandParser._DATE_REFERENCE_PATTERN.search(text) is not None

    @staticmethod
    def _fix_asr_punctuation(text: str) -> str:
        """修复 ASR 在时间词中间插入的错误标点

        例：'后天上，午' -> '后天上午'
        """
        _TIME_WORDS = CommandParser._ASR_TIME_WORDS

        def _try_merge(m):
            merged = m.group(1) + m.group(2)
            return merged if merged in _TIME_WORDS else m.group(0)

        return re.sub(r"(.)[，,、](.)", _try_merge, text)

    def _has_event_content(self, text: str) -> bool:
        """检查文本是否包含事件内容（非纯时间表达式）

        时间词、循环词（每天/每周/每月等）、周引用（这周/下周等）都不算事件内容。
        """
        _, remaining = self._rule_engine._time_parser.parse(text)
        # 去除标点和空白
        remaining = re.sub(r"[，,.。！!？?\s]", "", remaining)
        # 去除循环关键词（这些是时间修饰语，不是事件内容）
        recurrence_words = [
            "每天",
            "每日",
            "每周",
            "每月",
            "每年",
            "每个工作日",
            "每个星期",
            "工作日",
            "这周",
            "下周",
            "上周",
        ]
        for word in recurrence_words:
            remaining = remaining.replace(word, "")
        return len(remaining) > 0

    def _split_by_time_triggers(self, segment: str) -> list:
        """按时间触发词分割：遇到触发词且 buffer 包含事件内容则切分

        核心规则：只有当 buffer 中包含事件内容（非纯时间词）时才切分，
        确保 '明天早上' 不被拆散，而 '10点面试6月1号...' 正确分割。
        """
        parts = []
        buffer = ""
        pos = 0
        while pos < len(segment):
            m = self._COMMAND_TIME_TRIGGERS.search(segment, pos)
            if not m:
                buffer += segment[pos:]
                break
            buffer += segment[pos : m.start()]
            if self._has_event_content(buffer):
                # buffer 含事件内容 → 切分为新指令
                parts.append(buffer.strip())
                buffer = m.group()
            else:
                # buffer 纯时间或空 → 延伸
                buffer += m.group()
            pos = m.end()
        if buffer.strip():
            parts.append(buffer.strip())
        return parts

    def _is_valid_segment(self, text: str) -> bool:
        """过滤无效片段：太短、纯时间无事件

        例：'午'（单字）、'明天早上'（纯时间）均返回 False
        例外：含日期引用的纯时间片段（如 '明天'）返回 True，
              用于日期上下文继承。
        """
        text = text.strip()
        if len(text) <= 1:
            return False
        # 含日期引用的片段保留（用于日期上下文继承）
        if self._has_date_reference(text):
            return True
        # 纯时间片段：移除时间表达式后无实质内容
        _, remaining = self._rule_engine._time_parser.parse(text)
        remaining = re.sub(r"[，,.。！!？?\s]", "", remaining)
        return len(remaining) > 1

    def parse_multiple(self, text: str) -> List[ParsedCommand]:
        """解析可能包含多个指令的文本

        分三层拆分：ASR 纠错 → 连接词/标点 → 时间触发词 → 碎片过滤 → 逐句解析。

        日期上下文继承:
          维护 current_date 变量，遇到明确日期引用时更新，
          未识别到日期的片段继承上文的日期上下文。

        Args:
            text: 语音识别后的完整文本

        Returns:
            ParsedCommand 列表（仅包含可识别的指令）
        """
        # 0. ASR 标点修复（如 '后天上，午' -> '后天上午'）
        text = self._fix_asr_punctuation(text)

        # 第一层：按连接词/标点拆分
        raw = self._SPLIT_DELIMITERS.split(text)
        raw = [s.strip() for s in raw if s.strip()]

        # 第二层：时间触发词分割
        all_segments: List[str] = []
        for seg in raw:
            all_segments.extend(self._split_by_time_triggers(seg))

        # 碎片过滤（纯时间、单字等无效片段）
        all_segments = [s for s in all_segments if self._is_valid_segment(s)]

        # 如果拆分后只有一段，直接走单次解析
        if len(all_segments) <= 1:
            result = self.parse(text)
            return [result] if result.command_type != CommandType.UNKNOWN else []

        # 日期上下文：初始为 None（默认今天），遇到明确日期时更新
        current_date: Optional[datetime] = None
        results: List[ParsedCommand] = []

        for segment in all_segments:
            # 检测当前片段是否含明确日期引用（明天/后天/X月X号等）
            if self._has_date_reference(segment):
                # 先解析提取日期，更新上下文
                probe_time, _ = self._rule_engine._time_parser.parse(segment)
                if probe_time is not None:
                    current_date = probe_time.replace(hour=0, minute=0, second=0, microsecond=0)
                # 尝试正常解析（可能含事件内容）
                cmd = self.parse(segment)
            else:
                # 无日期引用，继承上文日期上下文
                cmd = self.parse(segment, base_date=current_date)

            # 过滤无法识别或标题为空的添加事件
            if cmd.command_type == CommandType.UNKNOWN:
                # 日期上下文片段（如单独的“明天”）不产生指令
                logger.debug(f"多指令解析: 忽略无法识别的片段 '{segment}'")
                continue
            if cmd.command_type == CommandType.ADD_EVENT and not cmd.title:
                logger.debug(f"多指令解析: 忽略空标题片段 '{segment}'")
                continue
            results.append(cmd)
            logger.info(
                f"多指令解析: '{segment}' -> {cmd.command_type.value}"
                f"{' [继承日期:' + current_date.strftime('%m/%d') + ']' if current_date else ''}"
            )

        return results
