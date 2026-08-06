# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""GuardExPolicy - configuration for the GuardEx SDK."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, List, Literal

from guardex._constants import DEFAULT_PII_THRESHOLD

if TYPE_CHECKING:
    from guardex.safety_route import SafetyRoute


# LlamaGuard category constants

_DEFAULT_BLOCKED: List[str] = ["S1", "S3", "S4", "S9", "S11"]

ALL_CATEGORIES: List[str] = [
    "S1","S2","S3","S4","S5","S6","S7","S8","S9","S10","S11","S12","S13","S14"
]

DEFAULT_PII_ENTITIES: List[str] = [
    # Personal Info
    "email",
    "phone_number",
    "name",
    "address",
    "ssn",
    "national_id",
    "passport_number",
    "date_of_birth",
    "driver_license",
    # Credentials & Secrets
    "password",
    "user_name",
    "private_key",
    "jwt_token",
    "auth_header",
    "secret",
    # API Keys & Tokens
    "api_key",
    "aws_key",
    "github_token",
    "slack_token",
    "stripe_key",
    "google_api_key",
    "openai_key",
    "twilio_sid",
    # Financial
    "credit_card",
    "bank_account",
    "iban",
    # Network & Infrastructure
    "ip_address",
    "ipv6_address",
    "mac_address",
    "hostname",
    "database_url",
]

ALL_PII_ENTITIES: List[str] = list(DEFAULT_PII_ENTITIES)
"""Read-only copy of ``DEFAULT_PII_ENTITIES`` exported for external reference.
Contains all 31 built-in entity types the server can detect.
Prefer importing ``DEFAULT_PII_ENTITIES`` directly when constructing policies."""


# Short conversational tokens that should never be tagged as PII even when
# they happen to fall in GLiNER's 0.6-0.8 false-positive band. Real PII
# (email, SSN, credit card, phone) consistently scores >=0.95.
DEFAULT_PII_ALLOW_LIST: List[str] = [
    "hi", "hello", "hey", "ok", "okay", "yes", "no",
    "thanks", "thank you", "bye", "goodbye", "sure", "please",
    "yo", "sup", "hola", "howdy",
    "good morning", "good evening", "good night", "good afternoon",
]


# Topic scope restriction

@dataclass
class TopicScope:
    """Topic scope restriction configuration.

    Defines which topics the chatbot is allowed to discuss.
    Queries outside these topics will be blocked at the scope gate.

    Parameters
    ----------
    topics : list[str]
        Anchor descriptions defining the allowed scope.
        e.g., ["retail banking", "credit cards", "loan products"]
    utterances : dict[str, list[str]] | None
        Optional per-topic example phrases (semantic-router pattern).
        Much more precise than topics alone - captures the actual query
        distribution instead of a single label.
        e.g., {"banking": ["What's my balance?", "Transfer money"]}
    examples : list[str] | None
        Optional example queries that are in-scope. Improves accuracy.
        e.g., ["What's my account balance?", "How do I apply for a mortgage?"]
    scope_width : str
        How strictly to enforce scope. "narrow" | "moderate" | "broad" | "fitted"
        - narrow: only clearly on-topic queries pass
        - moderate: allows related queries (default)
        - broad: only clearly off-topic is blocked
        - fitted: threshold was optimized via fit()
    threshold : float | None
        Manual cosine similarity threshold override (0.0-1.0).
        If set, overrides scope_width preset.
    alpha : float
        Hybrid matching weight (0.0 = dense only, 1.0 = sparse only).
        Set to 0.3 for hybrid dense+BM25 matching. Only effective when
        utterances are provided (BM25 needs text corpus).
    encoder_type : str | None
        Encoder type for embedding. None = default (sentence-transformer).
        Options: "sentence-transformer", "openai", "fastembed", "ollama".
    encoder_config : dict | None
        Extra kwargs passed to encoder constructor (e.g., model, api_key).
    """

    topics: List[str] = field(default_factory=list)
    utterances: dict[str, List[str]] | None = None
    examples: List[str] | None = None
    scope_width: Literal["narrow", "moderate", "broad", "fitted"] = "moderate"
    threshold: float | None = None
    alpha: float = 0.0
    encoder_type: str | None = None
    encoder_config: dict | None = None


# Main policy

