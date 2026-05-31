"""基于 Transformer 的意图分类器推理模块

用于替换 RuleEngine 中的关键词意图匹配。
加载微调后的模型，提供 predict() 接口。
"""

import json
import logging
from pathlib import Path
from typing import Optional

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

from config import get_app_dir

logger = logging.getLogger(__name__)

# 默认模型路径
DEFAULT_MODEL_PATH = "models/intent_classifier"


class IntentClassifier:
    """基于 Transformer 的意图分类器

    加载微调后的 chinese-roberta-wwm-ext 模型，
    对输入文本进行意图预测和置信度评分。

    用法：
        classifier = IntentClassifier()
        label, confidence = classifier.predict("明天下午三点开会")
        # -> ("add_event", 0.95)
    """

    def __init__(self, model_path: str = DEFAULT_MODEL_PATH, device: Optional[str] = None):
        """
        初始化意图分类器

        Args:
            model_path: 模型目录路径（含 config.json, model.safetensors 等）
            device: 指定设备 ("cuda"/"cpu")，None 则自动选择
        """
        self._model_path = Path(model_path)
        # 如果是相对路径且不存在，尝试基于应用根目录解析（支持打包模式）
        if not self._model_path.exists() and not self._model_path.is_absolute():
            self._model_path = get_app_dir() / model_path
        if not self._model_path.exists():
            raise FileNotFoundError(
                f"模型目录不存在: {model_path}。请先运行 scripts/train_intent_classifier.py 训练模型。"
            )

        # 自动选择设备
        if device is None:
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self._device = device

        logger.info(f"加载意图分类器: {model_path} (device={self._device})")

        # 加载 label_map
        label_map_path = self._model_path / "label_map.json"
        with open(label_map_path, "r", encoding="utf-8") as f:
            self._label_map = json.load(f)
        self._label_names = [k for k, v in sorted(self._label_map.items(), key=lambda x: x[1])]

        # 加载 tokenizer + model
        self._tokenizer = AutoTokenizer.from_pretrained(str(self._model_path))
        self._model = AutoModelForSequenceClassification.from_pretrained(str(self._model_path))
        self._model.to(self._device)
        self._model.eval()

        logger.info(f"意图分类器加载完成: {len(self._label_names)} 类别, device={self._device}")

    def predict(self, text: str, max_length: int = 48) -> tuple[str, float]:
        """预测文本意图

        Args:
            text: 输入文本
            max_length: 最大 token 长度

        Returns:
            (intent_label, confidence) 元组
            - intent_label: 预测的意图标签（如 "add_event"）
            - confidence: 置信度分数 (0.0~1.0)
        """
        text = text.strip()
        if not text:
            return "other", 0.0

        encoding = self._tokenizer(
            text,
            max_length=max_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        input_ids = encoding["input_ids"].to(self._device)
        attention_mask = encoding["attention_mask"].to(self._device)

        with torch.no_grad():
            outputs = self._model(input_ids=input_ids, attention_mask=attention_mask)
            probs = torch.softmax(outputs.logits, dim=-1)
            pred_idx = torch.argmax(probs, dim=-1).item()
            confidence = probs[0][pred_idx].item()

        label = self._label_names[pred_idx]
        return label, confidence

    def predict_batch(self, texts: list[str], max_length: int = 48) -> list[tuple[str, float]]:
        """批量预测（用于测试/评估）

        Args:
            texts: 文本列表
            max_length: 最大 token 长度

        Returns:
            [(intent_label, confidence), ...] 列表
        """
        results = []
        # 分批处理，每批 32 条
        batch_size = 32
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            encoding = self._tokenizer(
                batch_texts,
                max_length=max_length,
                padding="max_length",
                truncation=True,
                return_tensors="pt",
            )
            input_ids = encoding["input_ids"].to(self._device)
            attention_mask = encoding["attention_mask"].to(self._device)

            with torch.no_grad():
                outputs = self._model(input_ids=input_ids, attention_mask=attention_mask)
                probs = torch.softmax(outputs.logits, dim=-1)
                pred_indices = torch.argmax(probs, dim=-1)

            for j, pred_idx in enumerate(pred_indices):
                idx = pred_idx.item()
                conf = probs[j][idx].item()
                results.append((self._label_names[idx], conf))

        return results

    @property
    def label_names(self) -> list[str]:
        """支持的意图标签列表"""
        return list(self._label_names)

    @property
    def device(self) -> str:
        """当前使用的设备"""
        return self._device
