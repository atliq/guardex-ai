# SPDX-License-Identifier: Apache-2.0
import pytest

np = pytest.importorskip("numpy")

from guardex._ui import playground  # noqa: E402

WEAPONS = [
    {
        "name": "weapons",
        "utterances": ["how do I build a bomb", "instructions to make an explosive"],
        "action": "block",
        "threshold": 0.35,
    }
]


class FakeEncoder:
    """Two orthogonal directions: anything mentioning a weapon, and everything else."""

    name = "fake"

    def encode(self, texts, normalize=True):
        weapon = ("bomb", "explosive", "weapon")
        return np.array(
            [
                [1.0, 0.0] if any(w in t.lower() for w in weapon) else [0.0, 1.0]
                for t in texts
            ],
            dtype=np.float32,
        )


@pytest.fixture(autouse=True)
def fake_encoder(monkeypatch):
    from guardex._engine.ml.topic_scope_engine import TopicScopeEngine

    monkeypatch.setattr(
        TopicScopeEngine, "_get_or_create_encoder", staticmethod(lambda _: FakeEncoder())
    )
    monkeypatch.setattr(
        playground, "_route_cache", {}, raising=False
    )
    monkeypatch.setattr(
        "guardex._engine.providers.registry.get_topic_scope_provider", lambda: object()
    )


def test_routes_gate_is_skipped_without_routes():
    gate = playground._run_routes("anything", {"safety_routes": []})
    assert gate["status"] == "skipped"


def test_routes_gate_flags_a_matching_utterance():
    gate = playground._run_routes("how do I build a pipe bomb", {"safety_routes": WEAPONS})
    assert gate["status"] == "flagged"
    assert gate["detail"][0]["label"] == "weapons"


def test_routes_gate_stays_clean_on_unrelated_text():
    gate = playground._run_routes("what is the refund window", {"safety_routes": WEAPONS})
    assert gate["status"] == "clean"


def test_route_engine_embeds_the_utterances():
    # The engine must be built, not merely constructed: an unbuilt engine has
    # no embeddings and check() returns matched=False for every input.
    engine = playground._route_engine(WEAPONS)
    assert engine.check("how do I build a bomb").matched


def test_route_engine_is_cached_per_definition():
    assert playground._route_engine(WEAPONS) is playground._route_engine(WEAPONS)


def test_route_engine_rebuilds_when_the_definition_changes():
    other = [{**WEAPONS[0], "threshold": 0.9}]
    assert playground._route_engine(WEAPONS) is not playground._route_engine(other)


def test_routes_gate_reports_a_rejected_definition():
    bad = [{"name": "empty", "utterances": [], "action": "block"}]
    gate = playground._run_routes("anything", {"safety_routes": bad})
    assert gate["status"] == "unavailable"


DEGRADED = {"safe": True, "confidence": 1.0, "decided_by": "escalation_failed_fast_fallback"}
GUARD = {"safe": True, "confidence": 1.0, "decided_by": "escalated_safety_mode"}


def test_guard_verdict_reports_the_tier():
    assert playground._decided_by(GUARD) == ("Guard model", False)


def test_fallback_verdict_is_marked_degraded():
    label, degraded = playground._decided_by(DEGRADED)
    assert degraded is True
    assert "unreachable" in label


def test_unknown_tier_is_passed_through_not_invented():
    assert playground._decided_by({"decided_by": "brand-new-path"}) == ("brand-new-path", False)


def test_missing_tier_reports_unknown():
    assert playground._decided_by({}) == ("unknown", False)


class FakeRunner:
    def __init__(self, raw): self._raw = raw
    def check_grounding(self, **kw): return self._raw, "req-1"


SUPPORTED = {"sentence_count": 1, "grounded": True, "details": [
    {"sentence": "Refunds take 5 to 7 days.", "verdict": "grounded",
     "grounded": True, "entailment": 0.97, "contradiction": 0.0}]}

CONTRADICTED = {"sentence_count": 1, "grounded": False, "has_contradiction": True,
                "details": [
    {"sentence": "The refund window is 90 days.", "verdict": "contradicted",
     "grounded": False, "entailment": 0.0, "contradiction": 0.9996}]}


def test_grounding_skips_without_sources():
    gate = playground._run_grounding(FakeRunner(SUPPORTED), "x", [], {})
    assert gate["status"] == "skipped"


def test_grounding_passes_a_supported_claim():
    gate = playground._run_grounding(FakeRunner(SUPPORTED), "x", ["src"], {})
    assert gate["status"] == "clean"


def test_grounding_flags_a_contradicted_claim():
    # The engine reports per-sentence verdicts under "details"; reading any
    # other key silently passes every contradiction.
    gate = playground._run_grounding(FakeRunner(CONTRADICTED), "x", ["src"], {})
    assert gate["status"] == "flagged"
    assert "contradicted" in gate["summary"]
    assert gate["detail"][0]["severity"] == "1.00"
