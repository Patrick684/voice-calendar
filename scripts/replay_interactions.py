"""
交互日志回放与训练数据导出工具

功能：
1. 回放测试：将所有历史交互记录重新通过解析器，对比结果是否与标注一致
2. 导出训练数据：将 accepted=true 的条目导出为意图分类器的训练 JSONL
3. 追加记录：从命令行添加新的测试记录

用法：
    # 回放测试（对比所有标注）
    python scripts/replay_interactions.py replay

    # 导出训练数据到 data/intent/ 目录（合并到现有训练集）
    python scripts/replay_interactions.py export

    # 追加新记录（交互式）
    python scripts/replay_interactions.py add "明天下午三点开会" --label add_event

    # 统计日志概况
    python scripts/replay_interactions.py stats
"""

import json
import sys
from pathlib import Path
from collections import Counter

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

LOG_FILE = PROJECT_ROOT / "tests" / "interaction_log.jsonl"
TRAIN_FILE = PROJECT_ROOT / "data" / "intent" / "train.jsonl"


def load_log() -> list[dict]:
    """加载交互日志"""
    if not LOG_FILE.exists():
        return []
    entries = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def save_log(entries: list[dict]):
    """保存交互日志"""
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"已保存 {len(entries)} 条记录到 {LOG_FILE}")


def cmd_replay():
    """回放所有交互记录，对比解析结果"""
    from command.rule_engine import RuleEngine

    engine = RuleEngine()
    entries = load_log()

    if not entries:
        print("日志为空")
        return

    passed = 0
    failed = 0
    skipped = 0

    print("=" * 60)
    print("交互日志回放测试")
    print("=" * 60)

    for i, entry in enumerate(entries, 1):
        text = entry["text"]
        expected_label = entry["label"]
        expected_title = entry.get("expected_title", "")
        expected_recurrence = entry.get("expected_recurrence", "")

        result = engine.parse(text)
        actual_label = result.command_type.value
        actual_title = result.title
        actual_recurrence = result.recurrence_rule

        # 检查意图类型
        intent_ok = actual_label == expected_label
        # 检查标题（如果有期望值）
        title_ok = not expected_title or actual_title == expected_title
        # 检查循环规则（如果有期望值）
        recurrence_ok = not expected_recurrence or actual_recurrence == expected_recurrence

        all_ok = intent_ok and title_ok and recurrence_ok

        if all_ok:
            status = "通过"
            passed += 1
        else:
            status = "失败"
            failed += 1
            # 显示详细差异
            details = []
            if not intent_ok:
                details.append(f"意图: 期望'{expected_label}' 实际'{actual_label}'")
            if not title_ok:
                details.append(f"标题: 期望'{expected_title}' 实际'{actual_title}'")
            if not recurrence_ok:
                details.append(f"循环: 期望'{expected_recurrence}' 实际'{actual_recurrence}'")
            print(f"  [{i:2d}] [{status}] '{text}'")
            for d in details:
                print(f"         └─ {d}")
            continue

        print(f"  [{i:2d}] [{status}] '{text}' → {actual_label}, title='{actual_title}'")

    print()
    print(f"结果: {passed} 通过, {failed} 失败, {skipped} 跳过 (共 {len(entries)} 条)")
    return failed == 0


def cmd_export():
    """导出 accepted=true 的条目为训练数据"""
    entries = load_log()

    # 筛选已接受的条目
    accepted = [e for e in entries if e.get("accepted", True)]
    rejected = [e for e in entries if not e.get("accepted", True)]

    print(f"已接受: {len(accepted)} 条")
    print(f"已拒绝: {len(rejected)} 条")

    # 转为训练格式
    train_samples = []
    for entry in accepted:
        train_samples.append({"text": entry["text"].strip(), "label": entry["label"]})

    # 统计分布
    label_counts = Counter(s["label"] for s in train_samples)
    print("\n训练数据分布:")
    for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
        print(f"  {label}: {count}")

    # 写入独立的训练数据文件（不覆盖现有训练集）
    export_file = PROJECT_ROOT / "data" / "intent" / "interaction_log_train.jsonl"
    with open(export_file, "w", encoding="utf-8") as f:
        for sample in train_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    print(f"\n已导出到: {export_file}")

    # 提示合并到主训练集
    print("\n合并到主训练集:")
    print("  python scripts/replay_interactions.py merge")


def cmd_merge():
    """将日志训练数据合并到主训练集（去重）"""
    export_file = PROJECT_ROOT / "data" / "intent" / "interaction_log_train.jsonl"
    if not export_file.exists():
        print("请先运行 export 生成训练数据")
        return

    # 读取现有训练集
    existing_texts = set()
    existing_lines = []
    if TRAIN_FILE.exists():
        with open(TRAIN_FILE, "r", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line.strip())
                existing_texts.add(item["text"])
                existing_lines.append(line.strip())

    # 读取新数据
    new_samples = []
    with open(export_file, "r", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line.strip())
            if item["text"] not in existing_texts:
                new_samples.append(item)
                existing_texts.add(item["text"])

    if not new_samples:
        print("无新数据需要合并（已全部存在）")
        return

    # 合并写入
    with open(TRAIN_FILE, "a", encoding="utf-8") as f:
        for sample in new_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    print(f"已合并 {len(new_samples)} 条新数据到 {TRAIN_FILE}")
    print(f"训练集总计: {len(existing_lines) + len(new_samples)} 条")


def cmd_add(text: str, label: str, title: str = "", recurrence: str = ""):
    """追加新记录"""
    entries = load_log()

    new_entry = {
        "text": text,
        "label": label,
        "expected_title": title,
        "expected_recurrence": recurrence,
        "note": "",
        "accepted": True,
    }
    entries.append(new_entry)
    save_log(entries)

    # 即时验证
    from command.rule_engine import RuleEngine

    engine = RuleEngine()
    result = engine.parse(text)
    actual_label = result.command_type.value

    if actual_label == label:
        print(f"[通过] '{text}' → {actual_label}")
    else:
        print(f"[警告] '{text}' → {actual_label} (期望: {label})")


def cmd_stats():
    """统计日志概况"""
    entries = load_log()

    if not entries:
        print("日志为空")
        return

    print("=" * 40)
    print("交互日志统计")
    print("=" * 40)
    print(f"总计: {len(entries)} 条")

    # 意图分布
    label_counts = Counter(e["label"] for e in entries)
    print("\n意图分布:")
    for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
        pct = count / len(entries) * 100
        bar = "█" * int(pct / 2)
        print(f"  {label:15s} {count:3d} ({pct:4.1f}%) {bar}")

    # 接受/拒绝
    accepted = sum(1 for e in entries if e.get("accepted", True))
    rejected = len(entries) - accepted
    print(f"\n已接受: {accepted}")
    print(f"已拒绝: {rejected}")

    # 循环事件
    with_recurrence = sum(1 for e in entries if e.get("expected_recurrence"))
    print(f"循环事件: {with_recurrence}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1]

    if command == "replay":
        success = cmd_replay()
        sys.exit(0 if success else 1)
    elif command == "export":
        cmd_export()
    elif command == "merge":
        cmd_merge()
    elif command == "add":
        if len(sys.argv) < 4:
            print("用法: python replay_interactions.py add <text> <label> [--title <title>]")
            sys.exit(1)
        text = sys.argv[2]
        label = sys.argv[3]
        title = sys.argv[5] if "--title" in sys.argv else ""
        cmd_add(text, label, title)
    elif command == "stats":
        cmd_stats()
    else:
        print(f"未知命令: {command}")
        print("可用命令: replay, export, merge, add, stats")
        sys.exit(1)
