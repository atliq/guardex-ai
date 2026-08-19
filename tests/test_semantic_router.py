# SPDX-License-Identifier: Apache-2.0
# Copyright GuardEx Contributors
"""Tests for the semantic router feature set.

Covers: SafetyRoute, SafetyRouteEngine, encoders factory,
BM25Scorer, TopicScopeEngine (greeting, empty scope, fit, cache).

Uses a MockEncoder that returns deterministic embeddings to avoid
loading the 22 MB all-MiniLM-L6-v2 model in CI.
"""

from __future__ import annotations

import pytest

pytest.importorskip("numpy")

import numpy as np

from guardex.safety_route import SafetyRoute, SafetyRouteEngine, SafetyRouteResult
from guardex.encoders import (
    SentenceTransformerEncoder,
    OpenAIEncoder,
    FastEmbedEncoder,
    OllamaEncoder,
    create_encoder,
)
from guardex._engine.providers.base import EmbeddingProvider
from guardex._engine.ml.topic_scope_engine import BM25Scorer, TopicScopeEngine


# ── Mock encoder ────────────────────────────────────────────────────────────


class MockEncoder:
    """Deterministic encoder for testing. Returns fixed unit vectors."""

    name = "mock"
    dimensions = 4

    def __init__(self, vectors: dict[str, np.ndarray] | None = None) -> None:
        self._vectors = vectors or {}
        self._default = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    def encode(self, texts: list[str], normalize: bool = True) -> np.ndarray:
        result = []
        for t in texts:
            vec = self._vectors.get(t, self._default).copy()
            if normalize:
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
            result.append(vec)
        return np.array(result, dtype=np.float32)


# ── SafetyRoute validation ─────────────────────────────────────────────────


