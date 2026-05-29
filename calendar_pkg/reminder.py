"""提醒调度器 - 后台定时检查并触发事件提醒"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, List, Optional, Set

from calendar_pkg.event import CalendarEvent
from calendar_pkg.manager import CalendarManager

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """提醒调度器

    在后台线程中定期扫描即将触发的事件提醒，
    通过回调通知上层（GUI）显示提醒弹窗。
    """

    # 默认扫描间隔（秒）
    DEFAULT_CHECK_INTERVAL = 30

    def __init__(
        self,
        calendar_manager: CalendarManager,
        on_reminder: Optional[Callable[[CalendarEvent], None]] = None,
        check_interval: int = DEFAULT_CHECK_INTERVAL,
    ):
        """
        初始化提醒调度器

        Args:
            calendar_manager: 日历管理器实例
            on_reminder: 提醒触发回调（接收 CalendarEvent）
            check_interval: 扫描间隔秒数
        """
        self._manager = calendar_manager
        self._on_reminder = on_reminder
        self._check_interval = check_interval

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._triggered_ids: Set[int] = set()  # 已触发的提醒 ID（避免重复）
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        """调度器是否运行中"""
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        """启动提醒调度器"""
        if self.is_running:
            logger.warning("提醒调度器已在运行")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="ReminderScheduler"
        )
        self._thread.start()
        logger.info(f"提醒调度器已启动，扫描间隔: {self._check_interval}s")

    def stop(self):
        """停止提醒调度器"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("提醒调度器已停止")

    def reset_triggered(self):
        """重置已触发的提醒记录（跨天后调用）"""
        with self._lock:
            self._triggered_ids.clear()

    def set_callback(self, on_reminder: Callable[[CalendarEvent], None]):
        """动态更新提醒回调"""
        self._on_reminder = on_reminder

    def _run_loop(self):
        """后台扫描循环"""
        while not self._stop_event.is_set():
            try:
                self._check_reminders()
            except Exception as e:
                logger.error(f"提醒检查异常: {e}")

            # 等待下一次检查
            self._stop_event.wait(timeout=self._check_interval)

    def _check_reminders(self):
        """检查并触发到期的提醒"""
        now = datetime.now()

        # 查询未来一段时间内有提醒设置的事件
        upcoming = self._manager.get_pending_reminders(minutes_ahead=60)

        for event in upcoming:
            if event.id is None:
                continue

            # 检查是否应该触发提醒
            reminder_key = self._make_reminder_key(event, now)
            with self._lock:
                if reminder_key in self._triggered_ids:
                    continue

                if self._should_trigger(event, now):
                    self._triggered_ids.add(reminder_key)
                    self._fire_reminder(event)

    def _should_trigger(self, event: CalendarEvent, now: datetime) -> bool:
        """判断事件是否应该在此刻触发提醒

        Args:
            event: 事件对象
            now: 当前时间

        Returns:
            是否应该触发
        """
        if event.reminder_minutes is None:
            return False

        # 计算提醒触发时间 = 事件开始时间 - 提醒分钟数
        trigger_time = event.start_time - timedelta(
            minutes=event.reminder_minutes
        )

        # 当前时间在触发时间之后（含），且事件尚未结束
        return now >= trigger_time and now <= event.start_time

    def _fire_reminder(self, event: CalendarEvent):
        """触发提醒回调"""
        logger.info(f"触发提醒: {event.title} (提前 {event.reminder_minutes} 分钟)")
        if self._on_reminder:
            try:
                self._on_reminder(event)
            except Exception as e:
                logger.error(f"提醒回调执行失败: {e}")

    @staticmethod
    def _make_reminder_key(event: CalendarEvent, now: datetime) -> str:
        """生成提醒唯一键（同一天同一事件只触发一次）

        Args:
            event: 事件对象
            now: 当前时间

        Returns:
            唯一键字符串
        """
        date_str = now.strftime("%Y-%m-%d")
        return f"{event.id}_{date_str}"
