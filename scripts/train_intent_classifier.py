"""意图分类器训练脚本

基于 hfl/chinese-roberta-wwm-ext 微调，使用 MASSIVE zh-CN 数据。
特性：WeightedRandomSampler, early stopping, fp16 混合精度, F1-macro 选模型。

用法：
    python scripts/train_intent_classifier.py
"""

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import torch
from torch.utils.data import Dataset, DataLoader
from torch.amp import GradScaler, autocast
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    get_linear_schedule_with_warmup,
)
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    classification_report,
    confusion_matrix,
)
import numpy as np

# --- 配置 ---
MODEL_NAME = "chinese-roberta-wwm-ext"  # 本地目录（由 download.py 下载）
DATA_DIR = Path("data/intent")
OUTPUT_DIR = Path("models/intent_classifier")
MAX_LENGTH = 32          # 语音日历指令短句，32足够
BATCH_SIZE = 64
NUM_EPOCHS = 10
LEARNING_RATE = 2e-5     # 小数据微调更稳定
WEIGHT_DECAY = 0.01
WARMUP_STEPS = 200       # 数据量缩小后适当减少
EARLY_STOPPING_PATIENCE = 3  # 避免过早停止
EVAL_EVERY_STEPS = 200
FP16 = True
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class IntentDataset(Dataset):
    """JSONL 意图分类数据集"""

    def __init__(self, path: Path, tokenizer, label_map: dict, max_length: int):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.texts = []
        self.labels = []

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line.strip())
                self.texts.append(item["text"])
                self.labels.append(label_map[item["label"]])

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        encoding = self.tokenizer(
            self.texts[idx],
            max_length=self.max_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "labels": torch.tensor(self.labels[idx], dtype=torch.long),
        }


def build_weighted_sampler(dataset: IntentDataset) -> torch.utils.data.WeightedRandomSampler:
    """构建类别均衡采样器"""
    label_counts = Counter(dataset.labels)
    num_classes = len(label_counts)
    total = len(dataset)
    # 权重 = total / (num_classes * class_count)
    class_weights = {
        label: total / (num_classes * count) for label, count in label_counts.items()
    }
    sample_weights = [class_weights[label] for label in dataset.labels]
    return torch.utils.data.WeightedRandomSampler(
        weights=sample_weights,
        num_samples=len(sample_weights),
        replacement=True,
    )


def evaluate(model, dataloader, device, label_names: list) -> tuple[float, float, str]:
    """评估模型，返回 (accuracy, f1_macro, report)"""
    model.eval()
    all_preds, all_labels = [], []

    with torch.no_grad():
        for batch in dataloader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            preds = torch.argmax(outputs.logits, dim=-1)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())

    acc = accuracy_score(all_labels, all_preds)
    f1_macro = f1_score(all_labels, all_preds, average="macro")
    report = classification_report(
        all_labels, all_preds, target_names=label_names, zero_division=0
    )
    return acc, f1_macro, report


