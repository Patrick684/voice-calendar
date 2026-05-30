# -*- coding: utf-8 -*-
"""从 Kaggle 中文时间表达数据集中提取有用的日历时间词汇

筛选标准：
- 保留：日常生活中常用的相对/绝对时间表达（如 明天、下周一、下个月初）
- 过滤：文学性/历史性/成语性表达（如 洪荒、亘古、弹指之间）
"""

import zipfile
import xml.etree.ElementTree as ET
import json

xlsx_path = "C:/downloads/archive/1000_date_and_time_expression_in_Chinese.xlsx"

# 解析 Excel
z = zipfile.ZipFile(xlsx_path)
ss = ET.parse(z.open("xl/sharedStrings.xml"))
ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
strings = []
for si in ss.findall(".//s:si", ns):
    texts = [t.text or "" for t in si.findall(".//s:t", ns)]
    strings.append("".join(texts))

cell_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ws = ET.parse(z.open("xl/worksheets/sheet1.xml"))
rows = ws.findall(f".//{{{cell_ns}}}row")


def get_cell_value(cell):
    t = cell.get("t")
    v_elem = cell.find(f"{{{cell_ns}}}v")
    if v_elem is None:
        return ""
    v = v_elem.text or ""
    if t == "s":
        return strings[int(v)]
    return v


# 提取所有时间表达式（跳过表头）
all_expressions = []
for row in rows[1:]:
    cells = row.findall(f"{{{cell_ns}}}c")
    if len(cells) >= 2:
        expr = get_cell_value(cells[1]).strip()
        if expr:
            all_expressions.append(expr)

print(f"总共 {len(all_expressions)} 条时间表达式\n")

# ========================================
# 定义筛选规则
# ========================================

# 日历场景有用的关键词模式
USEFUL_PATTERNS = [
    # 相对日期
    "今天",
    "明天",
    "后天",
    "昨天",
    "前天",
    "大后天",
    "大前天",
    "今晚",
    "明晚",
    "今早",
    "明早",
    # 周相关
    "周",
    "星期",
    "礼拜",
    # 月相关
    "月",
    "号",
    # 时段
    "上午",
    "下午",
    "中午",
    "晚上",
    "早上",
    "凌晨",
    "傍晚",
    "早晨",
    "夜",
    # 点/分/时
    "点",
    "分",
    "时",
    # 循环
    "每天",
    "每周",
    "每月",
    "每年",
    "每个",
    # 相对词
    "下个",
    "上个",
    "这个",
    "本周",
    "下周",
    "上周",
    "本月",
    "下月",
    "上月",
    "年初",
    "年末",
    "月初",
    "月底",
    "月末",
    "周末",
    # 季节/节日（常用）
    "春节",
    "元旦",
    "国庆",
    "中秋",
    "端午",
    "清明",
    "五一",
    "十一",
    # 相对时间
    "之前",
    "之后",
    "以前",
    "以后",
    "左右",
    "前后",
    "天后",
    "天前",
    "小时后",
    "分钟后",
    "小时前",
    "分钟前",
    "半小时",
    "一刻钟",
    # 年份
    "年",
    # 具体时间格式
    ":",
    "：",
]

# 文学/历史/无关词（需要排除的）
EXCLUDE_PATTERNS = [
    "洪荒",
    "亘古",
    "远古",
    "太古",
    "混沌",
    "鸿蒙",
    "弹指",
    "刹那",
    "须臾",
    "瞬息",
    "霎",
    "倏忽",
    "永恒",
    "永远",
    "永世",
    "万世",
    "千古",
    "万古",
    "天荒地老",
    "沧海桑田",
    "斗转星移",
    "白驹过隙",
    "光阴似箭",
    "日月如梭",
    "岁月如歌",
    "时光荏苒",
    "朝",
    "暮",
    "旦",
    "夕",  # 文言文时间词
    "纪元",
    "世纪",
    "公元",
    "石器",
    "铁器",
    "青铜",
    "恐龙",
    "冰河",
    "冰川",
    "遥远",
    "久远",
    "悠久",
    "漫长",
    "片刻",
    "顷刻",
    "一瞬",
    "转眼",  # 太模糊，不是具体时间
    "遥遥无期",
    "天长地久",
    "地老天荒",
]


