# SPDX-License-Identifier: Apache-2.0
import pytest

from guardex._ui.schema import UI_CONFIG_FIELDS
from guardex._ui.state import ServerDefaults, UnknownConfigField


def test_schema_covers_the_screen_request_knobs():
    names = {f.name for f in UI_CONFIG_FIELDS}
    assert {
        "pii_action", "pii_threshold", "pii_entities", "pii_deny_list",
        "pii_allow_list", "pii_custom_regex", "pii_custom_context_keywords",
        "categories", "cascade_mode", "scope_topics", "scope_examples",
        "scope_width", "scope_threshold", "scope_alpha",
    } <= names


def test_schema_field_names_are_unique():
    names = [f.name for f in UI_CONFIG_FIELDS]
    assert len(names) == len(set(names))


def test_snapshot_starts_at_schema_defaults():
    defaults = ServerDefaults()
    snap = defaults.snapshot()
    assert snap["pii_action"] == "mask"
    assert snap["cascade_mode"] == "safety"


def test_replace_applies_a_partial_patch():
    defaults = ServerDefaults()
    updated = defaults.replace({"pii_threshold": 0.55})
    assert updated["pii_threshold"] == 0.55
    assert updated["pii_action"] == "mask"


def test_replace_rejects_unknown_fields():
    defaults = ServerDefaults()
    with pytest.raises(UnknownConfigField):
        defaults.replace({"nope": 1})


def test_replace_swaps_atomically_and_leaves_no_shared_reference():
    defaults = ServerDefaults()
    before = defaults.snapshot()
    defaults.replace({"pii_threshold": 0.55})
    assert before["pii_threshold"] != 0.55


def test_merge_request_prefers_explicit_request_values():
    defaults = ServerDefaults()
    defaults.replace({"pii_action": "block"})
    merged = defaults.merge_request({"pii_action": "none", "text": "hi"})
    assert merged["pii_action"] == "none"


def test_merge_request_fills_omitted_fields_from_defaults():
    defaults = ServerDefaults()
    defaults.replace({"pii_threshold": 0.55})
    merged = defaults.merge_request({"text": "hi"})
    assert merged["pii_threshold"] == 0.55


def test_merge_request_does_not_mutate_the_payload():
    defaults = ServerDefaults()
    payload = {"text": "hi"}
    defaults.merge_request(payload)
    assert payload == {"text": "hi"}


def test_reset_restores_schema_defaults():
    defaults = ServerDefaults()
    defaults.replace({"pii_threshold": 0.55})
    assert defaults.reset()["pii_threshold"] == ServerDefaults().snapshot()["pii_threshold"]
