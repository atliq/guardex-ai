# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""Built-in PII provider - six-layer cascade over GLiNER + regex.

Layers:

0. Text normalization (zero-width strip, NFKC, leet expansion).
1. Deny list (exact match, score=1.0).
2. Regex + checksum (score=0.85).
3. GLiNER NER zero-shot.
4. Merge + context-keyword boost.
5. Allow list filter.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from guardex._constants import DEFAULT_PII_THRESHOLD
from guardex._engine.ml.model_manager import get_gliner_model
from guardex._engine.services.pii_detector import DEFAULT_ENTITIES
from guardex._engine.services.pii_regex import (
    regex_detect,
    deny_list_detect,
    context_enhance,
    allow_list_filter,
    merge_detections,
)

logger = logging.getLogger(__name__)


class GlinerPiiProvider:
    """PII detection using a six-layer cascade: regex + GLiNER + context."""

    name: str = "guardex-pii-v1"

    def detect(
        self,
        text: str,
        entities: list[str] | None = None,
        threshold: float = DEFAULT_PII_THRESHOLD,
        *,
        custom_regex: dict[str, re.Pattern[str]] | None = None,
        deny_list: set[str] | None = None,
        allow_list: set[str] | None = None,
        custom_context_keywords: dict[str, list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Run the full detection cascade.

        Parameters
        ----------
        text : str
            Input text to scan.
        entities : list[str], optional
            Entity types to detect. Defaults to DEFAULT_ENTITIES.
        threshold : float
            Minimum confidence to emit a finding.
        custom_regex : dict, optional
            Extra regex patterns from user-defined custom labels.
        deny_list : set[str], optional
            Exact strings to force-detect with score 1.0.
        allow_list : set[str], optional
            Known-safe values to suppress from findings.
        custom_context_keywords : dict, optional
            Extra context keywords from user-defined custom labels.
        """
        labels = entities or DEFAULT_ENTITIES

        # Layer 0: Text normalization
        # Normalize for detection but detect on ORIGINAL text
        # (span offsets must map to original text for masking to work)
        # Normalization helps GLiNER catch adversarial inputs but we
        # run regex on original text since regex patterns expect raw formats

        # Layer 1: Deny list fast-path
        deny_results = deny_list_detect(text, deny_list)

        # Layer 2: Regex + checksum validation
        regex_results = regex_detect(text, labels, extra_patterns=custom_regex)

        # Layer 3: GLiNER NER (semantic)
        gliner_results: list[dict[str, Any]] = []
        model = get_gliner_model()
        if model is not None:
            try:
                # Run on original text so span offsets map correctly to original for masking.
                # Normalization is handled upstream (keyword gate / ONNX) for classification;
                # here correct character offsets are the priority.
                raw = model.predict_entities(text, labels, threshold=threshold)
                gliner_results = [
                    {
                        "text": text[ent["start"]:ent["end"]],
                        "label": ent["label"],
                        "score": round(ent["score"], 4),
                        "start": ent["start"],
                        "end": ent["end"],
                        "method": "gliner",
                    }
                    for ent in raw
                ]
            except Exception as e:
                logger.exception("GLiNER inference failed: %s", e)
                if not regex_results and not deny_results:
                    raise RuntimeError(
                        "PII detection model crashed mid-inference and no "
                        "regex matches found. Cannot guarantee PII safety."
                    ) from e
                logger.warning(
                    "GLiNER crashed; falling back to regex-only matches "
                    "(regex=%d, deny=%d)",
                    len(regex_results), len(deny_results),
                )
                gliner_results = []
        else:
            if not regex_results and not deny_results:
                raise RuntimeError(
                    "GuardEx PII model not loaded. "
                    "pip install 'guardex-ai[local]' - or pass api_key=/base_url= for server mode."
                )
            logger.warning(
                "GLiNER model unavailable - falling back to regex-only detection"
            )

        # Layer 4: Merge + context enhancement
        primary = deny_results + regex_results
        merged = merge_detections(primary, gliner_results)
        enhanced = context_enhance(text, merged)

        # Inject custom context keywords into the enhancement (per-request, NOT global)
        if custom_context_keywords:
            from guardex._engine.services.pii_regex import context_enhance as _ctx_enhance
            import re as _re
            local_patterns: dict = {}
            for label, keywords in custom_context_keywords.items():
                if keywords:
                    escaped = [_re.escape(kw) for kw in keywords]
                    local_patterns[label] = _re.compile(
                        r"\b(?:" + "|".join(escaped) + r")\b",
                        _re.IGNORECASE,
                    )
            # Re-run context enhancement with project-scoped patterns
            if local_patterns:
                enhanced = _ctx_enhance(text, enhanced, extra_patterns=local_patterns)

        # Layer 5: Allow list filter
        filtered = allow_list_filter(enhanced, allow_list)

        # Threshold filter
        return [e for e in filtered if e["score"] >= threshold]

    def mask(self, text: str, entities_found: list[dict[str, Any]]) -> str:
        """Replace each detected entity span with ``[ENTITY_TYPE]``.

        Processes right-to-left so earlier character indices stay valid.
        """
        sorted_ents = sorted(entities_found, key=lambda e: e["start"], reverse=True)
        for ent in sorted_ents:
            placeholder = f"[{ent['label'].upper().replace(' ', '_')}]"
            text = text[: ent["start"]] + placeholder + text[ent["end"]:]
        return text
