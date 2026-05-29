"""事件编辑对话框 - 添加/编辑日历事件的弹窗"""

import customtkinter as ctk
from datetime import datetime
from typing import Optional, Callable

from calendar_pkg.event import CalendarEvent


class EventDialog(ctk.CTkToplevel):
    """事件编辑对话框

    用于添加新事件或编辑已有事件。包含标题、时间、描述、
    全天事件开关、提醒设置等字段。
    """

    def __init__(
        self,
        master,
        event: Optional[CalendarEvent] = None,
        on_save: Optional[Callable[[dict], None]] = None,
        on_delete: Optional[Callable[[int], None]] = None,
        default_date: Optional[datetime] = None,
    ):
        """
        初始化事件对话框

        Args:
            master: 父窗口
            event: 编辑模式传入已有事件，添加模式传 None
            on_save: 保存回调，接收事件数据字典
            on_delete: 删除回调，接收事件 ID
            default_date: 默认日期（用于添加模式预填日期）
        """
        super().__init__(master)
        self._event = event
        self._on_save = on_save
        self._on_delete = on_delete
        self._is_edit = event is not None
        self._default_date = default_date

        self.title("编辑事件" if self._is_edit else "添加事件")
        self.geometry("420x480")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self._setup_ui()
        if self._is_edit:
            self._load_event()

        # 居中显示
        self.update_idletasks()
        x = master.winfo_x() + (master.winfo_width() - 420) // 2
        y = master.winfo_y() + (master.winfo_height() - 480) // 2
        self.geometry(f"+{x}+{y}")

    def _setup_ui(self):
        """构建表单 UI"""
        pad = {"padx": 15, "pady": 5}

        # 标题
        ctk.CTkLabel(self, text="标题:", font=ctk.CTkFont(size=13)).grid(row=0, column=0, sticky="w", **pad)
        self._title_entry = ctk.CTkEntry(self, width=300, placeholder_text="事件标题")
        self._title_entry.grid(row=0, column=1, sticky="ew", **pad)

        # 日期
        ctk.CTkLabel(self, text="日期:", font=ctk.CTkFont(size=13)).grid(row=1, column=0, sticky="w", **pad)
        self._date_entry = ctk.CTkEntry(
            self,
            width=300,
            placeholder_text="YYYY-MM-DD",
        )
        init_date = self._default_date if self._default_date else datetime.now()
        self._date_entry.insert(0, init_date.strftime("%Y-%m-%d"))
        self._date_entry.grid(row=1, column=1, sticky="ew", **pad)

        # 时间
        ctk.CTkLabel(self, text="时间:", font=ctk.CTkFont(size=13)).grid(row=2, column=0, sticky="w", **pad)
        self._time_entry = ctk.CTkEntry(
            self,
            width=300,
            placeholder_text="HH:MM（留空表示全天）",
        )
        self._time_entry.grid(row=2, column=1, sticky="ew", **pad)

        # 全天事件
        self._all_day_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self,
            text="全天事件",
            variable=self._all_day_var,
            font=ctk.CTkFont(size=13),
            command=self._toggle_all_day,
        ).grid(row=3, column=1, sticky="w", **pad)

        # 描述
        ctk.CTkLabel(self, text="描述:", font=ctk.CTkFont(size=13)).grid(row=4, column=0, sticky="nw", **pad)
        self._desc_text = ctk.CTkTextbox(self, width=300, height=80)
        self._desc_text.grid(row=4, column=1, sticky="ew", **pad)

        # 提醒
        ctk.CTkLabel(self, text="提醒:", font=ctk.CTkFont(size=13)).grid(row=5, column=0, sticky="w", **pad)
        self._reminder_var = ctk.StringVar(value="15 分钟")
        self._reminder_combo = ctk.CTkComboBox(
            self,
            width=300,
            values=["不提醒", "5 分钟", "10 分钟", "15 分钟", "30 分钟", "1 小时", "1 天"],
            variable=self._reminder_var,
        )
        self._reminder_combo.grid(row=5, column=1, sticky="ew", **pad)

        # 标签
        ctk.CTkLabel(self, text="标签:", font=ctk.CTkFont(size=13)).grid(row=6, column=0, sticky="w", **pad)
        self._tags_entry = ctk.CTkEntry(
            self,
            width=300,
            placeholder_text="逗号分隔，如: 工作,重要",
        )
        self._tags_entry.grid(row=6, column=1, sticky="ew", **pad)

        # 按钮区域
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=7, column=0, columnspan=2, pady=20)

        ctk.CTkButton(
            btn_frame,
            text="保存",
            width=100,
            command=self._on_save_click,
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame,
            text="取消",
            width=100,
            fg_color="gray",
            command=self.destroy,
        ).pack(side="left", padx=10)

        if self._is_edit and self._on_delete:
            ctk.CTkButton(
                btn_frame,
                text="删除",
                width=100,
                fg_color="#e74c3c",
                hover_color="#c0392b",
                command=self._on_delete_click,
            ).pack(side="left", padx=10)

        self.grid_columnconfigure(1, weight=1)

    def _toggle_all_day(self):
        """切换全天事件时禁用/启用时间输入"""
        if self._all_day_var.get():
            self._time_entry.configure(state="disabled")
        else:
            self._time_entry.configure(state="normal")

    def _load_event(self):
        """加载已有事件数据到表单"""
        event = self._event
        self._title_entry.insert(0, event.title)
        self._date_entry.delete(0, "end")
        self._date_entry.insert(0, event.start_time.strftime("%Y-%m-%d"))

        if event.is_all_day:
            self._all_day_var.set(True)
            self._time_entry.configure(state="disabled")
        else:
            self._time_entry.insert(0, event.start_time.strftime("%H:%M"))

        if event.description:
            self._desc_text.insert("1.0", event.description)

        # 提醒
        reminder_map = {
            None: "不提醒",
            5: "5 分钟",
            10: "10 分钟",
            15: "15 分钟",
            30: "30 分钟",
            60: "1 小时",
            1440: "1 天",
        }
        self._reminder_var.set(reminder_map.get(event.reminder_minutes, "15 分钟"))

        # 标签
        if event.tags:
            self._tags_entry.insert(0, ",".join(event.tags))

    def _on_save_click(self):
        """保存按钮点击"""
        data = self._collect_data()
        if data is None:
            return
        if self._on_save:
            self._on_save(data)
        self.destroy()

    def _on_delete_click(self):
        """删除按钮点击"""
        if self._event and self._on_delete:
            self._on_delete(self._event.id)
            self.destroy()

    def _collect_data(self) -> Optional[dict]:
        """收集表单数据

        Returns:
            事件数据字典，校验失败返回 None
        """
        title = self._title_entry.get().strip()
        if not title:
            self._show_error("请输入事件标题")
            return None

        # 解析日期
        date_str = self._date_entry.get().strip()
        time_str = self._time_entry.get().strip() if not self._all_day_var.get() else ""
        is_all_day = self._all_day_var.get()

        try:
            if is_all_day or not time_str:
                start_time = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=9)
                is_all_day = True
            else:
                start_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            self._show_error("日期时间格式错误，请使用 YYYY-MM-DD HH:MM")
            return None

        # 提醒
        reminder_map = {
            "不提醒": None,
            "5 分钟": 5,
            "10 分钟": 10,
            "15 分钟": 15,
            "30 分钟": 30,
            "1 小时": 60,
            "1 天": 1440,
        }
        reminder = reminder_map.get(self._reminder_var.get(), 15)

        # 标签
        tags_str = self._tags_entry.get().strip()
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

        # 描述
        description = self._desc_text.get("1.0", "end").strip()

        return {
            "title": title,
            "start_time": start_time,
            "is_all_day": is_all_day,
            "description": description,
            "reminder_minutes": reminder,
            "tags": tags,
        }

    def _show_error(self, message: str):
        """显示错误提示"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("提示")
        dialog.geometry("300x100")
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text=message, wraplength=260).pack(pady=15)
        ctk.CTkButton(dialog, text="确定", width=80, command=dialog.destroy).pack()
