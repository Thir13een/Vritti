from fastapi.testclient import TestClient

from server import app, cfg


client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


def test_chat_returns_error_when_local_backends_fail(monkeypatch):
    def failing_generate(_cfg, _prompt):
        return {
            "answer": "",
            "source": "error",
            "fallback_used": False,
            "reason": "local backend error: boom",
        }

    monkeypatch.setattr("server.generate", failing_generate)

    resp = client.post("/v1/chat", json={"prompt": "hi"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "error"
    assert body["fallback_used"] is False
    assert "local backend error" in body["reason"]

