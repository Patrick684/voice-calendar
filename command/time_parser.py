"""中文时间表达式解析器 - 将自然语言时间转为 datetime 对象

支持的表达形式：
- 今天/明天/后天/大后天 + 上午/下午/晚上 + 具体时间
- 昨天/前天/大前天 + 具体时间（过去日期）
- 上周X/上星期X（过去星期）
- 下周一/下周二.../下周日
- N天后/N小时前/N分钟前/N天前
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

    # 时间关键词及其拼音基准（用于近音纠错）
    TIME_KEYWORD_PINYIN = {
        "明天": ["ming", "tian"],
        "后天": ["hou", "tian"],
        "今天": ["jin", "tian"],
        "昨天": ["zuo", "tian"],
        "前天": ["qian", "tian"],
        "大后天": ["da", "hou", "tian"],
        "大前天": ["da", "qian", "tian"],
        "今晚": ["jin", "wan"],
        "明晚": ["ming", "wan"],
        "上午": ["shang", "wu"],
        "下午": ["xia", "wu"],
        "晚上": ["wan", "shang"],
    }

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

    def parse(
        self, text: str, base_date: Optional[datetime] = None
    ) -> Tuple[Optional[datetime], str]:
        """解析文本中的时间表达式

        Args:
            text: 输入文本
            base_date: 基准日期（用于日期上下文继承），默认使用当天

        Returns:
            (解析出的 datetime, 剩余文本)
            如果无法解析时间，datetime 为 None
        """
        # 近音纠错预处理
        text = self._fuzzy_correct_time_keywords(text)

        # 基准日期：外部传入（多指令上下文继承）或默认当天
        ref = base_date if base_date is not None else datetime.now()
        today = ref.replace(hour=0, minute=0, second=0, microsecond=0)
        result_time = None
        remaining = text

        # 1. 解析相对日期（今天/明天/后天/大后天/N天后）
        date_result, remaining = self._parse_relative_date(remaining, today)
        if date_result is not None:
            result_time = date_result

        # 2. 解析 "下周X"
        if result_time is None:
            weekday_result, remaining = self._parse_next_weekday(remaining, ref)
            if weekday_result is not None:
                result_time = weekday_result

        # 3. 解析 "X月X号" / "X号"
        if result_time is None:
            month_day_result, remaining = self._parse_month_day(remaining, ref)
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
                result_time = ref.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
            else:
                result_time = result_time.replace(hour=hour, minute=minute, second=0)
        elif period_hour is not None:
            # 只有时段没有具体时间，使用时段默认值
            if result_time is None:
                result_time = ref.replace(
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
        """解析相对日期：今天/明天/后天/大后天/昨天/前天/N天后/N天前"""
        patterns = [
            (r"大后天", 3),
            (r"大前天", -3),
            (r"后天", 2),
            (r"前天", -2),
            (r"明天", 1),
            (r"昨天|昨日", -1),
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

        # N天后 / N天前 / N小时后 / N分钟后
        match = re.search(r"(\d+|[一二两三四五六七八九十]+)\s*天后", text)
        if match:
            n = self._cn_to_int(match.group(1))
            remaining = text[:match.start()] + text[match.end():]
            return base_date + timedelta(days=n), remaining

        match = re.search(r"(\d+|[一二两三四五六七八九十]+)\s*天前", text)
        if match:
            n = self._cn_to_int(match.group(1))
            remaining = text[:match.start()] + text[match.end():]
            return base_date - timedelta(days=n), remaining

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
        """解析 下周X / 上周X / 周X"""
        # 上周X / 上星期X（过去）
        match = re.search(r"上(周|星期)([一二三四五六日天])", text)
        if match:
            target_weekday = self.WEEKDAY_MAP[match.group(2)]
            current_weekday = now.weekday()
            days_back = (current_weekday - target_weekday) % 7
            if days_back == 0:
                days_back = 7
            result = now.replace(
                hour=9, minute=0, second=0, microsecond=0
            ) - timedelta(days=days_back)
            remaining = text[:match.start()] + text[match.end():]
            return result, remaining

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
            r"([一二两三四五六七八九十]+)\s*点\s*(半|十五|三十|四十五)?", text
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
    def _fuzzy_correct_time_keywords(cls, text: str) -> str:
        """对文本中的时间关键词进行近音纠错

        使用拼音归一化 + 精确匹配策略，将 Whisper 可能误识别的近音词
        纠正为正确的时间关键词。

        归一化规则（处理常见中文发音混淆）：
        - n/l 不分（南方口音）：nan -> lan
        - 前鼻音/后鼻音不分：in -> ing
        - 翘舌/平舌不分：sh -> s

        例如：“明先” → “明天”，“后添” → “后天”

        Args:
            text: 待纠错的文本

        Returns:
            纠正后的文本
        """
        try:
            from pypinyin import lazy_pinyin
        except ImportError:
            return text

        # 按关键词长度降序排列，优先匹配长词（如“大后天”先于“后天”）
        sorted_keywords = sorted(
            cls.TIME_KEYWORD_PINYIN.items(),
            key=lambda x: len(x[0]),
            reverse=True,
        )

        corrected = text
        for pos in range(len(corrected)):
            for keyword, kw_pinyin in sorted_keywords:
                klen = len(keyword)
                if pos + klen > len(corrected):
                    continue
                candidate = corrected[pos:pos + klen]
                # 如果已经是正确关键词，跳过
                if candidate == keyword:
                    break  # 当前位置已匹配，跳到下一个位置
                # 如果候选词本身是另一个时间关键词，不替换
                if candidate in cls.TIME_KEYWORD_PINYIN:
                    break
                # 获取候选词的拼音
                try:
                    cand_pinyin = lazy_pinyin(candidate)
                except Exception:
                    continue
                # 归一化后精确匹配
                norm_cand = [cls._normalize_pinyin(p) for p in cand_pinyin]
                norm_kw = [cls._normalize_pinyin(p) for p in kw_pinyin]
                if norm_cand == norm_kw:
                    logger.info(f"近音纠错: '{candidate}' -> '{keyword}'")
                    corrected = corrected[:pos] + keyword + corrected[pos + klen:]
                    break  # 当前位置已纠正

        return corrected

    # 常见拼音混淆归一化规则（分两级，避免键冲突）
    # 第一级：声母混淆（翘舌/平舌、n/l）
    _PINYIN_INITIAL_NORM = {
        # 翘舌/平舌不分
        "shi": "si", "zhi": "zi", "chi": "ci",
        "shang": "sang", "zhang": "zang", "chang": "cang",
        "shu": "su", "zhu": "zu", "chu": "cu",
        "shen": "sen", "zhen": "zen",
        # n/l 不分
        "nan": "lan", "niu": "liu", "nong": "long",
        "nu": "lu", "nv": "lv", "nuan": "luan",
        "ne": "le", "nai": "lai", "nao": "lao",
        "nen": "len", "nang": "lang", "ning": "ling",
    }
    # 第二级：韵母混淆（前鼻音/后鼻音）
    _PINYIN_FINAL_NORM = {
        "yin": "ying", "jin": "jing", "xin": "xing",
        "lin": "ling", "min": "ming", "bin": "bing",
        "pin": "ping", "qin": "qing", "tin": "ting",
        "nin": "ning", "zhen": "zheng", "chen": "cheng",
        "shen": "sheng", "fen": "feng", "ben": "beng",
        "pen": "peng", "men": "meng", "gen": "geng",
        "ken": "keng", "hen": "heng", "wen": "weng",
    }

    @classmethod
    def _normalize_pinyin(cls, pinyin: str) -> str:
        """归一化拼音，消除常见发音混淆

        依次应用声母归一化和韵母归一化，任一规则命中即返回。

        Args:
            pinyin: 原始拼音

        Returns:
            归一化后的拼音
        """
        # 优先应用声母规则
        if pinyin in cls._PINYIN_INITIAL_NORM:
            return cls._PINYIN_INITIAL_NORM[pinyin]
        # 再应用韵母规则
        if pinyin in cls._PINYIN_FINAL_NORM:
            return cls._PINYIN_FINAL_NORM[pinyin]
        return pinyin

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
