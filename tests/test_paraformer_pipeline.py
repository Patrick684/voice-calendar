"""Paraformer 后处理管线对比测试

对比两种方案处理复杂多事件语音指令的效果：
- 方案 A：Paraformer 纯文本输出 + 我们的后处理链（TextCorrector + PunctuationRestorer + CommandParser）
- 方案 B：Paraformer 自带标点模型（ct-punc）输出 + CommandParser

测试重点：多事件分割准确性、循环事件识别、时间解析正确性
"""

import sys
import io
import os
import time
import wave
import tempfile
import numpy as np
from pathlib import Path

# 强制 UTF-8 输出
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ========== 复杂多事件测试用例 ==========
# 格式: (语音文本, 期望解析出的事件数量, 期望关键词列表)
COMPLEX_CASES = [
    # 多事件连续
    ("明天下午三点开会然后晚上八点跑步", 2, ["开会", "跑步"]),
    ("后天上午十点看牙医下午两点面试", 2, ["看牙医", "面试"]),
    ("帮我安排下周一上午九点开会下午三点健身晚上七点吃药", 3, ["开会", "健身", "吃药"]),
    # 循环事件
    ("每天早上七点起床打卡", 1, ["起床打卡"]),
    ("每周五下午四点健身", 1, ["健身"]),
    ("这周每天下午两点都要午睡", 1, ["午睡"]),
    # 复杂修饰
    ("大后天下午两点半去银行办事", 1, ["银行办事"]),
    ("三天后上午九点出发去机场", 1, ["出发"]),
    # 混合指令（增删改查）
    ("删除明天的会议然后帮我加后天下午三点面试", 2, ["会议", "面试"]),
    ("把明天的会改到后天然后取消下周三的客户会面", 2, ["会", "客户会面"]),
    # 长句多事件
    ("明天早上八点晨读然后十点开会下午两点面试晚上七点跑步", 4, ["晨读", "开会", "面试", "跑步"]),
]


def synthesize_audio(text: str, audio_dir: Path) -> str:
    """用 pyttsx3 合成单条音频"""
    import pyttsx3

    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    for v in voices:
        if "huihui" in v.name.lower():
            engine.setProperty("voice", v.id)
            break
    engine.setProperty("rate", 150)

    audio_path = str(audio_dir / f"test_{hash(text) & 0xFFFFFF:06x}.wav")
    engine.save_to_file(text, audio_path)
    engine.runAndWait()
    return audio_path


