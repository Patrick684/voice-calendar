"""测试精简prompt对延迟的影响"""

import json
import time
import os
from urllib import request

os.environ["NO_PROXY"] = "localhost,127.0.0.1"

# 极简prompt（~50 tokens vs 原始 ~200 tokens）
SHORT_PROMPT = (
    "日历指令解析器。输出JSON数组，每项含type(add/delete/query/update)、title、date、time字段。title仅保留核心事件名。"
)

# 原始prompt（~200 tokens）
LONG_PROMPT = """你是日历语音指令解析器。用户通过语音输入日历操作指令（无标点符号）。
请将输入拆分为独立指令，每条指令提取以下字段。
输出格式（严格 JSON 数组，不要输出任何其他内容）:
[{"type": "add" | "delete" | "query" | "update", "title": "事件标题", "date": "日期表达或空字符串", "time": "时间表达或空字符串", "recurrence": "循环规则或空字符串", "priority": "普通"}]
规则：
- add: 添加/安排事件，或隐式添加
- delete: 删除/取消事件，包括"不X了"
- query: 查看/查询日程
- update: 修改/推迟/提前
- title 只保留事件核心描述"""

cases = ["明天下午三点开会", "取消明天的会议", "后天上午十点面试还有下午三点健身", "不去健身了"]
opener = request.build_opener(request.ProxyHandler({}))

# 先 warmup
payload = json.dumps(
    {
        "model": "qwen2.5:3b",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "options": {"num_predict": 1},
    }
).encode()
req = request.Request("http://localhost:11434/api/chat", data=payload, headers={"Content-Type": "application/json"})
opener.open(req, timeout=60)

for label, prompt in [("LONG (~200 tok)", LONG_PROMPT), ("SHORT (~50 tok)", SHORT_PROMPT)]:
    print(f"\n{'=' * 50}")
    print(f"Prompt: {label}")
    print(f"{'=' * 50}")
    times = []
    for text in cases:
        payload = json.dumps(
            {
                "model": "qwen2.5:3b",
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text},
                ],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 128},
            }
        ).encode("utf-8")
        req = request.Request(
            "http://localhost:11434/api/chat", data=payload, headers={"Content-Type": "application/json"}
        )
        t0 = time.time()
        resp = opener.open(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - t0
        content = data.get("message", {}).get("content", "")[:80]
        status = "OK" if elapsed < 1.0 else "SLOW"
        print(f"  [{elapsed:.2f}s] [{status}] {text}")
        print(f"         -> {content}")
        times.append(elapsed)
    print(f"  --- Avg: {sum(times) / len(times):.2f}s | <1s: {sum(1 for t in times if t < 1.0)}/{len(times)}")
