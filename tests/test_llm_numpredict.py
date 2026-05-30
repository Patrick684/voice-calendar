"""快速延迟对比: qwen2.5:3b vs qwen2.5:1.5b"""

import json
import time
import os
from urllib import request

os.environ["NO_PROXY"] = "localhost,127.0.0.1"

PROMPT = '你是日历指令解析器。输出严格JSON数组:[{"type":"add"|"delete"|"query"|"update","title":"标题","date":"日期","time":"时间"}]。title只保留核心描述。'

cases = ["明天下午三点开会", "取消明天的会议", "不去健身了", "后天上午十点面试还有下午三点健身"]
opener = request.build_opener(request.ProxyHandler({}))

for model in ["qwen2.5:3b", "qwen2.5:1.5b"]:
    print(f"\n{'=' * 50}")
    print(f"Model: {model}")
    print(f"{'=' * 50}")
    # warmup
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
            "options": {"num_predict": 1},
        }
    ).encode("utf-8")
    req = request.Request("http://localhost:11434/api/chat", data=payload, headers={"Content-Type": "application/json"})
    opener.open(req, timeout=60)
    print("  (model loaded)")

    times = []
    for text in cases:
        payload = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": text},
                ],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 128},
            }
        ).encode("utf-8")
        req = request.Request(
            "http://localhost:11434/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
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
