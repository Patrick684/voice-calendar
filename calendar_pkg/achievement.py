"""成就系统 - 规则驱动的成就解锁"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Callable

from calendar_pkg.stats import StatsEngine


# 成就规则定义
ACHIEVEMENT_RULES = [
    {
        "id": "first_event",
        "name": "初次启程",
        "description": "创建第一个日程事件",
        "icon": "🌱",
        "check": lambda stats, total: total >= 1,
    },
    {
        "id": "ten_events",
        "name": "小有成就",
        "description": "累计创建 10 个事件",
        "icon": "🌿",
        "check": lambda stats, total: total >= 10,
    },
    {
        "id": "fifty_events",
        "name": "日程达人",
        "description": "累计创建 50 个事件",
        "icon": "🌳",
        "check": lambda stats, total: total >= 50,
    },
    {
        "id": "hundred_events",
        "name": "效率大师",
        "description": "累计创建 100 个事件",
        "icon": "🏆",
        "check": lambda stats, total: total >= 100,
    },
    {
        "id": "streak_3",
        "name": "三天打鱼",
        "description": "连续打卡 3 天",
        "icon": "🔥",
        "check": lambda stats, total: stats.get_streak() >= 3,
    },
    {
        "id": "streak_7",
        "name": "周周不断",
        "description": "连续打卡 7 天",
        "icon": "🔥",
        "check": lambda stats, total: stats.get_streak() >= 7,
    },
    {
        "id": "streak_30",
        "name": "月度坚持",
        "description": "连续打卡 30 天",
        "icon": "💎",
        "check": lambda stats, total: stats.get_streak() >= 30,
    },
    {
        "id": "health_10",
        "name": "健康先锋",
        "description": "创建 10 个健康类事件",
        "icon": "💪",
        "check": lambda stats, total: stats.get_category_summary().get("健康", 0) >= 10,
    },
    {
        "id": "work_20",
        "name": "工作狂人",
        "description": "创建 20 个工作类事件",
        "icon": "💼",
        "check": lambda stats, total: stats.get_category_summary().get("工作", 0) >= 20,
    },
    {
        "id": "study_15",
        "name": "学无止境",
        "description": "创建 15 个学习类事件",
        "icon": "📚",
        "check": lambda stats, total: stats.get_category_summary().get("学习", 0) >= 15,
    },
]


class AchievementEngine:
    """成就引擎

    管理成就规则、检测解锁、持久化已解锁成就。
    """

    def __init__(
        self,
        stats_engine: StatsEngine,
        save_path: str = "achievements.json",
    ):
        self._stats = stats_engine
        self._save_path = save_path
        self._unlocked: Dict[str, str] = {}  # {achievement_id: unlock_time_str}
        self._load()

    def _load(self):
        """加载已解锁成就"""
        if os.path.exists(self._save_path):
            try:
                with open(self._save_path, "r", encoding="utf-8") as f:
                    self._unlocked = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._unlocked = {}

    def _save(self):
        """保存已解锁成就"""
        try:
            with open(self._save_path, "w", encoding="utf-8") as f:
                json.dump(self._unlocked, f, ensure_ascii=False, indent=2)
        except IOError as e:
            import logging
            logging.getLogger(__name__).error(f"保存成就失败: {e}")

    def check_achievements(self) -> List[Dict]:
        """检查并解锁新成就

        Returns:
            新解锁的成就列表 [{id, name, description, icon, unlocked_at}]
        """
        newly_unlocked = []
        summary = self._stats.get_category_summary()
        total_events = sum(summary.values())

        for rule in ACHIEVEMENT_RULES:
            aid = rule["id"]
            if aid in self._unlocked:
                continue

            try:
                if rule["check"](self._stats, total_events):
                    unlock_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self._unlocked[aid] = unlock_time
                    newly_unlocked.append({
                        "id": aid,
                        "name": rule["name"],
                        "description": rule["description"],
                        "icon": rule["icon"],
                        "unlocked_at": unlock_time,
                    })
            except Exception:
                continue

        if newly_unlocked:
            self._save()

        return newly_unlocked

    def get_all_achievements(self) -> List[Dict]:
        """获取所有成就（含解锁状态）

        Returns:
            [{id, name, description, icon, unlocked: bool, unlocked_at}]
        """
        result = []
        for rule in ACHIEVEMENT_RULES:
            aid = rule["id"]
            unlocked = aid in self._unlocked
            result.append({
                "id": aid,
                "name": rule["name"],
                "description": rule["description"],
                "icon": rule["icon"],
                "unlocked": unlocked,
                "unlocked_at": self._unlocked.get(aid, ""),
            })
        return result

    def get_unlocked_count(self) -> int:
        """已解锁成就数量"""
        return len(self._unlocked)

    def get_total_count(self) -> int:
        """总成就数量"""
        return len(ACHIEVEMENT_RULES)
