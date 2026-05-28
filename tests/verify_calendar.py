"""
用途：验证日历核心层（event/storage/manager）功能是否正常
示例：python tests/verify_calendar.py
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calendar.event import CalendarEvent
from calendar.storage import SQLiteStorage
from calendar.manager import CalendarManager


def test_calendar_event():
    """测试 CalendarEvent 数据模型"""
    print("=" * 50)
    print("测试 CalendarEvent 数据模型")
    print("=" * 50)

    # 1. 基本创建
    now = datetime.now().replace(second=0, microsecond=0)
    event = CalendarEvent(title="测试会议", start_time=now)
    assert event.title == "测试会议"
    assert event.start_time == now
    assert event.end_time == now  # 默认等于 start_time
    assert event.id is None
    print(f"  [通过] 基本创建: {event}")

    # 2. 全天事件
    all_day = CalendarEvent(title="全天事件", start_time=now, is_all_day=True)
    assert all_day.is_all_day
    assert all_day.end_time.hour == 23
    print(f"  [通过] 全天事件: end_time={all_day.end_time}")

    # 3. 序列化与反序列化
    data = event.to_dict()
    assert isinstance(data["start_time"], str)
    assert isinstance(data["tags"], str)
    print(f"  [通过] 序列化: {data}")

    # 4. 带标签的事件
    tagged = CalendarEvent(title="标签测试", start_time=now, tags=["工作", "重要"])
    data = tagged.to_dict()
    assert data["tags"] == "工作,重要"
    print(f"  [通过] 标签序列化: {data['tags']}")

    print()


def test_sqlite_storage():
    """测试 SQLite 存储层"""
    print("=" * 50)
    print("测试 SQLiteStorage")
    print("=" * 50)

    # 使用临时数据库
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_calendar.db")
        storage = SQLiteStorage(db_path)

        now = datetime.now().replace(second=0, microsecond=0)

        # 1. 插入事件
        event = CalendarEvent(title="存储测试", start_time=now)
        event_id = storage.insert_event(event)
        assert event_id > 0
        print(f"  [通过] 插入事件: id={event_id}")

        # 2. 按 ID 查询
        fetched = storage.get_event_by_id(event_id)
        assert fetched is not None
        assert fetched.title == "存储测试"
        print(f"  [通过] 按 ID 查询: {fetched}")

        # 3. 更新事件
        updated = storage.update_event(event_id, title="已更新标题")
        assert updated
        fetched = storage.get_event_by_id(event_id)
        assert fetched.title == "已更新标题"
        print(f"  [通过] 更新事件: {fetched.title}")

        # 4. 时间范围查询
        tomorrow = now + timedelta(days=1)
        event2 = CalendarEvent(title="明天事件", start_time=tomorrow)
        storage.insert_event(event2)

        start = now - timedelta(hours=1)
        end = now + timedelta(days=2)
        results = storage.get_events_by_range(start, end)
        assert len(results) == 2
        print(f"  [通过] 范围查询: {len(results)} 条")

        # 5. 关键词搜索
        results = storage.search_events("更新")
        assert len(results) == 1
        assert results[0].title == "已更新标题"
        print(f"  [通过] 关键词搜索: {results[0].title}")

        # 6. 删除事件
        deleted = storage.delete_event(event_id)
        assert deleted
        assert storage.get_event_by_id(event_id) is None
        print(f"  [通过] 删除事件: id={event_id}")

        # 7. 事件计数
        count = storage.get_event_count()
        assert count == 1
        print(f"  [通过] 事件计数: {count}")

    print()


def test_calendar_manager():
    """测试 CalendarManager"""
    print("=" * 50)
    print("测试 CalendarManager")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_manager.db")
        manager = CalendarManager(db_path, default_reminder_minutes=15)

        now = datetime.now().replace(second=0, microsecond=0)

        # 1. 添加事件
        event = manager.add_event(
            title="团队会议", start_time=now + timedelta(hours=1)
        )
        assert event.id is not None
        assert event.reminder_minutes == 15
        print(f"  [通过] 添加事件: {event}")

        # 2. 获取今天事件
        today_events = manager.get_today_events()
        assert len(today_events) >= 1
        print(f"  [通过] 今日事件: {len(today_events)} 条")

        # 3. 获取未来事件
        future_event = manager.add_event(
            title="下周计划", start_time=now + timedelta(days=3)
        )
        upcoming = manager.get_upcoming_events(days=7)
        assert len(upcoming) >= 2
        print(f"  [通过] 未来事件: {len(upcoming)} 条")

        # 4. 修改事件
        updated = manager.update_event(event.id, title="全员会议")
        assert updated is not None
        assert updated.title == "全员会议"
        print(f"  [通过] 修改事件: {updated.title}")

        # 5. 搜索事件
        results = manager.search_events("全员")
        assert len(results) == 1
        print(f"  [通过] 搜索事件: {results[0].title}")

        # 6. 删除事件
        title = manager.delete_event(event.id)
        assert title == "全员会议"
        print(f"  [通过] 删除事件: {title}")

        # 7. 格式化输出
        events = manager.get_upcoming_events(days=7)
        formatted = CalendarManager.format_event_list(events)
        assert "下周计划" in formatted
        print(f"  [通过] 格式化输出:\n{formatted}")

        # 8. 月历标记日期
        dates = manager.get_month_event_dates(now.year, now.month)
        print(f"  [通过] 月历标记: {dates}")

    print()


if __name__ == "__main__":
    print("\n日历核心层功能验证\n")
    try:
        test_calendar_event()
        test_sqlite_storage()
        test_calendar_manager()
        print("=" * 50)
        print("全部测试通过!")
        print("=" * 50)
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
