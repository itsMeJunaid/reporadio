import pytest
from fastapi.testclient import TestClient

from reporadio.web.app import create_app
from reporadio.web.events import ProtocolError, event, parse_client


# ------------------------------------------------------------- protocol

def test_parse_tune_in():
    type_, payload = parse_client(
        {"type": "tune_in", "url": "https://github.com/x/y", "mode": "desi"}
    )
    assert type_ == "tune_in"
    assert payload.url.endswith("x/y")
    assert payload.mode == "desi"
    assert payload.lang is None


def test_parse_caller_audio_defaults():
    _, payload = parse_client({"type": "caller_audio", "end": True})
    assert payload.end is True
    assert payload.data == ""


def test_parse_controls():
    for t in ("pause", "resume", "skip"):
        assert parse_client({"type": t})[0] == t


def test_unknown_type_rejected():
    with pytest.raises(ProtocolError) as err:
        parse_client({"type": "explode"})
    assert "tune_in" in str(err.value)


def test_missing_url_rejected():
    with pytest.raises(ProtocolError):
        parse_client({"type": "tune_in"})


def test_event_builder_guards_types():
    assert event("ready", repo="x/y")["type"] == "ready"
    with pytest.raises(AssertionError):
        event("nonsense")


# ------------------------------------------------------------- HTTP API

@pytest.fixture
def client(tmp_path, monkeypatch):
    from reporadio import config
    from reporadio.versions import registry

    settings = config.Settings(groq_api_key="x", data_dir=tmp_path, _env_file=None)
    monkeypatch.setattr(registry, "get_settings", lambda: settings)
    return TestClient(create_app())


def test_api_modes(client):
    modes = client.get("/api/modes").json()
    assert {m["key"] for m in modes} == {"standard", "casual", "fun_roast", "desi"}
    desi = next(m for m in modes if m["key"] == "desi")
    assert desi["freq"] == "106.3"
    assert "Haan G" in desi["greeting"]


def test_api_versions_empty(client):
    data = client.get("/api/versions/x/y").json()
    assert data == {"repo": "x/y", "versions": [], "episodes": 0}


def test_static_studio_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "REPORADIO" in page.text
    assert client.get("/app.js").status_code == 200
    assert client.get("/style.css").status_code == 200


def test_ws_rejects_unknown_message(client):
    with client.websocket_connect("/ws/session") as ws:
        ws.send_json({"type": "explode"})
        reply = ws.receive_json()
        assert reply["type"] == "error"
        assert "unknown message type" in reply["message"]
