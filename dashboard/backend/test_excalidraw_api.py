import base64

from fastapi.testclient import TestClient
import pytest

import dashboard_api
from excalidraw_client import WorkerError


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SECBRAIN_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SECBRAIN_HTTP_USER", "test")
    monkeypatch.setenv("SECBRAIN_HTTP_PASSWORD", "password")
    return TestClient(dashboard_api.app)


def auth():
    encoded = base64.b64encode(b"test:password").decode()
    return {"Authorization": f"Basic {encoded}"}


def test_dashboard_requires_basic_auth(client, monkeypatch):
    monkeypatch.setattr(dashboard_api, "request_diagram", lambda *args: pytest.fail("unauthorized call"))
    assert client.post("/api/excalidraw/generate", json={"prompt": "draw"}).status_code == 401


def test_dashboard_routes_request_without_internal_data(client, monkeypatch):
    captured = {}
    def fake(prompt, model):
        captured.update(prompt=prompt, model=model)
        return {"filename": "one.excalidraw", "relative_path": "Local/Work/excalidraw-dev/one.excalidraw",
                "element_count": 1, "model": model}
    monkeypatch.setattr(dashboard_api, "request_diagram", fake)
    monkeypatch.setattr(dashboard_api.runtime.ollama, "get_config", lambda: {"model": "gemma4:12b"})
    response = client.post("/api/excalidraw/generate", json={"prompt": "draw"}, headers=auth())
    assert response.status_code == 200
    assert captured == {"prompt": "draw", "model": "gemma4:12b"}
    assert "192.168." not in response.text
    assert "token" not in response.text


@pytest.mark.parametrize("code,status", [("worker_unavailable", 503), ("invalid_scene", 422)])
def test_worker_errors_are_public_codes(client, monkeypatch, code, status):
    monkeypatch.setattr(dashboard_api, "request_diagram", lambda *args: (_ for _ in ()).throw(WorkerError(code)))
    response = client.post("/api/excalidraw/generate", json={"prompt": "draw", "model": "m"}, headers=auth())
    assert response.status_code == status
    assert response.json()["detail"] == code


def test_client_rejects_malformed_worker_path(monkeypatch):
    import excalidraw_client
    import io
    import json
    monkeypatch.setenv("SECBRAIN_EXCALIDRAW_WORKER_URL", "http://excalidraw-dev:8090")
    monkeypatch.setenv("SECBRAIN_EXCALIDRAW_TOKEN", "test-token")
    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *_): self.close()
    malicious = {"filename": "../../secret", "relative_path": "Local/Work/excalidraw-dev/../../secret",
                 "element_count": 1, "model": "m"}
    monkeypatch.setattr(excalidraw_client, "urlopen", lambda *_args, **_kwargs: Response(json.dumps(malicious).encode()))
    with pytest.raises(WorkerError) as error:
        excalidraw_client.request_diagram("draw", "m")
    assert error.value.code == "invalid_worker_response"


def test_client_maps_timeout_without_leaking_url(monkeypatch):
    import excalidraw_client
    monkeypatch.setenv("SECBRAIN_EXCALIDRAW_WORKER_URL", "http://excalidraw-dev:8090")
    monkeypatch.setenv("SECBRAIN_EXCALIDRAW_TOKEN", "test-token")
    monkeypatch.setattr(excalidraw_client, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("secret-url")))
    with pytest.raises(WorkerError) as error:
        excalidraw_client.request_diagram("draw", "m")
    assert str(error.value) == "worker_unavailable"


def test_client_waits_beyond_two_model_attempts(monkeypatch):
    import excalidraw_client
    from excalidraw_generator.service import GENERATION_BUDGET_SECONDS
    monkeypatch.setenv("SECBRAIN_EXCALIDRAW_WORKER_URL", "http://excalidraw-dev:8090")
    monkeypatch.setenv("SECBRAIN_EXCALIDRAW_TOKEN", "test-token")
    seen = []
    def fake_open(_request, timeout):
        seen.append(timeout)
        raise TimeoutError()
    monkeypatch.setattr(excalidraw_client, "urlopen", fake_open)
    with pytest.raises(WorkerError):
        excalidraw_client.request_diagram("draw", "m")
    assert seen[0] >= GENERATION_BUDGET_SECONDS + 20
