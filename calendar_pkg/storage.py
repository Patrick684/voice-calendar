"""SQLite 数据库存储模块 - 封装日历事件的持久化操作"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from calendar_pkg.event import CalendarEvent

logger = logging.getLogger(__name__)


class SQLiteStorage:
    """SQLite 数据库存储引擎

    负责日历事件的增删改查操作，所有时间以 ISO 8601 字符串存储。
    """

    # 数据库表结构版本（用于未来迁移）
    SCHEMA_VERSION = 4

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
        """初始化数据库表结构并执行迁移"""
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
            # 检查并执行 schema 迁移
            self._migrate(conn)
            conn.commit()
            logger.info(f"数据库初始化完成: {self._db_path}")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise
        finally:
            conn.close()

    def _migrate(self, conn: sqlite3.Connection):
        """执行增量 schema 迁移"""
        cursor = conn.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        )
        row = cursor.fetchone()
        current_version = int(row["value"]) if row else 0

        if current_version < 2:
            self._migrate_v1_to_v2(conn)
            logger.info("Schema 迁移完成: v1 -> v2 (+priority, +category)")

        if current_version < 3:
            self._migrate_v2_to_v3(conn)
            logger.info("Schema 迁移完成: v2 -> v3 (+recurrence_rule, +recurrence_end)")

        if current_version < 4:
            self._migrate_v3_to_v4(conn)
            logger.info("Schema 迁移完成: v3 -> v4 (+deleted_at)")

        # 更新版本号
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("schema_version", str(self.SCHEMA_VERSION)),
        )

    @staticmethod
    def _migrate_v1_to_v2(conn: sqlite3.Connection):
        """v1 → v2: 新增 priority 和 category 列"""
        for col, default in [("priority", "INTEGER DEFAULT 0"), ("category", "TEXT DEFAULT ''")]:
            try:
                conn.execute(f"ALTER TABLE events ADD COLUMN {col} {default}")
            except sqlite3.OperationalError:
                pass  # 列已存在

    @staticmethod
    def _migrate_v2_to_v3(conn: sqlite3.Connection):
        """v2 → v3: 新增 recurrence_rule 和 recurrence_end 列"""
        for col, default in [("recurrence_rule", "TEXT DEFAULT ''"), ("recurrence_end", "TEXT")]:
            try:
                conn.execute(f"ALTER TABLE events ADD COLUMN {col} {default}")
            except sqlite3.OperationalError:
                pass

    @staticmethod
    def _migrate_v3_to_v4(conn: sqlite3.Connection):
        """v3 → v4: 新增 deleted_at 列（软删除）"""
        try:
            conn.execute("ALTER TABLE events ADD COLUMN deleted_at TEXT")
        except sqlite3.OperationalError:
            pass  # 列已存在

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
                    reminder_minutes, priority, category,
                    recurrence_rule, recurrence_end, tags,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["title"],
                    data["start_time"],
                    data["end_time"],
                    data["description"],
                    int(data.get("is_all_day", False)),
                    data.get("reminder_minutes"),
                    data.get("priority", 0),
                    data.get("category", ""),
                    data.get("recurrence_rule", ""),
                    data.get("recurrence_end"),
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
        """软删除事件（设置 deleted_at 时间戳）

        Args:
            event_id: 事件 ID

        Returns:
            是否删除成功
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "UPDATE events SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                (
                    datetime.now().isoformat(timespec="seconds"),
                    datetime.now().isoformat(timespec="seconds"),
                    event_id,
                ),
            )
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"事件已软删除: id={event_id}")
            return deleted
        finally:
            conn.close()

    def hard_delete_event(self, event_id: int) -> bool:
        """彻底删除事件

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
                logger.info(f"事件已彻底删除: id={event_id}")
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
        """查询时间范围内的事件（排除已删除）

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
                     AND deleted_at IS NULL
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
                   WHERE (title LIKE ? OR description LIKE ?)
                     AND deleted_at IS NULL
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

    def get_recurring_events(self) -> List[CalendarEvent]:
        """获取所有循环事件（排除已删除）"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT * FROM events
                   WHERE recurrence_rule IS NOT NULL
                     AND recurrence_rule != ''
                     AND deleted_at IS NULL
                   ORDER BY start_time ASC"""
            )
            return [CalendarEvent.from_row(dict(row)) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_deleted_events(self) -> List[CalendarEvent]:
        """获取所有已删除的事件（回收站）"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT * FROM events
                   WHERE deleted_at IS NOT NULL
                   ORDER BY deleted_at DESC"""
            )
            return [CalendarEvent.from_row(dict(row)) for row in cursor.fetchall()]
        finally:
            conn.close()

    def restore_event(self, event_id: int) -> bool:
        """恢复已删除的事件

        Args:
            event_id: 事件 ID

        Returns:
            是否恢复成功
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "UPDATE events SET deleted_at = NULL, updated_at = ? WHERE id = ? AND deleted_at IS NOT NULL",
                (datetime.now().isoformat(timespec="seconds"), event_id),
            )
            conn.commit()
            restored = cursor.rowcount > 0
            if restored:
                logger.info(f"事件已恢复: id={event_id}")
            return restored
        finally:
            conn.close()

    def purge_deleted(self, days: int = 30) -> int:
        """彻底删除超过指定天数的已删除事件

        Args:
            days: 删除天数阈值

        Returns:
            被彻底删除的事件数量
        """
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM events WHERE deleted_at IS NOT NULL AND deleted_at < ?",
                (cutoff,),
            )
            conn.commit()
            count = cursor.rowcount
            if count:
                logger.info(f"已彻底删除 {count} 条过期事件")
            return count
        finally:
            conn.close()

