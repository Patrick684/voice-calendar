"""
用途：验证指令解析层（time_parser/rule_engine/parser/intent_classifier）功能是否正常
示例：python tests/verify_command.py
"""

import os
import sys
from datetime import datetime, timedelta

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from command.time_parser import TimeParser
from command.rule_engine import RuleEngine, CommandType
from command.parser import CommandParser

# IntentClassifier 可选（需 torch + transformers + 训练好的模型）
_HAS_INTENT_CLASSIFIER = False
try:
    from command.intent_classifier import IntentClassifier
    _HAS_INTENT_CLASSIFIER = True
except ImportError:
    pass


def test_time_parser():
    """测试中文时间解析"""
    print("=" * 50)
    print("测试 TimeParser 中文时间解析")
    print("=" * 50)

    parser = TimeParser()
    now = datetime.now()

    # 1. 相对日期
    cases = [
        ("明天下午三点开会", True, "明天+下午三点"),
        ("后天上午十点看牙", True, "后天+上午十点"),
        ("今天晚上八点跑步", True, "今天+晚上八点"),
        ("大后天下午两点面试", True, "大后天+下午两点"),
        ("三天后上午九点出发", True, "三天后+上午九点"),
    ]

    for text, should_have_time, desc in cases:
        result_time, remaining = parser.parse(text)
        if should_have_time:
            assert result_time is not None, f"解析失败: {text} ({desc})"
            print(f"  [通过] '{text}' → {result_time.strftime('%m-%d %H:%M')} | 剩余: '{remaining}'")
        else:
            print(f"  [通过] '{text}' → None | 剩余: '{remaining}'")

    # 2. 下周X
    result_time, remaining = parser.parse("下周一上午十点开会")
    assert result_time is not None
    assert result_time.weekday() == 0  # 周一
    print(f"  [通过] '下周一上午十点' → {result_time.strftime('%m-%d %H:%M')} (weekday={result_time.weekday()})")

    # 3. X月X号
    result_time, remaining = parser.parse("六月十五号下午三点聚会")
    assert result_time is not None
    assert result_time.month == 6
    assert result_time.day == 15
    print(f"  [通过] '六月十五号下午三点' → {result_time.strftime('%Y-%m-%d %H:%M')}")

    # 4. 具体时间
    result_time, remaining = parser.parse("明天15:30开会")
    assert result_time is not None
    assert result_time.hour == 15
    assert result_time.minute == 30
    print(f"  [通过] '明天15:30' → {result_time.strftime('%m-%d %H:%M')}")

    # 5. 中文数字时间
    result_time, remaining = parser.parse("明天下午三点半开会")
    assert result_time is not None
    assert result_time.hour == 15  # 下午 +12
    assert result_time.minute == 30
    print(f"  [通过] '明天下午三点半' → {result_time.strftime('%m-%d %H:%M')}")

    # 6. N天后
    result_time, remaining = parser.parse("五天后上午九点体检")
    assert result_time is not None
    expected_date = (now + timedelta(days=5)).date()
    assert result_time.date() == expected_date
    print(f"  [通过] '五天后上午九点' → {result_time.strftime('%m-%d %H:%M')}")

    print()


