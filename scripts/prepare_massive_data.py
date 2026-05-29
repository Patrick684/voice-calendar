"""MASSIVE 数据集预处理与增强脚本

功能：
1. 读取 MASSIVE zh-CN 数据，映射 60 种意图为 5 类
2. 对 delete_event/update_event 小类进行数据增强
3. Stratified train/dev/test 分割
4. 输出 JSONL + label_map.json
"""

import gzip
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
random.seed(42)

# --- 配置 ---
MASSIVE_ZH_CN_PATH = (
    r"C:\Users\16574\.cache\modelscope\hub\datasets\downloads"
    r"\9c533354e2ee7e88c0bdfbf9cabf4ab9f100f2f0b3a44e417012a6e4f3a94d92"
)
OUTPUT_DIR = Path("data/intent")
AUGMENT_TARGET = 500  # 小类增强目标数量
OTHER_MAX = 2000  # other 类最多保留条数（裁剪冗余）

# MASSIVE 意图 -> 我们的 5 类
INTENT_MAP = {
    # add_event: 创建日程/设置闹钟/设置提醒
    "calendar_set": "add_event",
    "alarm_set": "add_event",
    # query_event: 查询日程/查询时间/查询闹钟
    "calendar_query": "query_event",
    "datetime_query": "query_event",
    "alarm_query": "query_event",
    "datetime_convert": "query_event",
    # delete_event: 删除日程/取消闹钟
    "calendar_remove": "delete_event",
    "alarm_remove": "delete_event",
    # update_event: 无直接对应，需人工合成
    # other: 其余全部
}
DEFAULT_LABEL = "other"
LABEL_NAMES = [
    "add_event",
    "add_recurring",
    "delete_event",
    "delete_recurring",
    "update_event",
    "update_recurring",
    "query_event",
    "other",
]

# --- 语气词/填充词（用于增强） ---
FILLER_WORDS = ["嗯", "那个", "帮我", "请", "给我", "麻烦", "一下", "啊", "呢", "吧"]
FILLER_PREFIX = ["帮我", "请", "麻烦你", "能不能", "可以", "给我"]
FILLER_SUFFIX = ["一下", "吧", "呢", "啊", "好不好", "行不行"]

# --- 语音口语化增强（模拟 Whisper 转写特征） ---
COLLOQUIAL_PREFIX = ["哎", "嗯", "那个", "哎那个", "帮我一下", "那个帮我"]
COLLOQUIAL_FILLER = ["嗯", "呃", "那个"]

# --- update_event 合成模板 ---
UPDATE_TEMPLATES = [
    "把{event}改到{time}",
    "把{time}的{event}推迟一小时",
    "把{event}提前到{time}",
    "修改{event}的时间",
    "调整{time}的{event}",
    "{event}改到{time}",
    "推迟{event}到{time}",
    "提前{event}到{time}",
    "更改{event}的时间",
    "把{event}从{time}改到{time2}",
    "{time}的{event}改一下时间",
    "帮我改一下{event}的时间",
    "把{event}调到下周",
    "{event}推迟半个小时",
    "提前{event}的时间",
    "调整一下{event}的安排",
    "把会议改到{time}",
    "把约会推迟到{time}",
    "把提醒改到{time}",
    "将{event}改为{time}",
]

EVENT_WORDS = [
    "会议",
    "约会",
    "聚餐",
    "面试",
    "考试",
    "开会",
    "上课",
    "培训",
    "运动",
    "健身",
    "看牙",
    "理发",
    "出差",
    "报告",
    "答辩",
]

# --- 循环事件样本 ---
RECURRING_EVENTS = [
    "起床",
    "健身",
    "吃药",
    "吃饭",
    "上班",
    "打卡",
    "学习",
    "跑步",
    "午睡",
    "散步",
    "读书",
    "背单词",
    "瑜伽",
    "游泳",
]
WEEKDAY_WORDS = ["一", "二", "三", "四", "五", "六", "日"]
DAY_WORDS = ["1", "5", "10", "15", "20", "25"]
REC_TIME_WORDS = ["上午九点", "下午三点", "晚上八点", "早上七点", "中午十二点", "下午两点", "傍晚六点"]