def load_audio(filepath: str) -> np.ndarray:
    """加载 WAV 为 16kHz float32"""
    with wave.open(filepath, "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        sr = wf.getframerate()

    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    # 立体声转单声道
    if len(audio) > 0:
        with wave.open(filepath, "rb") as wf:
            if wf.getnchannels() > 1:
                audio = audio.reshape(-1, wf.getnchannels()).mean(axis=1)

    # 重采样到 16kHz
    if sr != 16000:
        ratio = 16000 / sr
        new_len = int(len(audio) * ratio)
        audio = np.interp(np.linspace(0, len(audio) - 1, new_len), np.arange(len(audio)), audio).astype(np.float32)

    return audio


def test_pipeline_a(model, audio_files, cases):
    """方案 A: Paraformer 纯文本 + 我们的后处理链 + CommandParser"""
    print("\n" + "=" * 60)
    print("  方案 A: Paraformer 纯文本 → TextCorrector → CommandParser")
    print("=" * 60)

    from engine.text_corrector import TextCorrector
    from command.parser import CommandParser

    corrector = TextCorrector()
    parser = CommandParser()

    results = []
    for i, (audio_path, (text, expected_count, keywords)) in enumerate(zip(audio_files, cases)):
        audio = load_audio(audio_path)

        t0 = time.time()
        # Paraformer 识别（纯文本，无标点）
        raw_text = model.generate(input=audio)
        if raw_text and len(raw_text) > 0:
            asr_text = raw_text[0].get("text", "") if isinstance(raw_text[0], dict) else str(raw_text[0])
            asr_text = asr_text.replace(" ", "").strip()
            # 去标点
            import unicodedata

            asr_text = "".join(ch for ch in asr_text if not unicodedata.category(ch).startswith("P"))
        else:
            asr_text = ""
        elapsed_asr = time.time() - t0

        # 后处理
        corrected = corrector.correct(asr_text) if asr_text else ""

        # 指令解析
        commands = parser.parse_multiple(corrected) if corrected else []
        elapsed_total = time.time() - t0

        # 评估
        event_count = len(commands)
        found_keywords = []
        for kw in keywords:
            for cmd in commands:
                if kw in (cmd.title or ""):
                    found_keywords.append(kw)
                    break

        count_ok = event_count == expected_count
        kw_ok = len(found_keywords) == len(keywords)
        status = "OK" if (count_ok and kw_ok) else "FAIL"

        results.append(
            {
                "text": text,
                "asr": asr_text,
                "commands": len(commands),
                "expected": expected_count,
                "count_ok": count_ok,
                "kw_found": len(found_keywords),
                "kw_total": len(keywords),
                "kw_ok": kw_ok,
                "time": elapsed_total,
            }
        )

        mark = "  " if status == "OK" else "!!"
        print(
            f"  {mark}[{i + 1:2d}] {status:>4s} | 事件:{event_count}/{expected_count} "
            f"| 关键词:{len(found_keywords)}/{len(keywords)} | {elapsed_total:.2f}s"
        )
        if asr_text != text:
            print(f"         ASR: '{asr_text}'")
        if not count_ok or not kw_ok:
            titles = [cmd.title for cmd in commands]
            print(f"         解析: {titles}")

    # 汇总
    total_ok = sum(1 for r in results if r["count_ok"] and r["kw_ok"])
    print(f"\n  {'─' * 50}")
    print(f"  总计: {total_ok}/{len(results)} 通过")
    print(f"  事件数正确率: {sum(r['count_ok'] for r in results)}/{len(results)}")
    print(f"  关键词命中率: {sum(r['kw_found'] for r in results)}/{sum(r['kw_total'] for r in results)}")
    return results


def test_pipeline_b(audio_files, cases):
    """方案 B: Paraformer + 自带标点模型 (ct-punc) → CommandParser

    注意：ct-punc 在当前环境可能崩溃（cuDNN 冲突），
    如果崩溃则跳过此方案。
    """
    print("\n" + "=" * 60)
    print("  方案 B: Paraformer + ct-punc 标点模型 → CommandParser")
    print("=" * 60)

    try:
        from funasr import AutoModel

        # 尝试加载带标点的模型（单独实例，不含 VAD 以避免冲突）
        punc_model = AutoModel(model="ct-punc", device="cpu", disable_update=True)
        print("  ct-punc 标点模型加载成功 (CPU)")
    except Exception as e:
        print(f"  ct-punc 加载失败: {e}")
        print("  跳过方案 B")
        return None

    from command.parser import CommandParser

    parser = CommandParser()

    # 需要一个 ASR 模型来识别
    from funasr import AutoModel as AM

    asr_model = AM(model="paraformer-zh", vad_model="fsmn-vad", device="cuda:0", disable_update=True)

    results = []
    for i, (audio_path, (text, expected_count, keywords)) in enumerate(zip(audio_files, cases)):
        audio = load_audio(audio_path)

        t0 = time.time()
        # Paraformer 识别
        raw_text = asr_model.generate(input=audio)
        if raw_text and len(raw_text) > 0:
            asr_text = raw_text[0].get("text", "") if isinstance(raw_text[0], dict) else str(raw_text[0])
            asr_text = asr_text.replace(" ", "").strip()
        else:
            asr_text = ""

        # 用 ct-punc 恢复标点
        if asr_text:
            punc_result = punc_model.generate(input=asr_text)
            if punc_result and len(punc_result) > 0:
                punc_text = punc_result[0].get("text", asr_text) if isinstance(punc_result[0], dict) else asr_text
            else:
                punc_text = asr_text
        else:
            punc_text = ""

        # 去标点后交给 parser（我们的 parser 期望无标点输入）
        import unicodedata

        clean_text = "".join(ch for ch in punc_text if not unicodedata.category(ch).startswith("P"))

        # 指令解析
        commands = parser.parse_multiple(clean_text) if clean_text else []
        elapsed_total = time.time() - t0

        # 评估
        event_count = len(commands)
        found_keywords = []
        for kw in keywords:
            for cmd in commands:
                if kw in (cmd.title or ""):
                    found_keywords.append(kw)
                    break

        count_ok = event_count == expected_count
        kw_ok = len(found_keywords) == len(keywords)
        status = "OK" if (count_ok and kw_ok) else "FAIL"

        results.append(
            {
                "text": text,
                "asr": asr_text,
                "punc": punc_text,
                "commands": len(commands),
                "expected": expected_count,
                "count_ok": count_ok,
                "kw_found": len(found_keywords),
                "kw_total": len(keywords),
                "kw_ok": kw_ok,
                "time": elapsed_total,
            }
        )

        mark = "  " if status == "OK" else "!!"
        print(
            f"  {mark}[{i + 1:2d}] {status:>4s} | 事件:{event_count}/{expected_count} "
            f"| 关键词:{len(found_keywords)}/{len(keywords)} | {elapsed_total:.2f}s"
        )
        if punc_text != text:
            print(f"         标点: '{punc_text}'")
        if not count_ok or not kw_ok:
            titles = [cmd.title for cmd in commands]
            print(f"         解析: {titles}")

    # 汇总
    total_ok = sum(1 for r in results if r["count_ok"] and r["kw_ok"])
    print(f"\n  {'─' * 50}")
    print(f"  总计: {total_ok}/{len(results)} 通过")
    print(f"  事件数正确率: {sum(r['count_ok'] for r in results)}/{len(results)}")
    print(f"  关键词命中率: {sum(r['kw_found'] for r in results)}/{sum(r['kw_total'] for r in results)}")
    return results


def main():
    print("=" * 60)
    print("  Paraformer 后处理管线对比测试")
    print("  测试场景：复杂多事件语音指令")
    print("=" * 60)

    # 1. 合成音频
    audio_dir = Path(tempfile.mkdtemp(prefix="pipeline_test_"))
    print(f"\n  音频缓存: {audio_dir}")
    print(f"  正在合成 {len(COMPLEX_CASES)} 条测试音频...")

    audio_files = []
    for i, (text, _, _) in enumerate(COMPLEX_CASES):
        path = synthesize_audio(text, audio_dir)
        if Path(path).exists() and Path(path).stat().st_size > 100:
            audio_files.append(path)
            print(f"    [{i + 1:2d}/{len(COMPLEX_CASES)}] OK")
        else:
            audio_files.append(None)
            print(f"    [{i + 1:2d}/{len(COMPLEX_CASES)}] FAIL")

    # 过滤失败的
    valid = [(f, c) for f, c in zip(audio_files, COMPLEX_CASES) if f]
    if not valid:
        print("  ERROR: 没有成功生成音频！")
        return
    audio_files = [v[0] for v in valid]
    cases = [v[1] for v in valid]
    print(f"  合成完成: {len(audio_files)}/{len(COMPLEX_CASES)}")

    # 2. 加载 Paraformer 模型（方案 A 和 B 共用 ASR）
    print("\n  正在加载 Paraformer 模型...")
    from funasr import AutoModel

    model = AutoModel(
        model="paraformer-zh",
        vad_model="fsmn-vad",
        device="cuda:0",
        disable_update=True,
    )
    print("  模型加载完成 (CUDA)")

    # 3. 方案 A 测试
    results_a = test_pipeline_a(model, audio_files, cases)

    # 4. 方案 B 测试（可能因 cuDNN 冲突失败）
    results_b = test_pipeline_b(audio_files, cases)

    # 5. 对比汇总
    print("\n" + "=" * 60)
    print("  对比汇总")
    print("=" * 60)

    a_pass = sum(1 for r in results_a if r["count_ok"] and r["kw_ok"])
    print(f"  方案 A（纯文本 + 我们的后处理）: {a_pass}/{len(results_a)} 通过")

    if results_b:
        b_pass = sum(1 for r in results_b if r["count_ok"] and r["kw_ok"])
        print(f"  方案 B（ct-punc 标点模型）:      {b_pass}/{len(results_b)} 通过")

        if a_pass >= b_pass:
            print("\n  结论: 方案 A（我们的后处理链）效果 >= 方案 B")
        else:
            print("\n  结论: 方案 B（ct-punc）效果更好，建议集成标点模型")
    else:
        print("  方案 B: 未能执行（ct-punc 加载失败）")
        print("\n  结论: 使用方案 A（纯文本 + 我们的后处理链）")


if __name__ == "__main__":
    main()