def test_rule_engine():
    """测试规则引擎指令识别"""
    print("=" * 50)
    print("测试 RuleEngine 指令识别")
    print("=" * 50)

    engine = RuleEngine()

    # 1. 添加事件
    test_cases = [
        ("帮我安排明天下午三点的团队会议", CommandType.ADD_EVENT, "团队会议"),
        ("添加一个下周一上午十点的面试", CommandType.ADD_EVENT, "面试"),
        ("提醒我后天晚上七点吃药", CommandType.ADD_EVENT, "吃药"),
    ]
    for text, expected_type, expected_title_contains in test_cases:
        result = engine.parse(text)
        assert result.command_type == expected_type, (
            f"类型不匹配: '{text}' → {result.command_type.value} (期望 {expected_type.value})"
        )
        assert expected_title_contains in result.title, (
            f"标题不匹配: '{text}' → title='{result.title}' (期望含 '{expected_title_contains}')"
        )
        print(f"  [通过] '{text}' → {result.command_type.value}, title='{result.title}'")

    # 2. 删除事件
    result = engine.parse("删掉明天的会议")
    assert result.command_type == CommandType.DELETE_EVENT
    print(f"  [通过] '删掉明天的会议' → {result.command_type.value}")

    result = engine.parse("取消后天的面试")
    assert result.command_type == CommandType.DELETE_EVENT
    print(f"  [通过] '取消后天的面试' → {result.command_type.value}")

    # 3. 查询事件
    result = engine.parse("今天有什么安排")
    assert result.command_type == CommandType.QUERY_EVENT
    assert result.time is not None
    print(f"  [通过] '今天有什么安排' → {result.command_type.value}, time={result.time.strftime('%m-%d')}")

    result = engine.parse("看看这周的日程")
    assert result.command_type == CommandType.QUERY_EVENT
    print(f"  [通过] '看看这周的日程' → {result.command_type.value}")

    # 4. 修改事件
    result = engine.parse("把明天的会改到后天")
    assert result.command_type == CommandType.UPDATE_EVENT
    print(f"  [通过] '把明天的会改到后天' → {result.command_type.value}")

    # 5. 隐式添加（无明确关键词）
    result = engine.parse("明天下午三点开会")
    assert result.command_type == CommandType.ADD_EVENT
    assert result.time is not None
    print(f"  [通过] '明天下午三点开会' → {result.command_type.value} (隐式), title='{result.title}'")

    # 6. 无法识别
    result = engine.parse("你好世界")
    assert result.command_type == CommandType.UNKNOWN
    print(f"  [通过] '你好世界' → {result.command_type.value}")

    print()


def test_command_parser():
    """测试混合指令解析器"""
    print("=" * 50)
    print("测试 CommandParser 混合解析")
    print("=" * 50)

    # 不启用 LLM
    parser = CommandParser(llm_enabled=False)
    assert not parser.llm_enabled

    result = parser.parse("安排明天下午两点的项目评审会")
    assert result.command_type == CommandType.ADD_EVENT
    assert result.time is not None
    assert "项目评审会" in result.title or "评审" in result.title
    print(f"  [通过] 规则引擎: '{result.original_text}' → {result.command_type.value}, title='{result.title}'")

    result = parser.parse("今天有什么日程")
    assert result.command_type == CommandType.QUERY_EVENT
    print(f"  [通过] 查询指令: → {result.command_type.value}")

    result = parser.parse("随便说点什么")
    assert result.command_type == CommandType.UNKNOWN
    print(f"  [通过] 未知指令: → {result.command_type.value}")

    print()


def test_fuzzy_correction():
    """测试时间关键词近音纠错"""
    print("=" * 50)
    print("测试 TimeParser 近音纠错")
    print("=" * 50)

    parser = TimeParser()

    # “名天”应纠错为“明天”（同音异字）
    result = parser._fuzzy_correct_time_keywords("名天下午三点开会")
    assert "明天" in result, f"期望包含'明天'，实际: {result}"
    print(f"  [通过] 近音纠错: '名天' -> '明天' => '{result}'")

    # “后添”应纠错为“后天”（同音异字）
    result = parser._fuzzy_correct_time_keywords("后添上午十点看牙")
    assert "后天" in result, f"期望包含'后天'，实际: {result}"
    print(f"  [通过] 近音纠错: '后添' -> '后天' => '{result}'")

    # “今填”应纠错为“今天”（同音异字）
    result = parser._fuzzy_correct_time_keywords("今填晚上八点吃药")
    assert "今天" in result, f"期望包含'今天'，实际: {result}"
    print(f"  [通过] 近音纠错: '今填' -> '今天' => '{result}'")

    # 正确词不应被修改
    result = parser._fuzzy_correct_time_keywords("明天下午三点开会")
    assert result == "明天下午三点开会", f"正确词被误改: {result}"
    print(f"  [通过] 正确词不被修改: '{result}'")

    # 纠错后应能正常解析时间
    parsed_time, remaining = parser.parse("名天下午三点开会")
    assert parsed_time is not None, "纠错后应解析到时间"
    assert parsed_time.hour == 15, f"期望 15 点，实际 {parsed_time.hour}"
    print(f"  [通过] 纠错后解析: '{parsed_time.strftime('%m-%d %H:%M')}' | 剩余: '{remaining}'")

    print()