@dataclass
class GuardExPolicy:
    """All tuneable knobs for GuardEx SDK behaviour.

    Parameters
    ----------
    api_key:
        GuardEx API key. Falls back to ``GUARDEX_API_KEY`` env var.
    base_url:
        GuardEx API server URL. Falls back to ``GUARDEX_BASE_URL`` env var.
        Empty (the default when the env var is unset) selects in-process
        local mode; any non-empty value selects server mode.
    block_on_unsafe_input:
        Gates the **safety-classifier verdict only** for input gates
        (``input``, ``prompt``, ``tool_input``, ``retrieval_query``). When
        False, ``screen()`` still reports the unsafe classification, but the
        enforcement methods (``screen_or_raise``, ``GuardedLLM``, the callback
        handler) no longer raise on it - observe-only. Prompt injection, topic
        scope, safety routes, and ``pii_action="block"`` are independent
        controls and always enforce; disable them via ``injection_check=False``,
        ``policy.topic_scope = None``, and ``pii_action="mask"`` respectively.
    block_on_unsafe_output:
        Same rule as ``block_on_unsafe_input`` but for output gates
        (``output``, ``tool_output``, ``retrieval_result``).
    blocked_categories:
        LlamaGuard category codes that trigger a block. Granular per-category
        filtering requires LlamaGuard (via Ollama) or a multilabel classifier.
        The default local binary classifier only distinguishes safe/toxic, so a
        customized subset has no fine-grained effect in local "speed" mode.
    fail_open:
        When True, treat server errors as SAFE (log warning).
        When False, raise on any server failure.
        Note: 401/403/422 always raise regardless of this setting.
    pii_enabled:
        Enable PII detection.
    pii_entities:
        Entity labels to detect.
    pii_action:
        'mask' to replace PII with placeholders, 'block' to raise PIIViolation.
    pii_threshold:
        Confidence threshold for PII detection.
    cascade_mode:
        ``'safety'`` runs all checks fully; ``'speed'`` enables server-side fast path.
    audit_logging:
        When True, every screening decision is emitted as a structured log entry
        at INFO level and forwarded to the server for dashboard audit trails.
    detailed_logging:
        When True, full request/response payloads are logged at DEBUG level.
    classify_min_confidence:
        Minimum confidence required to treat a classification as valid.
        Set to e.g. ``0.7`` to auto-pass low-confidence unsafe classifications.
        Default ``0.0`` means trust the server classification unconditionally.
    grounding_mode:
        Override grounding check mode. ``None`` uses the server default.
        ``'speed'`` uses embedding similarity; ``'accuracy'`` uses NLI cross-encoder.
    grounding_threshold:
        Per-sentence grounded score threshold. ``None`` uses the server default.
    """

    api_key: str = field(
        default_factory=lambda: os.getenv("GUARDEX_API_KEY", "")
    )
    base_url: str = field(
        default_factory=lambda: os.getenv("GUARDEX_BASE_URL", "")
    )
    block_on_unsafe_input: bool = True
    block_on_unsafe_output: bool = True
    blocked_categories: List[str] = field(default_factory=lambda: list(_DEFAULT_BLOCKED))
    fail_open: bool = False
    timeout: int = 30

    # PII settings
    pii_enabled: bool = True
    pii_entities: List[str] = field(default_factory=lambda: list(DEFAULT_PII_ENTITIES))
    pii_action: Literal["mask", "block"] = "mask"
    pii_threshold: float = DEFAULT_PII_THRESHOLD

    # PII customization extends the built-in detector with project-scoped rules.
    pii_deny_list: List[str] = field(default_factory=list)
    """Exact strings always tagged as PII (score=1.0).  Use for known
    sensitive identifiers (account numbers, internal IDs)."""

    pii_allow_list: List[str] = field(
        default_factory=lambda: list(DEFAULT_PII_ALLOW_LIST)
    )
    """Strings suppressed from PII findings.  Default ships 21
    conversational tokens (hi, hello, ok, ...) that GLiNER may otherwise
    mis-classify as password/user_name in the 0.6-0.8 confidence band."""

    pii_custom_regex: dict[str, str] = field(default_factory=dict)
    """Extra label → regex pattern (case-insensitive) added to detection.
    Patterns compile once on first use."""

    pii_custom_context_keywords: dict[str, List[str]] = field(default_factory=dict)
    """Extra label → context keywords that boost confidence when one of
    the keywords appears near a candidate match."""

    # Topic scope restriction
    topic_scope: TopicScope | None = None

    # Cascade / operational mode
    cascade_mode: Literal["safety", "speed"] = "safety"
    """'safety' runs all checks; 'speed' takes the server-side fast path."""

    # Observability - both flags are forwarded to the server and used for SDK
    # logging, so they have real effect (not dead config).
    audit_logging: bool = False
    """When True, every screening decision is emitted as a structured log entry
    at INFO level and forwarded to the server for dashboard audit trails."""

    detailed_logging: bool = False
    """When True, full request/response payloads are logged at DEBUG level."""

    # Confidence threshold for false-positive tuning
    classify_min_confidence: float = 0.0
    """Minimum confidence required to treat a classification as valid.
    If the server returns ``confidence < classify_min_confidence``, the SDK
    overrides the result to safe.  Default 0.0 means trust the server.
    Set to e.g. 0.7 to auto-pass low-confidence unsafe classifications."""

    # User-defined safety routes (custom blocklist categories)
    safety_routes: List["SafetyRoute"] = field(default_factory=list)
    """Custom safety categories defined by example utterances.
    Each route blocks/flags/masks queries matching its utterance patterns.
    See ``guardex.safety_route.SafetyRoute`` for details."""

    # Grounding / hallucination detection
    grounding_mode: Literal["speed", "accuracy"] | None = None
    """Override grounding check mode. None = use server default."""

    grounding_threshold: float | None = None
    """Per-sentence grounded score threshold. None = use server default."""

    # Friendly user-facing messages per category code, attached to blocked
    # ScreenResults by Guard.  Override per-category to customise refusal copy.
    refusal_messages: dict[str, str] = field(default_factory=lambda: {
        "S1":  "I can't help with content that could lead to violence or harm.",
        "S3":  "I can't help with content involving sexual crimes.",
        "S4":  "I can't help with content involving the exploitation of minors.",
        "S9":  "I can't help with content involving weapons of mass destruction.",
        "S11": (
            "If you're struggling, please reach out to a mental-health "
            "professional or a crisis line - in the US, dial or text 988. "
            "You're not alone, and help is available."
        ),
        "injection": (
            "I can't help with that - it looks like an attempt to override "
            "my instructions."
        ),
        "scope":     "That question is outside the topics I can help with.",
        "pii":       "I can't process messages containing sensitive personal data.",
    })

    @property
    def scope_enabled(self) -> bool:
        """True when topic-scope checking will actually evaluate.

        ``policy.topic_scope is None`` and ``policy.topic_scope.topics == []``
        both produce False so callers can use a single check without
        ``AttributeError`` risk.
        """
        return self.topic_scope is not None and bool(self.topic_scope.topics)

    def __post_init__(self) -> None:
        # Bounds validation - all threshold fields must be in [0.0, 1.0] because
        # they are compared directly against model confidence scores.  Values
        # outside this range silently produce wrong gate decisions (always block
        # or always pass), which is worse than an immediate error at config time.
        if not (0.0 <= self.pii_threshold <= 1.0):
            raise ValueError(
                f"pii_threshold must be in [0.0, 1.0], got {self.pii_threshold}"
            )
        if not (0.0 <= self.classify_min_confidence <= 1.0):
            raise ValueError(
                f"classify_min_confidence must be in [0.0, 1.0], got {self.classify_min_confidence}"
            )
        if self.grounding_threshold is not None and not (
            0.0 <= self.grounding_threshold <= 1.0
        ):
            raise ValueError(
                f"grounding_threshold must be in [0.0, 1.0], got {self.grounding_threshold}"
            )

    @classmethod
    def from_yaml(cls, path: str) -> "GuardExPolicy":
        """Load policy from a YAML file. Requires PyYAML."""
        try:
            import yaml
        except ImportError as e:
            raise ImportError(
                "PyYAML is required for GuardExPolicy.from_yaml(). "
                "Install with: pip install 'guardex-ai[yaml]' (or: pip install pyyaml)"
            ) from e

        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        # Handle nested topic_scope config
        if "topic_scope" in data and isinstance(data["topic_scope"], dict):
            data["topic_scope"] = TopicScope(**data["topic_scope"])
        # Handle nested safety_routes config
        if "safety_routes" in data and isinstance(data["safety_routes"], list):
            from guardex.safety_route import SafetyRoute as _SR
            data["safety_routes"] = [
                _SR(**r) if isinstance(r, dict) else r
                for r in data["safety_routes"]
            ]
        # fields(cls), not hasattr(cls, k): default_factory fields have no
        # class attribute and would be dropped by a hasattr check.
        _valid = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in _valid}
        # Warn about unknown keys - typos in YAML are otherwise silently ignored,
        # leading the user to believe a setting is applied when it is not.
        unknown = set(data.keys()) - set(filtered.keys())
        if unknown:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "Unknown fields in policy YAML (ignored): %s", ", ".join(sorted(unknown))
            )
        # Validate Literal fields that could silently accept invalid values
        pii_action = filtered.get("pii_action")
        if pii_action is not None and pii_action not in ("mask", "block"):
            raise ValueError(
                f"Invalid pii_action '{pii_action}' in policy YAML. Must be 'mask' or 'block'."
            )
        cascade_mode = filtered.get("cascade_mode")
        if cascade_mode is not None and cascade_mode not in ("safety", "speed"):
            raise ValueError(
                f"Invalid cascade_mode '{cascade_mode}' in policy YAML. Must be 'safety' or 'speed'."
            )
        grounding_mode = filtered.get("grounding_mode")
        if grounding_mode is not None and grounding_mode not in ("speed", "accuracy"):
            raise ValueError(
                f"Invalid grounding_mode '{grounding_mode}' in policy YAML. Must be 'speed' or 'accuracy'."
            )
        # Coerce YAML boolean-like strings for all boolean fields.
        # PyYAML parses unquoted true/false correctly, but quoted "true" stays as
        # a string.  Coerce all boolean fields consistently so YAML authors do not
        # need to remember quoting rules.
        _bool_fields = (
            "fail_open", "pii_enabled", "block_on_unsafe_input",
            "block_on_unsafe_output", "audit_logging", "detailed_logging",
        )
        for _bf in _bool_fields:
            _val = filtered.get(_bf)
            if isinstance(_val, str):
                filtered[_bf] = _val.lower() in ("true", "yes", "1")
        return cls(**filtered)
