# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""User-defined safety routes for custom blocklist categories.

Each route has example utterances and an action ("block" or "flag").
Matching is cosine similarity against the example embeddings - the
inverse of TopicScope (allowlist vs. blocklist).

The engine takes any EmbeddingProvider. Share the same encoder with
TopicScopeEngine to avoid loading the model twice.

Usage::

    from guardex import SafetyRoute, SafetyRouteEngine, SafetyRouteResult
    from guardex import SentenceTransformerEncoder

    routes = [
        SafetyRoute(
            name="competitor_mentions",
            utterances=["What about ProductX?", "Is CompetitorY better?",
                        "Compare with RivalZ", "Switch to AlternativeW"],
            action="block",
            threshold=0.35,
            description="Block mentions of competitor products",
        ),
        SafetyRoute(
            name="insider_trading",
            utterances=["Buy stock before announcement", "Non-public earnings info",
                        "Trade on material information", "Insider knowledge"],
            action="flag",
            threshold=0.40,
            description="Flag potential insider trading language",
        ),
    ]

    engine = SafetyRouteEngine(encoder=SentenceTransformerEncoder())
    engine.build(routes)
    result = engine.check("Is CompetitorY better than us?")
    # SafetyRouteResult(matched=True, route_name="competitor_mentions", ...)
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SafetyRoute:
    """A user-defined safety category with utterance-based detection.

    Parameters
    ----------
    name : str
        Unique identifier for this route (e.g., "competitor_mentions").
    utterances : list[str]
        Example phrases that should trigger this route.
        More utterances = better coverage of the semantic space.
    action : str
        What to do when matched: "block" or "flag".
    threshold : float
        Cosine similarity threshold for matching (0.0-1.0).
        Lower = more sensitive, higher = more specific.
        Default 0.35 is calibrated for all-MiniLM-L6-v2. If using a
        different encoder, calibrate this value empirically.
    description : str
        Human-readable description of what this route catches.
    metadata : dict
        Arbitrary metadata (e.g., compliance tags, severity levels).
    """

    name: str = ""
    utterances: tuple[str, ...] = ()
    action: Literal["block", "flag"] = "block"
    threshold: float = 0.35
    description: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Coerce list→tuple for YAML/dict construction compatibility
        if isinstance(self.utterances, list):
            object.__setattr__(self, "utterances", tuple(self.utterances))
        if not self.name:
            raise ValueError("SafetyRoute.name is required and cannot be empty.")
        if not (0.0 <= self.threshold <= 1.0):
            raise ValueError(
                f"SafetyRoute.threshold must be in [0.0, 1.0], got {self.threshold}"
            )


@dataclass(frozen=True)
class SafetyRouteResult:
    """Result of checking text against safety routes.

    Attributes:
        matched: True if any route was triggered.
        route_name: Name of the matched route, or None.
        action: Action to take ("block" or "flag"), or None.
        similarity: Cosine similarity to closest utterance in matched route.
        description: Human-readable description of matched route.
    """

    matched: bool
    route_name: str | None
    action: Literal["block", "flag"] | None
    similarity: float
    description: str = ""


def _segments(query: str) -> list[str]:
    """The whole query plus each of its sentences, deduplicated in order."""
    from guardex._engine.ml.grounding.splitter import split_sentences

    out = [query]
    for sentence in split_sentences(query):
        if sentence not in out:
            out.append(sentence)
    return out


class SafetyRouteEngine:
    """Matches queries against user-defined safety routes.

    Uses an EmbeddingProvider to encode route utterances at build time
    and query text at check time. Matching is based on cosine similarity
    between the query vector and the closest utterance vector per route.
    """

    def __init__(self, encoder: Any | None = None) -> None:
        """Initialize the engine.

        Args:
            encoder: An EmbeddingProvider instance. If None, a default
                     SentenceTransformerEncoder is created lazily.
        """
        self._encoder = encoder
        self._routes: list[SafetyRoute] = []
        self._route_embeddings: dict[str, np.ndarray] = {}
        self._lock = threading.Lock()

    def _get_encoder(self) -> Any:
        if self._encoder is not None:
            return self._encoder
        with self._lock:
            if self._encoder is not None:
                return self._encoder
            from guardex.encoders import SentenceTransformerEncoder
            self._encoder = SentenceTransformerEncoder()
            return self._encoder

    def build(self, routes: list[SafetyRoute]) -> None:
        """Pre-compute embeddings for all route utterances.

        Args:
            routes: List of SafetyRoute definitions.
        """
        encoder = self._get_encoder()
        new_embeddings: dict[str, np.ndarray] = {}

        if not routes:
            with self._lock:
                self._routes = []
                self._route_embeddings = {}
            return

        t0 = time.perf_counter()

        # Validate all routes before encoding (fail fast)
        seen_names: set[str] = set()
        for route in routes:
            if not route.utterances:
                raise ValueError(
                    f"SafetyRoute '{route.name}' has no utterances. "
                    "At least one utterance is required for matching."
                )
            if route.name in seen_names:
                raise ValueError(
                    f"Duplicate SafetyRoute name '{route.name}'. "
                    "Each route must have a unique name."
                )
            seen_names.add(route.name)

        # Batch all utterances into one encode call for GPU/API efficiency
        all_utterances: list[str] = []
        offsets: list[tuple[str, int, int]] = []  # (name, start, end)
        for route in routes:
            start = len(all_utterances)
            all_utterances.extend(route.utterances)
            offsets.append((route.name, start, len(all_utterances)))

        all_embeddings = encoder.encode(all_utterances, normalize=True)
        for name, start, end in offsets:
            new_embeddings[name] = all_embeddings[start:end]

        # Atomic swap under lock so check() never sees partial state
        with self._lock:
            self._routes = list(routes)
            self._route_embeddings = new_embeddings

        elapsed = (time.perf_counter() - t0) * 1000
        total_utterances = sum(len(r.utterances) for r in routes)
        logger.info(
            "Safety routes built: %d routes, %d utterances (%.1f ms)",
            len(routes),
            total_utterances,
            elapsed,
        )

    def check(self, query: str) -> SafetyRouteResult:
        """Check if a query matches any safety route.

        Args:
            query: The user's input text.

        Returns:
            SafetyRouteResult with match details.
        """
        # Snapshot under lock so we iterate a consistent state
        with self._lock:
            routes = self._routes
            route_embeddings = self._route_embeddings

        if not route_embeddings:
            return SafetyRouteResult(
                matched=False,
                route_name=None,
                action=None,
                similarity=0.0,
            )

        encoder = self._get_encoder()
        # One vector for a long message averages a short trigger phrase away,
        # so each sentence is scored on its own alongside the whole text.
        query_vecs = np.asarray(encoder.encode(_segments(query), normalize=True))

        best_match: SafetyRoute | None = None
        best_similarity = 0.0
        best_raw_similarity = 0.0  # Track closest match even below threshold

        for route in routes:
            embeddings = route_embeddings.get(route.name)
            if embeddings is None:
                continue
            # Max similarity between any utterance and any segment
            similarities = embeddings @ query_vecs.T
            max_sim = float(np.max(similarities))
            if max_sim > best_raw_similarity:
                best_raw_similarity = max_sim
            if max_sim >= route.threshold and max_sim > best_similarity:
                best_similarity = max_sim
                best_match = route

        if best_match is not None:
            return SafetyRouteResult(
                matched=True,
                route_name=best_match.name,
                action=best_match.action,
                similarity=best_similarity,
                description=best_match.description,
            )

        return SafetyRouteResult(
            matched=False,
            route_name=None,
            action=None,
            similarity=best_raw_similarity,
        )
