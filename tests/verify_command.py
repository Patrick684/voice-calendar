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

    try:
        import pypinyin  # noqa: F401
    except ImportError:
        print("  [跳过] pypinyin 未安装，无法测试近音纠错")
        print()
        return

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
        print(
            f"         - type={r.command_type.value}, title='{r.title}', time={r.time.strftime('%m-%d %H:%M') if r.time else 'None'}"
        )

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
        time_str = r.time.strftime("%m-%d %H:%M") if r.time else "None"
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
    assert r2.time.month == 6 and r2.time.day == 1, f"期望 06-01，实际 {r2.time.strftime('%m-%d')}"
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
    assert add_results[0].time.day == tomorrow.day, f"第1条期望明天，实际 {add_results[0].time.strftime('%m-%d')}"
    assert add_results[0].time.hour == 8
    assert add_results[1].time.day == tomorrow.day, f"第2条应继承明天，实际 {add_results[1].time.strftime('%m-%d')}"
    assert add_results[1].time.hour == 15
    print(
        f"  [通过] 同日期继承: '起床'={add_results[0].time.strftime('%m-%d %H:%M')}, "
        f"'开会'={add_results[1].time.strftime('%m-%d %H:%M')}"
    )

    # 2. 日期切换："后天上午10点面试6月1号早上9点买高铁票"
    #    "后天" 应解析为后天，"6月1号" 应更新上下文并绑定给"买高铁票"
    results = parser.parse_multiple("后天上午10点面试6月1号早上9点买高铁票")
    add_results = [r for r in results if r.command_type == CommandType.ADD_EVENT]
    assert len(add_results) == 2, f"期望 2 条，实际 {len(add_results)}"
    r1 = add_results[0]
    assert r1.time.day == day_after.day, (
        f"第1条期望后天({day_after.strftime('%m-%d')})，实际 {r1.time.strftime('%m-%d')}"
    )
    r2 = add_results[1]
    assert r2.time.month == 6 and r2.time.day == 1, f"第2条期望 06-01，实际 {r2.time.strftime('%m-%d')}"
    print(f"  [通过] 日期切换: '面试'={r1.time.strftime('%m-%d %H:%M')}, '买高铁票'={r2.time.strftime('%m-%d %H:%M')}")

    # 3. 完整场景："明天早上8点起床下午3点有个会后天上，午10点有个面试6月1号早上9点买高铁票"
    text = "明天早上8点起床下午3点有个会后天上，午10点有个面试6月1号早上9点买高铁票"
    results = parser.parse_multiple(text)
    add_results = [r for r in results if r.command_type == CommandType.ADD_EVENT]
    assert len(add_results) == 4, f"期望 4 条，实际 {len(add_results)}: {[r.title for r in add_results]}"
    # 第1条：明天 08:00 起床
    assert add_results[0].time.day == tomorrow.day
    assert add_results[0].time.hour == 8
    # 第2条：明天 15:00 有个会（继承明天）
    assert add_results[1].time.day == tomorrow.day, f"第2条应继承明天，实际 {add_results[1].time.strftime('%m-%d')}"
    assert add_results[1].time.hour == 15
    # 第3条：后天 10:00 面试
    assert add_results[2].time.day == day_after.day, f"第3条期望后天，实际 {add_results[2].time.strftime('%m-%d')}"
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
    assert parsed_time.day == 15 and parsed_time.month == 6, (
        f"base_date 未生效，期望 06-15，实际 {parsed_time.strftime('%m-%d')}"
    )
    assert parsed_time.hour == 15
    print(f"  [通过] base_date 直传: '下午三点' + base=06-15 -> {parsed_time.strftime('%m-%d %H:%M')}")

    # 5. 逗号后日期引用继承（回归测试：日期词被逗号切开后仍能传递上下文）
    text = "晚上9点打五位齐约明天，上午10点出门晚上9点回宿舍"
    results = parser.parse_multiple(text)
    add_results = [r for r in results if r.command_type == CommandType.ADD_EVENT]
    assert len(add_results) == 3, f"期望 3 条，实际 {len(add_results)}"
    # 第1条：今天 21:00（“明天”在逗号前，属于第1个片段）
    assert add_results[0].time.day == now.day, f"第1条期望今天，实际 {add_results[0].time.strftime('%m-%d')}"
    assert add_results[0].time.hour == 21
    # 第2条：明天 10:00（继承“明天”上下文）
    assert add_results[1].time.day == tomorrow.day, f"第2条应继承明天，实际 {add_results[1].time.strftime('%m-%d')}"
    assert add_results[1].time.hour == 10
    # 第3条：明天 21:00（继续继承“明天”）
    assert add_results[2].time.day == tomorrow.day, f"第3条应继承明天，实际 {add_results[2].time.strftime('%m-%d')}"
    assert add_results[2].time.hour == 21
    print(
        f"  [通过] 逗号后日期继承: "
        f"'{add_results[0].title}'={add_results[0].time.strftime('%m-%d %H:%M')}, "
        f"'{add_results[1].title}'={add_results[1].time.strftime('%m-%d %H:%M')}, "
        f"'{add_results[2].title}'={add_results[2].time.strftime('%m-%d %H:%M')}"
    )

    print()


