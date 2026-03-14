import agent


def test_post_heartbeat_logs_missing_url_only_once(monkeypatch):
    messages: list[str] = []

    monkeypatch.setattr(agent, "GATEWAY_HEARTBEAT_URL", "")
    monkeypatch.setattr(agent, "_missing_heartbeat_url_logged", False)
    monkeypatch.setattr(agent.logger, "info", lambda message, *args, **kwargs: messages.append(message))

    agent.post_heartbeat()
    agent.post_heartbeat()

    assert messages == ["heartbeat disabled because GATEWAY_HEARTBEAT_URL is not configured"]


def test_post_heartbeat_resets_missing_url_flag_after_success(monkeypatch):
    calls: list[tuple[str, str]] = []

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(agent, "GATEWAY_HEARTBEAT_URL", "http://gateway/v1/device/heartbeat")
    monkeypatch.setattr(agent, "DEVICE_ID", "device-a")
    monkeypatch.setattr(agent, "DEVICE_TOKEN", "token-1")
    monkeypatch.setattr(agent, "_missing_heartbeat_url_logged", True)
    monkeypatch.setattr(agent.urllib.request, "urlopen", lambda req, timeout=15: DummyResponse())
    monkeypatch.setattr(agent.logger, "debug", lambda message, *args, **kwargs: calls.append((message, kwargs["extra"]["device_id"])))

    agent.post_heartbeat()

    assert agent._missing_heartbeat_url_logged is False
    assert calls == [("heartbeat sent", "device-a")]
