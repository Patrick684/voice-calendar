"""日历管理器 - 封装事件 CRUD 和业务逻辑"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from calendar.event import CalendarEvent
from calendar.storage import SQLiteStorage

logger = logging.getLogger(__name__)


class CalendarManager:
    """日历管理器

    提供事件的增删改查操作，封装底层 SQLite 存储，
    并对上层（语音指令解析、UI）暴露简洁的接口。
    """

    def __init__(self, db_path: str, default_reminder_minutes: int = 15):
        """
        初始化日历管理器

        Args:
            db_path: SQLite 数据库文件路径
            default_reminder_minutes: 默认提醒提前分钟数
        """
        self._storage = SQLiteStorage(db_path)
        self._default_reminder_minutes = default_reminder_minutes
        logger.info(f"日历管理器已初始化，数据库: {db_path}")

    # ================================================================
    # CRUD 操作
    # ================================================================

    def add_event(
        self,
        title: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        description: str = "",
        is_all_day: bool = False,
        reminder_minutes: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ) -> CalendarEvent:
        """添加新事件

        Args:
            title: 事件标题
            start_time: 开始时间
            end_time: 结束时间
            description: 事件描述
            is_all_day: 是否全天事件
            reminder_minutes: 提醒分钟数（None 使用默认值）
            tags: 标签列表

        Returns:
            创建的事件对象（含 ID）
        """
        if reminder_minutes is None:
            reminder_minutes = self._default_reminder_minutes

        event = CalendarEvent(
            title=title,
            start_time=start_time,
            end_time=end_time,
            description=description,
            is_all_day=is_all_day,
            reminder_minutes=reminder_minutes,
            tags=tags or [],
        )
        event_id = self._storage.insert_event(event)
        event.id = event_id
        logger.info(f"事件已添加: {event}")
        return event

    def delete_event(self, event_id: int) -> Optional[str]:
        """删除事件

        Args:
            event_id: 事件 ID

        Returns:
            被删除事件的标题（用于反馈），如果不存在返回 None
        """
        event = self._storage.get_event_by_id(event_id)
        if event is None:
            logger.warning(f"事件不存在: id={event_id}")
            return None

        title = event.title
        if self._storage.delete_event(event_id):
            logger.info(f"事件已删除: {title}")
            return title
        return None

    def update_event(self, event_id: int, **kwargs) -> Optional[CalendarEvent]:
        """更新事件

        Args:
            event_id: 事件 ID
            **kwargs: 要更新的字段

        Returns:
            更新后的事件对象，如果不存在返回 None
        """
        if not self._storage.update_event(event_id, **kwargs):
            logger.warning(f"事件更新失败（不存在）: id={event_id}")
            return None
        return self._storage.get_event_by_id(event_id)

    def get_event(self, event_id: int) -> Optional[CalendarEvent]:
        """获取单个事件"""
        return self._storage.get_event_by_id(event_id)

    # ================================================================
    # 查询操作
    # ================================================================

    def get_events_by_date(self, date: datetime) -> List[CalendarEvent]:
        """查询指定日期的事件

        Args:
            date: 目标日期（只取年月日部分）

        Returns:
            当天的事件列表
        """
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self._storage.get_events_by_range(start, end)

    def get_events_by_range(
        self, start: datetime, end: datetime
    ) -> List[CalendarEvent]:
        """查询时间范围内的事件"""
        return self._storage.get_events_by_range(start, end)

    def get_today_events(self) -> List[CalendarEvent]:
        """获取今天的事件"""
        return self.get_events_by_date(datetime.now())

    def get_upcoming_events(self, days: int = 7) -> List[CalendarEvent]:
        """获取未来 N 天的事件

        Args:
            days: 天数范围

        Returns:
            事件列表
        """
        now = datetime.now()
        end = now + timedelta(days=days)
        return self._storage.get_events_by_range(now, end)

    def search_events(self, keyword: str) -> List[CalendarEvent]:
        """关键词搜索事件"""
        return self._storage.search_events(keyword)

    def get_month_event_dates(self, year: int, month: int) -> List[str]:
        """获取指定月份中有事件的日期列表（用于月历标记）"""
        return self._storage.get_all_event_dates(year, month)

    def get_event_count(self) -> int:
        """获取事件总数"""
        return self._storage.get_event_count()

    # ================================================================
    # 提醒相关
    # ================================================================

    def get_pending_reminders(self, minutes_ahead: int = 15) -> List[CalendarEvent]:
        """获取即将触发提醒的事件

        Args:
            minutes_ahead: 提前分钟数

        Returns:
            需要提醒的事件列表
        """
        now = datetime.now()
        return self._storage.get_upcoming_events(now, minutes_ahead)

    # ================================================================
    # 格式化输出（用于语音反馈和 UI 显示）
    # ================================================================

    @staticmethod
    def format_event_list(events: List[CalendarEvent]) -> str:
        """格式化事件列表为可读文本

        Args:
            events: 事件列表

        Returns:
            格式化后的文本字符串
        """
        if not events:
            return "没有事件"

        lines = []
        for event in events:
            time_str = event.start_time.strftime("%H:%M")
            if event.is_all_day:
                time_str = "全天"
            lines.append(f"  {time_str} {event.title}")
        return "\n".join(lines)

    @staticmethod
    def format_event_detail(event: CalendarEvent) -> str:
        """格式化单个事件的详细信息"""
        time_str = event.start_time.strftime("%Y-%m-%d %H:%M")
        if event.is_all_day:
            time_str = event.start_time.strftime("%Y-%m-%d") + " 全天"

        parts = [f"标题: {event.title}", f"时间: {time_str}"]
        if event.description:
            parts.append(f"描述: {event.description}")
        if event.tags:
            parts.append(f"标签: {', '.join(event.tags)}")
        if event.reminder_minutes is not None:
            parts.append(f"提醒: 提前 {event.reminder_minutes} 分钟")
        return "\n".join(parts)

