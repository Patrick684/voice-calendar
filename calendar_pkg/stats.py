"""打卡统计模块 - 完成率、热力图数据、趋势分析"""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

from calendar_pkg.storage import SQLiteStorage


class StatsEngine:
    """打卡统计引擎

    计算各分类完成率、生成热力图数据、趋势分析。
    """

    def __init__(self, storage: SQLiteStorage):
        self._storage = storage

    def get_monthly_stats(
        self, year: int, month: int
    ) -> Dict[str, Dict]:
        """获取指定月份各分类统计数据

        Returns:
            {category: {"total": int, "completed": int, "rate": float}}
        """
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)

        events = self._storage.get_events_by_range(start, end)
        stats: Dict[str, Dict] = {}

        for event in events:
            cat = event.category or "其他"
            if cat not in stats:
                stats[cat] = {"total": 0, "completed": 0, "rate": 0.0}
            stats[cat]["total"] += 1
            # 已完成的事件：start_time 在当前时间之前
            if event.start_time < datetime.now():
                stats[cat]["completed"] += 1

        # 计算完成率
        for cat_data in stats.values():
            if cat_data["total"] > 0:
                cat_data["rate"] = round(
                    cat_data["completed"] / cat_data["total"], 2
                )

        return stats

    def get_heatmap_data(
        self, year: int, month: int
    ) -> Dict[str, int]:
        """获取月度热力图数据（每天的事件数量）

        Returns:
            {"YYYY-MM-DD": count, ...}
        """
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)

        events = self._storage.get_events_by_range(start, end)
        heatmap: Dict[str, int] = {}

        for event in events:
            date_str = event.start_time.strftime("%Y-%m-%d")
            heatmap[date_str] = heatmap.get(date_str, 0) + 1

        return heatmap

    def get_trend_data(
        self, days: int = 30
    ) -> List[Tuple[str, int]]:
        """获取最近 N 天的每日事件数量趋势

        Returns:
            [(date_str, count), ...] 按日期升序
        """
        end = datetime.now()
        start = end - timedelta(days=days)
        events = self._storage.get_events_by_range(start, end)

        daily: Dict[str, int] = {}
        for event in events:
            date_str = event.start_time.strftime("%Y-%m-%d")
            daily[date_str] = daily.get(date_str, 0) + 1

        # 填充空白日期
        result = []
        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            result.append((date_str, daily.get(date_str, 0)))
            current += timedelta(days=1)

        return result

    def get_streak(self, category: str = "") -> int:
        """计算连续打卡天数

        Args:
            category: 指定分类，空字符串表示所有分类

        Returns:
            连续天数
        """
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        streak = 0
        check_date = today

        while True:
            day_end = check_date + timedelta(days=1)
            events = self._storage.get_events_by_range(check_date, day_end)

            if category:
                events = [e for e in events if e.category == category]

            if not events:
                break

            streak += 1
            check_date -= timedelta(days=1)

            # 最多回溯 365 天
            if streak >= 365:
                break

        return streak

    def get_category_summary(self) -> Dict[str, int]:
        """获取所有事件的分类汇总

        Returns:
            {category: total_count}
        """
        start = datetime(2000, 1, 1)
        end = datetime(2100, 1, 1)
        events = self._storage.get_events_by_range(start, end)

        summary: Dict[str, int] = {}
        for event in events:
            cat = event.category or "其他"
            summary[cat] = summary.get(cat, 0) + 1

        return summary
