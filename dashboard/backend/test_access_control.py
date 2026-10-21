import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from access_control import BasicAuthMiddleware, validate_auth_configuration


@pytest.fixture
def protected_app(monkeypatch):
    monkeypatch.setenv("SECBRAIN_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SECBRAIN_HTTP_USER", "tester")
    monkeypatch.setenv("SECBRAIN_HTTP_PASSWORD", "local-test-password")
    app = FastAPI()
    app.add_middleware(BasicAuthMiddleware)

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def frontend():
        return {"frontend": True}

    @app.get("/api/vault")
    def vault():
        return {"private": True}

    @app.post("/api/vault/write")
    def write():
        return {"written": True}

    return app


def _authorization(user="tester", password="local-test-password"):
    encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def test_missing_credentials_fail_closed(monkeypatch):
    monkeypatch.setenv("SECBRAIN_AUTH_REQUIRED", "1")
    monkeypatch.delenv("SECBRAIN_HTTP_USER", raising=False)
    monkeypatch.delenv("SECBRAIN_HTTP_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="Zugangsdaten fehlen"):
        validate_auth_configuration()


def test_invalid_auth_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("SECBRAIN_AUTH_REQUIRED", "true")
    with pytest.raises(RuntimeError, match="muss 0 oder 1 sein"):
        validate_auth_configuration()


def test_watcher_startup_rejects_missing_credentials(monkeypatch):
    import dashboard_api

    monkeypatch.setenv("SECBRAIN_AUTH_REQUIRED", "1")
    monkeypatch.delenv("SECBRAIN_HTTP_USER", raising=False)
    monkeypatch.delenv("SECBRAIN_HTTP_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="Zugangsdaten fehlen"):
        with TestClient(dashboard_api.app):
            pass


def test_healthcheck_only_is_public(protected_app):
    with TestClient(protected_app) as client:
        assert client.get("/healthz").status_code == 200
        for method, path in (("get", "/"), ("get", "/api/vault"), ("post", "/api/vault/write")):
            response = getattr(client, method)(path)
            assert response.status_code == 401
            assert response.headers["www-authenticate"].startswith("Basic ")


def test_authentication_covers_reads_and_writes(protected_app):
    with TestClient(protected_app) as client:
        assert client.get("/", headers=_authorization()).status_code == 200
        assert client.get("/api/vault", headers=_authorization()).status_code == 200
        assert client.post("/api/vault/write", headers=_authorization()).status_code == 200
        assert client.post("/api/vault/write", headers=_authorization(password="wrong")).status_code == 401
        assert client.get("/", headers={"Authorization": "Basic invalid!"}).status_code == 401


def test_watcher_app_protects_frontend_and_api(monkeypatch, tmp_path):
    import dashboard_api

    monkeypatch.setenv("SECBRAIN_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SECBRAIN_HTTP_USER", "tester")
    monkeypatch.setenv("SECBRAIN_HTTP_PASSWORD", "local-test-password")
    monkeypatch.setattr(dashboard_api.runtime.vault, "path", tmp_path)

    upload = {"filename": "Authentifiziert.md", "content_base64": base64.b64encode(b"# Test\n").decode()}

    with TestClient(dashboard_api.app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/").status_code == 401
        assert client.get("/api/status").status_code == 401
        assert client.post("/api/watcher-loop/autonomous/approve").status_code == 401
        assert client.post("/api/vault/inbox/upload", json=upload).status_code == 401
        assert client.get("/", headers=_authorization()).status_code == 200
        assert client.post("/api/vault/inbox/upload", json=upload, headers=_authorization()).status_code == 200
        assert (tmp_path / "01 Inbox" / "Authentifiziert.md").read_text() == "# Test\n"
