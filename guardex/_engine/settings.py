# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""Local mode settings - ML config only. No auth, no DB, no billing."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


def _get_package_version() -> str:
    """Single-source version lookup via guardex._version."""
    from guardex._version import get_package_version
    return get_package_version()


def _env(key: str, default: str) -> str:
    return os.environ.get(f"GUARDEX_{key.upper()}", default)


def _env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(f"GUARDEX_{key.upper()}")
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes")


def _env_float(key: str, default: float) -> float:
    val = os.environ.get(f"GUARDEX_{key.upper()}")
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        logger.warning(
            "GUARDEX_%s=%r is not a valid float; using default %.3g", key.upper(), val, default
        )
        return default


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(f"GUARDEX_{key.upper()}")
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        logger.warning(
            "GUARDEX_%s=%r is not a valid int; using default %d", key.upper(), val, default
        )
        return default


def _env_choice(key: str, default: str, choices: tuple[str, ...]) -> str:
    val = os.environ.get(f"GUARDEX_{key.upper()}")
    if val is None:
        return default
    normalized = val.strip().lower()
    if normalized in choices:
        return normalized
    logger.warning(
        "GUARDEX_%s=%r is not one of %s; using %r",
        key.upper(), val, "/".join(choices), default,
    )
    return default


@dataclass
class LocalSettings:
    # LlamaGuard via Ollama (optional)
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "llama-guard3:1b"))
    classifier_timeout: int = field(default_factory=lambda: _env_int("CLASSIFIER_TIMEOUT", 10))
    fail_open: bool = field(default_factory=lambda: _env_bool("FAIL_OPEN", False))

    # ONNX classifier
    onnx_classifier_enabled: bool = field(default_factory=lambda: _env_bool("ONNX_CLASSIFIER_ENABLED", True))
    onnx_model_path: str = field(default_factory=lambda: _env("ONNX_MODEL_PATH", ""))
    onnx_tokenizer_path: str = field(default_factory=lambda: _env("ONNX_TOKENIZER_PATH", ""))
    onnx_hf_repo: str = field(default_factory=lambda: _env("ONNX_HF_REPO", "AtliQ-Technologies/toxicity-fast-onnx"))
    onnx_use_int8: bool = field(default_factory=lambda: _env_bool("ONNX_USE_INT8", True))
    onnx_max_length: int = field(default_factory=lambda: _env_int("ONNX_MAX_LENGTH", 128))
    onnx_unsafe_threshold: float = field(default_factory=lambda: _env_float("ONNX_UNSAFE_THRESHOLD", 0.5))
    onnx_num_threads: int = field(default_factory=lambda: _env_int("ONNX_NUM_THREADS", 4))
    onnx_use_gpu: bool = field(default_factory=lambda: _env_bool("ONNX_USE_GPU", False))

    # Cascade
    cascade_enabled: bool = field(default_factory=lambda: _env_bool("CASCADE_ENABLED", True))
    cascade_safe_threshold: float = field(default_factory=lambda: _env_float("CASCADE_SAFE_THRESHOLD", 0.15))
    cascade_unsafe_threshold: float = field(default_factory=lambda: _env_float("CASCADE_UNSAFE_THRESHOLD", 0.85))
    # Invalid values fall back to "safety" (the stricter mode), never "speed".
    cascade_mode: Literal["safety", "speed"] = field(
        default_factory=lambda: _env_choice("CASCADE_MODE", "safety", ("safety", "speed"))
    )  # type: ignore[assignment]

    # PII
    gliner_model: str = field(default_factory=lambda: _env("GLINER_MODEL", "nvidia/gliner-pii"))
    gliner_max_concurrency: int = field(default_factory=lambda: _env_int("GLINER_MAX_CONCURRENCY", 4))

    # Text hardening
    text_normalization_enabled: bool = field(default_factory=lambda: _env_bool("TEXT_NORMALIZATION_ENABLED", True))
    keyword_gate_enabled: bool = field(default_factory=lambda: _env_bool("KEYWORD_GATE_ENABLED", True))
    max_input_chars: int = field(default_factory=lambda: _env_int("MAX_INPUT_CHARS", 32768))
    max_repetition_ratio: float = field(default_factory=lambda: _env_float("MAX_REPETITION_RATIO", 0.3))
    max_char_repeat: int = field(default_factory=lambda: _env_int("MAX_CHAR_REPEAT", 20))
    safety_logging_enabled: bool = field(default_factory=lambda: _env_bool("SAFETY_LOGGING_ENABLED", True))

    # Topic scope
    topic_scope_enabled: bool = field(default_factory=lambda: _env_bool("TOPIC_SCOPE_ENABLED", True))
    topic_scope_model: str = field(default_factory=lambda: _env("TOPIC_SCOPE_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    topic_scope_default_width: str = field(default_factory=lambda: _env("TOPIC_SCOPE_DEFAULT_WIDTH", "moderate"))

    # Grounding (off by default - the NLI cross-encoder is ~700 MB.
    # Enable via GUARDEX_GROUNDING_ENABLED=1 or in guardex.yaml when needed.)
    grounding_enabled: bool = field(default_factory=lambda: _env_bool("GROUNDING_ENABLED", False))
    grounding_nli_model: str = field(default_factory=lambda: _env("GROUNDING_NLI_MODEL", "cross-encoder/nli-deberta-v3-base"))
    grounding_default_mode: str = field(default_factory=lambda: _env("GROUNDING_DEFAULT_MODE", "accuracy"))
    grounding_threshold: float = field(default_factory=lambda: _env_float("GROUNDING_THRESHOLD", 0.55))
    grounding_overall_threshold: float = field(default_factory=lambda: _env_float("GROUNDING_OVERALL_THRESHOLD", 0.50))
    grounding_hybrid_neutral_threshold: float = field(default_factory=lambda: _env_float("GROUNDING_HYBRID_NEUTRAL_THRESHOLD", 0.65))

    # Cache
    cache_dir: str = field(default_factory=lambda: _env("CACHE_DIR", str(Path.home() / ".cache" / "guardex")))

    # App info (used by ML code)
    version: str = field(default_factory=lambda: _get_package_version())
    debug: bool = field(default_factory=lambda: _env_bool("DEBUG", False))


def load_local_settings() -> LocalSettings:
    """Load settings, optionally merging guardex.yaml from CWD."""
    settings = LocalSettings()
    _maybe_load_yaml(settings)
    return settings


def _maybe_load_yaml(settings: LocalSettings) -> None:
    """Merge guardex.yaml into settings if present in CWD. Silent if missing.

    A yaml value applies only when the corresponding ``GUARDEX_*`` env var
    is unset - env vars take precedence over the file.
    """
    yaml_path = Path("guardex.yaml")
    if not yaml_path.exists():
        return

    def _apply(env_key: str, attr: str, value: object) -> None:
        if f"GUARDEX_{env_key}" not in os.environ:
            setattr(settings, attr, value)

    try:
        import yaml  # optional dep, graceful skip
        with open(yaml_path) as f:
            data = yaml.safe_load(f) or {}
        models = data.get("models", {})
        if "classifier" in models:
            _apply("ONNX_HF_REPO", "onnx_hf_repo", models["classifier"])
        if "pii" in models:
            _apply("GLINER_MODEL", "gliner_model", models["pii"])
        if "embeddings" in models:
            _apply("TOPIC_SCOPE_MODEL", "topic_scope_model", models["embeddings"])
        if "ollama_url" in models:
            _apply("OLLAMA_URL", "ollama_url", models["ollama_url"])
        if "ollama_model" in models:
            _apply("OLLAMA_MODEL", "ollama_model", models["ollama_model"])
        grounding = data.get("grounding", {})
        if "enabled" in grounding:
            _apply("GROUNDING_ENABLED", "grounding_enabled", bool(grounding["enabled"]))
        if "model" in grounding:
            _apply("GROUNDING_NLI_MODEL", "grounding_nli_model", grounding["model"])
        if "mode" in grounding:
            _apply("GROUNDING_DEFAULT_MODE", "grounding_default_mode", grounding["mode"])
        policy = data.get("policy", {})
        if "fail_open" in policy:
            _apply("FAIL_OPEN", "fail_open", bool(policy["fail_open"]))
        if "cache_dir" in data:
            _apply("CACHE_DIR", "cache_dir", data["cache_dir"])
    except ImportError:
        pass  # PyYAML not installed - yaml config unavailable, using defaults
    except Exception as exc:
        logger.warning(
            "Failed to load guardex.yaml config (using defaults): %s", exc
        )


# Module-level singleton - imported as `settings` by ML code
local_settings: LocalSettings = load_local_settings()
