"""Durable evidence for the last approved Watcher run."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RunValidationService:
    """Keep run evidence in Watcher state, separate from the Vault."""

    SCHEMA_VERSION = 1

    def __init__(self, vault_path: Path | str, state_dir: Path | str | None = None) -> None:
        self.vault = Path(vault_path).resolve()
        root = state_dir or os.environ.get("SECBRAIN_WATCHER_STATE_DIR") or Path.home() / ".local/state/secbrain-watcher"
        self.state = Path(root).expanduser().resolve()
        if self.state == self.vault or self.vault in self.state.parents:
            raise ValueError("Der Validierungs-State muss außerhalb der Vault liegen.")
        self.evidence_path = self.state / "last-run-validation.json"
        self.pending_path = self.state / "run-validation-pending.json"
        self._generation = 0

    def _read_vault_bytes(self, relative: str) -> bytes:
        """Read through directory descriptors so symlink swaps cannot escape the Vault."""
        if not relative or relative.startswith("/") or "\\" in relative:
            raise ValueError("Ungültiger Vault-Pfad.")
        parts = relative.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("Ungültiger Vault-Pfad.")
        directory = os.open(self.vault, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in parts[:-1]:
                next_directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = next_directory
            file_descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            with os.fdopen(file_descriptor, "rb") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise OSError("Vault-Pfad ist keine reguläre Datei.")
                return handle.read()
        finally:
            os.close(directory)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=self.state)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                os.fchmod(handle.fileno(), 0o600)
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, path)
            directory = os.open(self.state, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(name).unlink(missing_ok=True)

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def begin(self, run_id: str, kind: str) -> None:
        if kind not in {"inbox", "knowledge_radar"} or not run_id:
            raise ValueError("Ungültiger Validierungslauf.")
        marker = {"run_id": run_id, "kind": kind}
        if self.pending_path.exists():
            marker["previous_pending"] = self._read_json(self.pending_path) or {"unreadable": True}
        self._write_json(self.pending_path, marker)
        self._generation += 1

    def finish(self, run_id: str, kind: str, execution: dict, inputs: list[dict], proposal: dict | None) -> dict:
        pending = self._read_json(self.pending_path)
        if not pending or pending.get("run_id") != run_id or pending.get("kind") != kind:
            raise RuntimeError("Der Übernahmemarker passt nicht zum abgeschlossenen Lauf.")
        paths = ([*execution.get("archived", []), *execution.get("created", []),
                  execution.get("proposal_path"), execution.get("log")]
                 if kind == "inbox" else [execution.get("target"), execution.get("log")])
        files = {}
        for raw in paths:
            if not raw:
                continue
            path = Path(raw).resolve()
            relative = path.relative_to(self.vault)
            files[relative.as_posix()] = hashlib.sha256(self._read_vault_bytes(relative.as_posix())).hexdigest()
        graph = self.vault / "08 KI-Wissensbank" / "_index" / "graph.json"
        evidence = {
            "schema_version": self.SCHEMA_VERSION,
            "run_id": run_id,
            "kind": kind,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "files": files,
            "indexer": {"ok": bool(execution.get("indexer", {}).get("ok"))},
            "commit": execution.get("commit", {}),
            "graph_sha256": hashlib.sha256(self._read_vault_bytes(graph.relative_to(self.vault).as_posix())).hexdigest() if graph.is_file() else None,
        }
        self._write_json(self.evidence_path, evidence)
        self.pending_path.unlink()
        self._generation += 1
        return evidence

    def abort(self, run_id: str) -> None:
        pending = self._read_json(self.pending_path)
        if pending and pending.get("run_id") == run_id:
            previous = pending.get("previous_pending")
            if isinstance(previous, dict):
                self._write_json(self.pending_path, previous)
            else:
                self.pending_path.unlink()
            self._generation += 1

    def status(self) -> dict:
        pending = self.pending_path.exists()
        evidence = self._read_json(self.evidence_path)
        if not self._valid_evidence(evidence):
            return {"available": False, "pending": pending, "evidence": None,
                    "reason": "Kein prüfbarer Lauf vorhanden."}
        return {"available": True, "pending": pending, "evidence": evidence}

    def _safe_path(self, relative: str) -> Path | None:
        if not relative or relative.startswith("/") or "\\" in relative:
            return None
        parts = relative.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            return None
        try:
            path = (self.vault / relative).resolve()
        except (OSError, RuntimeError):
            return None
        return path if path != self.vault and self.vault in path.parents else None

    def _valid_evidence(self, value: dict | None) -> bool:
        if not isinstance(value, dict) or value.get("schema_version") != self.SCHEMA_VERSION:
            return False
        if (not isinstance(value.get("kind"), str) or value["kind"] not in {"inbox", "knowledge_radar"}
                or not isinstance(value.get("run_id"), str) or not value["run_id"]):
            return False
        completed = value.get("completed_at")
        if not isinstance(completed, str):
            return False
        try:
            datetime.fromisoformat(completed)
        except ValueError:
            return False
        files = value.get("files")
        if not isinstance(files, dict) or not files:
            return False
        for relative, digest in files.items():
            if (not isinstance(relative, str) or self._safe_path(relative) is None
                    or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
                return False
        if not isinstance(value.get("commit"), dict) or not isinstance(value.get("indexer"), dict):
            return False
        if value["indexer"].get("ok") is not True or not isinstance(value["commit"].get("ok"), bool):
            return False
        graph_hash = value.get("graph_sha256")
        return graph_hash is None or (isinstance(graph_hash, str) and bool(re.fullmatch(r"[0-9a-f]{64}", graph_hash)))

    @staticmethod
    def _check(identifier: str, status: str, detail: str, path: str | None = None) -> dict:
        result = {"id": identifier, "status": status, "detail": detail}
        if path is not None:
            result["path"] = path
        return result

    def recheck(self, qmd_status: dict) -> dict:
        generation = self._generation
        result = {**self.status(), "checked_at": datetime.now(timezone.utc).isoformat(),
                  "checks": [], "overall": "nicht prüfbar"}
        if not result["available"] or result["pending"]:
            return result
        evidence = result["evidence"]
        checks = result["checks"]
        for relative, expected in evidence["files"].items():
            path = self._safe_path(relative)
            if path is None:
                return {**result, "available": False, "evidence": None, "checks": [],
                        "reason": "Der Prüfnachweis enthält einen ungültigen Pfad."}
            try:
                current = hashlib.sha256(self._read_vault_bytes(relative)).hexdigest()
            except FileNotFoundError:
                checks.append(self._check("file", "fehlt", "Datei fehlt seit dem Lauf.", relative))
            except (OSError, ValueError):
                checks.append(self._check("file", "nicht prüfbar", "Datei kann nicht gelesen werden.", relative))
            else:
                status = "bestanden" if current == expected else "geändert"
                detail = "Inhalt stimmt mit dem Lauf überein." if current == expected else "Inhalt wurde seit dem Lauf geändert."
                checks.append(self._check("file", status, detail, relative))

        commit = evidence["commit"]
        if not commit.get("ok"):
            detail = str(commit.get("reason") or "Für diesen Lauf war kein Commit erforderlich.")
            checks.append(self._check("commit", "nicht prüfbar", detail))
        else:
            revision = str(commit.get("revision") or "")
            if not re.fullmatch(r"[0-9a-f]{7,64}", revision):
                checks.append(self._check("commit", "nicht prüfbar", "Commitkennung im Nachweis ist ungültig."))
            else:
                exists = subprocess.run(
                    ["git", "-C", str(self.vault), "cat-file", "-e", f"{revision}^{{commit}}"],
                    capture_output=True,
                )
                if exists.returncode:
                    checks.append(self._check("commit", "fehlt", "Abschluss-Commit ist nicht vorhanden."))
                else:
                    reachable = subprocess.run(
                        ["git", "-C", str(self.vault), "merge-base", "--is-ancestor", revision, "HEAD"],
                        capture_output=True,
                    )
                    status = "bestanden" if reachable.returncode == 0 else "geändert"
                    detail = "Commit ist in der aktuellen Historie." if status == "bestanden" else "Commit ist nicht mehr in der aktuellen Historie."
                    checks.append(self._check("commit", status, detail))

        graph_hash = evidence.get("graph_sha256")
        graph = self.vault / "08 KI-Wissensbank" / "_index" / "graph.json"
        if graph_hash is None:
            checks.append(self._check("graph", "nicht prüfbar", "Beim Lauf lag kein Indexer-Export vor."))
        else:
            try:
                content = self._read_vault_bytes(graph.relative_to(self.vault).as_posix())
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    raise ValueError("Indexer-Export ist kein Objekt.")
            except FileNotFoundError:
                checks.append(self._check("graph", "fehlt", "Indexer-Export fehlt."))
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                checks.append(self._check("graph", "nicht prüfbar", "Indexer-Export ist nicht lesbar."))
            else:
                status = "bestanden" if hashlib.sha256(content).hexdigest() == graph_hash else "geändert"
                detail = "Indexer-Export stimmt überein." if status == "bestanden" else "Indexer-Export wurde seit dem Lauf geändert."
                checks.append(self._check("graph", status, detail))

        qmd_ready = bool(qmd_status.get("available"))
        checks.append(self._check("qmd", "bestanden" if qmd_ready else "nicht prüfbar",
                                  "QMD ist aktuell verfügbar." if qmd_ready else "QMD ist aktuell nicht verfügbar."))
        if all(check["status"] == "bestanden" for check in checks):
            result["overall"] = "bestanden"
        elif any(check["status"] in {"fehlt", "geändert"} for check in checks):
            result["overall"] = "geändert"
        latest = self.status()
        if self._generation != generation or latest["pending"] != result["pending"] or latest["evidence"] != evidence:
            return {**latest, "checked_at": result["checked_at"], "checks": [], "overall": "nicht prüfbar",
                    "reason": "Während der Prüfung hat sich der Watcher-Lauf geändert."}
        return result
