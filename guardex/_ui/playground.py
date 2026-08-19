# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""Composes every screening layer into one call for the Playground view.

The public ``/v1`` protocol stays frozen: this runs alongside it and reuses
the same LocalRunner, so nothing here changes what SDK callers see.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

from guardex._ui.state import ServerDefaults

GATE_ORDER = ["injection", "safety", "pii", "scope", "routes", "grounding"]

# Cascade tier that produced the safety verdict. The fallback paths answer with
# the fast model's opinion, which otherwise reads identically to a guard verdict.
DECIDED_BY = {
    "input_validation": ("Input validation", False),
    "keyword_gate": ("Keyword rule", False),
    "fast_unsafe": ("Toxicity model", False),
    "fast_safe": ("Toxicity model", False),
    "escalated_safety_mode": ("Guard model", False),
    "escalated_uncertain": ("Guard model", False),
    "fast_error": ("Guard model", False),
    "escalation_failed_fast_fallback": ("Toxicity model, guard unreachable", True),
    "escalation_skipped_breaker": ("Toxicity model, guard circuit open", True),
    "escalation_failed": ("No tier answered, guard unreachable", True),
}


def _decided_by(classify: Dict[str, Any]) -> tuple[str, bool]:
    """Return (label, degraded) for the tier behind a safety verdict."""
    path = classify.get("decided_by") or ""
    return DECIDED_BY.get(path, (path or "unknown", False))


def _gate(
    name: str,
    status: str,
    summary: str,
    duration_ms: float = 0.0,
    detail: Optional[List[Dict[str, Any]]] = None,
    note: str = "",
) -> Dict[str, Any]:
    """status: flagged | clean | degraded | skipped | unavailable."""
    return {
        "name": name,
        "status": status,
        "summary": summary,
        "duration_ms": round(duration_ms, 2),
        "detail": detail or [],
        "note": note,
    }


def _run_injection(text: str) -> Dict[str, Any]:
    from guardex.injection import InjectionDetector

    started = time.perf_counter()
    result = InjectionDetector().scan(text)
    elapsed = (time.perf_counter() - started) * 1000

    if not result.detected:
        return _gate("injection", "clean", "No injection patterns", elapsed)
    return _gate(
        "injection",
        "flagged",
        f"{len(result.matches)} pattern(s) matched",
        elapsed,
        [
            {
                "label": m.pattern_label,
                "severity": m.severity,
                "text": m.matched_text,
            }
            for m in result.matches
        ],
    )


_route_cache: Dict[str, Any] = {}
_route_cache_lock = threading.Lock()


def _route_engine(routes: List[Dict[str, Any]]) -> Any:
    """Return an engine with the routes' utterances already embedded.

    build() runs the encoder over every utterance, so it is cached against
    the route definitions rather than repeated on each screening call.
    """
    key = json.dumps(routes, sort_keys=True, default=str)
    with _route_cache_lock:
        cached = _route_cache.get(key)
    if cached is not None:
        return cached

    from guardex._engine.ml.topic_scope_engine import TopicScopeEngine
    from guardex._engine.settings import local_settings
    from guardex.safety_route import SafetyRoute, SafetyRouteEngine

    # Same model name the scope engine loaded with, so this hits its encoder
    # cache instead of pulling a second copy of the weights.
    encoder = TopicScopeEngine._get_or_create_encoder(local_settings.topic_scope_model)
    engine = SafetyRouteEngine(encoder)
    engine.build(
        [
            SafetyRoute(
                name=r.get("name", ""),
                utterances=tuple(r.get("utterances") or ()),
                action=r.get("action", "block"),
                threshold=float(r.get("threshold", 0.35)),
            )
            for r in routes
        ]
    )
    with _route_cache_lock:
        _route_cache[key] = engine
    return engine


