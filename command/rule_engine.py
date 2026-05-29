"""基于正则的指令识别引擎 - 解析语音文本中的操作意图"""

import re
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from command.time_parser import TimeParser

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """指令类型"""

    ADD_EVENT = "add_event"  # 添加事件
    DELETE_EVENT = "delete_event"  # 删除事件
    QUERY_EVENT = "query_event"  # 查询事件
    UPDATE_EVENT = "update_event"  # 修改事件
    UNKNOWN = "unknown"  # 无法识别


@dataclass
class ParsedCommand:
    """解析后的指令结果

    属性:
        command_type: 指令类型
        title: 事件标题（从文本中提取）
        time: 解析出的时间
        end_time: 结束时间（可选）
        priority: 优先级（0=普通, 1=重要, 2=紧急, 3=紧急且重要）
        original_text: 原始输入文本
        confidence: 置信度 (0.0~1.0)
    """

    command_type: CommandType
    title: str = ""
    time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    priority: int = 0
    recurrence_rule: str = ""
    original_text: str = ""
    confidence: float = 0.0


class RuleEngine:
    """基于正则的指令识别引擎

    通过关键词匹配和正则表达式识别语音文本中的操作意图，
    配合 TimeParser 提取时间实体。
    """

    # 添加事件的触发关键词
    ADD_KEYWORDS = [
        "添加",
        "新增",
        "新建",
        "创建",
        "安排",
        "记录",
        "预约",
        "提醒我",
        "帮我记",
        "设个",
        "定个",
        "加个",
        "加一个",
    ]

    # 删除事件的触发关键词
    DELETE_KEYWORDS = [
        "删除",
        "取消",
        "去掉",
        "删掉",
        "移除",
        "撤销",
        "不要了",
        "取消掉",
        "删了",
    ]

    # 查询事件的触发关键词
    QUERY_PHRASES = [
        "有什么安排",
        "有什么日程",
        "有什么事项",
        "有什么计划",
        "有哪些安排",
        "有哪些日程",
        "查看日程",
        "查看行程",
        "查看安排",
        "看看日程",
        "看看行程",
        "看看安排",
    ]

    # 查询单个关键词（优先级低于添加/删除，作为后备）
    QUERY_KEYWORDS = [
        "查看",
        "看看",
        "有什么",
        "有哪些",
        "日程",
        "行程",
        "计划",
        "待办",
        "待办事项",
        "事项",
    ]

    # 修改事件的触发关键词
    UPDATE_KEYWORDS = [
        "修改",
        "改一下",
        "改成",
        "更改",
        "调整",
        "推迟",
        "提前",
        "改到",
        "改为",
        "向前推",
        "往后推",
        "挪到",
        "移到",
    ]

    # 用于清理标题中的噪音词
    TITLE_NOISE_WORDS = [
        "一个",
        "一条",
        "一下",
        "帮我",
        "请",
        "给我",
        "要",
        "把",
        "将",
        "那个",
        "这个",
        "有个",
        "左右",
        "大约",
        "大概",
        "差不多",
        "小时",
        "分钟",
    ]

    # 标题首部噪音词（包含助词）
    TITLE_LEAD_NOISE = ["的", "了", "吧", "呢", "啊", "一个", "一条", "我"]

    # 优先级关键词（按优先级降序排列）
    PRIORITY_CRITICAL_WORDS = ["\u7d27\u6025\u4e14\u91cd\u8981", "\u65e2\u7d27\u6025\u53c8\u91cd\u8981"]
    PRIORITY_URGENT_WORDS = [
        "\u7d27\u6025",
        "\u5fc5\u987b",
        "\u622a\u6b62",
        "deadline",
        "\u9a6c\u4e0a",
        "\u7acb\u523b",
        "\u5c3d\u5feb",
    ]
    PRIORITY_IMPORTANT_WORDS = ["\u91cd\u8981", "\u52a1\u5fc5", "\u4e00\u5b9a", "\u4e0d\u80fd\u5fd8"]

    # 循环事件关键词 → RRULE 映射
    # 格式: (关键词, FREQ, 附加参数)
    RECURRENCE_PATTERNS = [
        # 长词优先（避免子串冲突）
        ("每个工作日", "WEEKLY", "BYDAY=MO,TU,WE,TH,FR"),
        ("每个星期", "WEEKLY", ""),
        ("每周", "WEEKLY", ""),
        ("每个月", "MONTHLY", ""),
        ("每月", "MONTHLY", ""),
        ("每年", "YEARLY", ""),
        ("每天", "DAILY", ""),
        ("每日", "DAILY", ""),
        ("工作日", "WEEKLY", "BYDAY=MO,TU,WE,TH,FR"),
    ]

    # 星期映射
    WEEKDAY_MAP = {
        "一": "MO",
        "二": "TU",
        "三": "WE",
        "四": "TH",
        "五": "FR",
        "六": "SA",
        "日": "SU",
        "天": "SU",
    }

    def __init__(self):
        self._time_parser = TimeParser()
        # 预编译正则（按优先级排列，长词优先）
        self._add_pattern = self._build_keyword_pattern(self.ADD_KEYWORDS)
        self._delete_pattern = self._build_keyword_pattern(self.DELETE_KEYWORDS)
        self._query_phrase_pattern = self._build_keyword_pattern(self.QUERY_PHRASES)
        self._query_pattern = self._build_keyword_pattern(self.QUERY_KEYWORDS)
        self._update_pattern = self._build_keyword_pattern(self.UPDATE_KEYWORDS)

    def parse(self, text: str, base_date: Optional[datetime] = None) -> ParsedCommand:
        """解析输入文本

        Args:
            text: 语音识别后的文本
            base_date: 基准日期（用于日期上下文继承），默认使用当天

        Returns:
            ParsedCommand 解析结果
        """
        text = text.strip()
        if not text:
            return ParsedCommand(command_type=CommandType.UNKNOWN, original_text=text)

        # 按优先级依次匹配
        for cmd_type, pattern in [
            (CommandType.DELETE_EVENT, self._delete_pattern),
            (CommandType.UPDATE_EVENT, self._update_pattern),
            (CommandType.QUERY_EVENT, self._query_phrase_pattern),  # 查询短语优先
            (CommandType.ADD_EVENT, self._add_pattern),
            (CommandType.QUERY_EVENT, self._query_pattern),  # 查询关键词后置
        ]:
            match = pattern.search(text)
            if match:
                return self._extract_details(cmd_type, text, match, base_date)

        # 无法匹配到关键词，尝试否定式删除（“不X了”、“别X了”）
        if self._detect_negation_delete(text):
            return self._build_delete_command(text)

        # 尝试隐式添加（有时间 + 标题的模式）
        implicit = self._try_implicit_add(text, base_date)
        if implicit is not None:
            return implicit

        return ParsedCommand(
            command_type=CommandType.UNKNOWN,
            original_text=text,
            confidence=0.0,
        )

    def _build_keyword_pattern(self, keywords: list) -> re.Pattern:
        """构建关键词匹配正则（长词优先，避免子串冲突）"""
        sorted_kw = sorted(keywords, key=len, reverse=True)
        escaped = [re.escape(kw) for kw in sorted_kw]
        pattern_str = "|".join(escaped)
        return re.compile(f"(?:{pattern_str})")

    def _extract_details(
        self,
        cmd_type: CommandType,
        text: str,
        keyword_match: re.Match,
        base_date: Optional[datetime] = None,
    ) -> ParsedCommand:
        """从文本中提取指令详情（时间、标题）

        Args:
            cmd_type: 指令类型
            text: 原始文本
            keyword_match: 关键词匹配结果

        Returns:
            ParsedCommand
        """
        # 移除关键词，剩余部分用于提取时间和标题
        text_without_keyword = (text[: keyword_match.start()] + text[keyword_match.end() :]).strip()

        # 检测优先级
        priority = self._detect_priority(text)

        # 先检测循环规则（必须在时间解析前，否则时间解析器会吞噬"周六"等导致无法匹配"每周六"）
        recurrence_rule, text_clean = self._detect_recurrence(text_without_keyword)
        if not recurrence_rule:
            recurrence_rule, _ = self._detect_recurrence(text)
            text_clean = text_without_keyword

        # 解析时间（使用已去除循环词的文本）
        parsed_time, remaining = self._time_parser.parse(text_clean, base_date=base_date)

        # 清理标题
        title = self._clean_title(remaining)

        # 查询指令不需要标题，时间范围就是查询条件
        if cmd_type == CommandType.QUERY_EVENT:
            # 如果原文中没有解析到时间，检查关键词是否包含时间信息
            if parsed_time is None:
                parsed_time, _ = self._time_parser.parse(text, base_date=base_date)
            return ParsedCommand(
                command_type=cmd_type,
                title=title,
                time=parsed_time,
                priority=priority,
                original_text=text,
                confidence=0.85,
            )

        return ParsedCommand(
            command_type=cmd_type,
            title=title,
            time=parsed_time,
            priority=priority,
            recurrence_rule=recurrence_rule,
            original_text=text,
            confidence=0.8,
        )

    def _try_implicit_add(self, text: str, base_date: Optional[datetime] = None) -> Optional[ParsedCommand]:
        """尝试隐式添加指令（无明确关键词，但有时间+标题）

        例如："明天下午三点开会" → 隐式添加事件

        Args:
            text: 输入文本
            base_date: 基准日期（用于日期上下文继承）

        Returns:
            ParsedCommand 或 None
        """
        # 先检测循环规则（必须在时间解析前，否则时间解析器会吞噬"周六"等导致无法匹配"每周六"）
        recurrence_rule, text_clean = self._detect_recurrence(text)

        parsed_time, remaining = self._time_parser.parse(text_clean, base_date=base_date)
        if parsed_time is not None:
            title = self._clean_title(remaining)
            if title:
                return ParsedCommand(
                    command_type=CommandType.ADD_EVENT,
                    title=title,
                    time=parsed_time,
                    priority=self._detect_priority(text),
                    recurrence_rule=recurrence_rule,
                    original_text=text,
                    confidence=0.75,  # 时间解析成功是强信号，隐式指令置信度可提高
                )
        return None

    @classmethod
    def _detect_priority(cls, text: str) -> int:
        """从文本中检测优先级关键词

        Args:
            text: 输入文本

        Returns:
            优先级值（0=普通, 1=重要, 2=紧急, 3=紧急且重要）
        """
        text_lower = text.lower()
        # 检查紧急且重要（最高优先级）
        for word in cls.PRIORITY_CRITICAL_WORDS:
            if word in text_lower:
                return 3
        # 检查紧急
        for word in cls.PRIORITY_URGENT_WORDS:
            if word in text_lower:
                return 2
        # 检查重要
        for word in cls.PRIORITY_IMPORTANT_WORDS:
            if word in text_lower:
                return 1
        return 0

    @classmethod
    def _detect_recurrence(cls, text: str) -> tuple:
        """从文本中检测循环规则

        支持的模式:
        - 每天/每日 → FREQ=DAILY
        - 每周/每个星期 → FREQ=WEEKLY
        - 每周X/每个星期X → FREQ=WEEKLY;BYDAY=XX
        - 每月/每个月 → FREQ=MONTHLY
        - 每年 → FREQ=YEARLY
        - 工作日/每个工作日 → FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR

        Args:
            text: 输入文本

        Returns:
            (recurrence_rule, cleaned_text) 元组
        """
        if not text:
            return "", text

        # 尝试匹配 “每周X” / “每个星期X” (带星期后缀)
        weekday_pattern = re.compile(r"(?:每周|每个星期)([一二三四五六日天])")
        m = weekday_pattern.search(text)
        if m:
            day_char = m.group(1)
            day_code = cls.WEEKDAY_MAP.get(day_char, "")
            if day_code:
                rule = f"FREQ=WEEKLY;BYDAY={day_code}"
                cleaned = text[: m.start()] + text[m.end() :]
                return rule, cleaned.strip()

        # 尝试匹配固定模式列表
        for keyword, freq, extra in cls.RECURRENCE_PATTERNS:
            if keyword in text:
                rule = f"FREQ={freq}"
                if extra:
                    rule += f";{extra}"
                cleaned = text.replace(keyword, "", 1).strip()
                return rule, cleaned

        return "", text

    def _clean_title(self, text: str) -> str:
        """清理事件标题，去除噪音词和多余空白

        Args:
            text: 待清理文本

        Returns:
            清理后的标题
        """
        if not text:
            return ""

        # 去除噪音词
        for word in self.TITLE_NOISE_WORDS:
            text = text.replace(word, "")

        # 去除优先级关键词（避免“必须完成报告”这类标题）
        for word in self.PRIORITY_URGENT_WORDS + self.PRIORITY_IMPORTANT_WORDS + self.PRIORITY_CRITICAL_WORDS:
            text = text.replace(word, "")

        # 去除首尾的连词、助词和标点
        text = re.sub(r"^[\uff0c,\u3001\s]+|[\uff0c,\u3002.!\uff01?\uff1f\s]+$", "", text)
        # 去除首部助词（的/了/吧等）
        for lead_word in self.TITLE_LEAD_NOISE:
            while text.startswith(lead_word):
                text = text[len(lead_word) :].strip()

        # 合并多余空白
        text = re.sub(r"\s+", " ", text).strip()

        return text

    @staticmethod
    def _detect_negation_delete(text: str) -> bool:
        """检测否定式删除语义（“不X了”、“别X了”、“不用X了”）"""
        negation_patterns = [
            r"不[\u4e00-\u9fa5]{1,6}了",
            r"别[\u4e00-\u9fa5]{1,6}了",
            r"不用[\u4e00-\u9fa5]{1,6}了",
            r"不[\u4e00-\u9fa5]{1,6}啦",
        ]
        for pat in negation_patterns:
            if re.search(pat, text):
                return True
        return False

    @classmethod
    def _build_delete_command(cls, text: str) -> ParsedCommand:
        """构建否定式删除指令（提取被否定的标题）"""
        # 尝试提取被否定的标题（跳过“不/别”前缀，只捕获实际动作）
        title_match = re.search(
            r"(?:今天|明天|昨天|后天|下周[一二三四五六日天]?|这周[一二三四五六日天]?)?"
            r"(?:上午|下午|晚上|早上|中午)?"
            r"(?:\d{1,2}[点时](?:半)?)?"
            r"不([\u4e00-\u9fa5]+?)(?:了|啦)",
            text,
        )
        if not title_match:
            title_match = re.search(
                r"(?:今天|明天|昨天|后天|下周[一二三四五六日天]?|这周[一二三四五六日天]?)?"
                r"(?:上午|下午|晚上|早上|中午)?"
                r"(?:\d{1,2}[点时](?:半)?)?"
                r"别([\u4e00-\u9fa5]+?)(?:了|啦)",
                text,
            )
        title = title_match.group(1) if title_match else ""
        return ParsedCommand(
            command_type=CommandType.DELETE_EVENT,
            title=title,
            original_text=text,
            confidence=0.7,
        )