def test_parse_multiple():
    """测试多指令拆分解析"""
    print("=" * 50)
    print("测试 CommandParser 多指令拆分")
    print("=" * 50)

    parser = CommandParser(llm_enabled=False)

    # 逗号分隔多事件
    results = parser.parse_multiple("明天下午三点开会，后天上午十点看牙")
    add_results = [r for r in results if r.command_type == CommandType.ADD_EVENT]
    assert len(add_results) >= 2, f"期望至少 2 条添加指令，实际 {len(add_results)}"
    print(f"  [通过] 逗号分隔: {len(add_results)} 条指令")
    for r in add_results:
        print(f"         - type={r.command_type.value}, title='{r.title}', time={r.time.strftime('%m-%d %H:%M') if r.time else 'None'}")

    # 连接词分隔
    results = parser.parse_multiple("安排明天的团队会议还有后天的面试")
    add_results = [r for r in results if r.command_type == CommandType.ADD_EVENT]
    assert len(add_results) >= 2, f"期望至少 2 条，实际 {len(add_results)}"
    print(f"  [通过] '还有'分隔: {len(add_results)} 条指令")

    # 时间边界拆分（无标点，核心修复场景）
    results = parser.parse_multiple("上午8点起床中午12点吃饭")
    add_results = [r for r in results if r.command_type == CommandType.ADD_EVENT]
    assert len(add_results) >= 2, f"期望 2 条，实际 {len(add_results)}"
    print(f"  [通过] 时间边界拆分(2事件): {len(add_results)} 条指令")
    for r in add_results:
        print(f"         - title='{r.title}', time={r.time.strftime('%m-%d %H:%M') if r.time else 'None'}")

    # 日期+时段不拆分（"明天下午"应为同一事件）
    results = parser.parse_multiple("明天下午三点开会后天上午十点面试")
    add_results = [r for r in results if r.command_type == CommandType.ADD_EVENT]
    assert len(add_results) >= 2, f"期望 2 条，实际 {len(add_results)}"
    print(f"  [通过] 日期+时段不拆分(2事件): {len(add_results)} 条指令")
    for r in add_results:
        print(f"         - title='{r.title}', time={r.time.strftime('%m-%d %H:%M') if r.time else 'None'}")

    # 三事件时间边界拆分
    results = parser.parse_multiple("上午8点起床中午12点吃饭晚上8点看电影")
    add_results = [r for r in results if r.command_type == CommandType.ADD_EVENT]
    assert len(add_results) >= 3, f"期望 3 条，实际 {len(add_results)}"
    print(f"  [通过] 时间边界拆分(3事件): {len(add_results)} 条指令")
    for r in add_results:
        print(f"         - title='{r.title}', time={r.time.strftime('%m-%d %H:%M') if r.time else 'None'}")

    # 单条指令正常返回
    results = parser.parse_multiple("明天下午三点开会")
    assert len(results) == 1
    print(f"  [通过] 单条指令: {len(results)} 条")

    # 无法识别的文本返回空列表
    results = parser.parse_multiple("你好世界")
    assert len(results) == 0
    print(f"  [通过] 无法识别: {len(results)} 条")

    print()


