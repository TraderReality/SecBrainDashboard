import base64
from pathlib import Path

from fastapi.testclient import TestClient

import dashboard_api
from loop.run_validation import RunValidationService


def _auth():
    value = base64.b64encode(b"tester:local-test-password").decode()
    return {"Authorization": f"Basic {value}"}


def _service(tmp_path: Path) -> RunValidationService:
    vault = tmp_path / "vault"
    archive = vault / "06 Archiv" / "note.md"
    note = vault / "08 KI-Wissensbank" / "note.md"
    log = vault / "08 KI-Wissensbank" / "_Log.md"
    proposal = vault / "08 KI-Wissensbank" / "_Vorschlaege" / "run.md"
    graph = vault / "08 KI-Wissensbank" / "_index" / "graph.json"
    for path, content in ((archive, b"abc"), (note, b"# Note\n"), (log, b"# Log\n"),
                          (proposal, b"status: umgesetzt\n"), (graph, b'{"nodes": []}\n')):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    service = RunValidationService(vault, tmp_path / "state")
    service.begin("RUN-API", "inbox")
    service.finish("RUN-API", "inbox", {
        "archived": [str(archive)], "created": [str(note)], "proposal_path": str(proposal),
        "log": str(log), "indexer": {"ok": True},
        "commit": {"ok": False, "reason": "Kein Git-Repository"},
    }, [{"name": "note.md", "content": "abc"}], {"path": str(proposal)})
    return service


def test_validation_routes_require_authentication(monkeypatch, tmp_path):
    monkeypatch.setenv("SECBRAIN_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SECBRAIN_HTTP_USER", "tester")
    monkeypatch.setenv("SECBRAIN_HTTP_PASSWORD", "local-test-password")
    monkeypatch.setattr(dashboard_api.watcher_orchestrator, "validation", _service(tmp_path), raising=False)
    with TestClient(dashboard_api.app) as client:
        assert client.get("/api/validation/last").status_code == 401
        assert client.post("/api/validation/last/recheck").status_code == 401
        assert client.get("/api/validation/last", headers=_auth()).status_code == 200


def test_validation_recheck_returns_historical_and_current_findings(monkeypatch, tmp_path):
    monkeypatch.setenv("SECBRAIN_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SECBRAIN_HTTP_USER", "tester")
    monkeypatch.setenv("SECBRAIN_HTTP_PASSWORD", "local-test-password")
    monkeypatch.setattr(dashboard_api.watcher_orchestrator, "validation", _service(tmp_path), raising=False)
    monkeypatch.setattr(dashboard_api.watcher_orchestrator, "is_active", lambda: False)
    monkeypatch.setattr(dashboard_api, "retrieval_status", lambda: {"available": True})
    with TestClient(dashboard_api.app) as client:
        historical = client.get("/api/validation/last", headers=_auth())
        current = client.post("/api/validation/last/recheck", headers=_auth())
    assert historical.status_code == 200
    assert historical.json()["evidence"]["run_id"] == "RUN-API"
    assert current.status_code == 200
    assert current.json()["checked_at"]
    assert any(item["id"] == "qmd" for item in current.json()["checks"])
    assert "/Users/" not in str(current.json())


def test_validation_recheck_rejects_active_run(monkeypatch, tmp_path):
    monkeypatch.setenv("SECBRAIN_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SECBRAIN_HTTP_USER", "tester")
    monkeypatch.setenv("SECBRAIN_HTTP_PASSWORD", "local-test-password")
    monkeypatch.setattr(dashboard_api.watcher_orchestrator, "validation", _service(tmp_path), raising=False)
    monkeypatch.setattr(dashboard_api.watcher_orchestrator, "is_active", lambda: True)
    with TestClient(dashboard_api.app) as client:
        assert client.post("/api/validation/last/recheck", headers=_auth()).status_code == 409


def test_validation_missing_or_corrupt_evidence_is_not_server_error(monkeypatch, tmp_path):
    monkeypatch.setenv("SECBRAIN_AUTH_REQUIRED", "1")
    monkeypatch.setenv("SECBRAIN_HTTP_USER", "tester")
    monkeypatch.setenv("SECBRAIN_HTTP_PASSWORD", "local-test-password")
    service = RunValidationService(tmp_path / "vault", tmp_path / "state")
    monkeypatch.setattr(dashboard_api.watcher_orchestrator, "validation", service, raising=False)
    with TestClient(dashboard_api.app) as client:
        assert client.get("/api/validation/last", headers=_auth()).json()["available"] is False
        service.state.mkdir()
        service.evidence_path.write_text("{broken", encoding="utf-8")
        response = client.get("/api/validation/last", headers=_auth())
        assert response.status_code == 200
        assert response.json()["available"] is False
