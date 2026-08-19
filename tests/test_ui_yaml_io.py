# SPDX-License-Identifier: Apache-2.0
import pytest

from guardex._ui.state import ServerDefaults
from guardex._ui.yaml_io import POLICY_FILENAME, load_policy, save_policy

pytest.importorskip("yaml")


def test_filename_is_stable():
    assert POLICY_FILENAME == "guardex.policy.yaml"


def test_save_writes_a_file(tmp_path):
    target = save_policy({"pii_action": "block"}, tmp_path / POLICY_FILENAME)
    assert target.exists()


def test_save_then_load_round_trips(tmp_path):
    config = ServerDefaults().replace({"pii_threshold": 0.55, "scope_topics": ["billing"]})
    save_policy(config, tmp_path / POLICY_FILENAME)
    loaded = load_policy(tmp_path / POLICY_FILENAME)
    assert loaded["pii_threshold"] == 0.55
    assert loaded["scope_topics"] == ["billing"]


def test_save_omits_fields_left_at_default(tmp_path):
    save_policy(ServerDefaults().snapshot(), tmp_path / POLICY_FILENAME)
    assert load_policy(tmp_path / POLICY_FILENAME) == {}


def test_load_returns_empty_dict_for_a_missing_file(tmp_path):
    assert load_policy(tmp_path / "absent.yaml") == {}


def test_load_rejects_a_non_mapping_document(tmp_path):
    path = tmp_path / POLICY_FILENAME
    path.write_text("- one\n- two\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_policy(path)


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    save_policy({"pii_action": "block"}, tmp_path / POLICY_FILENAME)
    assert [p.name for p in tmp_path.iterdir()] == [POLICY_FILENAME]
