import os
import subprocess
from pathlib import Path


ENTRYPOINT = Path(__file__).with_name("entrypoint.sh")


def _fake_qmd(tmp_path: Path) -> tuple[Path, Path]:
    log = tmp_path / "qmd.log"
    binary = tmp_path / "qmd"
    binary.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$QMD_TEST_LOG"\n'
        'if [ "$1 $2" = "collection list" ] && [ "${QMD_TEST_HAS_COLLECTION:-0}" = "1" ]; then\n'
        '  printf \'secbrain-dev (qmd://secbrain-dev/)\\n\'\n'
        "fi\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    return binary, log


def _run_entrypoint(tmp_path: Path, has_collection: bool) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    binary, log = _fake_qmd(tmp_path)
    vault = tmp_path / "vault"
    cache = tmp_path / "cache"
    config = tmp_path / "config"
    vault.mkdir()
    env = os.environ | {
        "SECBRAIN_QMD_BINARY": str(binary),
        "SECBRAIN_QMD_COLLECTION": "secbrain-dev",
        "SECBRAIN_VAULT_PATH": str(vault),
        "XDG_CACHE_HOME": str(cache),
        "XDG_CONFIG_HOME": str(config),
        "QMD_TEST_LOG": str(log),
        "QMD_TEST_HAS_COLLECTION": "1" if has_collection else "0",
    }
    result = subprocess.run(
        [str(ENTRYPOINT), "sh", "-c", "printf application-started"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, log.read_text(encoding="utf-8").splitlines()


def test_entrypoint_creates_missing_collection(tmp_path):
    result, calls = _run_entrypoint(tmp_path, has_collection=False)

    assert result.returncode == 0
    assert result.stdout == "application-started"
    assert calls == [
        "collection list",
        f"collection add {tmp_path / 'vault'} --name secbrain-dev --mask **/*.md",
        "status",
    ]


def test_entrypoint_updates_existing_collection(tmp_path):
    result, calls = _run_entrypoint(tmp_path, has_collection=True)

    assert result.returncode == 0
    assert calls == ["collection list", "update", "status"]


def test_entrypoint_rejects_missing_qmd(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    result = subprocess.run(
        [str(ENTRYPOINT), "true"],
        env=os.environ | {
            "SECBRAIN_QMD_BINARY": str(tmp_path / "missing-qmd"),
            "SECBRAIN_VAULT_PATH": str(vault),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "QMD-Binary wurde nicht gefunden" in result.stderr
