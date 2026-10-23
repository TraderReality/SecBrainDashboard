from fastapi.testclient import TestClient
import pytest

from excalidraw_generator import api


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SECBRAIN_EXCALIDRAW_TOKEN", "private-token")
    monkeypatch.setenv("SECBRAIN_EXCALIDRAW_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("SECBRAIN_EXCALIDRAW_OLLAMA_URL", "http://192.168.0.116:11434")
    monkeypatch.setenv("SECBRAIN_EXCALIDRAW_SHARE_PREFIX", "Local/Work/excalidraw-dev")
    return TestClient(api.app)


def test_token_and_generation(client, monkeypatch):
    monkeypatch.setattr(api, "generate_diagram", lambda *args: {
        "filename": "one.excalidraw", "relative_path": "Local/Work/excalidraw-dev/one.excalidraw",
        "element_count": 2, "model": "gemma4:12b"})
    request = {"prompt": "draw", "model": "gemma4:12b"}
    assert client.post("/generate", json=request).status_code == 401
    assert client.post("/generate", json=request, headers={"X-Worker-Token": "wrong"}).status_code == 401
    response = client.post("/generate", json=request, headers={"X-Worker-Token": "private-token"})
    assert response.status_code == 200
    assert response.json()["element_count"] == 2
    assert client.get("/healthz").json() == {"status": "ok"}


def test_missing_token_configuration(client, monkeypatch):
    monkeypatch.delenv("SECBRAIN_EXCALIDRAW_TOKEN")
    assert client.post("/generate", json={"prompt": "x", "model": "y"}).status_code == 503


def test_missing_model(client):
    response = client.post("/generate", json={"prompt": "draw", "model": ""},
                           headers={"X-Worker-Token": "private-token"})
    assert response.status_code == 422


def test_busy_request(client, monkeypatch):
    assert api._generation_lock.acquire(blocking=False)
    try:
        response = client.post("/generate", json={"prompt": "draw", "model": "m"},
                               headers={"X-Worker-Token": "private-token"})
        assert response.status_code == 429
    finally:
        api._generation_lock.release()
