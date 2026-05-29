"""热词管理模块 - 支持自定义热词表提升识别准确率"""

import json
from pathlib import Path
from typing import List, Dict, Optional


class HotwordCategory:
    """热词分类"""

    def __init__(self, name: str, hotwords: Optional[List[str]] = None):
        self.name = name
        self.hotwords = hotwords or []

    def to_dict(self) -> dict:
        return {"name": self.name, "hotwords": self.hotwords}

    @classmethod
    def from_dict(cls, data: dict) -> "HotwordCategory":
        return cls(name=data["name"], hotwords=data.get("hotwords", []))


class HotwordManager:
    """热词管理器，管理用户自定义热词和预置词库以提升 Whisper 识别准确率"""

    # 预置热词词库（按领域分类，覆盖常见易错词汇）
    BUILTIN_CATEGORIES: Dict[str, List[str]] = {
        "科技编程": [
            "Python",
            "JavaScript",
            "TypeScript",
            "React",
            "Vue",
            "Angular",
            "TensorFlow",
            "PyTorch",
            "Kubernetes",
            "Docker",
            "GitHub",
            "GitLab",
            "VSCode",
            "IntelliJ",
            "Linux",
            "Windows",
            "macOS",
            "Android",
            "iOS",
            "API",
            "HTTP",
            "JSON",
            "YAML",
            "SQL",
            "Redis",
            "MongoDB",
            "Transformer",
            "BERT",
            "GPT",
            "LLM",
            "CUDA",
            "GPU",
            "ChatGPT",
            "Copilot",
            "HuggingFace",
            "LangChain",
            "微服务",
            "容器化",
            "云原生",
            "持续集成",
            "敏捷开发",
        ],
        "网络用语": [
            "内卷",
            "躺平",
            "摆烂",
            "绝绝子",
            "YYDS",
            "破防",
            "元宇宙",
            "ChatGPT",
            "AI",
            "种草",
            "拔草",
            "出圈",
            "社死",
            "凡尔赛",
            "奥利给",
            "爷青回",
            "上头",
            "下头",
            "互联网嘴替",
            "电子榨菜",
            "显眼包",
            "多巴胺",
        ],
        "日常办公": [
            "Excel",
            "Word",
            "PowerPoint",
            "PPT",
            "Outlook",
            "Teams",
            "钉钉",
            "飞书",
            "企业微信",
            "腾讯会议",
            "Zoom",
            "OKR",
            "KPI",
            "ROI",
            "PPT",
            "周报",
            "日报",
            "复盘",
            "对齐",
            "拉通",
            "闭环",
            "赋能",
            "抓手",
        ],
        "日历日程": [
            "日程",
            "行程",
            "安排",
            "待办",
            "会议",
            "提醒",
            "备忘录",
            "日程表",
            "日历",
            "上午",
            "下午",
            "晚上",
            "明天",
            "后天",
            "下周",
            "预约",
            "面试",
            "复试",
            "评审",
            "团队会议",
            "项目评审",
            "周会",
            "月会",
            "年会",
            "培训",
            "汇报",
            "答辩",
            "体检",
            "复诊",
            "看牙",
            "拿药",
            "航班",
            "高铁",
            "火车",
            "飞机",
            "生日",
            "纪念日",
            "周年",
            "庆祝",
            "截止",
            "截稿",
            "提交",
            "交付",
        ],
    }

    # 预置分类默认激活状态
    BUILTIN_DEFAULT_ACTIVE = ["日历日程"]

    def __init__(self, hotword_file: Optional[str] = None):
        """
        初始化热词管理器

        Args:
            hotword_file: 热词持久化文件路径 (JSON)
        """
        self.hotword_file = Path(hotword_file) if hotword_file else None
        self._categories: Dict[str, HotwordCategory] = {}
        self._active_categories: List[str] = []
        self._global_hotwords: List[str] = []
        self._active_builtin: List[str] = list(self.BUILTIN_DEFAULT_ACTIVE)

        if self.hotword_file:
            self._load()

    def _load(self):
        """从文件加载热词"""
        if not self.hotword_file or not self.hotword_file.exists():
            return

        try:
            with open(self.hotword_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._global_hotwords = data.get("global_hotwords", [])
            self._active_categories = data.get("active_categories", [])
            self._active_builtin = data.get("active_builtin", list(self.BUILTIN_DEFAULT_ACTIVE))

            for cat_data in data.get("categories", []):
                cat = HotwordCategory.from_dict(cat_data)
                self._categories[cat.name] = cat

        except (json.JSONDecodeError, IOError, KeyError) as e:
            print(f"加载热词失败: {e}")

    def _save(self):
        """保存热词到文件"""
        if not self.hotword_file:
            return

        data = {
            "global_hotwords": self._global_hotwords,
            "active_categories": self._active_categories,
            "active_builtin": self._active_builtin,
            "categories": [cat.to_dict() for cat in self._categories.values()],
        }

        try:
            self.hotword_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.hotword_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"保存热词失败: {e}")

    # ---- 全局热词管理 ----

    def add_global_hotword(self, word: str):
        """添加全局热词（所有场景生效）"""
        word = word.strip()
        if word and word not in self._global_hotwords:
            self._global_hotwords.append(word)
            self._save()

    def remove_global_hotword(self, word: str):
        """移除全局热词"""
        if word in self._global_hotwords:
            self._global_hotwords.remove(word)
            self._save()

    def get_global_hotwords(self) -> List[str]:
        """获取所有全局热词"""
        return list(self._global_hotwords)

    # ---- 分类热词管理 ----

    def create_category(self, name: str) -> HotwordCategory:
        """创建热词分类"""
        if name not in self._categories:
            self._categories[name] = HotwordCategory(name)
            self._save()
        return self._categories[name]

    def delete_category(self, name: str):
        """删除热词分类"""
        if name in self._categories:
            del self._categories[name]
            if name in self._active_categories:
                self._active_categories.remove(name)
            self._save()

    def add_hotword(self, category: str, word: str):
        """向指定分类添加热词"""
        if category not in self._categories:
            self.create_category(category)

        word = word.strip()
        if word and word not in self._categories[category].hotwords:
            self._categories[category].hotwords.append(word)
            self._save()

    def remove_hotword(self, category: str, word: str):
        """从指定分类移除热词"""
        if category in self._categories:
            cat = self._categories[category]
            if word in cat.hotwords:
                cat.hotwords.remove(word)
                self._save()

    def get_categories(self) -> List[str]:
        """获取所有分类名称"""
        return list(self._categories.keys())

    def get_hotwords(self, category: str) -> List[str]:
        """获取指定分类的热词"""
        if category in self._categories:
            return list(self._categories[category].hotwords)
        return []

    # ---- 激活/停用分类 ----

    def activate_category(self, name: str):
        """激活热词分类"""
        if name in self._categories and name not in self._active_categories:
            self._active_categories.append(name)
            self._save()

    def deactivate_category(self, name: str):
        """停用热词分类"""
        if name in self._active_categories:
            self._active_categories.remove(name)
            self._save()

    def get_active_categories(self) -> List[str]:
        """获取已激活的用户分类"""
        return list(self._active_categories)

    # ---- 预置词库管理 ----

    def get_builtin_categories(self) -> List[str]:
        """获取所有预置词库分类名称"""
        return list(self.BUILTIN_CATEGORIES.keys())

    def get_builtin_hotwords(self, category: str) -> List[str]:
        """获取预置分类的热词列表"""
        return list(self.BUILTIN_CATEGORIES.get(category, []))

    def get_active_builtin_categories(self) -> List[str]:
        """获取已激活的预置分类"""
        return list(self._active_builtin)

    def activate_builtin_category(self, name: str):
        """激活预置词库分类"""
        if name in self.BUILTIN_CATEGORIES and name not in self._active_builtin:
            self._active_builtin.append(name)
            self._save()

    def deactivate_builtin_category(self, name: str):
        """停用预置词库分类"""
        if name in self._active_builtin:
            self._active_builtin.remove(name)
            self._save()

    # ---- Whisper initial_prompt 生成 ----

    def _collect_all_hotwords(self) -> List[str]:
        """
        收集所有生效的热词（全局 + 用户分类 + 预置词库），去重保序

        Returns:
            去重后的热词列表
        """
        all_hotwords = list(self._global_hotwords)

        # 添加已激活的用户分类热词
        for cat_name in self._active_categories:
            if cat_name in self._categories:
                all_hotwords.extend(self._categories[cat_name].hotwords)

        # 添加已激活的预置词库热词
        for cat_name in self._active_builtin:
            if cat_name in self.BUILTIN_CATEGORIES:
                all_hotwords.extend(self.BUILTIN_CATEGORIES[cat_name])

        # 去重保序
        return list(dict.fromkeys(all_hotwords))

    # 预置分类的自然语言上下文模板
    # Whisper 对自然语言 prompt 的响应比纯关键词列表更好
    _CATEGORY_CONTEXTS: Dict[str, str] = {
        "科技编程": "科技编程",
        "网络用语": "网络流行语",
        "日常办公": "办公职场",
    }

    def build_initial_prompt(self, weight: float = 1.5, max_words: int = 30) -> Optional[str]:
        """
        构建 Whisper 的 initial_prompt 字符串

        采用自然语言上下文 + 关键词的混合策略：
        1. 自然语言前缀描述场景（提升 Whisper 对语境的理解）
        2. 关键词列表补充专有名词（直接注入识别倾向）

        Args:
            weight: 热词权重（目前用于控制关键词列表长度）
            max_words: 最大不重复热词数量

        Returns:
            initial_prompt 字符串，如果没有热词则返回 None
        """
        all_hotwords = self._collect_all_hotwords()

        if not all_hotwords:
            return None

        # 智能截断：限制热词数量
        if len(all_hotwords) > max_words:
            all_hotwords = all_hotwords[:max_words]

        # 构建自然语言上下文前缀
        context_parts = []

        # 根据激活的预置分类生成场景描述
        active_contexts = []
        for cat_name in self._active_builtin:
            ctx = self._CATEGORY_CONTEXTS.get(cat_name, cat_name)
            active_contexts.append(ctx)
        for cat_name in self._active_categories:
            ctx = self._CATEGORY_CONTEXTS.get(cat_name, cat_name)
            active_contexts.append(ctx)

        if active_contexts:
            topics = "和".join(active_contexts[:3])  # 最多取 3 个主题
            context_parts.append(f"以下是关于{topics}的讨论。")

        # 拼接 prompt：自然语言前缀 + 关键词列表
        parts = []
        if context_parts:
            parts.append("。".join(context_parts) + "。")

        # 关键词列表（不重复，因为自然语言前缀已提供上下文）
        # 对于特别重要的词（weight > 1），可以重复一次
        prompt_words = []
        repeat = max(1, int(weight))
        for word in all_hotwords:
            prompt_words.append(word)
            if repeat > 1 and len(prompt_words) < max_words * 2:
                prompt_words.append(word)

        parts.append("，".join(prompt_words))

        return " ".join(parts)

    # ---- 导入/导出 ----

    def export_hotwords(self, filepath: str, format: str = "json"):
        """
        导出热词到文件

        Args:
            filepath: 导出文件路径
            format: 导出格式 (json/txt)
        """
        if format == "json":
            data = {
                "global_hotwords": self._global_hotwords,
                "categories": {name: cat.hotwords for name, cat in self._categories.items()},
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        elif format == "txt":
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("# 全局热词\n")
                for word in self._global_hotwords:
                    f.write(f"{word}\n")
                f.write("\n")
                for name, cat in self._categories.items():
                    f.write(f"# [{name}]\n")
                    for word in cat.hotwords:
                        f.write(f"{word}\n")
                    f.write("\n")

    def import_hotwords(self, filepath: str, format: str = "json"):
        """
        从文件导入热词

        Args:
            filepath: 导入文件路径
            format: 导入格式 (json/txt)
        """
        if format == "json":
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._global_hotwords.extend(data.get("global_hotwords", []))
            self._global_hotwords = list(dict.fromkeys(self._global_hotwords))

            for cat_name, words in data.get("categories", {}).items():
                if cat_name not in self._categories:
                    self.create_category(cat_name)
                for word in words:
                    if word not in self._categories[cat_name].hotwords:
                        self._categories[cat_name].hotwords.append(word)

        elif format == "txt":
            current_category = None
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        if line.startswith("# [") and line.endswith("]"):
                            current_category = line[3:-1]
                            self.create_category(current_category)
                        continue
                    if current_category:
                        self.add_hotword(current_category, line)
                    else:
                        self.add_global_hotword(line)

        self._save()
