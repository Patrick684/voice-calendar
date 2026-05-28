"""中文时间表达式解析器 - 将自然语言时间转为 datetime 对象

支持的表达形式：
- 今天/明天/后天/大后天 + 上午/下午/晚上 + 具体时间
- 下周一/下周二.../下周日
- N天后/N小时后
- X月X号/X号
- 具体时间：三点/三点半/十五点/15:00
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class TimeParser:
    """中文时间表达式解析器"""

    # 中文数字到阿拉伯数字映射
    CN_NUM = {
        "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
        "十一": 11, "十二": 12,
    }

    # 星期映射
    WEEKDAY_MAP = {
        "一": 0, "二": 1, "三": 2, "四": 3,
        "五": 4, "六": 5, "日": 6, "天": 6,
    }

    # 时段默认时间映射
    PERIOD_DEFAULTS = {
        "早上": 8, "早晨": 8, "上午": 9,
        "中午": 12, "下午": 14, "傍晚": 17,
        "晚上": 19, "晚间": 20, "凌晨": 2,
    }

    # 时段对 12 小时制的影响
    PERIOD_PM_OFFSET = {"下午", "晚上", "晚间", "傍晚"}

    def parse(self, text: str) -> Tuple[Optional[datetime], str]:
        """解析文本中的时间表达式

        Args:
            text: 输入文本

        Returns:
            (解析出的 datetime, 剩余文本)
            如果无法解析时间，datetime 为 None
        """
        now = datetime.now()
        base_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        result_time = None
        remaining = text

        # 1. 解析相对日期（今天/明天/后天/大后天/N天后）
        date_result, remaining = self._parse_relative_date(remaining, base_date)
        if date_result is not None:
            result_time = date_result

        # 2. 解析 "下周X"
        if result_time is None:
            weekday_result, remaining = self._parse_next_weekday(remaining, now)
            if weekday_result is not None:
                result_time = weekday_result

        # 3. 解析 "X月X号" / "X号"
        if result_time is None:
            month_day_result, remaining = self._parse_month_day(remaining, now)
            if month_day_result is not None:
                result_time = month_day_result

        # 4. 解析时段（上午/下午/晚上...）
        period_hour = None
        period_result, remaining = self._parse_period(remaining)
        if period_result is not None:
            period_hour = self.PERIOD_DEFAULTS.get(period_result)

        # 5. 解析具体时间（三点/三点半/15:00）
        time_result, remaining = self._parse_specific_time(remaining)
        if time_result is not None:
            hour, minute = time_result
            # 如果有时段修饰且是 12 小时制
            if period_result in self.PERIOD_PM_OFFSET and hour < 12:
                hour += 12
            if result_time is None:
                result_time = now.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
            else:
                result_time = result_time.replace(hour=hour, minute=minute, second=0)
        elif period_hour is not None:
            # 只有时段没有具体时间，使用时段默认值
            if result_time is None:
                result_time = now.replace(
                    hour=period_hour, minute=0, second=0, microsecond=0
                )
            else:
                result_time = result_time.replace(hour=period_hour, minute=0, second=0)

        # 清理剩余文本
        remaining = remaining.strip()
        return result_time, remaining

    def _parse_relative_date(
        self, text: str, base_date: datetime
    ) -> Tuple[Optional[datetime], str]:
        """解析相对日期：今天/明天/后天/大后天/N天后"""
        patterns = [
            (r"大后天", 3),
            (r"后天", 2),
            (r"明天", 1),
            (r"今天|今日", 0),
            (r"今晚|今天晚上|明晚|明天晚上", None),  # 特殊处理
        ]

        for pattern, days in patterns:
            match = re.search(pattern, text)
            if match:
                matched_text = match.group()
                remaining = text[:match.start()] + text[match.end():]

                if days is not None:
                    return base_date + timedelta(days=days), remaining

                # 特殊处理 "今晚" 等
                if "晚" in matched_text:
                    if "明天" in matched_text:
                        result = base_date + timedelta(days=1)
                    else:
                        result = base_date
                    return result, remaining

        # N天后 / N小时后 / N分钟后
        match = re.search(r"(\d+|[一二两三四五六七八九十]+)\s*天后", text)
        if match:
            n = self._cn_to_int(match.group(1))
            remaining = text[:match.start()] + text[match.end():]
            return base_date + timedelta(days=n), remaining

        match = re.search(r"(\d+|[一二两三四五六七八九十]+)\s*小时后", text)
        if match:
            n = self._cn_to_int(match.group(1))
            remaining = text[:match.start()] + text[match.end():]
            return datetime.now() + timedelta(hours=n), remaining

        match = re.search(r"(\d+|[一二两三四五六七八九十]+)\s*分钟后", text)
        if match:
            n = self._cn_to_int(match.group(1))
            remaining = text[:match.start()] + text[match.end():]
            return datetime.now() + timedelta(minutes=n), remaining

        return None, text

    def _parse_next_weekday(
        self, text: str, now: datetime
    ) -> Tuple[Optional[datetime], str]:
        """解析 下周X"""
        match = re.search(r"下(周|星期)([一二三四五六日天])", text)
        if match:
            target_weekday = self.WEEKDAY_MAP[match.group(2)]
            current_weekday = now.weekday()
            # 计算距离下个目标星期几的天数
            days_ahead = (target_weekday - current_weekday) % 7
            if days_ahead == 0:
                days_ahead = 7  # 下周日如果是周日则加 7 天
            result = now.replace(
                hour=9, minute=0, second=0, microsecond=0
            ) + timedelta(days=days_ahead)
            remaining = text[:match.start()] + text[match.end():]
            return result, remaining

        # 周X / 星期X（本周或最近的）
        match = re.search(r"(?:这)?(?:周|星期)([一二三四五六日天])", text)
        if match:
            target_weekday = self.WEEKDAY_MAP[match.group(1)]
            current_weekday = now.weekday()
            days_ahead = (target_weekday - current_weekday) % 7
            result = now.replace(
                hour=9, minute=0, second=0, microsecond=0
            ) + timedelta(days=days_ahead)
            remaining = text[:match.start()] + text[match.end():]
            return result, remaining

        return None, text

    def _parse_month_day(
        self, text: str, now: datetime
    ) -> Tuple[Optional[datetime], str]:
        """解析 X月X号 / X月X日 / X号"""
        # X月X号/日
        match = re.search(
            r"(\d{1,2}|[一二三四五六七八九十]+)\s*月\s*(\d{1,2}|[一二三四五六七八九十]+)\s*[号日]",
            text,
        )
        if match:
            month = self._cn_to_int(match.group(1))
            day = self._cn_to_int(match.group(2))
            year = now.year
            try:
                result = datetime(year, month, day, 9, 0, 0)
                # 如果日期已过，推到明年
                if result < now:
                    result = result.replace(year=year + 1)
                remaining = text[:match.start()] + text[match.end():]
                return result, remaining
            except ValueError:
                pass

        # X号/日（本月）
        match = re.search(r"(\d{1,2}|[一二三四五六七八九十]+)\s*[号日]", text)
        if match:
            day = self._cn_to_int(match.group(1))
            try:
                result = now.replace(day=day, hour=9, minute=0, second=0, microsecond=0)
                if result < now:
                    # 推到下个月
                    if now.month == 12:
                        result = result.replace(year=now.year + 1, month=1)
                    else:
                        result = result.replace(month=now.month + 1)
                remaining = text[:match.start()] + text[match.end():]
                return result, remaining
            except ValueError:
                pass

        return None, text

    def _parse_period(self, text: str) -> Tuple[Optional[str], str]:
        """解析时段（上午/下午/晚上等）"""
        periods = sorted(self.PERIOD_DEFAULTS.keys(), key=len, reverse=True)
        for period in periods:
            if period in text:
                remaining = text.replace(period, "", 1)
                return period, remaining
        return None, text

    def _parse_specific_time(self, text: str) -> Tuple[Optional[Tuple[int, int]], str]:
        """解析具体时间（三点/三点半/15:00/15点）"""
        # 数字时间: HH:MM 或 HH点MM分
        match = re.search(r"(\d{1,2})\s*[点:：]\s*(\d{1,2})\s*分?", text)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                remaining = text[:match.start()] + text[match.end():]
                return (hour, minute), remaining

        # 数字时间: HH点/MM:00
        match = re.search(r"(\d{1,2})\s*点", text)
        if match:
            hour = int(match.group(1))
            if 0 <= hour <= 23:
                remaining = text[:match.start()] + text[match.end():]
                return (hour, 0), remaining

        # 中文时间: 三点/三点半/三点十五
        match = re.search(
            r"([一二三四五六七八九十]+)\s*点\s*(半|十五|三十|四十五)?", text
        )
        if match:
            hour = self._cn_to_int(match.group(1))
            minute = 0
            if match.group(2):
                minute_map = {"半": 30, "十五": 15, "三十": 30, "四十五": 45}
                minute = minute_map.get(match.group(2), 0)
            if 1 <= hour <= 12:
                remaining = text[:match.start()] + text[match.end():]
                return (hour, minute), remaining

        # HH:MM 纯数字格式
        match = re.search(r"(\d{1,2})\s*[：:]\s*(\d{1,2})", text)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                remaining = text[:match.start()] + text[match.end():]
                return (hour, minute), remaining

        return None, text

    @classmethod
    def _cn_to_int(cls, text: str) -> int:
        """中文数字转阿拉伯数字"""
        if text.isdigit():
            return int(text)

        # 直接查表
        if text in cls.CN_NUM:
            return cls.CN_NUM[text]

        # 处理 "二十" "三十" 等
        if len(text) == 2 and text[0] in cls.CN_NUM and text[1] == "十":
            return cls.CN_NUM[text[0]] * 10

        # 处理 "十X" (十一 ~ 十九)
        if len(text) == 2 and text[0] == "十" and text[1] in cls.CN_NUM:
            return 10 + cls.CN_NUM[text[1]]

        # 处理 "二十X" (二十一 ~ 二十九)
        if len(text) == 3 and text[1] == "十":
            tens = cls.CN_NUM.get(text[0], 0)
            ones = cls.CN_NUM.get(text[2], 0)
            return tens * 10 + ones

        # 回退
        try:
            return int(text)
        except ValueError:
            return 0
