# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""In-memory ring buffer of screening events for the local Logs view."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Deque, Dict, List, Optional

DEFAULT_MAX_EVENTS = 1000


@dataclass
class ScreenEvent:
    ts: float
    stage: str
    action: str
    safe: bool
    category: Optional[str]
    confidence: float
    pii_count: int
    pii_labels: List[str]
    latency_ms: float
    gates: Dict[str, float] = field(default_factory=dict)
    flagged: List[str] = field(default_factory=list)
    decided_by: str = ""
    degraded: bool = False
    request_id: Optional[str] = None
    text: Optional[str] = None


# Gates whose verdict stops the request outright. Grounding is advisory: an
# unsupported claim is worth review, not a refusal.
BLOCKING_GATES = frozenset({"injection", "safety", "scope", "routes"})


def _derive_action(classify: Dict[str, Any], pii: Dict[str, Any]) -> str:
    if not classify.get("safe", True):
        return "block"
    if pii.get("has_pii", False):
        return "mask"
    return "pass"


def _derive_from_gates(
    gates: List[Dict[str, Any]], classify: Dict[str, Any], pii: Dict[str, Any]
) -> tuple[str, List[str]]:
    flagged = [g["name"] for g in gates if g.get("status") == "flagged"]
    if BLOCKING_GATES.intersection(flagged):
        return "block", flagged
    if "pii" in flagged or pii.get("has_pii", False):
        return "mask", flagged
    if flagged:
        return "flag", flagged
    return "pass", flagged


class EventRecorder:
    """Bounded, thread-safe log of recent screen() calls."""

    def __init__(
        self,
        maxlen: int = DEFAULT_MAX_EVENTS,
        store_text: bool = False,
    ) -> None:
        self._events: Deque[ScreenEvent] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self.store_text = store_text

    def record(
        self,
        *,
        stage: str,
        result: Dict[str, Any],
        latency_ms: float,
        request_id: Optional[str] = None,
        text: Optional[str] = None,
        gate_results: Optional[List[Dict[str, Any]]] = None,
        decided_by: str = "",
        degraded: bool = False,
    ) -> ScreenEvent:
        classify = result.get("classify") or {}
        pii = result.get("pii") or {}
        entities = pii.get("entities") or []
        gates = {
            d["gate"]: d.get("duration_ms", 0.0)
            for d in (result.get("_diagnostics") or [])
            if d.get("ran")
        }
        # Only the playground knows about injection, scope, routes and grounding.
        # Without them the action would reflect the classifier and PII alone.
        if gate_results is None:
            action, flagged = _derive_action(classify, pii), []
        else:
            action, flagged = _derive_from_gates(gate_results, classify, pii)
        event = ScreenEvent(
            ts=time.time(),
            stage=stage,
            action=action,
            safe=bool(classify.get("safe", True)),
            category=classify.get("category"),
            confidence=float(classify.get("confidence", 1.0)),
            pii_count=len(entities),
            pii_labels=[e.get("label", "") for e in entities],
            latency_ms=round(latency_ms, 2),
            gates=gates,
            flagged=flagged,
            decided_by=decided_by or str(classify.get("decided_by") or ""),
            degraded=degraded,
            request_id=request_id,
            text=text if self.store_text else None,
        )
        with self._lock:
            self._events.append(event)
        return event

    def recent(self, limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            snapshot = list(self._events)
        return [asdict(e) for e in reversed(snapshot[-limit:])]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            snapshot = list(self._events)
        total = len(snapshot)
        latencies = [e.latency_ms for e in snapshot if e.latency_ms > 0]
        categories: Dict[str, int] = {}
        for e in snapshot:
            if e.category:
                categories[e.category] = categories.get(e.category, 0) + 1
        return {
            "total": total,
            "passed": sum(1 for e in snapshot if e.action == "pass"),
            "blocked": sum(1 for e in snapshot if e.action == "block"),
            "masked": sum(1 for e in snapshot if e.action == "mask"),
            "flagged": sum(1 for e in snapshot if e.action == "flag"),
            "caught": sum(1 for e in snapshot if e.action != "pass"),
            "pii_total": sum(1 for e in snapshot if e.pii_count > 0),
            "avg_latency_ms": (
                round(sum(latencies) / len(latencies), 2) if latencies else 0.0
            ),
            "p95_latency_ms": (
                round(sorted(latencies)[int(len(latencies) * 0.95)], 2)
                if len(latencies) > 5
                else 0.0
            ),
            "categories": categories,
            "series": [{"t": e.ts, "v": e.latency_ms} for e in snapshot[-60:]],
        }

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
