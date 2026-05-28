"""识别历史记录模块 - 保存和查询语音识别结果"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class HistoryRecord:
    """单条识别记录"""

    def __init__(
        self,
        text: str,
        duration: float = 0.0,
        timestamp: Optional[str] = None,
        model: str = "",
    ):
        """
        初始化识别记录

        Args:
            text: 识别结果文本
            duration: 录音时长（秒）
            timestamp: ISO 格式时间戳，默认当前时间
            model: 使用的模型名称
        """
        self.text = text
        self.duration = duration
        self.timestamp = timestamp or datetime.now().isoformat(timespec="seconds")
        self.model = model

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "text": self.text,
            "duration": self.duration,
            "timestamp": self.timestamp,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryRecord":
        """从字典反序列化"""
        return cls(
            text=data["text"],
            duration=data.get("duration", 0.0),
            timestamp=data.get("timestamp", ""),
            model=data.get("model", ""),
        )

    @property
    def display_time(self) -> str:
        """格式化显示时间"""
        try:
            dt = datetime.fromisoformat(self.timestamp)
            return dt.strftime("%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return self.timestamp

    @property
    def text_preview(self) -> str:
        """文本预览（截断）"""
        return self.text[:50] + "..." if len(self.text) > 50 else self.text


class RecognitionHistory:
    """识别历史管理器"""

    # 默认最大保留记录数
    DEFAULT_MAX_RECORDS = 500

    def __init__(
        self, history_file: Optional[str] = None, max_records: int = DEFAULT_MAX_RECORDS
    ):
        """
        初始化历史管理器

        Args:
            history_file: 历史持久化文件路径 (JSON)
            max_records: 最大保留记录数
        """
        self.history_file = Path(history_file) if history_file else None
        self.max_records = max_records
        self._records: List[HistoryRecord] = []

        if self.history_file:
            self._load()

    def _load(self):
        """从文件加载历史"""
        if not self.history_file or not self.history_file.exists():
            return

        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.max_records = data.get("max_records", self.DEFAULT_MAX_RECORDS)
            for rec_data in data.get("records", []):
                self._records.append(HistoryRecord.from_dict(rec_data))

        except (json.JSONDecodeError, IOError, KeyError) as e:
            logger.warning(f"加载识别历史失败: {e}")

    def _save(self):
        """保存历史到文件"""
        if not self.history_file:
            return

        # 超过上限时裁剪旧记录
        if len(self._records) > self.max_records:
            self._records = self._records[-self.max_records :]

        data = {
            "max_records": self.max_records,
            "records": [r.to_dict() for r in self._records],
        }

        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"保存识别历史失败: {e}")

    # ---- 记录管理 ----

    def add_record(
        self, text: str, duration: float = 0.0, model: str = ""
    ) -> HistoryRecord:
        """
        添加一条识别记录

        Args:
            text: 识别文本
            duration: 录音时长
            model: 模型名称

        Returns:
            新建的记录对象
        """
        record = HistoryRecord(text=text, duration=duration, model=model)
        self._records.append(record)
        self._save()
        return record

    def get_records(self, limit: int = 0) -> List[HistoryRecord]:
        """
        获取历史记录（最新的在前面）

        Args:
            limit: 返回条数限制，0 表示全部

        Returns:
            记录列表（按时间倒序）
        """
        records = list(reversed(self._records))
        if limit > 0:
            records = records[:limit]
        return records

    def search(self, keyword: str) -> List[HistoryRecord]:
        """
        搜索历史记录

        Args:
            keyword: 搜索关键词

        Returns:
            匹配的记录列表（按时间倒序）
        """
        keyword_lower = keyword.lower()
        results = [r for r in self._records if keyword_lower in r.text.lower()]
        return list(reversed(results))

    def delete_record(self, index: int):
        """删除指定索引的记录（按正序）"""
        if 0 <= index < len(self._records):
            self._records.pop(index)
            self._save()

    def clear_all(self):
        """清空所有记录"""
        self._records.clear()
        self._save()

    @property
    def count(self) -> int:
        """记录总数"""
        return len(self._records)

    def get_statistics(self) -> dict:
        """
        获取统计信息

        Returns:
            包含总次数、总字数、总时长等统计
        """
        total_text_len = sum(len(r.text) for r in self._records)
        total_duration = sum(r.duration for r in self._records)
        return {
            "total_records": len(self._records),
            "total_characters": total_text_len,
            "total_duration_seconds": round(total_duration, 1),
            "avg_characters": round(total_text_len / len(self._records), 1)
            if self._records
            else 0,
        }