def test_parse_multiple_real_world():
    """真实语音输入场景测试（修复回归）"""
    print("=" * 50)
    print("测试 CommandParser 真实语音场景")
    print("=" * 50)

    parser = CommandParser(llm_enabled=False)

    # 原始失败案例（含 ASR 标点错误 "后天上，午"）
    text = "明天早上8点起床下午3点有个会后天上，午10点有个面试6月1号早上9点买高铁票。"
    results = parser.parse_multiple(text)
    add_results = [r for r in results if r.command_type == CommandType.ADD_EVENT]
    assert len(add_results) == 4, f"期望 4 条，实际 {len(add_results)}"
    print(f"  [通过] ASR错误+4事件分割: {len(add_results)} 条指令")
    for r in add_results:
        time_str = r.time.strftime('%m-%d %H:%M') if r.time else 'None'
        print(f"         - title='{r.title}', time={time_str}")

    # 碎片过滤：纯时间片段
    results = parser.parse_multiple("明天早上")
    assert len(results) == 0, f"纯时间应过滤，实际 {len(results)}"
    print("  [通过] 纯时间片段过滤: '明天早上' -> 0 条")

    # 碎片过滤：单字碎片
    results = parser.parse_multiple("午")
    assert len(results) == 0, f"单字应过滤，实际 {len(results)}"
    print("  [通过] 单字碎片过滤: '午' -> 0 条")

    # 日期不割裂："明天早上8点起床" 应保留日期
    results = parser.parse_multiple("明天早上8点起床")
    assert len(results) == 1
    r = results[0]
    assert r.time is not None
    from datetime import datetime, timedelta
    tomorrow = datetime.now() + timedelta(days=1)
    assert r.time.day == tomorrow.day, f"期望明天，实际 {r.time.strftime('%m-%d')}"
    assert r.time.hour == 8, f"期望 8 点，实际 {r.time.hour}"
    print(f"  [通过] 日期不割裂: '明天早上8点起床' -> {r.time.strftime('%m-%d %H:%M')}")

    # 跨事件日期绑定："6月1号" 应绑定给后续事件
    results = parser.parse_multiple("后天上午10点面试6月1号早上9点买高铁票")
    add_results = [r for r in results if r.command_type == CommandType.ADD_EVENT]
    assert len(add_results) == 2, f"期望 2 条，实际 {len(add_results)}"
    # 第二条应是 6月1号 09:00
    r2 = add_results[1]
    assert r2.time is not None
    assert r2.time.month == 6 and r2.time.day == 1, \
        f"期望 06-01，实际 {r2.time.strftime('%m-%d')}"
    assert r2.time.hour == 9, f"期望 9 点，实际 {r2.time.hour}"
    print(f"  [通过] 日期绑定后续事件: 买高铁票 -> {r2.time.strftime('%m-%d %H:%M')}")

    print()