def train():
    print(f"Device: {DEVICE}")
    if DEVICE == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

    # 加载 label_map
    with open(DATA_DIR / "label_map.json", "r", encoding="utf-8") as f:
        label_map = json.load(f)
    label_names = [k for k, v in sorted(label_map.items(), key=lambda x: x[1])]
    num_labels = len(label_map)
    print(f"Labels ({num_labels}): {label_names}")

    # 加载 tokenizer + model
    print(f"\nLoading model: {MODEL_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=num_labels
    )
    model.to(DEVICE)

    # 加载数据集
    print("Loading datasets...")
    train_ds = IntentDataset(DATA_DIR / "train.jsonl", tokenizer, label_map, MAX_LENGTH)
    dev_ds = IntentDataset(DATA_DIR / "dev.jsonl", tokenizer, label_map, MAX_LENGTH)
    test_ds = IntentDataset(DATA_DIR / "test.jsonl", tokenizer, label_map, MAX_LENGTH)
    print(f"  Train: {len(train_ds)}, Dev: {len(dev_ds)}, Test: {len(test_ds)}")

    # 计算温和类别权重（避免与 WeightedRandomSampler 双重过度纠偏）
    label_counts = Counter(train_ds.labels)
    num_classes = len(label_counts)
    total = len(train_ds)
    raw_weights = {lbl: total / (num_classes * cnt) for lbl, cnt in label_counts.items()}
    # 温和化：sqrt 压缩 + 归一化到 [1.0, ~2.0] 范围
    import math
    sqrt_weights = {lbl: math.sqrt(w) for lbl, w in raw_weights.items()}
    min_sw = min(sqrt_weights.values())
    mild_weights = {lbl: w / min_sw for lbl, w in sqrt_weights.items()}
    class_loss_weights = torch.tensor(
        [mild_weights[i] for i in range(num_classes)], dtype=torch.float, device=DEVICE
    )
    print(f"  class_loss_weights: {class_loss_weights.tolist()}")

    # DataLoader（train 用 WeightedRandomSampler）
    train_sampler = build_weighted_sampler(train_ds)
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, sampler=train_sampler)
    dev_loader = DataLoader(dev_ds, batch_size=BATCH_SIZE, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False)

    # 优化器 + 调度器
    no_decay = ["bias", "LayerNorm.weight"]
    optimizer_grouped = [
        {
            "params": [
                p for n, p in model.named_parameters()
                if not any(nd in n for nd in no_decay)
            ],
            "weight_decay": WEIGHT_DECAY,
        },
        {
            "params": [
                p for n, p in model.named_parameters()
                if any(nd in n for nd in no_decay)
            ],
            "weight_decay": 0.0,
        },
    ]
    optimizer = torch.optim.AdamW(optimizer_grouped, lr=LEARNING_RATE)

    total_steps = len(train_loader) * NUM_EPOCHS
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=WARMUP_STEPS, num_training_steps=total_steps
    )

    # FP16 scaler
    scaler = GradScaler(enabled=FP16 and DEVICE == "cuda")

    # 训练循环
    print(f"\nTraining config:")
    print(f"  epochs={NUM_EPOCHS}, batch_size={BATCH_SIZE}, lr={LEARNING_RATE}")
    print(f"  max_length={MAX_LENGTH}, warmup_steps={WARMUP_STEPS}, fp16={FP16}")
    print(f"  weighted_sampler=True, class_weight_loss=True")
    print(f"  class_loss_weights={class_loss_weights.tolist()}")
    print(f"  early_stopping_patience={EARLY_STOPPING_PATIENCE} (on F1-macro)")
    print(f"  total_steps={total_steps}")
    print()

    best_f1 = 0.0
    patience_counter = 0
    global_step = 0
    start_time = time.time()

    for epoch in range(NUM_EPOCHS):
        model.train()
        epoch_loss = 0.0
        num_batches = 0

        for batch in train_loader:
            input_ids = batch["input_ids"].to(DEVICE)
            attention_mask = batch["attention_mask"].to(DEVICE)
            labels = batch["labels"].to(DEVICE)

            optimizer.zero_grad()

            with autocast(device_type=DEVICE, enabled=FP16 and DEVICE == "cuda"):
                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    labels=labels,
                )
                # 加权损失：小类获得更大梯度信号
                loss_fn = torch.nn.CrossEntropyLoss(weight=class_loss_weights)
                loss = loss_fn(outputs.logits, labels)

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()

            epoch_loss += loss.item()
            num_batches += 1
            global_step += 1

            # 每 EVAL_EVERY_STEPS 评估
            if global_step % EVAL_EVERY_STEPS == 0:
                dev_acc, dev_f1, _ = evaluate(model, dev_loader, DEVICE, label_names)
                avg_loss = epoch_loss / num_batches
                elapsed = time.time() - start_time
                print(
                    f"  Step {global_step:>5} | Epoch {epoch+1} | "
                    f"Loss {avg_loss:.4f} | Dev Acc {dev_acc:.4f} | "
                    f"Dev F1-macro {dev_f1:.4f} | {elapsed:.0f}s"
                )

                if dev_f1 > best_f1:
                    best_f1 = dev_f1
                    patience_counter = 0
                    save_model(model, tokenizer, label_map, label_names)
                    print(f"    -> New best model saved! (F1-macro: {best_f1:.4f})")
                else:
                    patience_counter += 1
                    if patience_counter >= EARLY_STOPPING_PATIENCE:
                        print(
                            f"\n  Early stopping triggered at step {global_step} "
                            f"(patience={EARLY_STOPPING_PATIENCE})"
                        )
                        break

        if patience_counter >= EARLY_STOPPING_PATIENCE:
            break

        # Epoch 结束统计
        avg_epoch_loss = epoch_loss / max(num_batches, 1)
        print(f"Epoch {epoch+1}/{NUM_EPOCHS} complete, avg_loss={avg_epoch_loss:.4f}")

    elapsed_total = time.time() - start_time
    print(f"\nTraining complete in {elapsed_total:.1f}s")
    print(f"Best dev F1-macro: {best_f1:.4f}")

    # 最终测试集评估
    print("\n=== Test Set Evaluation ===")
    # 加载最优模型
    model = AutoModelForSequenceClassification.from_pretrained(str(OUTPUT_DIR))
    model.to(DEVICE)
    test_acc, test_f1, test_report = evaluate(model, test_loader, DEVICE, label_names)
    print(f"Test Accuracy: {test_acc:.4f}")
    print(f"Test F1-macro: {test_f1:.4f}")
    print(f"\n{test_report}")

    # Confusion matrix
    model.eval()
    all_preds, all_labels = [], []
    with torch.no_grad():
        for batch in test_loader:
            outputs = model(
                input_ids=batch["input_ids"].to(DEVICE),
                attention_mask=batch["attention_mask"].to(DEVICE),
            )
            preds = torch.argmax(outputs.logits, dim=-1)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(batch["labels"].numpy())

    cm = confusion_matrix(all_labels, all_preds)
    print("\nConfusion Matrix (rows=true, cols=pred):")
    header = "          " + "".join(f"{n[:8]:>10}" for n in label_names)
    print(header)
    for i, row in enumerate(cm):
        row_str = f"{label_names[i][:8]:>10}" + "".join(f"{v:>10}" for v in row)
        print(row_str)


def save_model(model, tokenizer, label_map: dict, label_names: list):
    """保存模型到 OUTPUT_DIR"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))
    with open(OUTPUT_DIR / "label_map.json", "w", encoding="utf-8") as f:
        json.dump(label_map, f, ensure_ascii=False, indent=2)
    with open(OUTPUT_DIR / "label_names.json", "w", encoding="utf-8") as f:
        json.dump(label_names, f, ensure_ascii=False)


if __name__ == "__main__":
    train()
