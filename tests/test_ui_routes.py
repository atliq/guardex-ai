# SPDX-License-Identifier: Apache-2.0
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from guardex._ui.events import EventRecorder  # noqa: E402
from guardex._ui.routes import build_router  # noqa: E402
from guardex._ui.state import ServerDefaults  # noqa: E402

CLEAN = {
    "classify": {"safe": True},
    "pii": {"has_pii": False, "entities": []},
    "_diagnostics": [],
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = fastapi.FastAPI()
    app.state.guardex_defaults = ServerDefaults()
    app.state.guardex_recorder = EventRecorder()
    app.include_router(build_router(app.state.guardex_defaults, app.state.guardex_recorder))
    return TestClient(app)


def test_get_config_returns_current_defaults(client):
    body = client.get("/v1/config").json()
    assert body["config"]["pii_action"] == "mask"


def test_get_schema_lists_fields(client):
    fields = client.get("/v1/config/schema").json()["fields"]
    assert any(f["name"] == "pii_threshold" for f in fields)


def test_get_schema_exposes_entity_options(client):
    options = client.get("/v1/config/schema").json()["options"]
    assert isinstance(options["pii_entities"], list)


def test_put_config_applies_a_patch(client):
    body = client.put("/v1/config", json={"pii_threshold": 0.55}).json()
    assert body["config"]["pii_threshold"] == 0.55


def test_put_config_persists_across_requests(client):
    client.put("/v1/config", json={"pii_action": "block"})
    assert client.get("/v1/config").json()["config"]["pii_action"] == "block"


def test_put_config_rejects_unknown_field_with_400(client):
    res = client.put("/v1/config", json={"nope": 1})
    assert res.status_code == 400


def test_reset_restores_defaults(client):
    client.put("/v1/config", json={"pii_action": "block"})
    assert client.post("/v1/config/reset").json()["config"]["pii_action"] == "mask"


def test_save_writes_the_policy_file(client, tmp_path):
    client.put("/v1/config", json={"pii_action": "block"})
    path = client.post("/v1/config/save").json()["path"]
    assert (tmp_path / "guardex.policy.yaml").exists()
    assert path.endswith("guardex.policy.yaml")


def test_logs_start_empty(client):
    assert client.get("/v1/logs").json()["events"] == []


def test_logs_expose_recorded_events(client):
    client.app.state.guardex_recorder.record(stage="input", result=CLEAN, latency_ms=5.0)
    assert len(client.get("/v1/logs").json()["events"]) == 1


def test_logs_respect_the_limit_parameter(client):
    for _ in range(5):
        client.app.state.guardex_recorder.record(stage="input", result=CLEAN, latency_ms=5.0)
    assert len(client.get("/v1/logs?limit=2").json()["events"]) == 2


def test_logs_stats_reports_total(client):
    client.app.state.guardex_recorder.record(stage="input", result=CLEAN, latency_ms=5.0)
    assert client.get("/v1/logs/stats").json()["total"] == 1


def test_delete_logs_clears_the_buffer(client):
    client.app.state.guardex_recorder.record(stage="input", result=CLEAN, latency_ms=5.0)
    client.delete("/v1/logs")
    assert client.get("/v1/logs").json()["events"] == []


def test_meta_reports_version(client):
    assert client.get("/v1/meta").json()["version"]
