# SPDX-License-Identifier: Apache-2.0
import pytest

pytest.importorskip("fastapi")

from guardex import server as gx_server  # noqa: E402

CLEAN = {
    "classify": {"safe": True, "category": None, "confidence": 1.0},
    "pii": {"has_pii": False, "entities": []},
    "text": "",
    "_diagnostics": [],
}


def test_screen_request_accepts_the_widened_pii_fields():
    req = gx_server.ScreenRequest(
        text="hi",
        pii_deny_list=["acme"],
        pii_allow_list=["support@example.com"],
        pii_custom_context_keywords={"BADGE": ["badge", "id"]},
    )
    assert req.pii_deny_list == ["acme"]
    assert req.pii_allow_list == ["support@example.com"]
    assert req.pii_custom_context_keywords == {"BADGE": ["badge", "id"]}


def test_module_exposes_shared_defaults_and_recorder():
    # RECORDER is module-global and any earlier test that screened will have
    # filled it, so clear before asserting the empty state.
    gx_server.RECORDER.clear()
    assert gx_server.DEFAULTS.snapshot()["pii_action"] == "mask"
    assert gx_server.RECORDER.recent() == []


def test_screen_records_an_event(monkeypatch):
    gx_server.RECORDER.clear()
    monkeypatch.setattr(
        gx_server._runner,
        "screen",
        lambda **kw: ({**CLEAN, "text": kw["text"]}, "req-1"),
    )
    gx_server._screen_one(gx_server.ScreenRequest(text="hello"))
    (event,) = gx_server.RECORDER.recent()
    assert event["action"] == "pass"
    assert event["request_id"] == "req-1"
    assert event["latency_ms"] >= 0
    gx_server.RECORDER.clear()


def test_screen_applies_server_defaults_for_omitted_fields(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        gx_server._runner, "screen", lambda **kw: (seen.update(kw) or (CLEAN, None))
    )
    gx_server.DEFAULTS.replace({"pii_threshold": 0.55})
    try:
        gx_server._screen_one(gx_server.ScreenRequest(text="hello"))
        assert seen["pii_threshold"] == 0.55
    finally:
        gx_server.DEFAULTS.reset()
        gx_server.RECORDER.clear()


def test_explicit_request_value_beats_the_server_default(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        gx_server._runner, "screen", lambda **kw: (seen.update(kw) or (CLEAN, None))
    )
    gx_server.DEFAULTS.replace({"pii_action": "block"})
    try:
        gx_server._screen_one(gx_server.ScreenRequest(text="hello", pii_action="none"))
        assert seen["pii_action"] == "none"
    finally:
        gx_server.DEFAULTS.reset()
        gx_server.RECORDER.clear()


def test_omitted_threshold_resolves_to_the_shared_constant(monkeypatch):
    from guardex._constants import DEFAULT_PII_THRESHOLD

    seen = {}
    monkeypatch.setattr(
        gx_server._runner, "screen", lambda **kw: (seen.update(kw) or (CLEAN, None))
    )
    gx_server.DEFAULTS.reset()
    gx_server._screen_one(gx_server.ScreenRequest(text="hello"))
    assert seen["pii_threshold"] == DEFAULT_PII_THRESHOLD
    gx_server.RECORDER.clear()


def test_install_ui_returns_false_without_built_assets(tmp_path):
    import fastapi

    from guardex._ui.mount import install_ui

    app = fastapi.FastAPI()
    assert install_ui(app, gx_server.DEFAULTS, gx_server.RECORDER, tmp_path / "absent") is False


def test_install_ui_mounts_when_assets_exist(tmp_path):
    import fastapi
    from fastapi.testclient import TestClient

    from guardex._ui.mount import install_ui

    assets = tmp_path / "ui_assets"
    assets.mkdir()
    (assets / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")

    app = fastapi.FastAPI()
    assert install_ui(app, gx_server.DEFAULTS, gx_server.RECORDER, assets) is True
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/v1/config").status_code == 200


def test_spa_deep_link_falls_back_to_index(tmp_path):
    import fastapi
    from fastapi.testclient import TestClient

    from guardex._ui.mount import install_ui

    assets = tmp_path / "ui_assets"
    assets.mkdir()
    (assets / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")

    app = fastapi.FastAPI()
    install_ui(app, gx_server.DEFAULTS, gx_server.RECORDER, assets)
    assert TestClient(app).get("/logs").status_code == 200
