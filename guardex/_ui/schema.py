# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 GuardEx
"""Declarative description of every knob the local UI can tune.

Single source of truth for the config API and the React Config page, so a
new field never needs a matching hand-edit in TypeScript.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from guardex._constants import DEFAULT_PII_THRESHOLD
from guardex._engine.services.pii_detector import DEFAULT_ENTITIES


@dataclass(frozen=True)
class ConfigField:
    name: str
    type: str
    default: Any
    label: str
    group: str
    help: str = ""
    choices: Optional[List[str]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    options_source: Optional[str] = None


UI_CONFIG_FIELDS: List[ConfigField] = [
    ConfigField(
        "pii_action", "enum", "mask", "PII action", "pii",
        "What to do when PII is found", choices=["mask", "block", "none"],
    ),
    ConfigField(
        "pii_threshold", "float", DEFAULT_PII_THRESHOLD, "PII threshold", "pii",
        "Lower detects more, at the cost of false positives",
        min=0.1, max=0.95, step=0.05,
    ),
    ConfigField(
        "pii_entities", "string_list", list(DEFAULT_ENTITIES), "PII entities", "pii",
        "Entity types to detect", options_source="pii_entities",
    ),
    ConfigField(
        "pii_deny_list", "string_list", [], "Deny list", "pii",
        "Literal strings always treated as PII",
    ),
    ConfigField(
        "pii_allow_list", "string_list", [], "Allow list", "pii",
        "Literal strings never treated as PII",
    ),
    ConfigField(
        "pii_custom_regex", "string_map", {}, "Custom regex", "pii",
        "Label to regular expression",
    ),
    ConfigField(
        "pii_custom_context_keywords", "string_list_map", {}, "Context keywords", "pii",
        "Label to nearby words that raise confidence",
    ),
    ConfigField(
        "categories", "string_list", [], "Blocked categories", "content",
        "Empty means the classifier default set", options_source="categories",
    ),
    ConfigField(
        "cascade_mode", "enum", "safety", "Cascade mode", "content",
        "safety runs the full cascade; speed short-circuits",
        choices=["safety", "speed"],
    ),
    ConfigField(
        "scope_topics", "string_list", [], "Topics", "scope",
        "In-scope topics; empty disables scope checking",
    ),
    ConfigField(
        "scope_examples", "string_list", [], "Examples", "scope",
        "Example in-scope utterances",
    ),
    ConfigField(
        "scope_width", "enum", "moderate", "Scope width", "scope", "",
        choices=["narrow", "moderate", "broad", "fitted"],
    ),
    ConfigField(
        "scope_threshold", "float_or_null", None, "Scope threshold", "scope",
        "Null derives the threshold from scope width",
        min=0.0, max=1.0, step=0.05,
    ),
    ConfigField(
        "scope_alpha", "float", 0.0, "Scope alpha", "scope",
        "Blend between topic and example similarity",
        min=0.0, max=1.0, step=0.05,
    ),

    ConfigField(
        "safety_routes", "route_list", [], "Custom routes", "routes",
        "Block your own categories using example utterances",
    ),

    ConfigField(
        "grounding_mode", "enum_or_null", None, "Grounding mode", "grounding",
        "accuracy runs NLI; speed uses embeddings only",
        choices=["speed", "accuracy"],
    ),
    ConfigField(
        "grounding_threshold", "float_or_null", None, "Grounding threshold", "grounding",
        "Null uses the engine default",
        min=0.0, max=1.0, step=0.05,
    ),
]

GATE_GROUPS = {
    "injection": [],
    "safety": ["categories", "cascade_mode"],
    "pii": [
        "pii_action", "pii_threshold", "pii_entities", "pii_deny_list",
        "pii_allow_list", "pii_custom_regex", "pii_custom_context_keywords",
    ],
    "scope": [
        "scope_topics", "scope_examples", "scope_width",
        "scope_threshold", "scope_alpha",
    ],
    "routes": ["safety_routes"],
    "grounding": ["grounding_mode", "grounding_threshold"],
}
