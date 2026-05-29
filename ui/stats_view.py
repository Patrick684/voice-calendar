"""统计与成就视图 - 热力图日历 + 完成率 + 成就徽章"""

import calendar as cal_mod
import logging
from datetime import datetime
from typing import Dict

import customtkinter as ctk

from calendar_pkg.stats import StatsEngine
from calendar_pkg.achievement import AchievementEngine

logger = logging.getLogger(__name__)


class StatsView(ctk.CTkToplevel):
    """统计与成就视图窗口

    包含三个标签页：
    1. 热力图日历 - 月度事件密度热力图
    2. 分类统计 - 各分类完成率
    3. 成就徽章 - 解锁进度
    """

    def __init__(
        self,
        master,
        stats_engine: StatsEngine,
        achievement_engine: AchievementEngine,
    ):
        super().__init__(master)
        self._stats = stats_engine
        self._achievements = achievement_engine

        self._view_year = datetime.now().year
        self._view_month = datetime.now().month

        self.title("统计与成就")
        self.geometry("650x550")
        self.resizable(False, False)
        self.transient(master)

        self._setup_ui()
        self._check_new_achievements()

        # 居中
        self.update_idletasks()
        x = master.winfo_x() + (master.winfo_width() - 650) // 2
        y = master.winfo_y() + (master.winfo_height() - 550) // 2
        self.geometry(f"+{x}+{y}")

    def _setup_ui(self):
        """构建 UI"""
        # 标签页
        self._tabview = ctk.CTkTabview(self)
        self._tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self._tab_heatmap = self._tabview.add("热力图日历")
        self._tab_stats = self._tabview.add("分类统计")
        self._tab_achievements = self._tabview.add("成就徽章")

        self._build_heatmap_tab()
        self._build_stats_tab()
        self._build_achievements_tab()

    # ================================================================
    # 热力图日历标签页
    # ================================================================

    def _build_heatmap_tab(self):
        """构建热力图标签页"""
        # 月份导航
        nav_frame = ctk.CTkFrame(self._tab_heatmap, fg_color="transparent")
        nav_frame.pack(fill="x", pady=(10, 5))

        self._heatmap_prev = ctk.CTkButton(
            nav_frame,
            text="◀",
            width=35,
            command=self._heatmap_prev_month,
        )
        self._heatmap_prev.pack(side="left", padx=5)

        self._heatmap_label = ctk.CTkLabel(
            nav_frame,
            text="",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self._heatmap_label.pack(side="left", padx=10)

        self._heatmap_next = ctk.CTkButton(
            nav_frame,
            text="▶",
            width=35,
            command=self._heatmap_next_month,
        )
        self._heatmap_next.pack(side="left", padx=5)

        # 连续打卡天数
        self._streak_label = ctk.CTkLabel(
            nav_frame,
            text="",
            font=ctk.CTkFont(size=13),
            text_color="#e67e22",
        )
        self._streak_label.pack(side="right", padx=10)

        # 热力图日历容器
        self._heatmap_frame = ctk.CTkFrame(self._tab_heatmap, fg_color="transparent")
        self._heatmap_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 图例
        legend_frame = ctk.CTkFrame(self._tab_heatmap, fg_color="transparent")
        legend_frame.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(
            legend_frame,
            text="事件密度:",
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(0, 5))
        for color, label in [
            ("#ebedf0", "0"),
            ("#9be9a8", "1-2"),
            ("#40c463", "3-5"),
            ("#30a14e", "6+"),
        ]:
            box = ctk.CTkFrame(legend_frame, width=15, height=15, fg_color=color)
            box.pack(side="left", padx=2)
            ctk.CTkLabel(
                legend_frame,
                text=label,
                font=ctk.CTkFont(size=10),
            ).pack(side="left", padx=(0, 8))

        self._refresh_heatmap()

    def _refresh_heatmap(self):
        """刷新月度热力图"""
        self._heatmap_label.configure(text=f"{self._view_year}年 {self._view_month}月")

        streak = self._stats.get_streak()
        self._streak_label.configure(text=f"🔥 连续打卡 {streak} 天")

        heatmap_data = self._stats.get_heatmap_data(self._view_year, self._view_month)

        # 清空旧内容
        for widget in self._heatmap_frame.winfo_children():
            widget.destroy()

        # 星期标题行
        weekday_frame = ctk.CTkFrame(self._heatmap_frame, fg_color="transparent")
        weekday_frame.pack(fill="x")
        for day_name in ["一", "二", "三", "四", "五", "六", "日"]:
            ctk.CTkLabel(
                weekday_frame,
                text=day_name,
                font=ctk.CTkFont(size=11, weight="bold"),
                width=35,
            ).pack(side="left", expand=True)

        # 日期格子
        days_frame = ctk.CTkFrame(self._heatmap_frame, fg_color="transparent")
        days_frame.pack(fill="both", expand=True)

        month_cal = cal_mod.monthcalendar(self._view_year, self._view_month)

        for week_idx, week in enumerate(month_cal):
            for day_idx, day in enumerate(week):
                if day == 0:
                    ctk.CTkLabel(days_frame, text="", width=35, height=35).grid(
                        row=week_idx,
                        column=day_idx,
                        padx=1,
                        pady=1,
                    )
                    continue

                date_str = f"{self._view_year:04d}-{self._view_month:02d}-{day:02d}"
                count = heatmap_data.get(date_str, 0)
                color = self._get_heatmap_color(count)

                cell = ctk.CTkButton(
                    days_frame,
                    text=str(day),
                    width=35,
                    height=35,
                    fg_color=color,
                    hover_color=color,
                    text_color="white" if count > 0 else "#999",
                    font=ctk.CTkFont(size=12),
                    command=lambda d=date_str, c=count: self._show_day_detail(d, c),
                )
                cell.grid(row=week_idx, column=day_idx, padx=1, pady=1)

            days_frame.grid_rowconfigure(week_idx, weight=1)
        for col in range(7):
            days_frame.grid_columnconfigure(col, weight=1)

    def _get_heatmap_color(self, count: int) -> str:
        """根据事件数量返回热力图颜色"""
        if count == 0:
            return "#ebedf0"
        elif count <= 2:
            return "#9be9a8"
        elif count <= 5:
            return "#40c463"
        else:
            return "#30a14e"

    def _show_day_detail(self, date_str: str, count: int):
        """显示某天事件数量详情"""
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"{date_str} 详情")
        dialog.geometry("300x120")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text=f"📅 {date_str}",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(15, 5))
        ctk.CTkLabel(
            dialog,
            text=f"当天事件数: {count}",
            font=ctk.CTkFont(size=13),
        ).pack()
        ctk.CTkButton(
            dialog,
            text="关闭",
            width=80,
            command=dialog.destroy,
        ).pack(pady=10)

    def _heatmap_prev_month(self):
        if self._view_month == 1:
            self._view_month = 12
            self._view_year -= 1
        else:
            self._view_month -= 1
        self._refresh_heatmap()

    def _heatmap_next_month(self):
        if self._view_month == 12:
            self._view_month = 1
            self._view_year += 1
        else:
            self._view_month += 1
        self._refresh_heatmap()

    # ================================================================
    # 分类统计标签页
    # ================================================================

    def _build_stats_tab(self):
        """构建分类统计标签页"""
        # 月份选择
        nav_frame = ctk.CTkFrame(self._tab_stats, fg_color="transparent")
        nav_frame.pack(fill="x", pady=(10, 5))

        self._stats_prev = ctk.CTkButton(
            nav_frame,
            text="◀",
            width=35,
            command=self._stats_prev_month,
        )
        self._stats_prev.pack(side="left", padx=5)

        self._stats_label = ctk.CTkLabel(
            nav_frame,
            text="",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self._stats_label.pack(side="left", padx=10)

        self._stats_next = ctk.CTkButton(
            nav_frame,
            text="▶",
            width=35,
            command=self._stats_next_month,
        )
        self._stats_next.pack(side="left", padx=5)

        # 统计卡片容器
        self._stats_scroll = ctk.CTkScrollableFrame(self._tab_stats)
        self._stats_scroll.pack(fill="both", expand=True, padx=10, pady=5)

        # 趋势图区域
        self._trend_frame = ctk.CTkFrame(self._tab_stats, corner_radius=8)
        self._trend_frame.pack(fill="x", padx=10, pady=(0, 10))

        self._refresh_stats()

    def _refresh_stats(self):
        """刷新分类统计"""
        self._stats_label.configure(text=f"{self._view_year}年 {self._view_month}月")

        stats = self._stats.get_monthly_stats(self._view_year, self._view_month)

        # 清空旧内容
        for widget in self._stats_scroll.winfo_children():
            widget.destroy()

        if not stats:
            ctk.CTkLabel(
                self._stats_scroll,
                text="本月暂无事件",
                font=ctk.CTkFont(size=13),
                text_color="gray",
            ).pack(pady=30)
        else:
            # 总览
            total_events = sum(d["total"] for d in stats.values())
            total_completed = sum(d["completed"] for d in stats.values())
            overall_rate = round(total_completed / total_events * 100, 1) if total_events > 0 else 0

            summary_card = ctk.CTkFrame(self._stats_scroll, corner_radius=8)
            summary_card.pack(fill="x", pady=5)
            ctk.CTkLabel(
                summary_card,
                text=f"本月总览: {total_events} 个事件 | 完成率 {overall_rate}%",
                font=ctk.CTkFont(size=14, weight="bold"),
            ).pack(padx=15, pady=10)

            # 各分类卡片
            category_colors = {
                "工作": "#2196F3",
                "健康": "#4CAF50",
                "学习": "#FF9800",
                "生活": "#9C27B0",
                "娱乐": "#E91E63",
                "社交": "#00BCD4",
                "其他": "#757575",
            }

            for cat_name, cat_data in sorted(stats.items(), key=lambda x: x[1]["total"], reverse=True):
                self._create_category_card(cat_name, cat_data, category_colors)

        # 刷新趋势图
        self._refresh_trend()

    def _create_category_card(self, cat_name: str, cat_data: Dict, colors: Dict):
        """创建分类统计卡片"""
        card = ctk.CTkFrame(self._stats_scroll, corner_radius=8)
        card.pack(fill="x", pady=3)

        # 顶部：分类名 + 颜色
        color = colors.get(cat_name, "#757575")
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(10, 5))

        color_dot = ctk.CTkFrame(header, width=12, height=12, fg_color=color)
        color_dot.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            header,
            text=cat_name,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left")

        rate_text = f"{cat_data['completed']}/{cat_data['total']} ({cat_data['rate'] * 100:.0f}%)"
        ctk.CTkLabel(
            header,
            text=rate_text,
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(side="right")

        # 进度条
        progress = ctk.CTkProgressBar(card, width=280)
        progress.pack(padx=15, pady=(0, 10))
        progress.set(cat_data["rate"])

    def _refresh_trend(self):
        """刷新趋势图（文字版）"""
        for widget in self._trend_frame.winfo_children():
            widget.destroy()

        trend_data = self._stats.get_trend_data(days=14)
        if not trend_data:
            return

        ctk.CTkLabel(
            self._trend_frame,
            text="📈 最近 14 天趋势",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=15, pady=(10, 5))

        # 文字版趋势
        max_count = max(count for _, count in trend_data) if trend_data else 1
        max_count = max(max_count, 1)

        trend_lines = []
        for date_str, count in trend_data[-14:]:
            bar_len = int(count / max_count * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            short_date = date_str[5:]  # MM-DD
            trend_lines.append(f"{short_date} |{bar}| {count}")

        trend_text = "\n".join(trend_lines)
        ctk.CTkLabel(
            self._trend_frame,
            text=trend_text,
            font=ctk.CTkFont(size=10, family="Consolas"),
            justify="left",
        ).pack(anchor="w", padx=15, pady=(0, 10))

    def _stats_prev_month(self):
        if self._view_month == 1:
            self._view_month = 12
            self._view_year -= 1
        else:
            self._view_month -= 1
        self._refresh_stats()

    def _stats_next_month(self):
        if self._view_month == 12:
            self._view_month = 1
            self._view_year += 1
        else:
            self._view_month += 1
        self._refresh_stats()

    # ================================================================
    # 成就徽章标签页
    # ================================================================

    def _build_achievements_tab(self):
        """构建成就徽章标签页"""
        # 总览
        self._ach_header = ctk.CTkFrame(self._tab_achievements, fg_color="transparent")
        self._ach_header.pack(fill="x", padx=10, pady=(10, 5))

        # 成就列表
        self._ach_scroll = ctk.CTkScrollableFrame(self._tab_achievements)
        self._ach_scroll.pack(fill="both", expand=True, padx=10, pady=5)

        self._refresh_achievements()

    def _refresh_achievements(self):
        """刷新成就列表"""
        for widget in self._ach_header.winfo_children():
            widget.destroy()
        for widget in self._ach_scroll.winfo_children():
            widget.destroy()

        achievements = self._achievements.get_all_achievements()
        unlocked = self._achievements.get_unlocked_count()
        total = self._achievements.get_total_count()

        ctk.CTkLabel(
            self._ach_header,
            text=f"🏆 成就进度: {unlocked}/{total}",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left", padx=10)

        for ach in achievements:
            self._create_achievement_card(ach)

    def _create_achievement_card(self, ach: Dict):
        """创建成就卡片"""
        card = ctk.CTkFrame(
            self._ach_scroll,
            corner_radius=8,
            fg_color="#f0f0f0" if not ach["unlocked"] else "#e8f5e9",
        )
        card.pack(fill="x", pady=3)

        # 图标 + 名称
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(10, 5))

        icon_text = ach["icon"] if ach["unlocked"] else "🔒"
        ctk.CTkLabel(
            header,
            text=icon_text,
            font=ctk.CTkFont(size=18),
            width=30,
        ).pack(side="left")

        name_color = "#333" if ach["unlocked"] else "#999"
        ctk.CTkLabel(
            header,
            text=ach["name"],
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=name_color,
        ).pack(side="left", padx=(5, 0))

        if ach["unlocked"]:
            ctk.CTkLabel(
                header,
                text="✓ 已解锁",
                font=ctk.CTkFont(size=11),
                text_color="#4CAF50",
            ).pack(side="right")

        # 描述
        desc_color = "#666" if ach["unlocked"] else "#aaa"
        ctk.CTkLabel(
            card,
            text=ach["description"],
            font=ctk.CTkFont(size=12),
            text_color=desc_color,
            anchor="w",
        ).pack(fill="x", padx=(50, 15), pady=(0, 5))

        if ach["unlocked"] and ach["unlocked_at"]:
            ctk.CTkLabel(
                card,
                text=f"解锁于 {ach['unlocked_at']}",
                font=ctk.CTkFont(size=10),
                text_color="#999",
                anchor="w",
            ).pack(fill="x", padx=(50, 15), pady=(0, 8))

    # ================================================================
    # 辅助
    # ================================================================

    def _check_new_achievements(self):
        """检查新成就并弹出提示"""
        new_achievements = self._achievements.check_achievements()
        if new_achievements:
            for ach in new_achievements:
                self._show_achievement_popup(ach)
            self._refresh_achievements()

    def _show_achievement_popup(self, ach: Dict):
        """弹出成就解锁通知"""
        popup = ctk.CTkToplevel(self)
        popup.title("成就解锁!")
        popup.geometry("300x130")
        popup.attributes("-topmost", True)
        popup.transient(self)

        ctk.CTkLabel(
            popup,
            text=f"{ach['icon']} 成就解锁!",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(15, 5))
        ctk.CTkLabel(
            popup,
            text=f"{ach['name']} - {ach['description']}",
            font=ctk.CTkFont(size=12),
            wraplength=260,
        ).pack()
        ctk.CTkButton(
            popup,
            text="太棒了!",
            width=80,
            command=popup.destroy,
        ).pack(pady=10)
