"""事件自动分类器 - 基于关键词规则将事件归类为指定类别"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class EventClassifier:
    """事件分类器

    通过关键词匹配将事件标题自动归类为预定义类别。
    预留模型分类接口（classify_with_model）。
    """

    # 类别 → 关键词映射表
    CATEGORY_KEYWORDS: Dict[str, List[str]] = {
        "工作": [
            "开会",
            "会议",
            "汇报",
            "评审",
            "面试",
            "加班",
            "上班",
            "项目",
            "报告",
            "提案",
            "讨论",
            "沟通",
            "客户",
            "出差",
            "周报",
            "月报",
            "复盘",
            "需求",
            "开发",
            "代码",
            "测试",
            "上线",
            "发布",
            "部署",
            "运维",
        ],
        "健康": [
            "健身",
            "跑步",
            "游泳",
            "瑜伽",
            "体检",
            "看病",
            "医院",
            "牙医",
            "配药",
            "吃药",
            "复查",
            "按摩",
            "理疗",
            "运动",
            "爬山",
            "骑车",
            "打球",
        ],
        "学习": [
            "学习",
            "读书",
            "看书",
            "上课",
            "培训",
            "考试",
            "复习",
            "作业",
            "论文",
            "研究",
            "练习",
            "背单词",
            "刷题",
            "网课",
            "讲座",
            "分享会",
        ],
        "生活": [
            "买菜",
            "做饭",
            "打扫",
            "洗衣",
            "购物",
            "超市",
            "快递",
            "缴费",
            "理发",
            "修理",
            "搬家",
            "装修",
            "宠物",
            "喂猫",
            "喂狗",
            "接孩子",
            "送孩子",
        ],
        "娱乐": [
            "电影",
            "游戏",
            "唱歌",
            "KTV",
            "聚餐",
            "约会",
            "旅行",
            "逛街",
            "演出",
            "展览",
            "派对",
            "聚会",
            "看球",
            "追剧",
            "综艺",
        ],
        "社交": [
            "生日",
            "纪念日",
            "婚礼",
            "葬礼",
            "探望",
            "拜访",
            "同学会",
            "团建",
            "聚餐",
        ],
    }

    # 默认类别
    DEFAULT_CATEGORY = "其他"

    def __init__(self, custom_keywords: Optional[Dict[str, List[str]]] = None):
        """
        初始化分类器

        Args:
            custom_keywords: 自定义关键词映射，会合并到默认映射中
        """
        self._keywords = {}
        for category, words in self.CATEGORY_KEYWORDS.items():
            self._keywords[category] = list(words)

        if custom_keywords:
            for category, words in custom_keywords.items():
                existing = self._keywords.get(category, [])
                self._keywords[category] = existing + words

    def classify(self, title: str) -> str:
        """对事件标题进行分类

        Args:
            title: 事件标题

        Returns:
            类别字符串（工作/健康/学习/生活/娱乐/社交/其他）
        """
        if not title:
            return self.DEFAULT_CATEGORY

        title_lower = title.lower()

        # 按类别遍历关键词，命中即返回
        for category, keywords in self._keywords.items():
            for keyword in keywords:
                if keyword in title_lower:
                    logger.debug(f"事件分类: '{title}' -> {category} (关键词: {keyword})")
                    return category

        return self.DEFAULT_CATEGORY

    @property
    def categories(self) -> List[str]:
        """所有可用类别列表"""
        return list(self._keywords.keys()) + [self.DEFAULT_CATEGORY]
