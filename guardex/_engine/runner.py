# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""In-process ML runtime for GuardEx - no server required.

LocalRunner is the default (and only) transport in the open-source build:
every ML step runs in-process - no HTTP, no external services, no credentials.
It is instantiated automatically by ``Guard()``.

Return shapes mirror the server JSON responses so that
``guard.py``'s ``_parse_screen_result()`` and ``_parse_grounding_result()``
consume them without any conditional logic.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Literal, Optional

from guardex._constants import DEFAULT_PII_THRESHOLD

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()
_providers_initialized = False


def _ensure_providers() -> None:
    """Lazy-initialize ML providers on first call (thread-safe, one-time)."""
    global _providers_initialized
    if _providers_initialized:
        return
    with _init_lock:
        if _providers_initialized:
            return
        from guardex._engine.providers import init_providers
        init_providers()
        _providers_initialized = True


_worker_loop: asyncio.AbstractEventLoop | None = None
_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()


def _ensure_worker_loop() -> asyncio.AbstractEventLoop:
    """Start (once) a dedicated background thread running an event loop.

    Async coroutines from sync call sites are submitted to this loop so
    that long-lived async resources (e.g. shared ``httpx.AsyncClient``
    instances in the classifier service) stay bound to the same loop
    across multiple ``screen()`` calls.
    """
    global _worker_loop, _worker_thread
    if _worker_loop is not None and not _worker_loop.is_closed():
        return _worker_loop
    with _worker_lock:
        if _worker_loop is not None and not _worker_loop.is_closed():
            return _worker_loop
        loop = asyncio.new_event_loop()
        thread = threading.Thread(
            target=loop.run_forever, name="guardex-localrunner", daemon=True,
        )
        thread.start()
        _worker_loop = loop
        _worker_thread = thread
        return loop


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from a synchronous call site.

    Submits the coroutine to a persistent background event loop so that
    async resources owned by providers persist across calls.  When a loop
    is already running on the calling thread (Jupyter / FastAPI), we still
    submit to the worker loop to avoid nested-loop issues.
    """
    loop = _ensure_worker_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


class LocalRunner:
    """In-process ML transport - the default local runtime for Guard().

    Runs every ML step (safety classification, PII detection, grounding,
    topic scope) inside the current Python process.  Prompt-injection
    screening happens client-side in ``guardex.injection`` before this
    runner is called.  No network calls and no credentials are required.
    Every method returns the same raw-dict shapes that guard.py's
    ``_parse_screen_result()`` and ``_parse_grounding_result()`` consume.
    """

    def __init__(self, fail_open: bool = False) -> None:
        self._fail_open = fail_open

    # Private ML helpers

    def _classify_raw(
        self,
        text: str,
        stage: str = "input",
        categories: Optional[List[str]] = None,
        cascade_mode: Optional[str] = None,
    ) -> dict[str, Any]:
        """Run the registered classifier and return a raw classify dict."""
        from guardex._engine.providers.registry import get_classifier_provider

        provider = get_classifier_provider()
        if provider is None:
            if self._fail_open:
                logger.error(
                    "GuardEx classifier provider not registered - "
                    "fail_open=True, returning safe=True (content NOT screened)"
                )
                return {"safe": True, "category": None, "categories": [], "confidence": 1.0}
            raise RuntimeError(
                "GuardEx classifier not loaded. "
                "pip install 'guardex-ai[local]' - or pass api_key=/base_url= for server mode."
            )

        raw = _run_async(provider.classify(text, stage=stage, categories=categories, cascade_mode=cascade_mode))
        return {
            "safe": raw.get("safe", True),
            "category": raw.get("category"),
            "categories": raw.get("categories", []),
            "confidence": raw.get("confidence", 1.0),
            "description": raw.get("description"),
            "decided_by": raw.get("_cascade_path") or getattr(provider, "name", ""), # Which cascade tier produced this verdict

        }

    def _pii_raw(
        self,
        text: str,
        entities: Optional[List[str]] = None,
        threshold: float = DEFAULT_PII_THRESHOLD,
        mask: bool = False,
        deny_list: Optional[List[str]] = None,
        allow_list: Optional[List[str]] = None,
        custom_regex: Optional[dict[str, str]] = None,
        custom_context_keywords: Optional[dict[str, List[str]]] = None,
    ) -> dict[str, Any]:
        """Run PII detection and return a raw pii dict."""
        import re as _re
        from guardex._engine.providers.registry import get_pii_provider

        provider = get_pii_provider()
        if provider is None:
            if self._fail_open:
                logger.error(
                    "GuardEx PII provider not registered - "
                    "fail_open=True, returning has_pii=False (PII NOT scanned)"
                )
                return {"has_pii": False, "entities": [], "masked_text": text if mask else None}
            raise RuntimeError(
                "GuardEx PII detector not loaded. "
                "pip install 'guardex-ai[local]' - or pass api_key=/base_url= for server mode."
            )

        compiled_regex: Optional[dict[str, _re.Pattern[str]]] = None
        effective_entities = list(entities) if entities else None
        if custom_regex:
            compiled_regex = {
                label: _re.compile(pat, _re.IGNORECASE)
                for label, pat in custom_regex.items()
            }
            # regex_detect only scans labels passed to it; ensure custom
            # labels are scanned alongside the user-selected entity types.
            from guardex._engine.services.pii_detector import DEFAULT_ENTITIES as _DE
            base = effective_entities if effective_entities is not None else list(_DE)
            for k in compiled_regex.keys():
                if k not in base:
                    base.append(k)
            effective_entities = base

        found: list[dict[str, Any]] = provider.detect(
            text,
            entities=effective_entities,
            threshold=threshold,
            custom_regex=compiled_regex,
            deny_list=set(deny_list) if deny_list else None,
            allow_list=set(allow_list) if allow_list else None,
            custom_context_keywords=custom_context_keywords,
        )
        has_pii = bool(found)
        masked_text: Optional[str] = None
        if mask and has_pii:
            masked_text = provider.mask(text, found)

        return {
            "has_pii": has_pii,
            "entities": found,
            "masked_text": masked_text,
        }

    def _scope_raw(
        self,
        text: str,
        topics: List[str],
        utterances: Optional[dict[str, List[str]]] = None,
        examples: Optional[List[str]] = None,
        scope_width: str = "moderate",
        threshold: Optional[float] = None,
        alpha: float = 0.0,
    ) -> Optional[dict[str, Any]]:
        """Run topic-scope check and return a raw scope dict, or None."""
        from guardex._engine.providers.registry import get_topic_scope_provider

        provider = get_topic_scope_provider()
        if provider is None:
            return None

        profile = provider.build_scope(
            topics,
            utterances=utterances,
            examples=examples,
            scope_width=scope_width,
            threshold=threshold,
        )
        raw = _run_async(provider.check_scope(text, profile, alpha=alpha))
        return {
            "allowed": raw.get("allowed", True),
            "distance": raw.get("distance", 0.0),
            "matched_topic": raw.get("matched_topic"),
            "confidence": raw.get("confidence", 1.0),
            "reason": raw.get("reason"),
        }

    # Public transport interface (mirrors GuardExClient)

    def screen(
        self,
        text: str,
        stage: str = "input",
        pii_action: Literal["mask", "block", "none"] = "mask",
        categories: Optional[List[str]] = None,
        pii_entities: Optional[List[str]] = None,
        pii_threshold: float = DEFAULT_PII_THRESHOLD,
        pii_deny_list: Optional[List[str]] = None,
        pii_allow_list: Optional[List[str]] = None,
        pii_custom_regex: Optional[dict[str, str]] = None,
        pii_custom_context_keywords: Optional[dict[str, List[str]]] = None,
        scope_topics: Optional[List[str]] = None,
        scope_utterances: Optional[dict[str, List[str]]] = None,
        scope_examples: Optional[List[str]] = None,
        scope_width: str = "moderate",
        scope_threshold: Optional[float] = None,
        scope_alpha: float = 0.0,
        cascade_mode: str = "safety",
        audit_log: bool = False,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> tuple[dict[str, Any], Optional[str]]:
        """Run the full ML pipeline in-process.

        Returns (raw_dict, request_id) - identical shape to the server's
        /v1/screen JSON response so guard.py's _parse_screen_result() is reused.
        ``raw_dict`` carries an extra ``_diagnostics`` key (list of dicts:
        gate, ran, skipped_reason, duration_ms, blocked, note) used by the
        SDK to populate ``ScreenResult.gates_run`` / ``ScreenResult.diagnostics``.
        """
        import time as _time
        _ensure_providers()
        request_id = str(uuid.uuid4())
        diagnostics: list[dict[str, Any]] = []

        def _trace(gate_name: str, ran: bool, t0: float,
                   skipped_reason: Optional[str] = None,
                   blocked: bool = False, note: Optional[str] = None,
                   ended: Optional[float] = None) -> None:
            diagnostics.append({
                "gate": gate_name,
                "ran": ran,
                "skipped_reason": skipped_reason,
                "duration_ms": ((ended if ended is not None else _time.perf_counter()) - t0) * 1000,
                "blocked": blocked,
                "note": note,
            })

        try:
            # Step 1 - Input validation (length, character set)
            from guardex._engine.ml.input_validator import validate_input

            t0 = _time.perf_counter()
            val = validate_input(text)
            if not val.valid:
                _trace("input_validation", True, t0, blocked=True, note=val.reason)
                return {
                    "classify": {
                        "safe": False,
                        "category": "S0",
                        "categories": ["S0"],
                        "confidence": 1.0,
                        "description": val.reason,
                        "decided_by": "input_validation",
                    },
                    "pii": {"has_pii": False, "entities": []},
                    "text": text,
                    "_diagnostics": diagnostics,
                }, request_id
            _trace("input_validation", True, t0)

            # Step 2 - Keyword gate (zero-latency hard blocks)
            from guardex._engine.ml.keyword_gate import check_keyword_gate

            t0 = _time.perf_counter()
            kw = check_keyword_gate(text)
            if kw.matched:
                # Every pattern in _SELF_HARM_PATTERNS ships with an
                # explicit category - if one is None at this point that's
                # a real bug, not a silent default to "Violent Crimes".
                if not kw.category:
                    raise RuntimeError(
                        f"Keyword gate matched pattern {kw.pattern!r} with no "
                        "category. Every keyword pattern must declare an S-code."
                    )
                _trace("keyword", True, t0, blocked=True, note=kw.pattern)
                return {
                    "classify": {
                        "safe": False,
                        "category": kw.category,
                        "categories": [kw.category],
                        "confidence": 1.0,
                        "description": f"Keyword match: {kw.pattern}",
                        "decided_by": "keyword_gate",
                    },
                    "pii": {"has_pii": False, "entities": []},
                    "text": text,
                    "_diagnostics": diagnostics,
                }, request_id
            _trace("keyword", True, t0)

            # Step 3 - Text normalisation (unicode homoglyph removal, etc.)
            from guardex._engine.ml.text_normalizer import normalize_for_classification

            normalized = normalize_for_classification(text)

            # Steps 4+5 - Safety classification and PII detection are
            # independent (neither consumes the other's output), so they run
            # concurrently: classify inference happens on the worker event
            # loop while PII (GLiNER + regex) runs on the calling thread.
            # The spawned thread only waits on the classify future, so both
            # models keep their usual threads.  Per-gate duration_ms values
            # overlap and may sum to more than total wall time.
            #
            # PII masks whenever the action is "mask" or "block" so the parser
            # has a masked_text to surface in either path.  "none" skips PII
            # entirely.  PII detection sees the normalized text too so
            # homoglyph PII (e.g. Cyrillic 'a' in an email) doesn't slip past
            # GLiNER the way it would slip past the safety classifier.
            do_pii = pii_action != "none"
            pii: dict[str, Any]
            t0 = _time.perf_counter()
            if do_pii:
                with ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="guardex-classify"
                ) as pool:
                    clf_future = pool.submit(
                        self._classify_raw, normalized, stage=stage,
                        categories=categories, cascade_mode=cascade_mode,
                    )
                    pii = self._pii_raw(
                        normalized,
                        entities=pii_entities,
                        threshold=pii_threshold,
                        mask=(pii_action in ("mask", "block")),
                        deny_list=pii_deny_list,
                        allow_list=pii_allow_list,
                        custom_regex=pii_custom_regex,
                        custom_context_keywords=pii_custom_context_keywords,
                    )
                    pii_ended = _time.perf_counter()
                    clf = clf_future.result()
                _trace("classify", True, t0,
                       blocked=(not clf.get("safe", True)),
                       note=clf.get("category"))
                _trace("pii", True, t0,
                       blocked=(pii.get("has_pii", False) and pii_action == "block"),
                       note=f"{len(pii.get('entities') or [])} entities",
                       ended=pii_ended)
            else:
                clf = self._classify_raw(normalized, stage=stage, categories=categories, cascade_mode=cascade_mode)
                _trace("classify", True, t0,
                       blocked=(not clf.get("safe", True)),
                       note=clf.get("category"))
                t0 = _time.perf_counter()
                pii = {"has_pii": False, "entities": [], "masked_text": None}
                _trace("pii", False, t0, skipped_reason="pii_action='none'")

            # Step 6 - Topic scope (optional)
            scope: Optional[dict[str, Any]] = None
            t0 = _time.perf_counter()
            if scope_topics:
                scope = self._scope_raw(
                    text,
                    scope_topics,
                    utterances=scope_utterances,
                    examples=scope_examples,
                    scope_width=scope_width,
                    threshold=scope_threshold,
                    alpha=scope_alpha,
                )
                if scope is None:
                    _trace("scope", False, t0, skipped_reason="scope provider not registered")
                else:
                    _trace("scope", True, t0,
                           blocked=(not scope.get("allowed", True)),
                           note=scope.get("matched_topic"))
            else:
                _trace("scope", False, t0, skipped_reason="no scope_topics in policy")

            output_text: str = pii.get("masked_text") or text
            result: dict[str, Any] = {
                "classify": clf,
                "pii": pii,
                "text": output_text,
                "_diagnostics": diagnostics,
            }
            if scope is not None:
                result["scope"] = scope

            return result, request_id

        except Exception as exc:
            if self._fail_open:
                logger.warning(
                    "GuardEx local runner error (fail_open=True): %s", exc
                )
                return {"_fail_open": True, "_diagnostics": diagnostics}, None
            raise

    def classify(
        self,
        text: str,
        stage: str = "input",
        categories: Optional[List[str]] = None,
        cascade_mode: Optional[str] = None,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Classify text for safety. Returns raw classify dict."""
        _ensure_providers()
        from guardex._engine.ml.text_normalizer import normalize_for_classification

        normalized = normalize_for_classification(text)
        return self._classify_raw(normalized, stage=stage, categories=categories, cascade_mode=cascade_mode)

    def pii_scan(
        self,
        text: str,
        entities: Optional[List[str]] = None,
        threshold: float = DEFAULT_PII_THRESHOLD,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Scan text for PII. Returns raw pii dict (no masked_text)."""
        _ensure_providers()
        raw = self._pii_raw(text, entities=entities, threshold=threshold, mask=False)
        return {"has_pii": raw["has_pii"], "entities": raw["entities"]}

    def pii_mask(
        self,
        text: str,
        entities: Optional[List[str]] = None,
        threshold: float = DEFAULT_PII_THRESHOLD,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Scan and mask PII. Returns raw pii dict with masked_text."""
        _ensure_providers()
        return self._pii_raw(text, entities=entities, threshold=threshold, mask=True)

    def screen_batch(
        self,
        texts: List[str],
        stage: str = "input",
        pii_action: Literal["mask", "block", "none"] = "mask",
        categories: Optional[List[str]] = None,
        pii_entities: Optional[List[str]] = None,
        pii_threshold: float = DEFAULT_PII_THRESHOLD,
        pii_custom_regex: Optional[dict[str, str]] = None,
        cascade_mode: str = "safety",
        extra_headers: Optional[dict[str, str]] = None,
    ) -> List[dict[str, Any]]:
        """Screen a batch of texts. Returns list of raw dicts (one per text)."""
        if not texts:
            return []
        results = []
        for t in texts:
            raw, _ = self.screen(
                text=t,
                stage=stage,
                pii_action=pii_action,
                categories=categories,
                pii_entities=pii_entities,
                pii_threshold=pii_threshold,
                pii_custom_regex=pii_custom_regex,
                cascade_mode=cascade_mode,
            )
            results.append(raw)
        return results

    def check_grounding(
        self,
        response_text: str,
        sources: List[str],
        mode: Optional[str] = None,
        threshold: Optional[float] = None,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> tuple[dict[str, Any], Optional[str]]:
        """Check response grounding against source chunks.

        Returns (raw_dict, request_id) - same shape as the server response,
        consumed by guard.py's _parse_grounding_result().
        """
        _ensure_providers()
        from guardex._engine.providers.registry import get_grounding_provider

        request_id = str(uuid.uuid4())
        provider = get_grounding_provider()
        if provider is None:
            raise RuntimeError(
                "GuardEx grounding engine not loaded. "
                "pip install 'guardex-ai[local]' - or pass api_key=/base_url= for server mode."
            )

        raw = _run_async(
            provider.check_grounding(
                response_text=response_text,
                sources=sources,
                mode=mode,
                threshold=threshold,
            )
        )
        return raw, request_id

    def close(self) -> None:
        """No-op - no HTTP connections to close."""

    def __enter__(self) -> "LocalRunner":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
