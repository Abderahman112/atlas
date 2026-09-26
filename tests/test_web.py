import pytest
from fastapi.testclient import TestClient

from atlas.demo import FakeClaude, install_fake_gmail
from atlas.events import bus
from atlas.service import Assistant
from atlas.web import create_app

AUTH = {"Authorization": "Bearer secret-token"}


@pytest.fixture()
def client(tmp_path):
    install_fake_gmail()
    assistant = Assistant(FakeClaude(speed=1000), db_path=tmp_path / "t.db")
    assistant.proactive.register_jobs()
    with TestClient(create_app(assistant, "secret-token")) as c:
        yield c
    for s in bus.agents.values():  # the bus is process-wide; leave it clean for other tests
        s.paused = False


def test_everything_but_health_needs_the_token(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/state").status_code == 401
    assert client.get("/api/state", headers={"Authorization": "Bearer nope"}).status_code == 401
    state = client.get("/api/state", headers=AUTH).json()
    assert {"atlas", "schedule", "inbox", "school", "coop", "planner", "triage"} <= set(state["agents"])
    assert "morning:work" in state["jobs"]


def test_pause_blocks_an_agent_and_effort_is_validated(client):
    r = client.post("/api/agents/inbox", json={"paused": True}, headers=AUTH)
    assert r.json()["paused"] and r.json()["model"] == "claude-haiku-4-5"
    assert client.post("/api/agents/inbox", json={"effort": "extreme"}, headers=AUTH).status_code == 422
    assert client.post("/api/agents/inbox", json={"effort": "high"}, headers=AUTH).status_code == 422  # Haiku
    assert client.post("/api/agents/nobody", json={"paused": True}, headers=AUTH).status_code == 404

    reply = client.post("/api/chat", json={"text": "summarise my inbox"}, headers=AUTH).json()["reply"]
    assert "paused" in reply.lower()
    assert any(e["type"] == "blocked" and e["agent"] == "inbox" for e in bus.recent)


def test_chat_runs_the_team_and_records_history(client):
    reply = client.post("/api/chat", json={"text": "any deadlines?"}, headers=AUTH).json()["reply"]
    assert "deadline" in reply
    history = client.get("/api/history", headers=AUTH).json()
    assert [m["role"] for m in history[-2:]] == ["user", "assistant"]
    types = {e["type"] for e in bus.recent}
    assert {"message_in", "delegate", "tool_call", "reply", "message_out"} <= types


def test_jobs_can_be_switched_off_and_run_manually(client):
    r = client.post("/api/jobs/evening", json={"enabled": False}, headers=AUTH)
    assert r.json()["enabled"] is False
    assert client.post("/api/jobs/evening/run", headers=AUTH).json() == {"started": True}
    assert client.post("/api/jobs/nope/run", headers=AUTH).status_code == 404


def test_websocket_requires_token_then_streams_snapshot(client):
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"token": "secret-token"})
        assert ws.receive_json()["type"] == "snapshot"
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"token": "wrong"})
        with pytest.raises(Exception):
            ws.receive_json()
