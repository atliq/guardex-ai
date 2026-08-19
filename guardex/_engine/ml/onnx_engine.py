# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""ONNX Runtime safety classifier.

Runs an encoder classifier exported to ONNX (optionally INT8-quantized)
instead of a generative model. Supports binary (safe/unsafe) and
multi-label (S1-S14) heads.

Usage::

    engine = OnnxSafetyEngine(
        model_path="models/safety-classifier.onnx",
        tokenizer_path="models/safety-classifier",
        label_map={0: "safe", 1: "S1", 2: "S2", ...},
    )
    result = engine.classify("...")
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class OnnxSafetyEngine:
    """ONNX Runtime inference engine for safety text classification.

    Parameters
    ----------
    model_path:
        Path to the ONNX model file (.onnx).
    tokenizer_path:
        Path to the HuggingFace tokenizer directory (or model name).
    label_map:
        Mapping from model output index to label string.
        Index 0 is typically "safe", index 1+ maps to category codes.
        Example: {0: "safe", 1: "unsafe"}
        Or multi-label: {0: "S1", 1: "S2", ..., 13: "S14"}
    category_map:
        Optional mapping from model label to GuardEx S-code.
        If None, labels are used as-is.
    max_length:
        Maximum token sequence length. Default 512.
    unsafe_threshold:
        Probability threshold above which a category is flagged. Default 0.5.
    num_threads:
        Number of intra-op threads for ONNX Runtime. Default 4.
    use_gpu:
        If True and CUDA is available, use GPU execution provider.
    """

    def __init__(
        self,
        model_path: str,
        tokenizer_path: str,
        label_map: dict[int, str] | None = None,
        category_map: dict[str, str] | None = None,
        max_length: int = 512,
        unsafe_threshold: float = 0.5,
        num_threads: int = 4,
        use_gpu: bool = False,
    ) -> None:
        import onnxruntime as ort
        from transformers import AutoTokenizer

        self._model_path = model_path
        self._max_length = max_length
        self._unsafe_threshold = unsafe_threshold
        self._category_map = category_map or {}

        # Default binary label map
        self._label_map = label_map or {0: "safe", 1: "unsafe"}

        # Load tokenizer
        logger.info("Loading tokenizer from '%s'...", tokenizer_path)
        self._tokenizer = AutoTokenizer.from_pretrained(
            tokenizer_path, use_fast=True,
        )

        # Configure ONNX Runtime session
        sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = num_threads
        sess_options.inter_op_num_threads = 1
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

        # Select execution provider
        if use_gpu:
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        else:
            providers = ["CPUExecutionProvider"]

        logger.info("Loading ONNX model from '%s' (providers=%s)...", model_path, providers)
        self._session = ort.InferenceSession(
            model_path,
            sess_options=sess_options,
            providers=providers,
        )

        # Discover input/output names
        self._input_names = [inp.name for inp in self._session.get_inputs()]
        self._output_names = [out.name for out in self._session.get_outputs()]
        logger.info(
            "ONNX model loaded. Inputs: %s, Outputs: %s",
            self._input_names, self._output_names,
        )

        # Detect model type from output shape
        output_shape = self._session.get_outputs()[0].shape
        self._num_labels = output_shape[-1] if len(output_shape) > 1 else 2
        self._is_binary = self._num_labels == 2

        logger.info(
            "Model type: %s (%d labels), threshold=%.2f",
            "binary" if self._is_binary else "multi-label",
            self._num_labels,
            self._unsafe_threshold,
        )

    def classify(
        self,
        text: str,
        stage: str = "input",
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run safety classification on text.

        Parameters
        ----------
        text:
            Text to classify.
        stage:
            'input' or 'output' - prepended as context to help the model.
        categories:
            Subset of categories to check. If None, all are checked.

        Returns
        -------
        dict with keys: safe (bool), category (str|None), categories (list[str])
        """
        prefixed_text = f"[{stage.upper()}] {text}"
        encoded = self._tokenizer(
            prefixed_text,
            max_length=self._max_length,
            truncation=True,
            padding="max_length",
            return_tensors="np",
        )

        # Build ONNX input feed
        feed = {}
        for name in self._input_names:
            if name == "input_ids":
                feed[name] = encoded["input_ids"].astype(np.int64)
            elif name == "attention_mask":
                feed[name] = encoded["attention_mask"].astype(np.int64)
            elif name == "token_type_ids" and "token_type_ids" in encoded:
                feed[name] = encoded["token_type_ids"].astype(np.int64)

        # Run inference
        outputs = self._session.run(self._output_names, feed)
        logits = outputs[0]  # shape: (1, num_labels)

        return self._parse_logits(logits[0], categories)

    def _parse_logits(
        self,
        logits: np.ndarray,
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        """Convert model logits to structured safety result.

        Handles both binary (safe vs unsafe) and multi-label (per-category) outputs.
        """
        if self._is_binary:
            return self._parse_binary(logits)
        else:
            return self._parse_multilabel(logits, categories)

    def _parse_binary(self, logits: np.ndarray) -> dict[str, Any]:
        """Binary classification: index 0 = safe, index 1 = unsafe."""
        probs = _softmax(logits)
        unsafe_prob = probs[1] if len(probs) > 1 else probs[0]

        if unsafe_prob < self._unsafe_threshold:
            return {
                "safe": True,
                "category": None,
                "categories": [],
                "confidence": float(1.0 - unsafe_prob),
            }

        # Binary model can't determine specific category - return generic unsafe
        return {
            "safe": False,
            "category": None,
            "categories": [],
            "confidence": float(unsafe_prob),
        }

    def _parse_multilabel(
        self,
        logits: np.ndarray,
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        """Multi-label classification: one output per category."""
        probs = _sigmoid(logits)

        flagged: list[tuple[str, float]] = []
        for idx, prob in enumerate(probs):
            if prob >= self._unsafe_threshold:
                label = self._label_map.get(idx)
                if label and label != "safe":
                    # Map to GuardEx S-code if mapping exists
                    category = self._category_map.get(label, label)
                    if categories is None or category in categories:
                        flagged.append((category, float(prob)))

        if not flagged:
            return {
                "safe": True,
                "category": None,
                "categories": [],
                "confidence": float(1.0 - max(probs, default=0.0)),
            }

        return {
            "safe": False,
            "category": flagged[0][0],
            "categories": [c for c, _ in flagged],
            "confidence": max(p for _, p in flagged),
        }

    @property
    def model_path(self) -> str:
        return self._model_path

    @property
    def num_labels(self) -> int:
        return self._num_labels


def _softmax(x: np.ndarray) -> np.ndarray:
    """Numerically stable softmax."""
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum()


def _sigmoid(x: np.ndarray) -> np.ndarray:
    """Element-wise sigmoid."""
    return 1.0 / (1.0 + np.exp(-x))


def quantize_model(
    input_path: str,
    output_path: str,
    quantization_type: str = "dynamic",
) -> str:
    """Quantize an ONNX model to INT8.

    Parameters
    ----------
    input_path:
        Path to the FP32 ONNX model.
    output_path:
        Path where the quantized model will be saved.
    quantization_type:
        'dynamic' (default, no calibration needed) or 'static' (needs calibration data).

    Returns
    -------
    Path to the quantized model.
    """
    from onnxruntime.quantization import quantize_dynamic, QuantType

    logger.info(
        "Quantizing model: %s -> %s (type=%s)",
        input_path, output_path, quantization_type,
    )

    if quantization_type == "dynamic":
        quantize_dynamic(
            model_input=input_path,
            model_output=output_path,
            weight_type=QuantType.QInt8,
        )
    else:
        raise ValueError(f"Unsupported quantization type: {quantization_type}")

    input_size = os.path.getsize(input_path) / (1024 * 1024)
    output_size = os.path.getsize(output_path) / (1024 * 1024)
    reduction = (1 - output_size / input_size) * 100

    logger.info(
        "Quantization complete: %.1fMB -> %.1fMB (%.1f%% reduction)",
        input_size, output_size, reduction,
    )
    return output_path


def export_model_to_onnx(
    model_name: str,
    output_dir: str,
    task: str = "text-classification",
    opset: int = 14,
    quantize: bool = True,
) -> dict[str, str]:
    """Export a HuggingFace model to ONNX format.

    Parameters
    ----------
    model_name:
        HuggingFace model name or path (e.g. 'distilbert-base-uncased').
    output_dir:
        Directory where ONNX model and tokenizer will be saved.
    task:
        ONNX export task. Default 'text-classification'.
    opset:
        ONNX opset version. Default 14.
    quantize:
        If True, also produce an INT8 quantized version.

    Returns
    -------
    dict with keys: 'model_path', 'tokenizer_path', and optionally 'quantized_path'.
    """
    from optimum.onnxruntime import ORTModelForSequenceClassification
    from transformers import AutoTokenizer

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info("Exporting '%s' to ONNX (task=%s, opset=%d)...", model_name, task, opset)

    # Export model
    model = ORTModelForSequenceClassification.from_pretrained(
        model_name, export=True,
    )
    model.save_pretrained(str(output_path))

    # Save tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.save_pretrained(str(output_path))

    model_file = str(output_path / "model.onnx")
    result = {
        "model_path": model_file,
        "tokenizer_path": str(output_path),
    }

    # Quantize if requested
    if quantize:
        quantized_file = str(output_path / "model_int8.onnx")
        quantize_model(model_file, quantized_file, "dynamic")
        result["quantized_path"] = quantized_file

    # Save label map if model has id2label config
    try:
        from transformers import AutoConfig
        config = AutoConfig.from_pretrained(model_name)
        if hasattr(config, "id2label"):
            label_map_path = output_path / "label_map.json"
            with open(label_map_path, "w") as f:
                json.dump(config.id2label, f, indent=2)
            result["label_map_path"] = str(label_map_path)
            logger.info("Saved label map: %s", config.id2label)
    except Exception as e:
        logger.warning("Could not extract label map: %s", e)

    logger.info("Export complete: %s", result)
    return result