def test_priority_detection():
    """测试优先级关键词自动识别"""
    print("=" * 50)
    print("测试优先级检测")
    print("=" * 50)

    engine = RuleEngine()

    # 普通（无关键词）
    result = engine.parse("明天下午三点开会")
    assert result.priority == 0, f"期望 0，实际 {result.priority}"
    print(f"  [通过] 普通: '明天下午三点开会' -> priority={result.priority}")

    # 重要
    result = engine.parse("明天下午三点重要会议")
    assert result.priority == 1, f"期望 1，实际 {result.priority}"
    print(f"  [通过] 重要: '明天下午三点重要会议' -> priority={result.priority}")

    # 紧急
    result = engine.parse("安排明天马上截止的项目提交")
    assert result.priority == 2, f"期望 2，实际 {result.priority}"
    print(f"  [通过] 紧急: '安排明天马上截止的项目提交' -> priority={result.priority}")

    # 紧急且重要
    result = engine.parse("安排紧急且重要的客户电话")
    assert result.priority == 3, f"期望 3，实际 {result.priority}"
    print(f"  [通过] 紧急且重要: '安排紧急且重要的客户电话' -> priority={result.priority}")

    # 隐式添加也检测优先级
    result = engine.parse("明天务必完成报告")
    assert result.priority == 1, f"隐式期望 1，实际 {result.priority}"
    print(f"  [通过] 隐式优先级: '明天务必完成报告' -> priority={result.priority}")

    # CommandParser 透传
    parser = CommandParser(llm_enabled=False)
    result = parser.parse("安排明天下午立刻处理的紧急任务")
    assert result.priority == 2, f"透传期望 2，实际 {result.priority}"
    print(f"  [通过] CommandParser 透传: priority={result.priority}")

    print()


def test_event_classification():
    """测试事件自动分类"""
    print("=" * 50)
    print("测试事件自动分类")
    print("=" * 50)

    from calendar_pkg.classifier import EventClassifier

    classifier = EventClassifier()

    # 工作类
    result = classifier.classify("明天下午三点开会")
    assert result == "工作", f"期望'工作'，实际: {result}"
    print(f"  [通过] '明天下午三点开会' -> {result}")

    # 健康类
    result = classifier.classify("早上去跑步")
    assert result == "健康", f"期望'健康'，实际: {result}"
    print(f"  [通过] '早上去跑步' -> {result}")

    # 学习类
    result = classifier.classify("晚上读书两小时")
    assert result == "学习", f"期望'学习'，实际: {result}"
    print(f"  [通过] '晚上读书两小时' -> {result}")

    # 生活类
    result = classifier.classify("去超市买菜")
    assert result == "生活", f"期望'生活'，实际: {result}"
    print(f"  [通过] '去超市买菜' -> {result}")

    # 娱乐类
    result = classifier.classify("周末看电影")
    assert result == "娱乐", f"期望'娱乐'，实际: {result}"
    print(f"  [通过] '周末看电影' -> {result}")

    # 社交类
    result = classifier.classify("参加小明的婚礼")
    assert result == "社交", f"期望'社交'，实际: {result}"
    print(f"  [通过] '参加小明的婚礼' -> {result}")

    # 其他类
    result = classifier.classify("随便逛逛")
    assert result == "其他", f"期望'其他'，实际: {result}"
    print(f"  [通过] '随便逛逛' -> {result}")

    # 空标题
    result = classifier.classify("")
    assert result == "其他", f"空标题期望'其他'，实际: {result}"
    print(f"  [通过] 空标题 -> {result}")

    # 自定义关键词
    custom = EventClassifier(custom_keywords={"工作": ["写代码", "调试"]})
    result = custom.classify("下午写代码")
    assert result == "工作", f"自定义期望'工作'，实际: {result}"
    print(f"  [通过] 自定义关键词: '下午写代码' -> {result}")

    # 类别列表
    categories = classifier.categories
    assert "工作" in categories and "其他" in categories
    print(f"  [通过] 类别列表: {categories}")

    print()


def test_recurrence_detection():
    """测试循环事件触发词识别与 RRULE 解析"""
    print("=" * 50)
    print("测试循环事件检测")
    print("=" * 50)

    engine = RuleEngine()

    # 每天
    result = engine.parse("安排每天早上八点跑步")
    assert result.recurrence_rule == "FREQ=DAILY", f"期望 FREQ=DAILY，实际: {result.recurrence_rule}"
    print(f"  [通过] 每天: '{result.recurrence_rule}'")

    # 每周
    result = engine.parse("安排每周下午三点开会")
    assert result.recurrence_rule == "FREQ=WEEKLY", f"期望 FREQ=WEEKLY，实际: {result.recurrence_rule}"
    print(f"  [通过] 每周: '{result.recurrence_rule}'")

    # 每周X
    result = engine.parse("安排每周一上午十点汇报")
    assert result.recurrence_rule == "FREQ=WEEKLY;BYDAY=MO", (
        f"期望 FREQ=WEEKLY;BYDAY=MO，实际: {result.recurrence_rule}"
    )
    print(f"  [通过] 每周一: '{result.recurrence_rule}'")

    # 每个星期X
    result = engine.parse("安排每个星期五下午两点开会")
    assert result.recurrence_rule == "FREQ=WEEKLY;BYDAY=FR", (
        f"期望 FREQ=WEEKLY;BYDAY=FR，实际: {result.recurrence_rule}"
    )
    print(f"  [通过] 每个星期五: '{result.recurrence_rule}'")

    # 每月
    result = engine.parse("安排每月下午三点复盘")
    assert result.recurrence_rule == "FREQ=MONTHLY", f"期望 FREQ=MONTHLY，实际: {result.recurrence_rule}"
    print(f"  [通过] 每月: '{result.recurrence_rule}'")

    # 工作日
    result = engine.parse("安排工作日早上九点打卡")
    assert "BYDAY=MO,TU,WE,TH,FR" in result.recurrence_rule, (
        f"期望含 BYDAY=MO,TU,WE,TH,FR，实际: {result.recurrence_rule}"
    )
    print(f"  [通过] 工作日: '{result.recurrence_rule}'")

    # 非循环事件不应有 recurrence_rule
    result = engine.parse("安排明天下午三点开会")
    assert result.recurrence_rule == "", f"非循环期望空，实际: {result.recurrence_rule}"
    print(f"  [通过] 非循环: recurrence_rule='{result.recurrence_rule}'")

    print()


