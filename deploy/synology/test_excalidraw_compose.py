"""Guard the isolation contract of the two diagram workers."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent


def test_separate_workers_and_dashboard_links():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    services = compose["services"]
    for profile in ("main", "dev"):
        worker = services[f"excalidraw-{profile}"]
        dashboard = services[profile]
        assert worker["profiles"] == [profile]
        assert "ports" not in worker
        assert worker["read_only"] is True
        assert worker["cap_drop"] == ["ALL"]
        assert worker["user"] == "${SECBRAIN_UID}:${SECBRAIN_GID}"
        assert worker["mem_limit"]
        assert any(str(item).startswith("/tmp:") for item in worker["tmpfs"])
        assert len(worker["volumes"]) == 1
        mount = worker["volumes"][0]
        assert mount["source"].startswith(f"${{SECBRAIN_{profile.upper()}_EXCALIDRAW_DIR:?")
        assert mount["target"] == "/work/excalidraw"
        assert mount["bind"]["create_host_path"] is False
        assert dashboard["environment"]["SECBRAIN_EXCALIDRAW_WORKER_URL"] == f"http://excalidraw-{profile}:8090"
        assert "SECBRAIN_EXCALIDRAW_TOKEN" in dashboard["environment"]
        assert worker["environment"]["SECBRAIN_EXCALIDRAW_TOKEN"] == dashboard["environment"]["SECBRAIN_EXCALIDRAW_TOKEN"]
        assert worker["environment"]["SECBRAIN_EXCALIDRAW_SHARE_PREFIX"] == "Local/Work/excalidraw" + ("-dev" if profile == "dev" else "")


def test_worker_image_is_private():
    dockerfile = (ROOT / "Dockerfile.excalidraw-generator").read_text()
    assert "excalidraw_generator.api:app" in dockerfile
    assert "8090" in dockerfile
    assert "requirements-excalidraw-lock.txt" in dockerfile
    assert "excalidraw_generator" in dockerfile


def test_required_token_interpolation():
    compose = (ROOT / "compose.yaml").read_text()
    assert "SECBRAIN_MAIN_EXCALIDRAW_TOKEN:?" in compose
    assert "SECBRAIN_DEV_EXCALIDRAW_TOKEN:?" in compose
