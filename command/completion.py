"""智能纠错与补全模块 - 检测不完整信息并生成补全建议"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from command.rule_engine import ParsedCommand, CommandType

logger = logging.getLogger(__name__)


class CommandCompleter:
    """指令补全器

    检测语音识别后的不完整信息，并生成补全建议。
    补全规则：
    - 无时间 → 默认 14:00
    - 无日期 → 默认明天
    - 无标题 → 使用原始文本
    """

    # 默认补全值
    DEFAULT_HOUR = 14
    DEFAULT_MINUTE = 0

    def __init__(self, default_hour: int = DEFAULT_HOUR, default_minute: int = DEFAULT_MINUTE):
        self._default_hour = default_hour
        self._default_minute = default_minute

    def check_completeness(self, command: ParsedCommand) -> dict:
        """检查指令完整性

        Args:
            command: 解析后的指令

        Returns:
            {
                "complete": bool,          # 是否完整
                "missing": list[str],      # 缺失的字段列表
                "suggestion": str | None,  # 补全建议文本（语音反馈用）
            }
        """
        if command.command_type != CommandType.ADD_EVENT:
            return {"complete": True, "missing": [], "suggestion": None}

        missing = []
        suggestions = []

        # 检查时间
        if command.time is None:
            missing.append("time")
            suggestions.append("时间")

        # 检查标题
        if not command.title or not command.title.strip():
            missing.append("title")
            suggestions.append("标题")

        is_complete = len(missing) == 0

        suggestion_text = None
        if not is_complete:
            parts = "、".join(suggestions)
            suggestion_text = f"检测到缺少{parts}，"
            if "time" in missing:
                default_time = self._get_default_time()
                suggestion_text += f"已为您补全为{default_time.month}月{default_time.day}日 {default_time.hour:02d}:{default_time.minute:02d}"

        return {
            "complete": is_complete,
            "missing": missing,
            "suggestion": suggestion_text,
        }

    def complete_command(self, command: ParsedCommand) -> ParsedCommand:
        """自动补全不完整的指令

        Args:
            command: 解析后的指令

        Returns:
            补全后的指令
        """
        if command.command_type != CommandType.ADD_EVENT:
            return command

        # 补全时间
        if command.time is None:
            command.time = self._get_default_time()
            logger.info(f"自动补全时间: {command.time.strftime('%Y-%m-%d %H:%M')}")

        # 补全标题
        if not command.title or not command.title.strip():
            command.title = command.original_text
            logger.info(f"自动补全标题: {command.title}")

        return command

    def _get_default_time(self) -> datetime:
        """获取默认补全时间（明天 14:00）"""
        tomorrow = datetime.now() + timedelta(days=1)
        return tomorrow.replace(
            hour=self._default_hour,
            minute=self._default_minute,
            second=0,
            microsecond=0,
        )
