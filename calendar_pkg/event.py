"""日历事件数据模型 - 定义事件结构和序列化方式"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List


@dataclass
class CalendarEvent:
    """日历事件数据模型

    属性:
        id: 事件唯一标识（自增主键）
        title: 事件标题
        start_time: 开始时间
        end_time: 结束时间（None 表示瞬时事件或与 start_time 相同）
        description: 事件描述/备注
        is_all_day: 是否全天事件
        reminder_minutes: 提前提醒分钟数（None 表示不提醒）
        priority: 优先级（0=普通, 1=重要, 2=紧急, 3=紧急且重要）
        tags: 事件标签列表
        created_at: 创建时间
        updated_at: 最后更新时间
    """

    # 优先级常量
    PRIORITY_NORMAL = 0
    PRIORITY_IMPORTANT = 1
    PRIORITY_URGENT = 2
    PRIORITY_CRITICAL = 3

    PRIORITY_LABELS = {
        0: "普通", 1: "重要", 2: "紧急", 3: "紧急且重要",
    }

    title: str
    start_time: datetime
    end_time: Optional[datetime] = None
    description: str = ""
    is_all_day: bool = False
    reminder_minutes: Optional[int] = 15
    priority: int = 0
    tags: List[str] = field(default_factory=list)
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self):
        """初始化后处理：自动填充时间字段"""
        now = datetime.now().isoformat(timespec="seconds")
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now
        # 全天事件默认 end_time 为 start_time 当天 23:59
        if self.is_all_day and self.end_time is None:
            self.end_time = self.start_time.replace(hour=23, minute=59, second=59)
        # 非全天事件 end_time 默认等于 start_time
        elif self.end_time is None:
            self.end_time = self.start_time

    def to_dict(self) -> dict:
        """序列化为字典（用于 JSON/数据库存储）"""
        data = asdict(self)
        # datetime 转为 ISO 字符串
        for key in ("start_time", "end_time"):
            if isinstance(data.get(key), datetime):
                data[key] = data[key].isoformat(timespec="seconds")
        # tags 列表转为逗号分隔字符串（SQLite 存储）
        if isinstance(data.get("tags"), list):
            data["tags"] = ",".join(data["tags"]) if data["tags"] else ""
        return data

    @classmethod
    def from_row(cls, row: dict) -> "CalendarEvent":
        """从数据库行（dict）构建事件对象

        Args:
            row: 数据库查询返回的字典

        Returns:
            CalendarEvent 实例
        """
        # 解析时间字段
        start_time = cls._parse_datetime(row["start_time"])
        end_time = cls._parse_datetime(row.get("end_time"))

        # 解析 tags
        tags_str = row.get("tags", "") or ""
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

        return cls(
            id=row["id"],
            title=row["title"],
            start_time=start_time,
            end_time=end_time,
            description=row.get("description", ""),
            is_all_day=bool(row.get("is_all_day", 0)),
            reminder_minutes=row.get("reminder_minutes"),
            priority=row.get("priority", 0) or 0,
            tags=tags,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    @staticmethod
    def _parse_datetime(value) -> Optional[datetime]:
        """解析时间字段，兼容字符串和 datetime 对象"""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None

    @property
    def duration_minutes(self) -> float:
        """事件时长（分钟）"""
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds() / 60
        return 0

    @property
    def is_upcoming(self) -> bool:
        """事件是否即将发生（未来事件）"""
        return self.start_time > datetime.now()

    @property
    def priority_label(self) -> str:
        """优先级的中文标签"""
        return self.PRIORITY_LABELS.get(self.priority, "普通")

    def __repr__(self) -> str:
        time_str = self.start_time.strftime("%Y-%m-%d %H:%M")
        return f"CalendarEvent(id={self.id}, title='{self.title}', time={time_str})"
