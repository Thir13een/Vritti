from server import health, chat, ChatRequest


def test_health_endpoint():
    result = health()
    assert result["status"] in ("ok", "degraded")
    assert "backend" in result


def test_chat_returns_error_when_local_backends_fail(monkeypatch):
    def failing_generate(_cfg, _prompt):
        return {
            "answer": "",
            "source": "error",
            "api_polished": False,
            "reason": "local backend error: boom",
        }

    monkeypatch.setattr("server.generate", failing_generate)

    body = chat(ChatRequest(prompt="hi"))
    assert body["source"] == "error"
    assert body["api_polished"] is False
    assert "local backend error" in body["reason"]
