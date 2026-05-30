"""基于正则的指令识别引擎 - 解析语音文本中的操作意图"""

import re
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from command.time_parser import TimeParser
from command.recurrence_resolver import RecurrenceResolver

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
    recurrence_end: Optional[datetime] = None
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
        "往前推",
        "向后推",
        "往后延",
        "向后延",
        "后延",
        "延后",
        "挂到",
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
        "大约是",  # "大约是"优先于"大约"，避免残留"是"
        "差不多是",
        "大概是",
        "大约",
        "大概",
        "差不多",
        "都",  # 循环句式中的“都”不是标题部分（如“每天都要午睡”）
        # 通用量词/修饰词（如“删除今天的所有事件”中的“所有”）
        "所有",
        "全部",
        "一切",
        "整个",
        "事件",
        "安排",
        "日程",
        "事项",
    ]

    # 口语填充词（动词间的量词/助词，时间已剥离后可安全删除）
    TITLE_ORAL_FILLERS = ["个", "了", "啊", "吧", "呢"]

    # 口语前缀（导向动词，标题中不需要）
    TITLE_ORAL_PREFIXES = ["去", "来", "得"]

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
        self._recurrence_resolver = RecurrenceResolver()
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
            (CommandType.QUERY_EVENT, self._query_pattern),  # 查询关键词先于添加（避免“安排”匹配“查看...安排”）
            (CommandType.ADD_EVENT, self._add_pattern),
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

        # UPDATE 专用路径：双时间解析
        if cmd_type == CommandType.UPDATE_EVENT:
            return self._extract_update_details(text, keyword_match, base_date)

        # 检测优先级
        priority = self._detect_priority(text)

        # 先检测循环规则（必须在时间解析前，否则时间解析器会吞噬"周六"等导致无法匹配"每周六"）
        recurrence_rule, text_clean, rec_start, rec_end = self._detect_recurrence(
            text_without_keyword, base_date=base_date
        )
        if not recurrence_rule:
            recurrence_rule, _, rec_start, rec_end = self._detect_recurrence(text, base_date=base_date)
            text_clean = text_without_keyword

        # 如果 resolver 提供了首次发生时间，用作 parsed_time 的基础
        if rec_start:
            # 用 resolver 的日期作为时间解析的基准
            parsed_time, remaining = self._time_parser.parse(text_clean, base_date=rec_start)
            if parsed_time is None:
                parsed_time = rec_start
                remaining = text_clean
        else:
            # 解析时间（使用已去除循环词的文本）
            parsed_time, remaining = self._time_parser.parse(text_clean, base_date=base_date)

        # 持续事件检测
        end_time, remaining = self._detect_duration(remaining, parsed_time)

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
            end_time=end_time,
            priority=priority,
            recurrence_rule=recurrence_rule,
            recurrence_end=rec_end,
            original_text=text,
            confidence=0.8,
        )

    @staticmethod
    def _auto_advance_past_time(parsed_time: Optional[datetime], text: str) -> Optional[datetime]:
        """对 ADD_EVENT 的过去时间自动前推到明天

        规则：如果解析出的时间已过去（今天内），且原文中无明确过去日期标记（昨天/前天/上周），
        则自动推迟到明天同一时间。

        例：用户在下午说"午夜零点跨年倒计时" → 今天 0:00 已过 → 推到明天 0:00
        """
        if parsed_time is None:
            return None

        from datetime import timedelta

        now = datetime.now()

        # 只对“今天内的过去时间”生效
        if parsed_time.date() != now.date():
            return parsed_time
        if parsed_time >= now:
            return parsed_time

        # 检查是否有明确的过去日期标记
        past_markers = ["昨天", "昨日", "前天", "大前天", "上周", "上星期"]
        for marker in past_markers:
            if marker in text:
                return parsed_time  # 用户明确指定过去，不前推

        # 自动前推到明天
        return parsed_time + timedelta(days=1)

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
        recurrence_rule, text_clean, rec_start, rec_end = self._detect_recurrence(text, base_date=base_date)

        if rec_start:
            parsed_time, remaining = self._time_parser.parse(text_clean, base_date=rec_start)
            if parsed_time is None:
                parsed_time = rec_start
                remaining = text_clean
        else:
            parsed_time, remaining = self._time_parser.parse(text_clean, base_date=base_date)

        # 持续事件检测
        end_time, remaining = self._detect_duration(remaining, parsed_time)

        if parsed_time is not None:
            title = self._clean_title(remaining)
            if title:
                # 过去时间自动前推（ADD_EVENT 专用）
                original_time = parsed_time
                parsed_time = self._auto_advance_past_time(parsed_time, text)
                # 如果时间被前推了，end_time 也同步前推
                if end_time and parsed_time != original_time:
                    offset = parsed_time - original_time
                    end_time = end_time + offset
                return ParsedCommand(
                    command_type=CommandType.ADD_EVENT,
                    title=title,
                    time=parsed_time,
                    end_time=end_time,
                    priority=self._detect_priority(text),
                    recurrence_rule=recurrence_rule,
                    recurrence_end=rec_end,
                    original_text=text,
                    confidence=0.75,
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

    def _detect_recurrence(self, text: str, base_date: Optional[datetime] = None) -> tuple:
        """从文本中检测循环规则（委托给 RecurrenceResolver）

        支持的模式:
        - 范围内每天: "下周每天"/"这周每天" (带 UNTIL)
        - 每月X号: "每个月1号" (带 BYMONTHDAY)
        - 每天/每日 → FREQ=DAILY
        - 每周/每个星期 → FREQ=WEEKLY
        - 每周X/每个星期X → FREQ=WEEKLY;BYDAY=XX
        - 每月/每个月 → FREQ=MONTHLY
        - 每年 → FREQ=YEARLY
        - 工作日/每个工作日 → FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR

        Args:
            text: 输入文本
            base_date: 基准日期

        Returns:
            (recurrence_rule, cleaned_text, start_time, end_time) 四元组
        """
        if not text:
            return "", text, None, None

        result = self._recurrence_resolver.resolve(text, base_date=base_date)
        return result.rule, result.cleaned_text, result.start_time, result.end_time

    # UPDATE 专用偏移量解析模式
    _UPDATE_OFFSET_PATTERNS = [
        (
            re.compile(
                r"([\u4e00\u4e24\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\d]+)\s*\u4e2a?\u534a\u5c0f\u65f6"
            ),
            0.5,
            "hour",
        ),
        (
            re.compile(r"([\u4e00\u4e24\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\d]+)\s*\u4e2a?\u5c0f\u65f6"),
            1.0,
            "hour",
        ),
        (re.compile(r"\u534a\u5c0f\u65f6"), 0.5, "hour"),
        (re.compile(r"\u534a\u5929"), 12.0, "hour"),
        (
            re.compile(r"([\u4e00\u4e24\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\d]+)\s*\u5206\u949f?"),
            1.0,
            "minute",
        ),
    ]

    # UPDATE 指令偏移类关键词
    _UPDATE_DELAY_KEYWORDS = ["推迟", "延后", "往后推", "向后推", "后延"]
    _UPDATE_ADVANCE_KEYWORDS = ["提前", "向前推", "往前推", "前移"]

    def _extract_update_details(
        self,
        text: str,
        keyword_match: re.Match,
        base_date: Optional[datetime] = None,
    ) -> ParsedCommand:
        """UPDATE 专用解析：以 keyword 为分界点，左侧提取源时间+标题，右侧提取目标时间/偏移量

        模式:
        - "把[后天的][会议]改到[下周三]" → left="把后天的会议", right="下周三"
        - "推迟[明天的][面试]" → left="", right="明天的面试"
        - "[看牙]推迟[一个小时]" → left="看牙", right="一个小时"
        - "[六月一号的面试]向前推[一个小时]" → left="六月一号的面试", right="一个小时"

        返回:
            ParsedCommand, 其中:
            - title: 事件名称（用于搜索）
            - time: 目标时间（绝对调整时）或 None（相对偏移时）
            - end_time: 源时间（用于定位事件，复用字段）
            - original_text: 原始文本（供执行层提取偏移信息）
        """
        keyword = keyword_match.group(0)
        left_part = text[: keyword_match.start()].strip()
        right_part = text[keyword_match.end() :].strip()

        # 清理常见前缀: "把"/"将"
        for prefix in ["把", "将"]:
            if left_part.startswith(prefix):
                left_part = left_part[len(prefix) :].strip()

        # Step 1: 判断是相对偏移还是绝对时间
        is_delay = any(kw == keyword or kw in text for kw in self._UPDATE_DELAY_KEYWORDS)
        is_advance = any(kw == keyword or kw in text for kw in self._UPDATE_ADVANCE_KEYWORDS)
        is_relative = is_delay or is_advance

        # Step 2: 提取偏移量（如果是相对偏移）
        offset_minutes = 0
        if is_relative:
            # 从 right_part 和 left_part 中查找偏移量
            search_text = right_part or left_part
            for pattern, multiplier, unit in self._UPDATE_OFFSET_PATTERNS:
                m = pattern.search(search_text)
                if m:
                    if m.lastindex and m.lastindex >= 1:
                        num_str = m.group(1)
                        try:
                            num = int(num_str)
                        except ValueError:
                            num = self._CN_NUM_MAP.get(num_str, 1)
                    else:
                        num = 1
                    if unit == "hour":
                        offset_minutes = int(num * multiplier * 60)
                    else:
                        offset_minutes = int(num * multiplier)
                    # 从搜索文本中移除偏移表达
                    if search_text == right_part:
                        right_part = (right_part[: m.start()] + right_part[m.end() :]).strip()
                    else:
                        left_part = (left_part[: m.start()] + left_part[m.end() :]).strip()
                    break

            if offset_minutes == 0:
                offset_minutes = 60  # 默认 1 小时
            if is_advance:
                offset_minutes = -offset_minutes

        # Step 3: 从左侧提取源时间 + 标题
        source_time = None
        title = ""

        # 左侧可能是 "后天的会议" / "明天的面试" / "看牙" / "六月一号的面试"
        if left_part:
            source_time, left_remaining = self._time_parser.parse(left_part, base_date=base_date)
            title = self._clean_title(left_remaining)

        # 如果左侧没有标题，从右侧找（如 "推迟明天的面试"）
        if not title and right_part:
            rt, right_remaining = self._time_parser.parse(right_part, base_date=base_date)
            if rt:
                if source_time is None:
                    source_time = rt
                title = self._clean_title(right_remaining)
            else:
                title = self._clean_title(right_part)

        # Step 4: 从右侧提取目标时间（绝对调整时）
        target_time = None
        if not is_relative and right_part:
            target_time, _ = self._time_parser.parse(right_part, base_date=base_date)

        # 如果时间解析失败且非相对模式，尝试从全文解析
        if target_time is None and not is_relative:
            # 尝试从全文解析（去掉keyword后）
            full_text = (left_part + " " + right_part).strip()
            target_time, _ = self._time_parser.parse(full_text, base_date=base_date)

        return ParsedCommand(
            command_type=CommandType.UPDATE_EVENT,
            title=title,
            time=target_time,  # 目标时间（绝对调整）或 None（相对偏移）
            end_time=source_time,  # 复用: 源时间（用于定位事件）
            original_text=text,
            confidence=0.8,
        )

    # 持续时长检测模式
    _DURATION_PATTERNS = [
        (re.compile(r"([一二两三四五六七八九十\d]+)\s*个?半小时"), 0.5, "hour"),  # "一个半小时"
        (re.compile(r"([一二两三四五六七八九十\d]+)\s*个?小时"), 1.0, "hour"),  # "三小时"
        (re.compile(r"半小时"), 0.5, "hour"),  # "半小时"
        (re.compile(r"([一二两三四五六七八九十\d]+)\s*分钟"), 1.0, "minute"),  # "30分钟"
        (re.compile(r"一整天"), 8.0, "hour"),  # "一整天" → 8小时
    ]
    _CN_NUM_MAP = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }

    @classmethod
    def _detect_duration(cls, text: str, start_time: Optional[datetime] = None) -> tuple:
        """从文本中检测持续时长，计算 end_time

        Args:
            text: 剩余文本（时间解析后）
            start_time: 事件开始时间

        Returns:
            (end_time, cleaned_text) 元组
        """
        if not text or start_time is None:
            return None, text

        from datetime import timedelta

        for pattern, multiplier, unit in cls._DURATION_PATTERNS:
            m = pattern.search(text)
            if m:
                # 提取数值
                if m.lastindex and m.lastindex >= 1:
                    num_str = m.group(1)
                    try:
                        num = int(num_str)
                    except ValueError:
                        num = cls._CN_NUM_MAP.get(num_str, 0)
                else:
                    # 无捕获组（如"半小时"、"一整天"）
                    num = 1

                if num <= 0:
                    continue

                if unit == "hour":
                    duration_minutes = int(num * multiplier * 60)
                else:
                    duration_minutes = int(num * multiplier)

                end_time = start_time + timedelta(minutes=duration_minutes)
                cleaned = text[: m.start()] + text[m.end() :]
                logger.info(f"持续事件检测: {num}{unit} → end_time={end_time.strftime('%H:%M')}")
                return end_time, cleaned.strip()

        return None, text

    # "一个"后面跟这些词时不应被删除（时间/量词短语保护）
    _NOISE_PROTECT_SUFFIXES = ["小时", "半小时", "钟头", "分钟", "月", "星期", "礼拜"]

    def _clean_title(self, text: str) -> str:
        """清理事件标题，去除噪音词、口语填充词和多余空白

        Args:
            text: 待清理文本

        Returns:
            清理后的标题
        """
        if not text:
            return ""

        # 去除噪音词（带保护逻辑）
        for word in self.TITLE_NOISE_WORDS:
            if word == "一个":
                # 保护 "一个小时"、"一个半小时"、"一个月" 等
                protected = False
                for suffix in self._NOISE_PROTECT_SUFFIXES:
                    if f"一个{suffix}" in text or f"一个半{suffix}" in text:
                        protected = True
                        break
                if protected:
                    continue
            text = text.replace(word, "")

        # 去除口语填充词（如 "开个会" → "开会"，"跑个步" → "跑步"）
        for filler in self.TITLE_ORAL_FILLERS:
            text = text.replace(filler, "")

        # 去除口语前缀（仅当前缀后还有内容时）
        for prefix in self.TITLE_ORAL_PREFIXES:
            if text.startswith(prefix) and len(text) > len(prefix):
                text = text[len(prefix) :]

        # 去除优先级关键词（避免“必须完成报告”这类标题）
        all_priority_words = self.PRIORITY_URGENT_WORDS + self.PRIORITY_IMPORTANT_WORDS + self.PRIORITY_CRITICAL_WORDS
        for word in all_priority_words:
            text = re.sub(re.escape(word) + r"的?", "", text)

        # 去除首尾的连词、助词和标点
        text = re.sub(r"^[\uff0c,\u3001\s]+|[\uff0c,\u3002.!\uff01?\uff1f\s]+$", "", text)
        # 去除首部助词（的/了/吧等）
        for lead_word in self.TITLE_LEAD_NOISE:
            while text.startswith(lead_word):
                text = text[len(lead_word) :].strip()
        # 去除尾部孤立助词/填充词（如 "开会 是" → "开会"）
        text = re.sub(r"\s+[是的了吧呢啊呀]$", "", text)

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