def test_date_context_inheritance():
    """测试多指令日期上下文继承"""
    print("=" * 50)
    print("测试日期上下文继承")
    print("=" * 50)

    parser = CommandParser(llm_enabled=False)
    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    day_after = now + timedelta(days=2)

    # 1. 同日期连续事件："明天早上8点起床下午3点开会"
    #    "下午3点" 应继承 "明天"
    results = parser.parse_multiple("明天早上8点起床下午3点开会")
    add_results = [r for r in results if r.command_type == CommandType.ADD_EVENT]
    assert len(add_results) == 2, f"期望 2 条，实际 {len(add_results)}"
    assert add_results[0].time.day == tomorrow.day, \
        f"第1条期望明天，实际 {add_results[0].time.strftime('%m-%d')}"
    assert add_results[0].time.hour == 8
    assert add_results[1].time.day == tomorrow.day, \
        f"第2条应继承明天，实际 {add_results[1].time.strftime('%m-%d')}"
    assert add_results[1].time.hour == 15
    print(f"  [通过] 同日期继承: '起床'={add_results[0].time.strftime('%m-%d %H:%M')}, "
          f"'开会'={add_results[1].time.strftime('%m-%d %H:%M')}")

    # 2. 日期切换："后天上午10点面试6月1号早上9点买高铁票"
    #    "后天" 应解析为后天，"6月1号" 应更新上下文并绑定给"买高铁票"
    results = parser.parse_multiple("后天上午10点面试6月1号早上9点买高铁票")
    add_results = [r for r in results if r.command_type == CommandType.ADD_EVENT]
    assert len(add_results) == 2, f"期望 2 条，实际 {len(add_results)}"
    r1 = add_results[0]
    assert r1.time.day == day_after.day, \
        f"第1条期望后天({day_after.strftime('%m-%d')})，实际 {r1.time.strftime('%m-%d')}"
    r2 = add_results[1]
    assert r2.time.month == 6 and r2.time.day == 1, \
        f"第2条期望 06-01，实际 {r2.time.strftime('%m-%d')}"
    print(f"  [通过] 日期切换: '面试'={r1.time.strftime('%m-%d %H:%M')}, "
          f"'买高铁票'={r2.time.strftime('%m-%d %H:%M')}")

    # 3. 完整场景："明天早上8点起床下午3点有个会后天上，午10点有个面试6月1号早上9点买高铁票"
    text = "明天早上8点起床下午3点有个会后天上，午10点有个面试6月1号早上9点买高铁票"
    results = parser.parse_multiple(text)
    add_results = [r for r in results if r.command_type == CommandType.ADD_EVENT]
    assert len(add_results) == 4, \
        f"期望 4 条，实际 {len(add_results)}: {[r.title for r in add_results]}"
    # 第1条：明天 08:00 起床
    assert add_results[0].time.day == tomorrow.day
    assert add_results[0].time.hour == 8
    # 第2条：明天 15:00 有个会（继承明天）
    assert add_results[1].time.day == tomorrow.day, \
        f"第2条应继承明天，实际 {add_results[1].time.strftime('%m-%d')}"
    assert add_results[1].time.hour == 15
    # 第3条：后天 10:00 面试
    assert add_results[2].time.day == day_after.day, \
        f"第3条期望后天，实际 {add_results[2].time.strftime('%m-%d')}"
    assert add_results[2].time.hour == 10
    # 第4条：6月1号 09:00 买高铁票
    assert add_results[3].time.month == 6 and add_results[3].time.day == 1
    assert add_results[3].time.hour == 9
    print("  [通过] 完整场景 4 事件:")
    for r in add_results:
        print(f"         - '{r.title}' @ {r.time.strftime('%m-%d %H:%M')}")

    # 4. base_date 参数直接传递测试
    from command.time_parser import TimeParser
    tp = TimeParser()
    base = datetime(2026, 6, 15)
    parsed_time, _ = tp.parse("下午三点开会", base_date=base)
    assert parsed_time is not None
    assert parsed_time.day == 15 and parsed_time.month == 6, \
        f"base_date 未生效，期望 06-15，实际 {parsed_time.strftime('%m-%d')}"
    assert parsed_time.hour == 15
    print(f"  [通过] base_date 直传: '下午三点' + base=06-15 -> {parsed_time.strftime('%m-%d %H:%M')}")

    print()


def test_intent_classifier_import():
    """测试 IntentClassifier 导入和基本接口"""
    print("=" * 50)
    print("测试 IntentClassifier 导入")
    print("=" * 50)

    if not _HAS_INTENT_CLASSIFIER:
        print("  [跳过] torch/transformers 未安装，IntentClassifier 不可用")
        print()
        return

    print("  [通过] IntentClassifier 导入成功")

    # 测试模型不存在时的 FileNotFoundError
    try:
        clf = IntentClassifier(model_path="models/nonexistent_model")
        assert False, "应当抛出 FileNotFoundError"
    except FileNotFoundError:
        print("  [通过] 模型路径不存在时正确抛出 FileNotFoundError")

    print()