def is_useful(expr: str) -> bool:
    """判断表达式是否对日历场景有用"""
    # 先排除
    for pat in EXCLUDE_PATTERNS:
        if pat in expr:
            return False
    # 再筛入
    for pat in USEFUL_PATTERNS:
        if pat in expr:
            return True
    # 纯数字+年/月/日
    import re

    if re.search(r"\d+\s*[年月日号]", expr):
        return True
    if re.search(r"\d{1,2}:\d{2}", expr):
        return True
    return False


# 分类
useful = []
excluded = []
for expr in all_expressions:
    if is_useful(expr):
        useful.append(expr)
    else:
        excluded.append(expr)

print(f"有用的时间表达: {len(useful)} 条")
print(f"排除的文学/历史词: {len(excluded)} 条")
print()

# 进一步分类有用词汇
categories = {
    "相对日期": [],  # 明天、后天、大后天
    "周相关": [],  # 下周一、这个礼拜五
    "月日相关": [],  # 下个月5号、月初
    "时段/时间": [],  # 上午、下午三点、凌晨
    "循环": [],  # 每天、每周五
    "绝对日期": [],  # 2024年5月20日、6月1号
    "相对时间差": [],  # 三天后、半小时前
    "节日": [],  # 春节、国庆
    "其他有用": [],
}

import re

for expr in useful:
    if any(kw in expr for kw in ["每天", "每周", "每月", "每年", "每个"]):
        categories["循环"].append(expr)
    elif any(
        kw in expr
        for kw in ["今天", "明天", "后天", "昨天", "前天", "大后天", "大前天", "今晚", "明晚", "今早", "明早"]
    ):
        categories["相对日期"].append(expr)
    elif any(kw in expr for kw in ["周", "星期", "礼拜"]):
        categories["周相关"].append(expr)
    elif any(
        kw in expr for kw in ["天后", "天前", "小时后", "分钟后", "小时前", "分钟前", "之后", "之前", "以后", "以前"]
    ):
        categories["相对时间差"].append(expr)
    elif any(kw in expr for kw in ["春节", "元旦", "国庆", "中秋", "端午", "清明", "五一", "十一"]):
        categories["节日"].append(expr)
    elif re.search(r"\d{4}\s*年", expr) or re.search(r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]", expr):
        categories["绝对日期"].append(expr)
    elif any(kw in expr for kw in ["月", "号", "月初", "月底", "月末"]):
        categories["月日相关"].append(expr)
    elif any(
        kw in expr for kw in ["上午", "下午", "中午", "晚上", "早上", "凌晨", "傍晚", "早晨", "夜", "点", "分", "时"]
    ):
        categories["时段/时间"].append(expr)
    else:
        categories["其他有用"].append(expr)

# 输出分类结果
print("=" * 60)
print("分类结果:")
print("=" * 60)
for cat_name, items in categories.items():
    if items:
        print(f"\n【{cat_name}】({len(items)} 条)")
        for item in sorted(items):
            print(f"  {item}")

# 输出被排除的前30个（供参考）
print(f"\n\n{'=' * 60}")
print("被排除的词汇示例 (前30个):")
print("=" * 60)
for item in excluded[:30]:
    print(f"  {item}")

# 保存有用词汇到 JSON 供后续使用
output = {
    "total_useful": len(useful),
    "total_excluded": len(excluded),
    "categories": {k: v for k, v in categories.items() if v},
}
with open("scripts/kaggle_useful_time_words.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print("\n有用词汇已保存到 scripts/kaggle_useful_time_words.json")
