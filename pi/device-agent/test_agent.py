import json

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


def test_post_heartbeat_includes_auth_header_when_token_set(monkeypatch):
    captured_req = {}

    class DummyResponse:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def capture_urlopen(req, timeout=15):
        captured_req["headers"] = dict(req.headers)
        captured_req["data"] = json.loads(req.data.decode("utf-8"))
        return DummyResponse()

    monkeypatch.setattr(agent, "GATEWAY_HEARTBEAT_URL", "http://gateway/v1/device/heartbeat")
    monkeypatch.setattr(agent, "DEVICE_ID", "pi-01")
    monkeypatch.setattr(agent, "DEVICE_TOKEN", "my-secret-token")
    monkeypatch.setattr(agent, "_missing_heartbeat_url_logged", False)
    monkeypatch.setattr(agent.urllib.request, "urlopen", capture_urlopen)
    monkeypatch.setattr(agent.logger, "debug", lambda *a, **kw: None)

    agent.post_heartbeat()

    assert captured_req["headers"]["Authorization"] == "Bearer my-secret-token"
    assert captured_req["headers"]["Content-type"] == "application/json"
    assert captured_req["data"]["device_id"] == "pi-01"
    assert isinstance(captured_req["data"]["timestamp"], int)


def test_post_heartbeat_omits_auth_header_when_no_token(monkeypatch):
    captured_req = {}

    class DummyResponse:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def capture_urlopen(req, timeout=15):
        captured_req["headers"] = dict(req.headers)
        return DummyResponse()

    monkeypatch.setattr(agent, "GATEWAY_HEARTBEAT_URL", "http://gateway/v1/device/heartbeat")
    monkeypatch.setattr(agent, "DEVICE_ID", "pi-01")
    monkeypatch.setattr(agent, "DEVICE_TOKEN", "")
    monkeypatch.setattr(agent, "_missing_heartbeat_url_logged", False)
    monkeypatch.setattr(agent.urllib.request, "urlopen", capture_urlopen)
    monkeypatch.setattr(agent.logger, "debug", lambda *a, **kw: None)

    agent.post_heartbeat()

    assert "Authorization" not in captured_req["headers"]


def test_post_heartbeat_payload_structure(monkeypatch):
    captured_data = {}

    class DummyResponse:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def capture_urlopen(req, timeout=15):
        captured_data.update(json.loads(req.data.decode("utf-8")))
        return DummyResponse()

    monkeypatch.setattr(agent, "GATEWAY_HEARTBEAT_URL", "http://gateway/v1/device/heartbeat")
    monkeypatch.setattr(agent, "DEVICE_ID", "pi-test-42")
    monkeypatch.setattr(agent, "DEVICE_TOKEN", "")
    monkeypatch.setattr(agent, "_missing_heartbeat_url_logged", False)
    monkeypatch.setattr(agent.urllib.request, "urlopen", capture_urlopen)
    monkeypatch.setattr(agent.logger, "debug", lambda *a, **kw: None)

    agent.post_heartbeat()

    assert captured_data["device_id"] == "pi-test-42"
    assert "timestamp" in captured_data
    assert isinstance(captured_data["timestamp"], int)
    assert captured_data["timestamp"] > 0


def test_post_heartbeat_sends_to_correct_url(monkeypatch):
    captured_url = {}

    class DummyResponse:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def capture_urlopen(req, timeout=15):
        captured_url["url"] = req.full_url
        return DummyResponse()

    monkeypatch.setattr(agent, "GATEWAY_HEARTBEAT_URL", "https://my-server.com/v1/device/heartbeat")
    monkeypatch.setattr(agent, "DEVICE_ID", "pi-01")
    monkeypatch.setattr(agent, "DEVICE_TOKEN", "")
    monkeypatch.setattr(agent, "_missing_heartbeat_url_logged", False)
    monkeypatch.setattr(agent.urllib.request, "urlopen", capture_urlopen)
    monkeypatch.setattr(agent.logger, "debug", lambda *a, **kw: None)

    agent.post_heartbeat()

    assert captured_url["url"] == "https://my-server.com/v1/device/heartbeat"