def test_intent_classifier_inference():
    """测试 IntentClassifier 推理（需要训练好的模型）"""
    print("=" * 50)
    print("测试 IntentClassifier 推理")
    print("=" * 50)

    if not _HAS_INTENT_CLASSIFIER:
        print("  [跳过] torch/transformers 未安装")
        print()
        return

    import os
    model_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models", "intent_classifier",
    )
    if not os.path.exists(model_path):
        print(f"  [跳过] 模型未训练: {model_path}")
        print("         请先运行 scripts/train_intent_classifier.py")
        print()
        return

    # 加载模型（自动选 CPU/GPU）
    clf = IntentClassifier(model_path=model_path)
    print(f"  [通过] 模型加载成功 (device={clf.device})")
    print(f"         标签: {clf.label_names}")

    # 验证标签完整性
    expected_labels = {"add_event", "query_event", "delete_event", "update_event", "other"}
    assert set(clf.label_names) == expected_labels, (
        f"标签不匹配: {set(clf.label_names)} vs {expected_labels}"
    )
    print("  [通过] 标签完整性验证")

    # 单条推理测试
    test_cases = [
        ("帮我安排明天下午三点的团队会议", "add_event"),
        ("今天有什么日程安排", "query_event"),
        ("删掉明天的面试", "delete_event"),
        ("把后天的会议改到大后天", "update_event"),
        ("今天天气怎么样", "other"),
    ]
    for text, expected_intent in test_cases:
        label, confidence = clf.predict(text)
        status = "通过" if label == expected_intent else "警告"
        print(f"  [{status}] '{text}' → {label} ({confidence:.3f}) [期望: {expected_intent}]")

    # 批量推理测试
    texts = [t for t, _ in test_cases]
    results = clf.predict_batch(texts)
    assert len(results) == len(texts), f"批量推理数量不匹配: {len(results)} vs {len(texts)}"
    print(f"  [通过] 批量推理: {len(results)} 条")

    # 置信度范围验证
    for label, conf in results:
        assert 0.0 <= conf <= 1.0, f"置信度越界: {conf}"
        assert label in expected_labels, f"未知标签: {label}"
    print("  [通过] 置信度范围验证")

    print()


def test_parser_with_intent_model():
    """测试 CommandParser 集成意图分类模型"""
    print("=" * 50)
    print("测试 CommandParser + IntentClassifier 集成")
    print("=" * 50)

    # 1. 模型未启用时，正常工作（回退到规则引擎）
    parser = CommandParser(llm_enabled=False, intent_model_enabled=False)
    result = parser.parse("明天下午三点开会")
    assert result.command_type == CommandType.ADD_EVENT
    print(f"  [通过] 模型未启用: 规则引擎正常 → {result.command_type.value}")

    # 2. 模型启用但路径不存在时，应回退到规则引擎
    parser_fallback = CommandParser(
        llm_enabled=False,
        intent_model_enabled=True,
        intent_model_path="models/nonexistent_model",
    )
    result = parser_fallback.parse("安排明天的团队会议")
    assert result.command_type == CommandType.ADD_EVENT
    print(f"  [通过] 模型路径不存在: 回退到规则引擎 → {result.command_type.value}")

    # 3. 模型启用且存在时，测试完整流程
    if not _HAS_INTENT_CLASSIFIER:
        print("  [跳过] torch/transformers 未安装，无法测试模型集成")
        print()
        return

    import os
    model_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models", "intent_classifier",
    )
    if not os.path.exists(model_path):
        print(f"  [跳过] 模型未训练: {model_path}")
        print()
        return

    parser_model = CommandParser(
        llm_enabled=False,
        intent_model_enabled=True,
        intent_model_path=model_path,
        intent_confidence_threshold=0.8,
    )

    # 测试日历相关指令（模型应识别）
    model_cases = [
        ("帮我安排明天下午三点的团队会议", CommandType.ADD_EVENT),
        ("今天有什么安排", CommandType.QUERY_EVENT),
        ("删掉后天的面试", CommandType.DELETE_EVENT),
    ]
    for text, expected_type in model_cases:
        result = parser_model.parse(text)
        status = "通过" if result.command_type == expected_type else "警告"
        print(f"  [{status}] 模型集成: '{text}' → {result.command_type.value} "
              f"(confidence={result.confidence:.3f}) [期望: {expected_type.value}]")

    # 测试非日历指令（模型应识别为 UNKNOWN）
    result = parser_model.parse("帮我订一张去北京的机票")
    print(f"  [信息] 非日历指令: → {result.command_type.value} "
          f"(confidence={result.confidence:.3f})")

    print()


if __name__ == "__main__":
    print("\n指令解析层功能验证\n")
    try:
        test_time_parser()
        test_rule_engine()
        test_command_parser()
        test_fuzzy_correction()
        test_parse_multiple()
        test_parse_multiple_real_world()
        test_date_context_inheritance()
        test_intent_classifier_import()
        test_intent_classifier_inference()
        test_parser_with_intent_model()
        print("=" * 50)
        print("全部测试通过!")
        print("=" * 50)
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
