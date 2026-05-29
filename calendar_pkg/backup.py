"""日历数据备份与恢复模块 - 支持 JSON 格式的导出/导入"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List

from calendar_pkg.event import CalendarEvent
from calendar_pkg.storage import SQLiteStorage

logger = logging.getLogger(__name__)


class CalendarBackup:
    """日历数据备份管理器

    支持全量导出为 JSON 文件和从 JSON 恢复，
    提供合并（保留现有数据）和覆盖（清空后导入）两种导入模式。
    """

    EXPORT_VERSION = 1  # 导出格式版本号

    def __init__(self, storage: SQLiteStorage):
        """
        初始化备份管理器

        Args:
            storage: SQLite 存储实例
        """
        self._storage = storage

    def export_json(self, path: str) -> int:
        """全量导出为 JSON 文件

        Args:
            path: 导出文件路径

        Returns:
            导出的事件数量
        """
        # 获取所有事件（包括已删除的）
        events = self._get_all_events()

        data = {
            "version": self.EXPORT_VERSION,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "event_count": len(events),
            "events": [e.to_dict() for e in events],
        }

        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)

        with open(path_obj, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"数据已导出: {path}, {len(events)} 条事件")
        return len(events)

    def import_json(self, path: str, mode: str = "merge") -> dict:
        """从 JSON 文件恢复数据

        Args:
            path: JSON 文件路径
            mode: 导入模式
                - "merge": 合并（跳过已存在的事件，按标题+时间判重）
                - "overwrite": 覆盖（清空现有数据后导入）

        Returns:
            {"imported": int, "skipped": int, "total": int}
        """
        if mode not in ("merge", "overwrite"):
            raise ValueError(f"不支持的导入模式: {mode}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict) or "events" not in data:
            raise ValueError("无效的备份文件格式")

        events_data = data["events"]
        result = {"imported": 0, "skipped": 0, "total": len(events_data)}

        if mode == "overwrite":
            self._clear_all_events()

        for event_dict in events_data:
            try:
                event = CalendarEvent.from_row(event_dict)
                if mode == "merge" and self._event_exists(event):
                    result["skipped"] += 1
                    continue
                # 清除 id 让数据库自动分配
                event.id = None
                self._storage.insert_event(event)
                result["imported"] += 1
            except Exception as e:
                logger.warning(f"导入事件失败: {e}")
                result["skipped"] += 1

        logger.info(f"数据导入完成: {path}, 导入 {result['imported']} 条, 跳过 {result['skipped']} 条")
        return result

    def _get_all_events(self) -> List[CalendarEvent]:
        """获取所有事件（包括已软删除的）"""
        conn = self._storage._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM events ORDER BY start_time ASC")
            return [CalendarEvent.from_row(dict(row)) for row in cursor.fetchall()]
        finally:
            conn.close()

    def _clear_all_events(self):
        """清空所有事件"""
        conn = self._storage._get_connection()
        try:
            conn.execute("DELETE FROM events")
            conn.commit()
            logger.info("已清空所有事件")
        finally:
            conn.close()

    def _event_exists(self, event: CalendarEvent) -> bool:
        """检查事件是否已存在（按标题+开始时间判重）"""
        conn = self._storage._get_connection()
        try:
            cursor = conn.execute(
                """SELECT COUNT(*) as cnt FROM events
                   WHERE title = ? AND start_time = ?""",
                (event.title, event.start_time.isoformat(timespec="seconds")),
            )
            return cursor.fetchone()["cnt"] > 0
        finally:
            conn.close()