def test_recurrence_expansion():
    """测试循环事件展开查询"""
    print("=" * 50)
    print("测试循环事件展开")
    print("=" * 50)

    import tempfile
    from calendar_pkg.manager import CalendarManager

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        mgr = CalendarManager(db_path=db_path)

        # 创建每天事件，起始为今天 08:00
        today = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
        event = mgr.add_event(
            title="每日跑步",
            start_time=today,
            recurrence_rule="FREQ=DAILY",
        )
        assert event.recurrence_rule == "FREQ=DAILY"
        assert event.is_recurring
        print(f"  [通过] 创建循环事件: {event.title}, rule={event.recurrence_rule}")

        # 查询未来 7 天，应展开为 6 个虚拟实例（排除原始事件本身）
        range_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
        range_end = range_start + timedelta(days=7)
        events = mgr.get_events_by_range(range_start, range_end)
        daily_events = [e for e in events if e.title == "每日跑步"]
        # 原始事件 + 6 个展开实例 = 7
        assert len(daily_events) == 7, f"期望 7 条，实际 {len(daily_events)}"
        print(f"  [通过] 7 天展开: {len(daily_events)} 条（含原始）")

        # 每周事件展开
        weekly_start = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
        # 找到下一个周一
        days_until_monday = (7 - weekly_start.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = weekly_start + timedelta(days=days_until_monday)
        mgr.add_event(
            title="每周会议",
            start_time=next_monday,
            recurrence_rule="FREQ=WEEKLY",
        )
        range_end_4w = next_monday + timedelta(days=27)
        events = mgr.get_events_by_range(next_monday, range_end_4w)
        weekly_events = [e for e in events if e.title == "每周会议"]
        # 27 天内应有 4 个周一实例（含原始）
        assert len(weekly_events) == 4, f"4 周每周事件期望 4 条，实际 {len(weekly_events)}"
        print(f"  [通过] 4 周每周展开: {len(weekly_events)} 条")

    print()


def test_category_storage_roundtrip():
    """测试 category 字段存储读写"""
    print("=" * 50)
    print("测试 category 存储读写")
    print("=" * 50)

    import tempfile
    from calendar_pkg.manager import CalendarManager

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        mgr = CalendarManager(db_path=db_path)

        # 添加事件（自动分类）
        event = mgr.add_event(
            title="下午三点开会讨论项目",
            start_time=datetime.now() + timedelta(days=1),
        )
        assert event.category == "工作", f"自动分类期望'工作'，实际: {event.category}"
        print(f"  [通过] 自动分类: '{event.title}' -> {event.category}")

        # 手动指定分类
        event2 = mgr.add_event(
            title="晚上看电影",
            start_time=datetime.now() + timedelta(days=1),
            category="娱乐",
        )
        assert event2.category == "娱乐", f"手动分类期望'娱乐'，实际: {event2.category}"
        print(f"  [通过] 手动分类: '{event2.title}' -> {event2.category}")

        # 读取验证
        loaded = mgr.get_event(event.id)
        assert loaded is not None
        assert loaded.category == "工作", f"读取分类期望'工作'，实际: {loaded.category}"
        print(f"  [通过] 存储读取: category={loaded.category}")

    print()


def test_past_date_parsing():
    """测试过去日期解析"""
    print("=" * 50)
    print("测试过去日期解析")
    print("=" * 50)

    parser = TimeParser()
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    day_before = now - timedelta(days=2)

    # 昨天
    result, remaining = parser.parse("昨天下午三点开会")
    assert result is not None
    assert result.day == yesterday.day, f"期望昨天({yesterday.strftime('%m-%d')})，实际 {result.strftime('%m-%d')}"
    assert result.hour == 15
    print(f"  [通过] 昨天: {result.strftime('%m-%d %H:%M')}")

    # 前天
    result, remaining = parser.parse("前天上午十点看牙")
    assert result is not None
    assert result.day == day_before.day, f"期望前天({day_before.strftime('%m-%d')})，实际 {result.strftime('%m-%d')}"
    print(f"  [通过] 前天: {result.strftime('%m-%d %H:%M')}")

    # 3天前
    result, remaining = parser.parse("3天前下午两点健身")
    assert result is not None
    expected = now - timedelta(days=3)
    assert result.day == expected.day, f"期望 3 天前({expected.strftime('%m-%d')})，实际 {result.strftime('%m-%d')}"
    print(f"  [通过] 3天前: {result.strftime('%m-%d %H:%M')}")

    # 上周X
    result, remaining = parser.parse("上周五下午三点开会")
    assert result is not None
    assert result.weekday() == 4, f"期望周五(4)，实际 weekday={result.weekday()}"
    assert result < now, "上周五应是过去日期"
    print(f"  [通过] 上周五: {result.strftime('%m-%d %H:%M')} (weekday={result.weekday()})")

    # 过去事件创建
    import tempfile
    from calendar_pkg.manager import CalendarManager

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        mgr = CalendarManager(db_path=db_path)
        event = mgr.add_event(
            title="昨天的会议",
            start_time=yesterday.replace(hour=15, minute=0),
        )
        assert event.id is not None
        loaded = mgr.get_event(event.id)
        assert loaded is not None
        print(f"  [通过] 过去事件创建: {loaded.title} @ {loaded.start_time.strftime('%m-%d %H:%M')}")

    print()


def test_backup_export_import():
    """测试备份导出/导入"""
    print("=" * 50)
    print("测试备份导出/导入")
    print("=" * 50)

    import tempfile
    from calendar_pkg.manager import CalendarManager

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        mgr = CalendarManager(db_path=db_path)

        # 添加几个事件
        mgr.add_event(title="开会", start_time=datetime.now() + timedelta(days=1))
        mgr.add_event(title="健身", start_time=datetime.now() + timedelta(days=2))
        mgr.add_event(title="读书", start_time=datetime.now() + timedelta(days=3))
        assert mgr.get_event_count() == 3

        # 导出
        backup_path = os.path.join(tmpdir, "backup.json")
        count = mgr.export_backup(backup_path)
        assert count == 3, f"期望导出 3 条，实际 {count}"
        assert os.path.exists(backup_path)
        print(f"  [通过] 导出: {count} 条事件")

        # 导入到新的数据库（合并模式）
        db_path2 = os.path.join(tmpdir, "test2.db")
        mgr2 = CalendarManager(db_path=db_path2)
        result = mgr2.import_backup(backup_path, mode="merge")
        assert result["imported"] == 3, f"期望导入 3 条，实际 {result}"
        print(f"  [通过] 合并导入: {result}")

        # 再次合并导入，应跳过已存在的
        result2 = mgr2.import_backup(backup_path, mode="merge")
        assert result2["skipped"] == 3, f"期望跳过 3 条，实际 {result2}"
        print(f"  [通过] 重复导入跳过: {result2}")

        # 覆盖模式
        result3 = mgr2.import_backup(backup_path, mode="overwrite")
        assert result3["imported"] == 3, f"覆盖期望导入 3 条，实际 {result3}"
        assert mgr2.get_event_count() == 3
        print(f"  [通过] 覆盖导入: {result3}")

    print()


def test_soft_delete_restore():
    """测试软删除和回收站"""
    print("=" * 50)
    print("测试软删除与回收站")
    print("=" * 50)

    import tempfile
    from calendar_pkg.manager import CalendarManager

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        mgr = CalendarManager(db_path=db_path)

        # 创建事件
        e1 = mgr.add_event(title="会议A", start_time=datetime.now() + timedelta(days=1))
        e2 = mgr.add_event(title="会议B", start_time=datetime.now() + timedelta(days=2))
        assert mgr.get_event_count() == 2

        # 软删除
        title = mgr.delete_event(e1.id)
        assert title == "会议A"
        print(f"  [通过] 软删除: {title}")

        # 查询应排除已删除的
        deleted = mgr.get_deleted_events()
        assert len(deleted) == 1
        assert deleted[0].title == "会议A"
        print(f"  [通过] 回收站: {len(deleted)} 条")

        # 恢复
        ok = mgr.restore_event(e1.id)
        assert ok
        deleted_after = mgr.get_deleted_events()
        assert len(deleted_after) == 0
        print("  [通过] 恢复事件")

        # 彻底删除
        mgr.delete_event(e2.id)
        ok = mgr.hard_delete_event(e2.id)
        assert ok
        deleted_final = mgr.get_deleted_events()
        assert len(deleted_final) == 0
        print("  [通过] 彻底删除")

    print()


def test_stats_engine():
    """测试统计引擎"""
    print("=" * 50)
    print("测试统计引擎")
    print("=" * 50)

    import tempfile
    from calendar_pkg.manager import CalendarManager
    from calendar_pkg.stats import StatsEngine

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        mgr = CalendarManager(db_path=db_path)
        stats = StatsEngine(mgr.storage)

        now = datetime.now()
        # 创建几个事件
        mgr.add_event(title="跑步", start_time=now - timedelta(days=1, hours=2), category="健康")
        mgr.add_event(title="开会", start_time=now - timedelta(days=1, hours=1), category="工作")
        mgr.add_event(title="学习Python", start_time=now + timedelta(hours=1), category="学习")
        mgr.add_event(title="看电影", start_time=now + timedelta(days=2), category="娱乐")

        # 月度统计
        monthly = stats.get_monthly_stats(now.year, now.month)
        assert "健康" in monthly or "工作" in monthly
        print(f"  [通过] 月度统计: {len(monthly)} 个分类")

        # 热力图数据
        heatmap = stats.get_heatmap_data(now.year, now.month)
        assert len(heatmap) > 0
        print(f"  [通过] 热力图: {len(heatmap)} 天有事件")

        # 趋势数据
        trend = stats.get_trend_data(days=7)
        assert len(trend) > 0
        print(f"  [通过] 趋势数据: {len(trend)} 天")

        # 分类汇总
        summary = stats.get_category_summary()
        assert sum(summary.values()) == 4
        print(f"  [通过] 分类汇总: {summary}")

    print()


def test_achievement_engine():
    """测试成就系统"""
    print("=" * 50)
    print("测试成就系统")
    print("=" * 50)

    import tempfile
    from calendar_pkg.manager import CalendarManager
    from calendar_pkg.stats import StatsEngine
    from calendar_pkg.achievement import AchievementEngine

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        ach_path = os.path.join(tmpdir, "achievements.json")
        mgr = CalendarManager(db_path=db_path)
        stats_engine = StatsEngine(mgr.storage)
        ach_engine = AchievementEngine(stats_engine, save_path=ach_path)

        # 创建事件前检查
        all_ach = ach_engine.get_all_achievements()
        assert len(all_ach) > 0
        assert ach_engine.get_unlocked_count() == 0
        print(f"  [通过] 初始状态: {ach_engine.get_total_count()} 个成就, 0 解锁")

        # 创建一个事件后检查
        mgr.add_event(title="测试事件", start_time=datetime.now())
        new_achs = ach_engine.check_achievements()
        # 应该解锁 "初次启程"
        assert len(new_achs) >= 1
        assert any(a["id"] == "first_event" for a in new_achs)
        print(f"  [通过] 解锁成就: {[a['name'] for a in new_achs]}")

        # 再次检查不应重复解锁
        new_achs2 = ach_engine.check_achievements()
        assert len(new_achs2) == 0
        print("  [通过] 不重复解锁")

        # 持久化检查
        ach_engine2 = AchievementEngine(stats_engine, save_path=ach_path)
        assert ach_engine2.get_unlocked_count() >= 1
        print("  [通过] 成就持久化")

    print()


def test_reminder_sound_and_dnd():
    """测试个性化提醒音效和免打扰"""
    print("=" * 50)
    print("测试个性化提醒与免打扰")
    print("=" * 50)

    from calendar_pkg.reminder import ReminderScheduler
    from datetime import datetime

    sounds = {"工作": "bell.wav", "健康": "chime.wav", "默认": "default.wav"}
    scheduler = ReminderScheduler.__new__(ReminderScheduler)
    scheduler._reminder_sounds = sounds
    scheduler._dnd_enabled = True
    scheduler._dnd_start = "22:00"
    scheduler._dnd_end = "07:00"

    # 音效映射
    assert scheduler.get_sound_for_category("工作") == "bell.wav"
    assert scheduler.get_sound_for_category("健康") == "chime.wav"
    assert scheduler.get_sound_for_category("其他") == "default.wav"
    print(f"  [通过] 音效映射: 工作={sounds['工作']}, 健康={sounds['健康']}, 默认={sounds['默认']}")

    # 免打扰时段（跨日：22:00-07:00）
    assert scheduler._is_in_dnd_period(datetime(2026, 1, 1, 23, 0))  # 23:00 在 DND 内
    assert scheduler._is_in_dnd_period(datetime(2026, 1, 1, 5, 30))  # 05:30 在 DND 内
    assert not scheduler._is_in_dnd_period(datetime(2026, 1, 1, 10, 0))  # 10:00 不在 DND
    assert not scheduler._is_in_dnd_period(datetime(2026, 1, 1, 21, 0))  # 21:00 不在 DND
    print("  [通过] 跨日免打扰: 22:00-07:00")

    # 同日免打扰
    scheduler._dnd_start = "12:00"
    scheduler._dnd_end = "14:00"
    assert scheduler._is_in_dnd_period(datetime(2026, 1, 1, 13, 0))
    assert not scheduler._is_in_dnd_period(datetime(2026, 1, 1, 15, 0))
    print("  [通过] 同日免打扰: 12:00-14:00")

    print()


def test_command_completion():
    """测试智能补全"""
    print("=" * 50)
    print("测试智能补全")
    print("=" * 50)

    from command.completion import CommandCompleter
    from command.rule_engine import ParsedCommand, CommandType

    completer = CommandCompleter()

    # 完整指令
    cmd = ParsedCommand(
        command_type=CommandType.ADD_EVENT,
        title="开会",
        time=datetime.now() + timedelta(days=1),
    )
    check = completer.check_completeness(cmd)
    assert check["complete"] is True
    print("  [通过] 完整指令: complete=True")

    # 缺少时间
    cmd_no_time = ParsedCommand(
        command_type=CommandType.ADD_EVENT,
        title="开会",
        time=None,
    )
    check = completer.check_completeness(cmd_no_time)
    assert check["complete"] is False
    assert "time" in check["missing"]
    assert check["suggestion"] is not None
    print(f"  [通过] 缺少时间: suggestion='{check['suggestion']}'")

    # 补全后
    completed = completer.complete_command(cmd_no_time)
    assert completed.time is not None
    assert completed.time.hour == 14  # 默认 14:00
    print(f"  [通过] 补全时间: {completed.time.strftime('%m-%d %H:%M')}")

    # 缺少标题
    cmd_no_title = ParsedCommand(
        command_type=CommandType.ADD_EVENT,
        title="",
        time=datetime.now(),
        original_text="原始文本",
    )
    completed = completer.complete_command(cmd_no_title)
    assert completed.title == "原始文本"
    print(f"  [通过] 补全标题: '{completed.title}'")

    # 非 ADD 指令不补全
    cmd_query = ParsedCommand(command_type=CommandType.QUERY_EVENT)
    check = completer.check_completeness(cmd_query)
    assert check["complete"] is True
    print("  [通过] 非 ADD 指令: 不补全")

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
        "models",
        "intent_classifier",
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

    # 验证标签完整性（支持 5 类或 8 类标签）
    expected_labels_5 = {"add_event", "query_event", "delete_event", "update_event", "other"}
    expected_labels_8 = expected_labels_5 | {"add_recurring", "delete_recurring", "update_recurring"}
    actual_labels = set(clf.label_names)
    has_recurring = actual_labels == expected_labels_8
    if actual_labels == expected_labels_5:
        print("  [通过] 标签完整性验证 (5类)")
    elif has_recurring:
        print("  [通过] 标签完整性验证 (8类，含循环标签)")
    else:
        assert False, f"标签不匹配: {actual_labels}"
    expected_labels = actual_labels

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
        "models",
        "intent_classifier",
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
        print(
            f"  [{status}] 模型集成: '{text}' → {result.command_type.value} "
            f"(confidence={result.confidence:.3f}) [期望: {expected_type.value}]"
        )

    # 测试非日历指令（模型应识别为 UNKNOWN）
    result = parser_model.parse("帮我订一张去北京的机票")
    print(f"  [信息] 非日历指令: → {result.command_type.value} (confidence={result.confidence:.3f})")

    print()


def test_interaction_log_regressions():
    """回归测试：验证实际语音交互日志中暴露的问题"""
    print("=" * 50)
    print("测试实际交互日志回归问题")
    print("=" * 50)

    engine = RuleEngine()
    now = datetime.now()

    # P0: 循环触发词不应吞噬标题
    result = engine.parse("每周六下午五点健身")
    assert result.command_type == CommandType.ADD_EVENT, f"期望 add_event, 得到 {result.command_type}"
    assert "每" not in result.title, f"标题含循环触发词: '{result.title}'"
    assert result.title == "健身", f"标题应为'健身', 实际为'{result.title}'"
    assert result.recurrence_rule == "FREQ=WEEKLY;BYDAY=SA", f"循环规则错误: '{result.recurrence_rule}'"
    print(f"  [通过] 循环标题: '{result.title}', 规则: {result.recurrence_rule}")

    result2 = engine.parse("每天早上九点起床")
    assert "每天" not in result2.title, f"标题含循环触发词: '{result2.title}'"
    assert result2.title == "起床", f"标题应为'起床', 实际为'{result2.title}'"
    assert result2.recurrence_rule == "FREQ=DAILY", f"循环规则错误: '{result2.recurrence_rule}'"
    print(f"  [通过] 循环标题: '{result2.title}', 规则: {result2.recurrence_rule}")

    # P0: 同日期不应解析到下一年
    today_str = f"{now.month}月{now.day}号"
    result3 = engine.parse(f"{today_str}晚上七点吃饭")
    assert result3.time is not None, f"解析失败: {today_str}晚上七点吃饭"
    assert result3.time.year == now.year, f"同日期不应跳到下一年: {result3.time}"
    print(f"  [通过] 同日期: '{today_str}晚上七点' → {result3.time.strftime('%Y-%m-%d %H:%M')}")

    # P1: "不 X 了"应识别为删除
    result4 = engine.parse("今天中午十二点不吃外卖了")
    assert result4.command_type == CommandType.DELETE_EVENT, f"'不X了'应为 delete, 实际为 {result4.command_type}"
    print(f"  [通过] 否定删除: '不吃外卖了' → {result4.command_type.value}")

    result5 = engine.parse("今天下午八点不上课了")
    assert result5.command_type == CommandType.DELETE_EVENT, f"'不X了'应为 delete, 实际为 {result5.command_type}"
    print(f"  [通过] 否定删除: '不上课了' → {result5.command_type.value}")

    # P1: "向前推"应识别为修改
    result6 = engine.parse("六月一号的面试向前推一个小时")
    assert result6.command_type == CommandType.UPDATE_EVENT, f"'向前推'应为 update, 实际为 {result6.command_type}"
    print(f"  [通过] 时间调整: '向前推一个小时' → {result6.command_type.value}")

    # P1: "挪到"应识别为修改
    result7 = engine.parse("活动挪到三十号")
    assert result7.command_type == CommandType.UPDATE_EVENT, f"'挪到'应为 update, 实际为 {result7.command_type}"
    print(f"  [通过] 时间调整: '挪到三十号' → {result7.command_type.value}")

    print()


def test_asr_text_correction():
    """测试 ASR 后处理纠错链路"""
    print("=" * 50)
    print("测试 ASR 后处理纠错")
    print("=" * 50)

    from engine.text_corrector import TextCorrector

    corrector = TextCorrector(enabled=True)

    # 日历场景同音纠错
    test_cases = [
        ("这株每天下午两点都要五岁", "这周每天下午两点都要午睡", "日历同音: 这株→这周, 五岁→午睡"),
        ("名天下午三点开会", "明天下午三点开会", "日历同音: 名天→明天"),
        ("后添上午十点看牙", "后天上午十点看牙", "日历同音: 后添→后天"),
        ("今天晚上八点见身", "今天晚上八点健身", "日历同音: 见身→健身"),
        ("零晨三点开会", "凌晨三点开会", "日历同音: 零晨→凌晨"),
    ]

    for input_text, expected_contains, desc in test_cases:
        result = corrector.correct(input_text)
        # 检查关键部分是否被纠正
        # 注: 的/地/得规则可能会添加“的”，所以用 in 检查
        assert expected_contains in result or result == expected_contains, (
            f"{desc} 失败: '{input_text}' → '{result}', 期望包含 '{expected_contains}'"
        )
        print(f"  [通过] {desc}")

    # PostProcessor 拼音规则测试
    from engine.post_processor import PostProcessor

    pp = PostProcessor()

    pp_cases = [
        ("这株每天下午两点都要五睡", "这周", "PostProcessor: 这株→这周"),
        ("名天下午三点面试", "明天", "PostProcessor: 名天→明天"),
        ("后添上午十点看牙", "后天", "PostProcessor: 后添→后天"),
        ("五睡两个小时", "午睡", "PostProcessor: 五睡→午睡"),
    ]

    for input_text, expected_contains, desc in pp_cases:
        result = pp.process(input_text)
        assert expected_contains in result, f"{desc} 失败: '{input_text}' → '{result}', 期望包含 '{expected_contains}'"
        print(f"  [通过] {desc}")

    # TimeParser 时间词纠错测试
    tp_cases = [
        ("帮晚六点吃饭", "傍晚", "TimeParser: 帮晚→傍晚"),
        ("零晨三点开会", "凌晨", "TimeParser: 零晨→凌晨"),
    ]

    from command.time_parser import TimeParser

    tp = TimeParser()
    for input_text, expected_keyword, desc in tp_cases:
        # _fuzzy_correct 是 classmethod，直接调用
        corrected = TimeParser._fuzzy_correct_time_keywords(input_text)
        assert expected_keyword in corrected, (
            f"{desc} 失败: '{input_text}' → '{corrected}', 期望包含 '{expected_keyword}'"
        )
        print(f"  [通过] {desc}")

    print()


def test_recurrence_resolver():
    """测试 RecurrenceResolver 循环日期计算"""
    print("=" * 50)
    print("测试 RecurrenceResolver")
    print("=" * 50)

    from command.recurrence_resolver import RecurrenceResolver

    resolver = RecurrenceResolver()
    now = datetime.now()
    weekday = now.weekday()  # 0=周一

    # 1. 下周每天 -> FREQ=DAILY, UNTIL=下周日
    r = resolver.resolve("下周每天下午三点健身", base_date=now)
    assert r.rule == "FREQ=DAILY", f"规则错误: {r.rule}"
    assert r.end_time is not None, "UNTIL 不应为 None"
    next_monday = now + timedelta(days=7 - weekday)
    next_sunday = next_monday + timedelta(days=6)
    assert r.end_time.date() == next_sunday.date(), f"UNTIL 日期错误: {r.end_time.date()} vs {next_sunday.date()}"
    assert "下午三点健身" in r.cleaned_text, f"cleaned_text 错误: {r.cleaned_text}"
    print(f"  [通过] 下周每天: rule={r.rule}, end={r.end_time.strftime('%m-%d')}")

    # 2. 这周每天 (前向) -> UNTIL=本周日
    r = resolver.resolve("这周每天上午九点起床", base_date=now)
    assert r.rule == "FREQ=DAILY", f"规则错误: {r.rule}"
    this_sunday = now + timedelta(days=6 - weekday)
    assert r.end_time.date() == this_sunday.date(), f"UNTIL 日期错误: {r.end_time.date()} vs {this_sunday.date()}"
    print(f"  [通过] 这周每天(前向): end={r.end_time.strftime('%m-%d')}")

    # 3. 这周每天 + 过去时态 (后向) -> 周一到今天
    r = resolver.resolve("这周每天下午两点都学习了", base_date=now)
    assert r.rule == "FREQ=DAILY", f"规则错误: {r.rule}"
    this_monday = now - timedelta(days=weekday)
    assert r.start_time.date() == this_monday.date(), f"start 日期错误: {r.start_time.date()}"
    assert r.end_time.date() == now.date(), f"end 日期错误: {r.end_time.date()} vs {now.date()}"
    print(f"  [通过] 这周每天(后向): start={r.start_time.strftime('%m-%d')}, end={r.end_time.strftime('%m-%d')}")

    # 4. 每个月1号 -> BYMONTHDAY=1
    r = resolver.resolve("每个月1号下午三点存工资", base_date=now)
    assert "BYMONTHDAY=1" in r.rule, f"规则错误: {r.rule}"
    assert r.end_time is None, "无限循环不应有 UNTIL"
    assert "下午三点存工资" in r.cleaned_text, f"cleaned_text 错误: {r.cleaned_text}"
    print(f"  [通过] 每个月1号: rule={r.rule}")

    # 5. 每月15号 -> BYMONTHDAY=15
    r = resolver.resolve("每月15号上午十点交房租", base_date=now)
    assert "BYMONTHDAY=15" in r.rule, f"规则错误: {r.rule}"
    print(f"  [通过] 每月15号: rule={r.rule}")

    # 6. 每天 (无范围) -> FREQ=DAILY, 无 UNTIL
    r = resolver.resolve("每天下午两点午睡", base_date=now)
    assert r.rule == "FREQ=DAILY", f"规则错误: {r.rule}"
    assert r.end_time is None, "无限循环不应有 UNTIL"
    print(f"  [通过] 每天(无限): rule={r.rule}")

    # 7. 每周六 -> WEEKLY;BYDAY=SA
    r = resolver.resolve("每周六下午五点健身", base_date=now)
    assert "BYDAY=SA" in r.rule, f"规则错误: {r.rule}"
    print(f"  [通过] 每周六: rule={r.rule}")

    # 8. 工作日 -> WEEKLY;BYDAY=MO,TU,WE,TH,FR
    r = resolver.resolve("工作日早上九点打卡", base_date=now)
    assert "BYDAY=MO,TU,WE,TH,FR" in r.rule, f"规则错误: {r.rule}"
    print(f"  [通过] 工作日: rule={r.rule}")

    print()


def test_duration_detection():
    """测试持续事件时长检测"""
    print("=" * 50)
    print("测试持续事件检测")
    print("=" * 50)

    from command.rule_engine import RuleEngine

    engine = RuleEngine()

    # 1. 学习三小时
    r = engine.parse("明天下午两点学习三小时")
    assert r.end_time is not None, "end_time 不应为 None"
    assert r.time is not None, "time 不应为 None"
    duration_min = (r.end_time - r.time).total_seconds() / 60
    assert duration_min == 180, f"时长错误: {duration_min} 分钟"
    assert r.title == "学习", f"标题错误: {r.title}"
    print(f"  [通过] 学习三小时: end_time={r.end_time.strftime('%H:%M')}, title={r.title}")

    # 2. 开会半小时
    r = engine.parse("明天下午两点开会半小时")
    assert r.end_time is not None, "end_time 不应为 None"
    duration_min = (r.end_time - r.time).total_seconds() / 60
    assert duration_min == 30, f"时长错误: {duration_min} 分钟"
    print(f"  [通过] 开会半小时: end_time={r.end_time.strftime('%H:%M')}")

    # 3. 跑步45分钟
    r = engine.parse("明天下午两点跑步45分钟")
    assert r.end_time is not None, "end_time 不应为 None"
    duration_min = (r.end_time - r.time).total_seconds() / 60
    assert duration_min == 45, f"时长错误: {duration_min} 分钟"
    print(f"  [通过] 跑步45分钟: end_time={r.end_time.strftime('%H:%M')}")

    # 4. 非持续事件
    r = engine.parse("明天下午三点开会")
    assert r.end_time is None, f"非持续事件不应有 end_time: {r.end_time}"
    print("  [通过] 非持续事件: end_time=None")

    print()


def test_scoped_recurring_integration():
    """测试有界循环事件展开集成"""
    print("=" * 50)
    print("测试有界循环事件展开")
    print("=" * 50)

    import tempfile
    from calendar_pkg.manager import CalendarManager

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        mgr = CalendarManager(db_path=db_path)

        now = datetime.now()
        weekday = now.weekday()
        next_monday = (now + timedelta(days=7 - weekday)).replace(hour=15, minute=0, second=0, microsecond=0)
        next_sunday = (next_monday + timedelta(days=6)).replace(hour=23, minute=59, second=59)

        event = mgr.add_event(
            title="下周健身",
            start_time=next_monday,
            recurrence_rule="FREQ=DAILY",
            recurrence_end=next_sunday,
        )
        assert event.id is not None, "事件创建失败"

        # 查询下周范围
        range_start = next_monday - timedelta(days=1)
        range_end = next_sunday + timedelta(days=1)
        events = mgr.get_events_by_range(range_start, range_end)

        # 应包含原始事件 + 6 个展开实例 = 7
        recurring_instances = [e for e in events if e.title == "下周健身"]
        assert len(recurring_instances) == 7, f"期望7个实例，实际: {len(recurring_instances)}"
        print(f"  [通过] 下周每天展开: {len(recurring_instances)} 个实例")

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
        test_priority_detection()
        test_event_classification()
        test_category_storage_roundtrip()
        test_recurrence_detection()
        test_recurrence_expansion()
        test_past_date_parsing()
        test_backup_export_import()
        test_soft_delete_restore()
        test_stats_engine()
        test_achievement_engine()
        test_reminder_sound_and_dnd()
        test_command_completion()
        test_intent_classifier_import()
        test_intent_classifier_inference()
        test_parser_with_intent_model()
        test_interaction_log_regressions()
        test_asr_text_correction()
        test_recurrence_resolver()
        test_duration_detection()
        test_scoped_recurring_integration()
        print("=" * 50)
        print("全部测试通过!")
        print("=" * 50)
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