def _run_routes(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    routes = config.get("safety_routes") or []
    if not routes:
        return _gate(
            "routes",
            "skipped",
            "No custom routes defined",
            note="Add routes in Config to block your own categories",
        )

    from guardex._engine.providers.registry import get_topic_scope_provider

    if get_topic_scope_provider() is None:
        return _gate(
            "routes",
            "unavailable",
            "Embedding model not loaded",
            note="pip install 'guardex-ai[scope]'",
        )

    started = time.perf_counter()
    try:
        engine = _route_engine(routes)
    except ValueError as exc:
        return _gate("routes", "unavailable", "Route definition rejected", note=str(exc))
    result = engine.check(text)
    elapsed = (time.perf_counter() - started) * 1000

    if not result.matched:
        return _gate(
            "routes",
            "clean",
            f"{len(routes)} route(s), no match",
            elapsed,
            note=f"closest {result.similarity:.2f}, lower a threshold to catch it",
        )
    return _gate(
        "routes",
        "flagged",
        f"Matched '{result.route_name}'",
        elapsed,
        [
            {
                "label": result.route_name or "",
                "severity": result.action or "",
                "text": f"similarity {result.similarity:.2f}",
            }
        ],
    )


def _run_grounding(
    runner: Any, text: str, sources: List[str], config: Dict[str, Any]
) -> Dict[str, Any]:
    if not sources:
        return _gate(
            "grounding",
            "skipped",
            "No reference sources given",
            note="Paste sources to check the text against them",
        )

    started = time.perf_counter()
    try:
        raw, _ = runner.check_grounding(
            response_text=text,
            sources=sources,
            mode=config.get("grounding_mode") or "speed",
            threshold=config.get("grounding_threshold"),
        )
    except Exception as exc:
        return _gate(
            "grounding",
            "unavailable",
            "Grounding engine not loaded",
            note=str(exc).split("\n")[0],
        )
    elapsed = (time.perf_counter() - started) * 1000

    details = raw.get("details") or []
    total = raw.get("sentence_count") or len(details)
    bad = [d for d in details if not d.get("grounded", True)]
    if not bad:
        return _gate(
            "grounding", "clean", f"{total} sentence(s) supported", elapsed
        )

    contradicted = sum(1 for d in bad if d.get("verdict") == "contradicted")
    summary = f"{len(bad)} of {total} unsupported"
    if contradicted:
        summary += f", {contradicted} contradicted"
    return _gate(
        "grounding",
        "flagged",
        summary,
        elapsed,
        [
            {
                "label": d.get("verdict", "ungrounded"),
                # Contradiction and entailment are separate scores, not
                # complements: report the one the verdict turned on.
                "severity": f"{d.get('contradiction', 0.0):.2f}"
                if d.get("verdict") == "contradicted"
                else f"{d.get('entailment', 0.0):.2f}",
                "text": d.get("sentence", ""),
            }
            for d in bad
        ],
    )


def run_playground(
    runner: Any,
    defaults: ServerDefaults,
    text: str,
    stage: str = "input",
    sources: Optional[List[str]] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run every gate over one input and return a uniform per-gate result."""
    config = defaults.merge_request(overrides or {})
    sources = sources or []
    gates: Dict[str, Dict[str, Any]] = {}

    gates["injection"] = _run_injection(text)

    policy_keys = (
        "pii_action",
        "pii_threshold",
        "pii_entities",
        "pii_deny_list",
        "pii_allow_list",
        "pii_custom_regex",
        "pii_custom_context_keywords",
        "categories",
        "cascade_mode",
        "scope_topics",
        "scope_examples",
        "scope_width",
        "scope_threshold",
        "scope_alpha",
    )

    started = time.perf_counter()
    raw, request_id = runner.screen(
        text=text,
        stage=stage,
        **{k: config[k] for k in policy_keys},
    )
    total_ms = (time.perf_counter() - started) * 1000

    timings = {
        d["gate"]: d.get("duration_ms", 0.0)
        for d in (raw.get("_diagnostics") or [])
        if d.get("ran")
    }
    skipped = {
        d["gate"]: d.get("skipped_reason", "")
        for d in (raw.get("_diagnostics") or [])
        if not d.get("ran")
    }

    from guardex._engine.providers.registry import (
        get_classifier_provider,
        get_pii_provider,
    )

    classify = raw.get("classify") or {}
    if get_classifier_provider() is None:
        # fail_open makes the runner return safe=True with no model behind it.
        # Reporting that as "clean" would claim a check that never ran.
        gates["safety"] = _gate(
            "safety",
            "unavailable",
            "Safety model not loaded",
            note="pip install 'guardex-ai[safety]'",
        )
    elif classify.get("safe", True):
        tier, degraded = _decided_by(classify)
        gates["safety"] = _gate(
            "safety",
            "degraded" if degraded else "clean",
            f"Safe ({classify.get('confidence', 1.0):.0%} confidence)",
            timings.get("classify", 0.0),
            note=tier,
        )
    else:
        cat = classify.get("category")
        tier, degraded = _decided_by(classify)
        gates["safety"] = _gate(
            "safety",
            "flagged",
            f"Unsafe{f' · {cat}' if cat else ''}",
            timings.get("classify", 0.0),
            [
                {
                    "label": cat or "unsafe",
                    "severity": f"{classify.get('confidence', 0):.0%}",
                    "text": classify.get("description") or "",
                }
            ],
            note=tier,
        )

    pii = raw.get("pii") or {}
    entities = pii.get("entities") or []
    if "pii" in skipped:
        gates["pii"] = _gate("pii", "skipped", "Disabled", note=skipped["pii"])
    elif get_pii_provider() is None:
        gates["pii"] = _gate(
            "pii",
            "unavailable",
            "PII model not loaded",
            note="pip install 'guardex-ai[pii]'",
        )
    elif not entities:
        gates["pii"] = _gate("pii", "clean", "No PII found", timings.get("pii", 0.0))
    else:
        gates["pii"] = _gate(
            "pii",
            "flagged",
            f"{len(entities)} entity type(s) found",
            timings.get("pii", 0.0),
            [
                {
                    "label": e.get("label", ""),
                    "severity": f"{e.get('score', 0):.0%}",
                    "text": e.get("text", ""),
                    "method": e.get("method", ""),
                }
                for e in entities
            ],
        )

    scope = raw.get("scope")
    scope_reason = skipped.get("scope", "")
    if scope is None and "provider" in scope_reason:
        gates["scope"] = _gate(
            "scope",
            "unavailable",
            "Embedding model not loaded",
            note="pip install 'guardex-ai[scope]'",
        )
    elif scope is None:
        gates["scope"] = _gate(
            "scope",
            "skipped",
            "No topics configured",
            note=scope_reason or "Set scope topics in Config",
        )
    elif scope.get("allowed", True):
        gates["scope"] = _gate(
            "scope",
            "clean",
            f"In scope · {scope.get('matched_topic') or 'matched'}",
            timings.get("scope", 0.0),
        )
    else:
        gates["scope"] = _gate(
            "scope",
            "flagged",
            "Out of scope",
            timings.get("scope", 0.0),
            [
                {
                    "label": "off-topic",
                    "severity": f"{scope.get('score', 0):.2f}"
                    if scope.get("score") is not None
                    else "",
                    "text": f"closest topic: {scope.get('matched_topic') or 'none'}",
                }
            ],
        )

    gates["routes"] = _run_routes(text, config)
    gates["grounding"] = _run_grounding(runner, text, sources, config)

    tier, degraded = _decided_by(classify)
    return {
        "gates": [gates[name] for name in GATE_ORDER],
        "text": raw.get("text", text),
        "total_ms": round(total_ms, 2),
        "request_id": request_id,
        "decided_by": tier,
        "degraded": degraded,
        "raw": raw,
    }