RECURRING_ADD_TEMPLATES = [
    "每天{time}{event}",
    "每日{time}{event}",
    "每周{weekday}{time}{event}",
    "每个星期{weekday}{time}{event}",
    "每个月{day}号{time}{event}",
    "每月{day}号{event}",
    "工作日{time}{event}",
    "周一到周五{time}{event}",
    "下周每天{time}{event}",
    "这周每天{time}{event}",
    "每天都要{event}",
    "每天{time}都要{event}",
    "提醒我每天{time}{event}",
    "帮我设置每天{time}的{event}",
    "每{weekday}下午{event}",
    "安排每天{event}",
    "设置每周{weekday}的{event}",
    "我要每天{time}{event}",
    "坚持每天{event}",
    "养成每天{time}{event}的习惯",
]

RECURRING_DELETE_TEMPLATES = [
    "取消每天的{event}",
    "不要每天{event}了",
    "停止每周{weekday}的{event}",
    "把每月的{event}取消掉",
    "不用每天{event}了",
    "删掉每天{time}的{event}",
    "取消每周{weekday}的{event}",
    "别再每天{event}了",
    "去掉每天的{event}提醒",
    "把每天的{event}删了",
]

RECURRING_UPDATE_TEMPLATES = [
    "把每天的{event}改到{time}",
    "把每周{weekday}的{event}推迟一小时",
    "每天的{event}改成{time}",
    "把每天的{event}提前半小时",
    "修改每周{weekday}的{event}时间",
    "把每月的{event}改到{day}号",
    "调整每天{event}的时间",
    "工作日的{event}改到{time}",
]
TIME_WORDS = [
    "明天",
    "后天",
    "下周一",
    "下午三点",
    "上午十点",
    "晚上八点",
    "三点半",
    "五点",
    "九点",
    "中午十二点",
    "早上七点",
    "傍晚六点",
]


def load_massive_zh_cn(path: str) -> list[dict]:
    """加载 MASSIVE zh-CN gzip 数据"""
    data = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def map_intents(data: list[dict]) -> list[dict]:
    """将 MASSIVE 意图映射为 5 类"""
    mapped = []
    for item in data:
        original_intent = item.get("label", "")
        label = INTENT_MAP.get(original_intent, DEFAULT_LABEL)
        mapped.append({"text": item["text"].strip(), "label": label})
    return mapped


def augment_with_fillers(text: str) -> str:
    """随机插入/删除语气词增强"""
    augmented = text
    action = random.choice(["insert_prefix", "insert_suffix", "insert_filler", "noop"])
    if action == "insert_prefix":
        prefix = random.choice(FILLER_PREFIX)
        augmented = prefix + augmented
    elif action == "insert_suffix":
        suffix = random.choice(FILLER_SUFFIX)
        augmented = augmented + suffix
    elif action == "insert_filler":
        filler = random.choice(FILLER_WORDS[:4])  # 只用自然语气词
        pos = random.randint(0, max(0, len(augmented) - 1))
        augmented = augmented[:pos] + filler + augmented[pos:]
    return augmented


