"""SQLite 数据库存储模块 - 封装日历事件的持久化操作"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from calendar.event import CalendarEvent

logger = logging.getLogger(__name__)


class SQLiteStorage:
    """SQLite 数据库存储引擎

    负责日历事件的增删改查操作，所有时间以 ISO 8601 字符串存储。
    """

    # 数据库表结构版本（用于未来迁移）
    SCHEMA_VERSION = 1

    def __init__(self, db_path: str):
        """
        初始化数据库存储

        Args:
            db_path: 数据库文件路径（如 %APPDATA%/VoiceCalendar/calendar.db）
        """
        self._db_path = db_path
        # 确保目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # 初始化数据库表
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接（每次操作使用独立连接，线程安全）"""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据库表结构"""
        conn = self._get_connection()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    description TEXT DEFAULT '',
                    is_all_day INTEGER DEFAULT 0,
                    reminder_minutes INTEGER DEFAULT 15,
                    tags TEXT DEFAULT '',
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_events_start_time
                    ON events(start_time);
                CREATE INDEX IF NOT EXISTS idx_events_end_time
                    ON events(end_time);

                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)
            # 写入 schema 版本
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                ("schema_version", str(self.SCHEMA_VERSION)),
            )
            conn.commit()
            logger.info(f"数据库初始化完成: {self._db_path}")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise
        finally:
            conn.close()

    def insert_event(self, event: CalendarEvent) -> int:
        """插入新事件

        Args:
            event: 事件对象

        Returns:
            新事件的 ID
        """
        data = event.to_dict()
        # 移除 id（自增生成）
        data.pop("id", None)

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """INSERT INTO events
                   (title, start_time, end_time, description, is_all_day,
                    reminder_minutes, tags, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["title"],
                    data["start_time"],
                    data["end_time"],
                    data["description"],
                    int(data.get("is_all_day", False)),
                    data.get("reminder_minutes"),
                    data.get("tags", ""),
                    data.get("created_at"),
                    data.get("updated_at"),
                ),
            )
            conn.commit()
            event_id = cursor.lastrowid
            logger.info(f"事件已创建: id={event_id}, title='{data['title']}'")
            return event_id
        finally:
            conn.close()

    def update_event(self, event_id: int, **kwargs) -> bool:
        """更新事件

        Args:
            event_id: 事件 ID
            **kwargs: 要更新的字段和值

        Returns:
            是否更新成功
        """
        if not kwargs:
            return False

        # 自动更新 updated_at
        kwargs["updated_at"] = datetime.now().isoformat(timespec="seconds")

        # 处理特殊字段
        if "tags" in kwargs and isinstance(kwargs["tags"], list):
            kwargs["tags"] = ",".join(kwargs["tags"])
        if "start_time" in kwargs and isinstance(kwargs["start_time"], datetime):
            kwargs["start_time"] = kwargs["start_time"].isoformat(timespec="seconds")
        if "end_time" in kwargs and isinstance(kwargs["end_time"], datetime):
            kwargs["end_time"] = kwargs["end_time"].isoformat(timespec="seconds")
        if "is_all_day" in kwargs:
            kwargs["is_all_day"] = int(kwargs["is_all_day"])

        # 构建 SET 子句
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [event_id]

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                f"UPDATE events SET {set_clause} WHERE id = ?", values
            )
            conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.info(f"事件已更新: id={event_id}, fields={list(kwargs.keys())}")
            return updated
        finally:
            conn.close()

    def delete_event(self, event_id: int) -> bool:
        """删除事件

        Args:
            event_id: 事件 ID

        Returns:
            是否删除成功
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"事件已删除: id={event_id}")
            return deleted
        finally:
            conn.close()

    def get_event_by_id(self, event_id: int) -> Optional[CalendarEvent]:
        """根据 ID 获取事件

        Args:
            event_id: 事件 ID

        Returns:
            CalendarEvent 或 None
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM events WHERE id = ?", (event_id,)
            )
            row = cursor.fetchone()
            if row:
                return CalendarEvent.from_row(dict(row))
            return None
        finally:
            conn.close()

    def get_events_by_range(
        self, start: datetime, end: datetime
    ) -> List[CalendarEvent]:
        """查询时间范围内的事件

        Args:
            start: 范围起始时间
            end: 范围结束时间

        Returns:
            事件列表，按开始时间升序
        """
        start_str = start.isoformat(timespec="seconds")
        end_str = end.isoformat(timespec="seconds")

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT * FROM events
                   WHERE start_time >= ? AND start_time <= ?
                   ORDER BY start_time ASC""",
                (start_str, end_str),
            )
            return [CalendarEvent.from_row(dict(row)) for row in cursor.fetchall()]
        finally:
            conn.close()

    def search_events(self, keyword: str, limit: int = 50) -> List[CalendarEvent]:
        """关键词搜索事件（搜索标题和描述）

        Args:
            keyword: 搜索关键词
            limit: 最大返回数量

        Returns:
            匹配的事件列表
        """
        pattern = f"%{keyword}%"
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT * FROM events
                   WHERE title LIKE ? OR description LIKE ?
                   ORDER BY start_time ASC
                   LIMIT ?""",
                (pattern, pattern, limit),
            )
            return [CalendarEvent.from_row(dict(row)) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_upcoming_events(
        self, from_time: datetime, minutes_ahead: int
    ) -> List[CalendarEvent]:
        """获取即将发生的事件（用于提醒调度）

        Args:
            from_time: 基准时间（通常为当前时间）
            minutes_ahead: 提前分钟数

        Returns:
            即将触发提醒的事件列表
        """
        from_str = from_time.isoformat(timespec="seconds")
        ahead_time = from_time.replace(
            minute=from_time.minute + minutes_ahead
        ) if minutes_ahead < 60 else from_time
        # 简化处理：用 datetime 计算
        from datetime import timedelta
        ahead_str = (from_time + timedelta(minutes=minutes_ahead)).isoformat(
            timespec="seconds"
        )

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT * FROM events
                   WHERE start_time > ? AND start_time <= ?
                     AND reminder_minutes IS NOT NULL
                   ORDER BY start_time ASC""",
                (from_str, ahead_str),
            )
            return [CalendarEvent.from_row(dict(row)) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_all_event_dates(self, year: int, month: int) -> List[str]:
        """获取指定月份中有事件的日期列表（用于月历视图标记）

        Args:
            year: 年份
            month: 月份

        Returns:
            日期字符串列表 (YYYY-MM-DD)
        """
        start = f"{year:04d}-{month:02d}-01"
        if month == 12:
            end = f"{year + 1:04d}-01-01"
        else:
            end = f"{year:04d}-{month + 1:02d}-01"

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT DISTINCT SUBSTR(start_time, 1, 10) as date_str
                   FROM events
                   WHERE start_time >= ? AND start_time < ?
                   ORDER BY date_str""",
                (start, end),
            )
            return [row["date_str"] for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_event_count(self) -> int:
        """获取事件总数"""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM events")
            return cursor.fetchone()["cnt"]
        finally:
            conn.close()

