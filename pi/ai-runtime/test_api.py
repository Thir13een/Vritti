from server import health, chat, ChatRequest


def test_health_endpoint():
    assert health() == {"status": "ok"}


def test_chat_returns_error_when_local_backends_fail(monkeypatch):
    def failing_generate(_cfg, _prompt):
        return {
            "answer": "",
            "source": "error",
            "fallback_used": False,
            "reason": "local backend error: boom",
        }

    monkeypatch.setattr("server.generate", failing_generate)

    body = chat(ChatRequest(prompt="hi"))
    assert body["source"] == "error"
    assert body["fallback_used"] is False
    assert "local backend error" in body["reason"]