def augment_colloquial(text: str) -> str:
    """语音口语化增强：模拟 Whisper 转写特征"""
    augmented = text
    action = random.choice(
        [
            "add_prefix",  # 口语前缀：哎/那个/帮我一下
            "slight_repeat",  # 轻微重复：明天明天下午开会
            "ultra_short",  # 极简短句（去修饰词）
            "add_filler",  # 插入语气词：嗯/呃
            "noop",
        ]
    )
    if action == "add_prefix":
        prefix = random.choice(COLLOQUIAL_PREFIX)
        augmented = prefix + augmented
    elif action == "slight_repeat" and len(text) >= 2:
        # 重复开头 1-2 个字
        repeat_len = min(2, len(text))
        augmented = text[:repeat_len] + text
    elif action == "ultra_short" and len(text) > 6:
        # 截取核心部分（模拟极简口语）
        start = random.randint(0, max(0, len(text) // 3))
        end = start + random.randint(4, max(5, len(text) * 2 // 3))
        augmented = text[start:end]
    elif action == "add_filler":
        filler = random.choice(COLLOQUIAL_FILLER)
        pos = random.randint(0, max(0, len(text) - 1))
        augmented = text[:pos] + filler + text[pos:]
    return augmented if augmented else text


def generate_update_events(count: int) -> list[dict]:
    """合成 update_event 样本"""
    samples = []
    for _ in range(count):
        template = random.choice(UPDATE_TEMPLATES)
        event = random.choice(EVENT_WORDS)
        time = random.choice(TIME_WORDS)
        time2 = random.choice([t for t in TIME_WORDS if t != time])
        text = template.format(event=event, time=time, time2=time2)
        samples.append({"text": text, "label": "update_event"})
    return samples


def generate_recurring_samples(count: int) -> tuple[list[dict], list[dict], list[dict]]:
    """合成循环事件样本 (add_recurring, delete_recurring, update_recurring)

    Returns:
        (add_samples, delete_samples, update_samples) 三元组
    """
    add_samples = []
    for _ in range(count):
        template = random.choice(RECURRING_ADD_TEMPLATES)
        event = random.choice(RECURRING_EVENTS)
        time = random.choice(REC_TIME_WORDS)
        weekday = random.choice(WEEKDAY_WORDS)
        day = random.choice(DAY_WORDS)
        text = template.format(event=event, time=time, weekday=weekday, day=day)
        add_samples.append({"text": text, "label": "add_recurring"})

    delete_samples = []
    for _ in range(count // 2):
        template = random.choice(RECURRING_DELETE_TEMPLATES)
        event = random.choice(RECURRING_EVENTS)
        time = random.choice(REC_TIME_WORDS)
        weekday = random.choice(WEEKDAY_WORDS)
        text = template.format(event=event, time=time, weekday=weekday)
        delete_samples.append({"text": text, "label": "delete_recurring"})

    update_samples = []
    for _ in range(count // 2):
        template = random.choice(RECURRING_UPDATE_TEMPLATES)
        event = random.choice(RECURRING_EVENTS)
        time = random.choice(REC_TIME_WORDS)
        weekday = random.choice(WEEKDAY_WORDS)
        day = random.choice(DAY_WORDS)
        text = template.format(event=event, time=time, weekday=weekday, day=day)
        update_samples.append({"text": text, "label": "update_recurring"})

    return add_samples, delete_samples, update_samples


# 循环关键词（用于重标注 MASSIVE 数据中的循环样本）
_RECURRING_KEYWORDS = ["每天", "每日", "每周", "每月", "每年", "每个星期", "工作日", "重复", "循环"]


def relabel_recurring_samples(data: list[dict]) -> list[dict]:
    """将 MASSIVE 中含循环关键词的 add_event 样本重标注为 add_recurring"""
    relabeled = []
    for item in data:
        if item["label"] == "add_event" and any(kw in item["text"] for kw in _RECURRING_KEYWORDS):
            relabeled.append({"text": item["text"], "label": "add_recurring"})
        else:
            relabeled.append(item)
    return relabeled


def augment_class(data: list[dict], target_label: str, target_count: int, use_colloquial: bool = False) -> list[dict]:
    """对小类进行增强至目标数量

    Args:
        use_colloquial: 是否使用语音口语化增强（更适合日历场景）
    """
    class_samples = [d for d in data if d["label"] == target_label]
    current_count = len(class_samples)
    if current_count >= target_count:
        return class_samples

    needed = target_count - current_count
    augmented = list(class_samples)  # start with originals
    augment_fn = augment_colloquial if use_colloquial else augment_with_fillers

    attempts = 0
    while len(augmented) < target_count and attempts < needed * 10:
        original = random.choice(class_samples)
        new_text = augment_fn(original["text"])
        if new_text != original["text"]:
            augmented.append({"text": new_text, "label": target_label})
        attempts += 1

    return augmented[:target_count]


def stratified_split(data: list[dict], train_ratio=0.8, dev_ratio=0.1, test_ratio=0.1):
    """按类别分层分割数据"""
    by_label = defaultdict(list)
    for item in data:
        by_label[item["label"]].append(item)

    train, dev, test = [], [], []
    for label, items in by_label.items():
        random.shuffle(items)
        n = len(items)
        n_train = int(n * train_ratio)
        n_dev = int(n * dev_ratio)
        train.extend(items[:n_train])
        dev.extend(items[n_train : n_train + n_dev])
        test.extend(items[n_train + n_dev :])

    random.shuffle(train)
    random.shuffle(dev)
    random.shuffle(test)
    return train, dev, test


def print_distribution(data: list[dict], title: str):
    """打印类别分布"""
    counts = Counter(d["label"] for d in data)
    print(f"\n=== {title} ===")
    for label in LABEL_NAMES:
        print(f"  {label}: {counts.get(label, 0)}")
    print(f"  TOTAL: {len(data)}")


def main():
    print("Step 1: 加载 MASSIVE zh-CN 数据...")
    raw_data = load_massive_zh_cn(MASSIVE_ZH_CN_PATH)
    print(f"  原始样本数: {len(raw_data)}")

    print("\nStep 2: 映射意图为 8 类...")
    mapped = map_intents(raw_data)

    # 重标注循环样本
    mapped = relabel_recurring_samples(mapped)
    n_relabeled = sum(1 for d in mapped if d["label"] == "add_recurring")
    print(f"  重标注循环样本: {n_relabeled} 条 add_event -> add_recurring")
    print_distribution(mapped, "映射后分布（增强前）")

    print("\nStep 3: 数据增强...")
    # 增强 delete_event（使用口语化增强）
    delete_augmented = augment_class(mapped, "delete_event", AUGMENT_TARGET, use_colloquial=True)
    print(f"  delete_event: {sum(1 for d in mapped if d['label'] == 'delete_event')} -> {len(delete_augmented)}")

    # 合成 update_event
    update_samples = generate_update_events(AUGMENT_TARGET)
    print(f"  update_event: 0 -> {len(update_samples)} (合成)")

    # 合成循环事件样本
    rec_add, rec_del, rec_upd = generate_recurring_samples(AUGMENT_TARGET)
    print(f"  add_recurring: {len(rec_add)} (合成)")
    print(f"  delete_recurring: {len(rec_del)} (合成)")
    print(f"  update_recurring: {len(rec_upd)} (合成)")

    # 裁剪 other 样本（去除冗余无关意图）
    other_samples = [d for d in mapped if d["label"] == "other"]
    if len(other_samples) > OTHER_MAX:
        random.shuffle(other_samples)
        other_samples = other_samples[:OTHER_MAX]
    print(f"  other: {sum(1 for d in mapped if d['label'] == 'other')} -> {len(other_samples)} (裁剪)")

    # 对 add_event/query_event 也做口语化增强（不增加数量，替换部分样本）
    calendar_labels = ["add_event", "query_event"]
    calendar_augmented = []
    for label in calendar_labels:
        samples = [d for d in mapped if d["label"] == label]
        n_aug = min(len(samples) // 3, 200)  # 增强 1/3 样本
        aug_samples = []
        for _ in range(n_aug):
            orig = random.choice(samples)
            new_text = augment_colloquial(orig["text"])
            if new_text != orig["text"]:
                aug_samples.append({"text": new_text, "label": label})
        calendar_augmented.extend(samples)
        calendar_augmented.extend(aug_samples)
        print(f"  {label}: {len(samples)} -> {len(samples) + len(aug_samples)} (+口语增强)")

    # 合并所有数据
    final_data = calendar_augmented + delete_augmented + update_samples + other_samples + rec_add + rec_del + rec_upd
    print_distribution(final_data, "增强后分布")

    print("\nStep 4: Stratified train/dev/test 分割...")
    train, dev, test = stratified_split(final_data)
    print_distribution(train, "Train")
    print_distribution(dev, "Dev")
    print_distribution(test, "Test")

    print("\nStep 5: 保存文件...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for split_name, split_data in [("train", train), ("dev", dev), ("test", test)]:
        out_path = OUTPUT_DIR / f"{split_name}.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for item in split_data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"  {out_path}: {len(split_data)} samples")

    # 保存 label_map
    label_map = {label: idx for idx, label in enumerate(LABEL_NAMES)}
    with open(OUTPUT_DIR / "label_map.json", "w", encoding="utf-8") as f:
        json.dump(label_map, f, ensure_ascii=False, indent=2)
    print(f"  {OUTPUT_DIR / 'label_map.json'}: {label_map}")

    print("\nDone! 数据已保存到", OUTPUT_DIR)


if __name__ == "__main__":
    main()
