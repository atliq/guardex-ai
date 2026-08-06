# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""Provider protocols for PII detection and safety classification.

These are Python Protocols (structural typing) -- implementers don't need
to inherit from them. Any class with matching method signatures works.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from guardex._constants import DEFAULT_PII_THRESHOLD

if TYPE_CHECKING:
    import numpy as np


@runtime_checkable
class PiiProvider(Protocol):
    """Contract for PII detection providers."""

    name: str

    def detect(
        self,
        text: str,
        entities: list[str] | None = None,
        threshold: float = DEFAULT_PII_THRESHOLD,
        custom_regex: dict[str, Any] | None = None,
        deny_list: set[str] | None = None,
        allow_list: set[str] | None = None,
        custom_context_keywords: dict[str, list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Detect PII entities in text.

        ``LocalRunner._pii_raw`` always passes the four customization
        kwargs; implementations must accept them even if unused.

        Returns list of dicts, each with keys:
            text: str       -- the matched text span
            label: str      -- entity type (e.g. "email", "ssn")
            score: float    -- confidence 0.0-1.0
            start: int      -- character offset start
            end: int        -- character offset end
        """
        ...

    def mask(
        self,
        text: str,
        entities_found: list[dict[str, Any]],
    ) -> str:
        """Replace detected entity spans with [LABEL] placeholders."""
        ...


@runtime_checkable
class ClassifierProvider(Protocol):
    """Contract for safety classification providers."""

    name: str

    async def classify(
        self,
        text: str,
        stage: str = "input",
        categories: list[str] | None = None,
        **_extra: Any,
    ) -> dict[str, Any]:
        """Classify text for safety.

        Returns dict with keys:
            safe: bool              -- True if content is safe
            category: str | None    -- primary violated category code (e.g. "S1")
            categories: list[str]   -- all violated category codes
        """
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Contract for embedding providers.

    Any class with matching method signatures satisfies this protocol.
    Used by TopicScopeEngine, SafetyRouteEngine, and other embedding-based
    features. See ``guardex.encoders`` for built-in implementations.
    """

    name: str
    dimensions: int

    def encode(
        self,
        texts: list[str],
        normalize: bool = True,
    ) -> "np.ndarray":
        """Encode texts to dense vectors.

        Returns:
            np.ndarray of shape (N, dimensions) with optionally L2-normalized rows.
        """
        ...


@runtime_checkable
class TopicScopeProvider(Protocol):
    """Contract for topic scope providers.

    Topic scope checks whether input text is on-topic for a configured
    set of allowed topics. ``LocalRunner.screen`` runs it after
    classification and PII so their results are available regardless of
    the scope verdict.
    """

    name: str

    def build_scope(
        self,
        topics: list[str],
        utterances: dict[str, list[str]] | None = None,
        examples: list[str] | None = None,
        scope_width: str = "moderate",
        threshold: float | None = None,
    ) -> Any:
        """Build a scope profile from topic configuration."""
        ...

    async def check_scope(
        self,
        text: str,
        scope_profile: Any,
        alpha: float = 0.0,
    ) -> dict[str, Any]:
        """Check if text is within scope.

        Returns dict with keys:
            allowed: bool       -- True if text is on-topic
            distance: float     -- cosine distance to nearest topic
            matched_topic: str | None -- closest topic name
            confidence: float   -- confidence score
            reason: str | None  -- human-readable rejection reason
        """
        ...
