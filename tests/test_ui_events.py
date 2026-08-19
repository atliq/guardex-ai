# SPDX-License-Identifier: Apache-2.0
from guardex._ui.events import EventRecorder

RESULT = {
    "classify": {"safe": False, "category": "S1", "confidence": 0.93},
    "pii": {"has_pii": True, "entities": [{"label": "EMAIL"}, {"label": "SSN"}]},
    "text": "masked",
    "_diagnostics": [
        {"gate": "keyword", "ran": True, "duration_ms": 0.4, "blocked": False},
        {"gate": "classify", "ran": True, "duration_ms": 31.2, "blocked": True},
        {"gate": "pii", "ran": True, "duration_ms": 12.0, "blocked": False},
        {"gate": "scope", "ran": False, "skipped_reason": "no scope_topics in policy"},
    ],
}


def test_record_extracts_verdict_fields():
    rec = EventRecorder()
    rec.record(stage="input", result=RESULT, latency_ms=44.0, request_id="r1", text="raw")
    (event,) = rec.recent()
    assert event["stage"] == "input"
    assert event["safe"] is False
    assert event["category"] == "S1"
    assert event["action"] == "block"
    assert event["pii_count"] == 2
    assert event["pii_labels"] == ["EMAIL", "SSN"]
    assert event["latency_ms"] == 44.0
    assert event["request_id"] == "r1"


def test_text_is_not_stored_by_default():
    rec = EventRecorder()
    rec.record(stage="input", result=RESULT, latency_ms=1.0, request_id=None, text="secret")
    assert rec.recent()[0]["text"] is None


def test_text_is_stored_when_opted_in():
    rec = EventRecorder(store_text=True)
    rec.record(stage="input", result=RESULT, latency_ms=1.0, request_id=None, text="secret")
    assert rec.recent()[0]["text"] == "secret"


def test_action_is_mask_when_pii_found_and_content_safe():
    result = {**RESULT, "classify": {"safe": True, "category": None, "confidence": 1.0}}
    rec = EventRecorder()
    rec.record(stage="input", result=result, latency_ms=1.0, request_id=None, text=None)
    assert rec.recent()[0]["action"] == "mask"


def test_action_is_pass_when_clean():
    result = {
        "classify": {"safe": True, "category": None, "confidence": 1.0},
        "pii": {"has_pii": False, "entities": []},
        "_diagnostics": [],
    }
    rec = EventRecorder()
    rec.record(stage="output", result=result, latency_ms=1.0, request_id=None, text=None)
    assert rec.recent()[0]["action"] == "pass"


def test_gate_timings_are_flattened():
    rec = EventRecorder()
    rec.record(stage="input", result=RESULT, latency_ms=44.0, request_id=None, text=None)
    gates = rec.recent()[0]["gates"]
    assert gates["classify"] == 31.2
    assert "scope" not in gates


def test_ring_buffer_evicts_oldest():
    rec = EventRecorder(maxlen=3)
    for _ in range(5):
        rec.record(stage="input", result=RESULT, latency_ms=1.0, request_id=None, text=None)
    assert len(rec.recent(limit=100)) == 3


def test_recent_returns_newest_first():
    rec = EventRecorder()
    rec.record(stage="input", result=RESULT, latency_ms=1.0, request_id="old", text=None)
    rec.record(stage="input", result=RESULT, latency_ms=1.0, request_id="new", text=None)
    assert rec.recent()[0]["request_id"] == "new"


def test_stats_aggregates_counts_and_latency():
    rec = EventRecorder()
    safe = {
        "classify": {"safe": True, "category": None},
        "pii": {"has_pii": False, "entities": []},
        "_diagnostics": [],
    }
    rec.record(stage="input", result=RESULT, latency_ms=40.0, request_id=None, text=None)
    rec.record(stage="input", result=safe, latency_ms=20.0, request_id=None, text=None)
    stats = rec.stats()
    assert stats["total"] == 2
    assert stats["blocked"] == 1
    assert stats["passed"] == 1
    assert stats["pii_total"] == 1
    assert stats["avg_latency_ms"] == 30.0
    assert stats["categories"] == {"S1": 1}


def _gates(**status):
    return [
        {"name": n, "status": status.get(n, "clean")}
        for n in ["injection", "safety", "pii", "scope", "routes", "grounding"]
    ]


CLEAN_RESULT = {
    "classify": {"safe": True, "category": None},
    "pii": {"has_pii": False, "entities": []},
    "_diagnostics": [],
}


def test_injection_catch_is_not_logged_as_pass():
    rec = EventRecorder()
    rec.record(
        stage="input",
        result=CLEAN_RESULT,
        latency_ms=1.0,
        gate_results=_gates(injection="flagged"),
    )
    event = rec.recent()[0]
    assert event["action"] == "block"
    assert event["flagged"] == ["injection"]


def test_scope_and_routes_also_block():
    for gate in ("scope", "routes"):
        rec = EventRecorder()
        rec.record(
            stage="input",
            result=CLEAN_RESULT,
            latency_ms=1.0,
            gate_results=_gates(**{gate: "flagged"}),
        )
        assert rec.recent()[0]["action"] == "block", gate


def test_grounding_flags_rather_than_blocks():
    rec = EventRecorder()
    rec.record(
        stage="output",
        result=CLEAN_RESULT,
        latency_ms=1.0,
        gate_results=_gates(grounding="flagged"),
    )
    assert rec.recent()[0]["action"] == "flag"


def test_pii_alone_masks():
    rec = EventRecorder()
    rec.record(
        stage="input",
        result=CLEAN_RESULT,
        latency_ms=1.0,
        gate_results=_gates(pii="flagged"),
    )
    assert rec.recent()[0]["action"] == "mask"


def test_all_clean_gates_pass():
    rec = EventRecorder()
    rec.record(stage="input", result=CLEAN_RESULT, latency_ms=1.0, gate_results=_gates())
    event = rec.recent()[0]
    assert event["action"] == "pass"
    assert event["flagged"] == []


def test_plain_screen_path_keeps_the_old_derivation():
    rec = EventRecorder()
    rec.record(stage="input", result=RESULT, latency_ms=1.0)
    event = rec.recent()[0]
    assert event["action"] == "block"
    assert event["flagged"] == []


def test_stats_counts_caught_across_actions():
    rec = EventRecorder()
    rec.record(
        stage="input", result=CLEAN_RESULT, latency_ms=1.0,
        gate_results=_gates(injection="flagged"),
    )
    rec.record(
        stage="input", result=CLEAN_RESULT, latency_ms=1.0,
        gate_results=_gates(grounding="flagged"),
    )
    rec.record(stage="input", result=CLEAN_RESULT, latency_ms=1.0, gate_results=_gates())
    stats = rec.stats()
    assert stats["blocked"] == 1
    assert stats["flagged"] == 1
    assert stats["passed"] == 1
    assert stats["caught"] == 2


def test_clear_empties_the_buffer():
    rec = EventRecorder()
    rec.record(stage="input", result=RESULT, latency_ms=1.0, request_id=None, text=None)
    rec.clear()
    assert rec.recent() == []
    assert rec.stats()["total"] == 0
