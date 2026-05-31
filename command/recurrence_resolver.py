"""循环日期计算工具 - 解析自然语言中的循环模式并生成结构化循环信息

支持的模式:
- 范围内每天: "下周每天"/"这周每天"/"上周每天" (带 UNTIL)
- 每月X号: "每个月1号"/"每月15号" (带 BYMONTHDAY)
- 普通循环: 每天/每周/每周X/每月/每年/工作日 (简单 FREQ)

"周"方向推理:
- "这周每天" + 过去时态("都学习了") → 后向: 周一 → 今天
- "这周每天" + 默认 → 前向: 今天 → 周日
- "下周每天"/"上周每天" → 始终完整周一~周日
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# 中文数字 → 整数映射
_CN_NUM = {
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
    "十一": 11,
    "十二": 12,
    "十三": 13,
    "十四": 14,
    "十五": 15,
    "十六": 16,
    "十七": 17,
    "十八": 18,
    "十九": 19,
    "二十": 20,
    "二十一": 21,
    "二十二": 22,
    "二十三": 23,
    "二十四": 24,
    "二十五": 25,
    "二十六": 26,
    "二十七": 27,
    "二十八": 28,
    "二十九": 29,
    "三十": 30,
    "三十一": 31,
}


@dataclass
class RecurrenceResult:
    """循环解析结果

    Attributes:
        rule: RRULE 字符串（如 "FREQ=DAILY", "FREQ=MONTHLY;BYMONTHDAY=1"）
        start_time: 首次发生时间（用于 DTSTART，None 表示由时间解析器决定）
        end_time: 循环终止时间（None 表示无限循环）
        cleaned_text: 移除循环关键词后的文本（交给时间解析器）
    """

    rule: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    cleaned_text: str = ""


class RecurrenceResolver:
    """循环日期计算工具

    从自然语言文本中提取循环模式，生成结构化的循环信息。
    设计为在时间解析器之前调用，避免时间解析器消费循环关键词。
    """

    # 过去时态指示词（用于"这周每天"方向判断）
    PAST_INDICATORS = [
        "都学习了",
        "都做了",
        "都完成了",
        "已经",
        "都上了",
        "都跑了",
        "都练了",
        "都吃了",
        "都打了",
        "都走了",
        "都看了",
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

    # 普通循环模式（按优先级排序，长关键词优先）
    RECURRENCE_PATTERNS = [
        ("\u5de5\u4f5c\u65e5\u6bcf\u5929", "WEEKLY", "BYDAY=MO,TU,WE,TH,FR"),
        ("\u4f11\u606f\u65e5\u6bcf\u5929", "WEEKLY", "BYDAY=SA,SU"),
        ("\u6bcf\u4e2a\u5de5\u4f5c\u65e5", "WEEKLY", "BYDAY=MO,TU,WE,TH,FR"),
        ("\u6bcf\u4e2a\u4f11\u606f\u65e5", "WEEKLY", "BYDAY=SA,SU"),
        ("\u6bcf\u4e2a\u661f\u671f", "WEEKLY", ""),
        ("\u6bcf\u5468", "WEEKLY", ""),
        ("\u6bcf\u4e2a\u6708", "MONTHLY", ""),
        ("\u6bcf\u6708", "MONTHLY", ""),
        ("\u6bcf\u5e74", "YEARLY", ""),
        ("\u5de5\u4f5c\u65e5", "WEEKLY", "BYDAY=MO,TU,WE,TH,FR"),
        ("\u4f11\u606f\u65e5", "WEEKLY", "BYDAY=SA,SU"),
        ("\u5468\u672b", "WEEKLY", "BYDAY=SA,SU"),
        ("\u6bcf\u5929", "DAILY", ""),
        ("\u6bcf\u65e5", "DAILY", ""),
    ]

    # 周范围 + 每天模式: (下周|这周|上周) + 每天
    _SCOPED_DAILY_PATTERN = re.compile(r"(下周|这周|上周)每天")

    # 每月X号模式
    _MONTHLY_DAY_PATTERN = re.compile(r"(?:每个月|每月)\s*(\d{1,2}|[一二三四五六七八九十百]+)\s*[号日]")

    # 每周X模式（带星期后缀，可选月份范围前缀）
    _WEEKDAY_PATTERN = re.compile(r"(?:(?:下|这|上)个?月)?(?:每周|每个星期)([一二三四五六日天])")

    def resolve(self, text: str, base_date: Optional[datetime] = None) -> RecurrenceResult:
        """解析文本中的循环模式

        按优先级依次尝试：
        1. 范围内每天（"下周每天"/"这周每天"）
        2. 每月X号（"每个月1号"）
        3. 每周X（"每周六"）
        4. 普通模式（"每天"/"每周"等）

        Args:
            text: 输入文本
            base_date: 基准日期（默认今天）

        Returns:
            RecurrenceResult（如果无循环，rule 为空字符串）
        """
        ref = base_date if base_date is not None else datetime.now()
        today = ref.replace(hour=0, minute=0, second=0, microsecond=0)

        # 1. 范围内每天
        result = self._try_scoped_daily(text, today)
        if result.rule:
            return result

        # 2. 每月X号
        result = self._try_monthly_by_day(text, today)
        if result.rule:
            return result

        # 3. 每周X（带星期后缀）
        result = self._try_weekday(text)
        if result.rule:
            return result

        # 4. 普通模式
        result = self._try_simple(text)
        if result.rule:
            return result

        return RecurrenceResult(cleaned_text=text)

    def _try_scoped_daily(self, text: str, today: datetime) -> RecurrenceResult:
        """尝试匹配"下周每天"/"这周每天"/"上周每天"

        Args:
            text: 输入文本
            today: 今天的日期（无时分秒）

        Returns:
            RecurrenceResult
        """
        m = self._SCOPED_DAILY_PATTERN.search(text)
        if not m:
            return RecurrenceResult(cleaned_text=text)

        week_ref = m.group(1)  # "下周"/"这周"/"上周"
        weekday = today.weekday()  # 0=周一

        if week_ref == "下周":
            # 下周一 ~ 下周日
            week_start = today + timedelta(days=7 - weekday)
            week_end = week_start + timedelta(days=6)
        elif week_ref == "上周":
            # 上周一 ~ 上周日
            week_start = today - timedelta(days=weekday + 7)
            week_end = week_start + timedelta(days=6)
        else:
            # "这周" → 根据时态判断方向
            is_past = any(indicator in text for indicator in self.PAST_INDICATORS)
            if is_past:
                # 后向：周一 → 今天
                week_start = today - timedelta(days=weekday)
                week_end = today
            else:
                # 前向：今天 → 周日
                week_start = today
                week_end = today + timedelta(days=6 - weekday)

        cleaned = text[: m.start()] + text[m.end() :]
        until = week_end.replace(hour=23, minute=59, second=59)

        logger.info(
            f"循环解析: 范围内每天, week_ref={week_ref}, "
            f"start={week_start.strftime('%Y-%m-%d')}, end={until.strftime('%Y-%m-%d')}"
        )

        return RecurrenceResult(
            rule="FREQ=DAILY",
            start_time=week_start,
            end_time=until,
            cleaned_text=cleaned.strip(),
        )

    def _try_monthly_by_day(self, text: str, today: datetime) -> RecurrenceResult:
        """尝试匹配"每个月X号"/"每月X号"

        Args:
            text: 输入文本
            today: 今天的日期

        Returns:
            RecurrenceResult
        """
        m = self._MONTHLY_DAY_PATTERN.search(text)
        if not m:
            return RecurrenceResult(cleaned_text=text)

        day_str = m.group(1)
        day = self._cn_to_int(day_str)
        if day < 1 or day > 31:
            return RecurrenceResult(cleaned_text=text)

        # 构造首次发生时间（本月X号 09:00 默认）
        try:
            start = today.replace(day=day, hour=9, minute=0, second=0, microsecond=0)
            # 如果本月该日已过，推到下月
            if day < today.day:
                if today.month == 12:
                    start = start.replace(year=today.year + 1, month=1)
                else:
                    start = start.replace(month=today.month + 1)
        except ValueError:
            # 无效的日期（如 2月30号）
            return RecurrenceResult(cleaned_text=text)

        cleaned = text[: m.start()] + text[m.end() :]
        rule = f"FREQ=MONTHLY;BYMONTHDAY={day}"

        logger.info(f"循环解析: 每月X号, day={day}, start={start.strftime('%Y-%m-%d')}")

        return RecurrenceResult(
            rule=rule,
            start_time=start,
            end_time=None,
            cleaned_text=cleaned.strip(),
        )

    def _try_weekday(self, text: str) -> RecurrenceResult:
        """尝试匹配"每周X"/"每个星期X"（可选月份范围前缀）

        支持：每周五、下个月每周五、这个月每周五

        Returns:
            RecurrenceResult
        """
        m = self._WEEKDAY_PATTERN.search(text)
        if not m:
            return RecurrenceResult(cleaned_text=text)

        day_char = m.group(1)
        day_code = self.WEEKDAY_MAP.get(day_char, "")
        if not day_code:
            return RecurrenceResult(cleaned_text=text)

        # 计算下一个正确星期几作为 start_time
        target_weekday = list(self.WEEKDAY_MAP.values()).index(day_code)  # 0=MO ... 6=SU
        today = datetime.now()
        today_weekday = today.weekday()  # 0=Monday
        days_ahead = target_weekday - today_weekday
        if days_ahead <= 0:
            days_ahead += 7
        next_occurrence = today.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)

        cleaned = text[: m.start()] + text[m.end() :]
        return RecurrenceResult(
            rule=f"FREQ=WEEKLY;BYDAY={day_code}",
            start_time=next_occurrence,
            cleaned_text=cleaned.strip(),
        )

    def _try_simple(self, text: str) -> RecurrenceResult:
        """尝试匹配普通循环模式

        Returns:
            RecurrenceResult
        """
        for keyword, freq, extra in self.RECURRENCE_PATTERNS:
            if keyword in text:
                rule = f"FREQ={freq}"
                if extra:
                    rule += f";{extra}"
                cleaned = text.replace(keyword, "", 1).strip()
                return RecurrenceResult(
                    rule=rule,
                    cleaned_text=cleaned,
                )

        return RecurrenceResult(cleaned_text=text)

    @staticmethod
    def _cn_to_int(text: str) -> int:
        """中文数字转整数

        Args:
            text: 中文数字或阿拉伯数字

        Returns:
            对应的整数
        """
        # 先尝试直接转 int
        try:
            return int(text)
        except ValueError:
            pass

        # 查表
        if text in _CN_NUM:
            return _CN_NUM[text]

        # 处理 "十X" 格式（十二、十五等）
        if text.startswith("十") and len(text) == 2:
            return 10 + _CN_NUM.get(text[1], 0)

        # 处理 "X十" 和 "X十Y" 格式
        if "十" in text:
            parts = text.split("十")
            tens = _CN_NUM.get(parts[0], 1) if parts[0] else 1
            ones = _CN_NUM.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
            return tens * 10 + ones

        return 0