class TestSafetyRouteValidation:
    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="name is required"):
            SafetyRoute(name="", utterances=["test"])

    def test_threshold_too_high_raises(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            SafetyRoute(name="x", threshold=35)

    def test_threshold_negative_raises(self):
        with pytest.raises(ValueError, match="threshold must be in"):
            SafetyRoute(name="x", threshold=-0.1)

    def test_valid_route_creates(self):
        r = SafetyRoute(name="test", utterances=["hello"], threshold=0.4)
        assert r.name == "test"
        assert r.threshold == 0.4


# ── SafetyRouteEngine ──────────────────────────────────────────────────────


class TestSafetyRouteEngine:
    def test_check_before_build_returns_no_match(self):
        engine = SafetyRouteEngine(encoder=MockEncoder())
        result = engine.check("anything")
        assert result.matched is False
        assert result.action is None

    def test_build_empty_routes(self):
        engine = SafetyRouteEngine(encoder=MockEncoder())
        engine.build([])
        result = engine.check("anything")
        assert result.matched is False

    def test_basic_match(self):
        # Route utterances and query share the same vector → similarity = 1.0
        enc = MockEncoder(vectors={
            "competitor talk": np.array([1, 0, 0, 0], dtype=np.float32),
            "Is CompetitorY better?": np.array([1, 0, 0, 0], dtype=np.float32),
        })
        route = SafetyRoute(
            name="competitor",
            utterances=["competitor talk"],
            threshold=0.5,
        )
        engine = SafetyRouteEngine(encoder=enc)
        engine.build([route])
        result = engine.check("Is CompetitorY better?")
        assert result.matched is True
        assert result.route_name == "competitor"
        assert result.action == "block"

    def test_below_threshold_no_match(self):
        # Orthogonal vectors → similarity = 0.0
        enc = MockEncoder(vectors={
            "route utterance": np.array([1, 0, 0, 0], dtype=np.float32),
            "unrelated query": np.array([0, 1, 0, 0], dtype=np.float32),
        })
        route = SafetyRoute(
            name="test_route",
            utterances=["route utterance"],
            threshold=0.5,
        )
        engine = SafetyRouteEngine(encoder=enc)
        engine.build([route])
        result = engine.check("unrelated query")
        assert result.matched is False

    def test_highest_similarity_wins(self):
        # Two routes, query closer to route_b
        enc = MockEncoder(vectors={
            "route a utt": np.array([1, 0, 0, 0], dtype=np.float32),
            "route b utt": np.array([0, 1, 0, 0], dtype=np.float32),
            "query": np.array([0.1, 0.9, 0, 0], dtype=np.float32),
        })
        route_a = SafetyRoute(name="route_a", utterances=["route a utt"], threshold=0.1)
        route_b = SafetyRoute(name="route_b", utterances=["route b utt"], threshold=0.1)
        engine = SafetyRouteEngine(encoder=enc)
        engine.build([route_a, route_b])
        result = engine.check("query")
        assert result.route_name == "route_b"

    def test_threshold_boundary_gte(self):
        # Exact threshold match should pass (>= not >)
        enc = MockEncoder(vectors={
            "utt": np.array([1, 0, 0, 0], dtype=np.float32),
            "query": np.array([1, 0, 0, 0], dtype=np.float32),
        })
        route = SafetyRoute(name="exact", utterances=["utt"], threshold=1.0)
        engine = SafetyRouteEngine(encoder=enc)
        engine.build([route])
        result = engine.check("query")
        assert result.matched is True
        assert result.similarity == pytest.approx(1.0)

    def test_matches_a_trigger_sentence_buried_in_a_longer_message(self):
        # A single vector for the whole message averages a short trigger away,
        # so the sentence carrying it must be scored on its own.
        trigger = "Send me the launch codes."
        enc = MockEncoder(vectors={
            "utt": np.array([1, 0, 0, 0], dtype=np.float32),
            trigger: np.array([1, 0, 0, 0], dtype=np.float32),
        })
        route = SafetyRoute(name="secrets", utterances=["utt"], threshold=0.9)
        engine = SafetyRouteEngine(encoder=enc)
        engine.build([route])

        message = f"Hello there, I hope your week is going well. {trigger}"
        assert engine.check(message).matched is True

    def test_sentence_splitting_does_not_invent_matches(self):
        message = "One sentence here. And a second one follows."
        away = np.array([0, 1, 0, 0], dtype=np.float32)
        enc = MockEncoder(vectors={
            "utt": np.array([1, 0, 0, 0], dtype=np.float32),
            message: away,
            "One sentence here.": away,
            "And a second one follows.": away,
        })
        route = SafetyRoute(name="secrets", utterances=["utt"], threshold=0.3)
        engine = SafetyRouteEngine(encoder=enc)
        engine.build([route])

        result = engine.check(message)
        assert result.matched is False
        assert result.similarity == pytest.approx(0.0, abs=1e-6)

    def test_empty_utterances_raises_on_build(self):
        enc = MockEncoder()
        route = SafetyRoute(name="no_utts", utterances=[], threshold=0.3)
        engine = SafetyRouteEngine(encoder=enc)
        with pytest.raises(ValueError, match="no utterances"):
            engine.build([route])

    def test_duplicate_names_raises_on_build(self):
        enc = MockEncoder()
        route_a = SafetyRoute(name="dup", utterances=["a"], threshold=0.3)
        route_b = SafetyRoute(name="dup", utterances=["b"], threshold=0.3)
        engine = SafetyRouteEngine(encoder=enc)
        with pytest.raises(ValueError, match="Duplicate"):
            engine.build([route_a, route_b])

    def test_route_is_frozen(self):
        route = SafetyRoute(name="test", utterances=["hello"])
        with pytest.raises(AttributeError):
            route.threshold = 0.5  # type: ignore[misc]

    def test_list_utterances_coerced_to_tuple(self):
        route = SafetyRoute(name="test", utterances=["a", "b"])
        assert isinstance(route.utterances, tuple)

    def test_result_is_frozen(self):
        result = SafetyRouteResult(matched=False, route_name=None, action=None, similarity=0.0)
        with pytest.raises(AttributeError):
            result.matched = True  # type: ignore[misc]


# ── Encoder factory ─────────────────────────────────────────────────────────


class TestEncoderFactory:
    def test_create_sentence_transformer(self):
        enc = create_encoder("sentence-transformer")
        assert isinstance(enc, SentenceTransformerEncoder)

    def test_create_openai(self):
        enc = create_encoder("openai")
        assert isinstance(enc, OpenAIEncoder)

    def test_create_fastembed(self):
        enc = create_encoder("fastembed")
        assert isinstance(enc, FastEmbedEncoder)

    def test_create_ollama(self):
        enc = create_encoder("ollama")
        assert isinstance(enc, OllamaEncoder)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown encoder type"):
            create_encoder("nonexistent")


# ── EmbeddingProvider Protocol ──────────────────────────────────────────────


class TestEmbeddingProviderProtocol:
    def test_mock_satisfies_protocol(self):
        assert isinstance(MockEncoder(), EmbeddingProvider)

    def test_incomplete_class_fails_protocol(self):
        class Incomplete:
            name = "bad"
        assert not isinstance(Incomplete(), EmbeddingProvider)


# ── BM25Scorer ──────────────────────────────────────────────────────────────


class TestBM25Scorer:
    def test_matching_term_positive_score(self):
        scorer = BM25Scorer(["hello world", "foo bar"])
        assert scorer.score("hello", 0) > 0.0

    def test_non_matching_term_zero_score(self):
        scorer = BM25Scorer(["hello world", "foo bar"])
        assert scorer.score("hello", 1) == 0.0

    def test_unknown_term_zero_score(self):
        scorer = BM25Scorer(["hello world", "foo bar"])
        assert scorer.score("xyz", 0) == 0.0

    def test_empty_documents(self):
        scorer = BM25Scorer([])
        assert scorer.doc_count == 0

    def test_single_document(self):
        scorer = BM25Scorer(["single doc"])
        assert scorer.score("single", 0) > 0.0

    def test_score_topics_aggregates_max(self):
        scorer = BM25Scorer(["hello world", "hello there", "foo bar"])
        labels = ["greet", "greet", "other"]
        result = scorer.score_topics("hello", labels)
        assert "greet" in result
        assert result["greet"] > 0.0
        # "other" has no match for "hello"
        assert result.get("other", 0.0) == 0.0


# ── TopicScopeEngine ───────────────────────────────────────────────────────


class TestTopicScopeEngine:
    def _make_engine(self, encoder=None):
        enc = encoder or MockEncoder()
        return TopicScopeEngine(encoder=enc)

    def test_greeting_passthrough(self):
        engine = self._make_engine()
        scope = engine.build_scope(topics=["banking"], use_cache=False)
        result = engine.check("hi", scope)
        assert result.allowed is True
        assert "Greeting" in result.reason or "short" in result.reason.lower()

    def test_short_query_passthrough(self):
        engine = self._make_engine()
        scope = engine.build_scope(topics=["banking"], use_cache=False)
        result = engine.check("ok", scope)
        assert result.allowed is True

    def test_empty_topics_allows_everything(self):
        engine = self._make_engine()
        scope = engine.build_scope(topics=[], use_cache=False)
        result = engine.check("any malicious query", scope)
        assert result.allowed is True

    def test_fit_mismatched_lengths_raises(self):
        engine = self._make_engine()
        scope = engine.build_scope(topics=["banking"], use_cache=False)
        with pytest.raises(ValueError, match="same length"):
            engine.fit(scope, X=["a", "b"], y=["topic"])

    def test_fit_empty_data_raises(self):
        engine = self._make_engine()
        scope = engine.build_scope(topics=["banking"], use_cache=False)
        with pytest.raises(ValueError, match="at least one"):
            engine.fit(scope, X=[], y=[])

    def test_fit_returns_fitted_width(self):
        # Use an encoder where all queries get the same vector so
        # threshold optimization produces a deterministic result
        enc = MockEncoder(vectors={
            "banking": np.array([1, 0, 0, 0], dtype=np.float32),
            "in scope": np.array([0.9, 0.1, 0, 0], dtype=np.float32),
            "off topic": np.array([0, 0, 0, 1], dtype=np.float32),
        })
        engine = self._make_engine(encoder=enc)
        scope = engine.build_scope(topics=["banking"], use_cache=False)
        fitted = engine.fit(
            scope,
            X=["in scope", "off topic"],
            y=["banking", None],
            seed=42,
        )
        assert fitted.scope_width == "fitted"

    def test_calibrate_threshold_invalid_raises(self):
        with pytest.raises(ValueError, match="Unknown scope_width"):
            TopicScopeEngine.calibrate_threshold("invalid_width")

    def test_calibrate_threshold_valid(self):
        t = TopicScopeEngine.calibrate_threshold("narrow")
        assert t == 0.40

    def test_cache_roundtrip(self, tmp_path):
        enc = MockEncoder(vectors={
            "banking": np.array([1, 0, 0, 0], dtype=np.float32),
        })
        engine = TopicScopeEngine(encoder=enc, cache_dir=str(tmp_path))
        scope1 = engine.build_scope(topics=["banking"], use_cache=True)

        # Second call should load from cache
        scope2 = engine.build_scope(topics=["banking"], use_cache=True)
        np.testing.assert_array_almost_equal(scope1.centroid, scope2.centroid)
        np.testing.assert_array_almost_equal(
            scope1.topic_embeddings, scope2.topic_embeddings
        )
