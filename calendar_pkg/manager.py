"""日历管理器 - 封装事件 CRUD 和业务逻辑"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from dateutil.rrule import rrulestr

from calendar_pkg.event import CalendarEvent
from calendar_pkg.storage import SQLiteStorage
from calendar_pkg.classifier import EventClassifier
from calendar_pkg.backup import CalendarBackup

logger = logging.getLogger(__name__)


class CalendarManager:
    """日历管理器

    提供事件的增删改查操作，封装底层 SQLite 存储，
    并对上层（语音指令解析、UI）暴露简洁的接口。
    """

    # 循环事件最大实例数（约一个月）
    MAX_RECURRING_INSTANCES = 31

    def __init__(self, db_path: str, default_reminder_minutes: int = 15):
        """
        初始化日历管理器

        Args:
            db_path: SQLite 数据库文件路径
            default_reminder_minutes: 默认提醒提前分钟数
        """
        self._storage = SQLiteStorage(db_path)
        self._default_reminder_minutes = default_reminder_minutes
        self._classifier = EventClassifier()
        logger.info(f"日历管理器已初始化，数据库: {db_path}")

    @property
    def storage(self) -> SQLiteStorage:
        """暴露底层 storage（供 StatsEngine 等使用）"""
        return self._storage

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
        priority: int = 0,
        category: str = "",
        recurrence_rule: str = "",
        recurrence_end=None,
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
            priority: 优先级（0=普通, 1=重要, 2=紧急, 3=紧急且重要）
            category: 事件分类（空字符串时自动分类）
            recurrence_rule: 循环规则（iCal RRULE 格式）
            recurrence_end: 循环结束时间

        Returns:
            创建的事件对象（含 ID）
        """
        if reminder_minutes is None:
            reminder_minutes = self._default_reminder_minutes

        # 未指定分类时自动分类
        if not category:
            category = self._classifier.classify(title)

        event = CalendarEvent(
            title=title,
            start_time=start_time,
            end_time=end_time,
            description=description,
            is_all_day=is_all_day,
            reminder_minutes=reminder_minutes,
            tags=tags or [],
            priority=priority,
            category=category,
            recurrence_rule=recurrence_rule,
            recurrence_end=recurrence_end,
        )
        event_id = self._storage.insert_event(event)
        event.id = event_id
        logger.info(f"事件已添加: {event}")

        # 循环事件：自动创建真实实例（最多 MAX_RECURRING_INSTANCES 条）
        if recurrence_rule:
            self._generate_recurring_instances(event)

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
        """查询指定日期的事件（含循环事件展开）

        Args:
            date: 目标日期（只取年月日部分）

        Returns:
            当天的事件列表（含循环事件的虚拟实例）
        """
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self.get_events_by_range(start, end)

    def get_events_by_range(self, start: datetime, end: datetime) -> List[CalendarEvent]:
        """查询时间范围内的事件（循环事件已实例化，无需虚拟展开）"""
        events = self._storage.get_events_by_range(start, end)
        # 按开始时间排序
        events.sort(key=lambda e: e.start_time)
        return events

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
    # 循环事件实例化
    # ================================================================

    def _generate_recurring_instances(self, parent: CalendarEvent, max_count: int = None):
        """为循环事件生成真实子事件实例

        Args:
            parent: 循环事件模板（含 recurrence_rule）
            max_count: 最大生成数（含 parent 本身），默认 MAX_RECURRING_INSTANCES
        """
        if not parent.recurrence_rule or parent.id is None:
            return

        if max_count is None:
            max_count = self.MAX_RECURRING_INSTANCES

        try:
            # 构建 RRULE
            rrule_string = f"DTSTART:{parent.start_time.strftime('%Y%m%dT%H%M%S')}\nRRULE:{parent.recurrence_rule}"
            if parent.recurrence_end:
                rrule_string += f";UNTIL={parent.recurrence_end.strftime('%Y%m%dT%H%M%S')}"

            rule = rrulestr(rrule_string)
            duration = timedelta(minutes=parent.duration_minutes) if parent.duration_minutes else timedelta(0)

            # 已有实例数（含 parent 本身算 1）
            existing = self._storage.get_children_count(parent.id)
            remaining = max_count - 1 - existing  # -1 因为 parent 本身算一条

            if remaining <= 0:
                return

            # 找到已生成的最新时间，从其之后继续生成
            last_time = self._storage.get_last_child_time(parent.id)
            search_start = last_time if last_time else parent.start_time

            # 生成新实例
            count = 0
            for dt in rule:
                if dt <= search_start:
                    continue
                if dt == parent.start_time:
                    continue

                child = CalendarEvent(
                    title=parent.title,
                    start_time=dt,
                    end_time=dt + duration if duration else None,
                    description=parent.description,
                    is_all_day=parent.is_all_day,
                    reminder_minutes=parent.reminder_minutes,
                    priority=parent.priority,
                    category=parent.category,
                    tags=list(parent.tags),
                    recurrence_parent_id=parent.id,
                )
                child_id = self._storage.insert_event(child)
                child.id = child_id
                count += 1
                if count >= remaining:
                    break

            if count > 0:
                logger.info(f"循环事件实例化: '{parent.title}' 新增 {count} 条实例")

        except (ValueError, TypeError) as e:
            logger.warning(f"循环事件实例化失败: {parent.title}, error={e}")

    def expand_recurring_events(self):
        """启动时检查并补充循环事件实例

        确保每个循环事件都有足够的未来实例（最多 MAX_RECURRING_INSTANCES 条）。
        应在应用启动时调用。
        """
        recurring = self._storage.get_recurring_events()
        if not recurring:
            return

        logger.info(f"检查循环事件实例化: {len(recurring)} 个循环模板")
        for parent in recurring:
            self._generate_recurring_instances(parent)

    @staticmethod
    def _expand_recurring(event: CalendarEvent, range_start: datetime, range_end: datetime) -> List[CalendarEvent]:
        """将循环事件展开为指定范围内的具体实例（保留兼容，但不再在查询中使用）

        Args:
            event: 循环事件
            range_start: 范围起始
            range_end: 范围结束

        Returns:
            展开后的事件实例列表（id 为 None，表示虚拟实例）
        """
        if not event.recurrence_rule:
            return []

        instances = []
        try:
            # 构建 RRULE 字符串
            rrule_string = f"DTSTART:{event.start_time.strftime('%Y%m%dT%H%M%S')}\nRRULE:{event.recurrence_rule}"
            if event.recurrence_end:
                rrule_string += f";UNTIL={event.recurrence_end.strftime('%Y%m%dT%H%M%S')}"

            rule = rrulestr(rrule_string)

            # 计算事件时长
            duration = timedelta(minutes=event.duration_minutes) if event.duration_minutes else timedelta(0)

            # 在范围内查找实例
            for dt in rule.between(range_start, range_end, inc=True):
                # 跳过原始事件本身（已在普通事件查询中返回）
                if dt == event.start_time:
                    continue
                instance = CalendarEvent(
                    title=event.title,
                    start_time=dt,
                    end_time=dt + duration if duration else None,
                    description=event.description,
                    is_all_day=event.is_all_day,
                    reminder_minutes=event.reminder_minutes,
                    priority=event.priority,
                    category=event.category,
                    tags=list(event.tags),
                )
                instances.append(instance)
        except (ValueError, TypeError) as e:
            logger.warning(f"循环事件展开失败: {event.title}, rule={event.recurrence_rule}, error={e}")

        return instances

    # ================================================================
    # 回收站操作
    # ================================================================

    def get_deleted_events(self) -> List[CalendarEvent]:
        """获取回收站中的事件"""
        return self._storage.get_deleted_events()

    def restore_event(self, event_id: int) -> bool:
        """恢复已删除的事件"""
        return self._storage.restore_event(event_id)

    def hard_delete_event(self, event_id: int) -> bool:
        """彻底删除事件"""
        return self._storage.hard_delete_event(event_id)

    def clear_all_deleted(self) -> int:
        """一键清空回收站"""
        return self._storage.clear_all_deleted()

    def purge_deleted(self, days: int = 30) -> int:
        """清理超过指定天数的已删除事件"""
        return self._storage.purge_deleted(days)

    # ================================================================
    # 备份操作
    # ================================================================

    def export_backup(self, path: str) -> int:
        """导出备份为 JSON 文件"""
        backup = CalendarBackup(self._storage)
        return backup.export_json(path)

    def import_backup(self, path: str, mode: str = "merge") -> dict:
        """从 JSON 文件导入备份"""
        backup = CalendarBackup(self._storage)
        return backup.import_json(path, mode)

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
