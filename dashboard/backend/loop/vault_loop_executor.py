"""Deterministic Vault operations for an explicitly approved Watcher run."""

from __future__ import annotations

import re
import os
import base64
import fcntl
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any


class VaultLoopExecutor:
    """Reads Inbox input and applies only code-defined, approved operations."""

    MAX_FILE_BYTES = 512 * 1024
    INDEX_LOCK_MARKER = b"SecBrain Watcher index transaction\n"

    def __init__(self, vault_path: Path | str) -> None:
        self.vault = Path(vault_path).resolve()
        self.inbox = self.vault / "01 Inbox"
        self.archive = self.vault / "06 Archiv"
        self.knowledge = self.vault / "08 KI-Wissensbank"
        self.proposals = self.knowledge / "_Vorschlaege"
        state_root = Path(os.environ.get("SECBRAIN_WATCHER_STATE_DIR") or Path.home() / ".local/state/secbrain-watcher")
        self.pending_proposals = state_root.expanduser().resolve() / "loop-proposals"
        self.resync_marker = state_root.expanduser().resolve() / "qmd-resync-required"
        self.transaction_journal = state_root.expanduser().resolve() / "loop-transaction.json"
        self.transaction_lock = state_root.expanduser().resolve() / "loop-transaction.lock"
        self._transaction_lock_fd: int | None = None
        if self.vault == self.pending_proposals or self.vault in self.pending_proposals.parents:
            raise ValueError("Der Watcher-State muss außerhalb der Vault liegen.")

    def snapshot_inbox(self) -> list[dict[str, Any]]:
        inputs = []
        for path in sorted(self.inbox.glob("*.md")):
            if path.name.startswith("."):
                continue
            size = path.stat().st_size
            if size > self.MAX_FILE_BYTES:
                raise ValueError(f"Inbox-Datei ist zu groß ({size} Byte): {path.name}")
            inputs.append({
                "name": path.name,
                "path": str(path),
                "content": path.read_text(encoding="utf-8"),
                "size": size,
            })
        if not inputs:
            raise ValueError("In 01 Inbox wurde keine Markdown-Datei gefunden.")
        return inputs

    def ensure_commit_ready(self) -> None:
        """Refuse a production run before analysis if an atomic final commit is impossible."""
        self._recover_interrupted_apply()
        probe = subprocess.run(
            ["git", "-C", str(self.vault), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True,
        )
        if probe.returncode != 0:
            self._ensure_qmd_synced()
            return
        for role, variable in (("Autor", "GIT_AUTHOR_IDENT"), ("Committer", "GIT_COMMITTER_IDENT")):
            identity = subprocess.run(
                ["git", "-C", str(self.vault), "var", variable],
                capture_output=True, text=True,
            )
            if identity.returncode != 0:
                raise RuntimeError(f"Git-Autorenkennung für {role} fehlt; der Watcher startet nicht.")
        staged = subprocess.run(
            ["git", "-C", str(self.vault), "diff", "--cached", "--name-only"],
            capture_output=True, text=True, check=True,
        ).stdout
        if staged.strip():
            raise RuntimeError("Die Vault enthält bereits gestagte Änderungen; der Watcher startet nicht.")
        status = subprocess.run(
            ["git", "-C", str(self.vault), "-c", "core.quotepath=false", "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        # New or edited Inbox documents are the intended input of a run. Everything
        # outside that boundary would make the final all-or-nothing commit ambiguous.
        unrelated = []
        for line in status:
            path = line[3:].strip().strip('"') if len(line) >= 4 else ""
            if not path.startswith("01 Inbox/"):
                unrelated.append(line)
        if unrelated:
            raise RuntimeError(
                "Die Vault enthält bereits ungesicherte Änderungen. Der Watcher startet nicht, "
                "weil sonst kein sauberer, atomarer Abschluss-Commit garantiert werden kann: "
                + "; ".join(unrelated[:5])
            )
        self._ensure_qmd_synced()

    def _ensure_qmd_synced(self) -> None:
        if not self.resync_marker.is_file():
            return
        index_dir = self.knowledge / "_index"
        before = self._snapshot_index(index_dir)
        try:
            self._run_indexer()
        except Exception as exc:
            raise RuntimeError(f"QMD-Wiederaufbau vor einem neuen Lauf fehlgeschlagen: {exc}") from exc
        finally:
            self._restore_index(index_dir, before)
        self.resync_marker.unlink()

    @staticmethod
    def _snapshot_index(index_dir: Path) -> dict[Path, bytes]:
        return {p.relative_to(index_dir): p.read_bytes() for p in index_dir.rglob("*") if p.is_file()} if index_dir.exists() else {}

    @staticmethod
    def _restore_index(index_dir: Path, before: dict[Path, bytes]) -> None:
        if index_dir.exists():
            for path in index_dir.rglob("*"):
                if path.is_file() and path.relative_to(index_dir) not in before:
                    path.unlink()
        for relative, value in before.items():
            path = index_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)

    def context(self, inputs: list[dict[str, Any]]) -> str:
        source_names = ", ".join(item["name"] for item in inputs)
        contents = []
        for item in inputs:
            contents.append(f"### ECHTE INBOX-DATEI: {item['name']}\n{item['content']}")
        inventory = []
        pages_by_stem: dict[str, Path] = {}
        for path in sorted(self.vault.rglob("*.md")):
            rel = path.relative_to(self.vault)
            if rel.parts[0] in {"01 Inbox", "06 Archiv", "07 Anhänge"}:
                continue
            if path.name.startswith("_"):
                continue
            inventory.append(str(rel))
            pages_by_stem.setdefault(path.stem.casefold(), path)
            if len(inventory) >= 120:
                break
        requested_links = []
        for item in inputs:
            requested_links.extend(re.findall(r"\[\[([^\]|#]+)", item["content"]))
        existing_pages = []
        seen: set[Path] = set()
        for target in requested_links:
            page = pages_by_stem.get(target.strip().casefold())
            if page and page not in seen:
                seen.add(page)
                body = page.read_text(encoding="utf-8")[:12000]
                existing_pages.append(
                    f"### GELESENE VAULT-SEITE: {page.relative_to(self.vault)}\n{body}"
                )
        return (
            f"Inbox-Snapshot (keine erfundenen Dateien): {source_names}\n\n"
            + "\n\n".join(contents)
            + "\n\n### BESTEHENDER VAULT-BESTAND (Pfadinventar)\n"
            + "\n".join(f"- {item}" for item in inventory)
            + "\n\n### INHALT DER VERLINKTEN, VORHANDENEN VAULT-SEITEN\n"
            + ("\n\n".join(existing_pages) or "(keine verlinkte Seite im Bestand gefunden)")
        )[:50000]

    def create_proposal(
        self, run_id: str, goal: str, author: str, inputs: list[dict[str, Any]], results: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.pending_proposals.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.pending_proposals / f"Watcher-Vorschlag-{run_id}.md"
        files = "\n".join(f"- `{item['name']}` ({item['size']} Byte)" for item in inputs)
        analysis = "\n\n".join(
            f"### Station {item['station_id']:02d} – {item['station']}\n\n{item['output']}"
            for item in results
        )
        content = (
            "---\n"
            f"id: watcher-vorschlag-{run_id.lower()}\n"
            "typ: vorschlag\nstatus: wartet-auf-freigabe\n"
            f"erstellt: {date.today().isoformat()}\n---\n\n"
            f"# Watcher-Vorschlag {run_id}\n\n## Aufgabe\n\n{goal}\n\n"
            f"## Fixierter Inbox-Snapshot\n\n{files}\n\n"
            f"## Bestätigte Herkunft\n\n- **Urheber:** {author or 'nicht angegeben'}\n\n"
            "## Vorgesehene, kontrollierte Umsetzung\n\n"
            "1. Rohdatei unverändert nach `06 Archiv` verschieben.\n"
            "2. Eine kuratierte Quellenseite mit Herkunft, Kernaussagen, Bestandsbezug und offenen Fragen anlegen.\n"
            "3. Abgeleitete Indexdaten einschließlich Vektor-Embeddings neu erzeugen.\n"
            "4. Den freigegebenen Lauf atomar committen.\n\n"
            f"## Stationsanalyse\n\n{analysis}\n"
        )
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        return {"path": str(path), "files": [item["name"] for item in inputs]}

    def reject(self, proposal: dict[str, Any]) -> None:
        self._set_proposal_status(Path(proposal["path"]), "abgelehnt")

    def apply(self, inputs: list[dict[str, Any]], proposal: dict[str, Any], author: str = "") -> dict[str, Any]:
        self.ensure_commit_ready()
        pending_path = Path(proposal["path"]).resolve()
        if pending_path.parent != self.pending_proposals or not pending_path.is_file():
            raise RuntimeError("Der freigegebene Vorschlag fehlt im getrennten Watcher-State.")
        approved_path = self.proposals / pending_path.name
        if approved_path.exists():
            raise RuntimeError(f"Freigegebener Vorschlag existiert bereits: {approved_path.name}")
        self.archive.mkdir(parents=True, exist_ok=True)
        self.knowledge.mkdir(parents=True, exist_ok=True)
        created: list[str] = []
        archived: list[str] = []

        # Validate the complete transaction before the first content mutation.
        operations = []
        for item in inputs:
            source = Path(item["path"]).resolve()
            if source.parent != self.inbox.resolve() or not source.is_file():
                raise RuntimeError(f"Fixierte Inbox-Datei fehlt oder wurde verändert: {item['name']}")
            if source.read_text(encoding="utf-8") != item["content"]:
                raise RuntimeError(f"Inbox-Datei wurde seit der Analyse verändert: {item['name']}")
            target = self.archive / item["name"]
            note_title = self._source_title(item["name"], author)
            note = self.knowledge / f"{note_title}.md"
            if target.exists() or note.exists():
                raise RuntimeError(f"Zieldatei existiert bereits; nichts wurde überschrieben: {item['name']}")
            operations.append((item, source, target, note))

        log_path = self.knowledge / "_Log.md"
        index_dir = self.knowledge / "_index"
        original = {path: path.read_bytes() if path.is_file() else None for _, source, target, note in operations for path in (source, target, note)}
        original[approved_path] = None
        original[log_path] = log_path.read_bytes() if log_path.is_file() else None
        original[pending_path] = pending_path.read_bytes()
        index_before = self._snapshot_index(index_dir)
        expected: dict[Path, bytes | None] = {path: value for path, value in original.items()}
        note_bytes_by_path = {}
        for item, source, target, note in operations:
            note_bytes = self._source_note(item, target, author).encode("utf-8")
            note_bytes_by_path[note] = note_bytes
            expected[note] = note_bytes
            expected[source] = None
            expected[target] = original[source]
        expected[approved_path] = self._status_bytes(original[pending_path], "umgesetzt")
        expected[pending_path] = expected[approved_path]
        log_entry = (
            f"\n- {datetime.now().astimezone().isoformat(timespec='seconds')} · Watcher: "
            f"{len(operations)} freigegebene Inbox-Datei(en) unverändert archiviert, "
            f"{len(operations)} Quellenseite(n) angelegt; Vorschlag `{approved_path.name}` umgesetzt.\n"
        )
        previous_log = original[log_path].decode("utf-8") if original[log_path] is not None else "# Log\n"
        expected[log_path] = (previous_log.rstrip() + "\n" + log_entry).encode("utf-8")
        git_head = self._git_head()
        self._write_transaction(original, expected, index_before, git_head)
        try:
            self._mark_qmd_resync()
            for item, source, target, note in operations:
                note.write_bytes(note_bytes_by_path[note])
                source.replace(target)
                created.append(str(note))
                archived.append(str(target))

            self.proposals.mkdir(parents=True, exist_ok=True)
            approved_path.write_bytes(expected[approved_path])
            log_path.write_bytes(expected[log_path])
            index = self._run_indexer()
            pending_path.write_bytes(expected[pending_path])
            self._check_expected(expected)
            paths = [path for _, source, target, note in operations for path in (source, target, note)]
            paths.extend((approved_path, log_path, index_dir))
            commit = self._commit_run(approved_path.stem, paths, expected)
            self.transaction_journal.unlink(missing_ok=True)
            self.resync_marker.unlink(missing_ok=True)
        except Exception as exc:
            self._rollback_apply(original, expected, index_dir, index_before, git_head, exc, allow_original=True)
            self.transaction_journal.unlink(missing_ok=True)
            raise RuntimeError(
                f"{exc} Vault auf den Stand vor Freigabe zurückgesetzt; "
                "QMD wird vor dem nächsten Lauf automatisch neu aufgebaut."
            ) from exc
        finally:
            self._release_transaction_lock()
        return {
            "created": created, "archived": archived, "log": str(log_path),
            "indexer": index, "commit": commit,
        }

    def apply_research(self, proposal: dict[str, Any]) -> dict[str, Any]:
        """Apply exactly one server-created Radar proposal after explicit approval."""
        if proposal.get("kind") != "knowledge_radar" or not proposal.get("proposal_id"):
            raise ValueError("Ungültiger Wissensradar-Vorschlag.")
        proposed = proposal.get("proposed_markdown")
        if not isinstance(proposed, str) or not proposed.strip() or len(proposed.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("Der freigegebene Markdown-Inhalt fehlt oder ist zu groß.")
        target = (self.vault / str(proposal.get("target") or "")).resolve()
        if self.vault not in target.parents or target.suffix.casefold() != ".md":
            raise ValueError("Das Radar-Ziel liegt außerhalb der Vault oder ist keine Markdown-Datei.")

        self.ensure_commit_ready()
        target_exists = bool(proposal.get("target_exists"))
        if target_exists != target.is_file():
            raise RuntimeError("Der Zustand der vorgeschlagenen Zielseite hat sich seit der Freigabe geändert.")
        original = target.read_text(encoding="utf-8") if target_exists else ""
        original_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()
        if original_hash != proposal.get("original_hash"):
            raise RuntimeError("Die Zielseite wurde seit Erstellung des Vorschlags verändert.")
        if hashlib.sha256(proposed.encode("utf-8")).hexdigest() != proposal.get("proposed_hash"):
            raise RuntimeError("Der freigegebene Radar-Inhalt stimmt nicht mit seinem Prüf-Hash überein.")

        log_path = self.knowledge / "_Log.md"
        index_dir = self.knowledge / "_index"
        original_bytes = {
            target: target.read_bytes() if target.is_file() else None,
            log_path: log_path.read_bytes() if log_path.is_file() else None,
        }
        index_before = self._snapshot_index(index_dir)
        previous_log = original_bytes[log_path].decode("utf-8") if original_bytes[log_path] is not None else "# Log\n"
        log_entry = (
            f"\n- {datetime.now().astimezone().isoformat(timespec='seconds')} · Wissensradar: "
            f"Vorschlag `{proposal['proposal_id']}` nach Station-06-Freigabe in "
            f"`{target.relative_to(self.vault)}` übernommen.\n"
        )
        expected_bytes = {
            target: proposed.encode("utf-8"),
            log_path: (previous_log.rstrip() + "\n" + log_entry).encode("utf-8"),
        }
        git_head = self._git_head()
        self._write_transaction(original_bytes, expected_bytes, index_before, git_head)
        try:
            self._mark_qmd_resync()
            self.knowledge.mkdir(parents=True, exist_ok=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(expected_bytes[target])
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_name, target)
            finally:
                Path(temporary_name).unlink(missing_ok=True)
            log_path.write_bytes(expected_bytes[log_path])
            index = self._run_indexer()
            self._check_expected(expected_bytes)
            commit = self._commit_run(
                f"Wissensradar-{proposal['proposal_id']}", [target, log_path, index_dir], expected_bytes,
            )
            self.transaction_journal.unlink(missing_ok=True)
            self.resync_marker.unlink(missing_ok=True)
        except Exception as exc:
            self._rollback_apply(original_bytes, expected_bytes, index_dir, index_before, git_head, exc, allow_original=True)
            self.transaction_journal.unlink(missing_ok=True)
            raise RuntimeError(f"{exc} Vault auf den Stand vor Freigabe zurückgesetzt; QMD wird erneut aufgebaut.") from exc
        finally:
            self._release_transaction_lock()
        return {
            "target": str(target), "log": str(log_path), "indexer": index, "commit": commit,
            "verified_hash": proposal["proposed_hash"], "wikilinks": list(proposal.get("wikilinks") or []),
        }

    def _source_note(self, item: dict[str, Any], archive_path: Path, author: str) -> str:
        title = self._title(item["name"])
        source_title = self._source_title(item["name"], author)
        identifier = self._slug(source_title)
        rel_archive = archive_path.relative_to(self.vault)
        links = list(dict.fromkeys(re.findall(r"\[\[([^\]|#]+)", item["content"])))
        relation_lines = [f"- Fachlicher Bezug: [[{link}]]." for link in links]
        relation_lines.append("- Kontrolliert durch den [[SecBrain-Aufbau|SecBrain-Pflege-Loop]].")
        key_points = self._key_points(item["content"])
        questions = self._open_questions(item["content"])
        return (
            "---\n"
            f"id: {identifier}\ntyp: quelle\ntitel: {source_title}\nstatus: entwurf\n"
            f"erstellt: {date.today().isoformat()}\ngeaendert: {date.today().isoformat()}\n"
            f"quelle: {rel_archive}\ntags: [quelle, inbox, watcher]\n---\n\n"
            f"# {source_title}\n\n## Herkunft\n\n"
            f"- **Rohquelle:** `{rel_archive}`\n"
            f"- **Urheber:** {author or 'nicht angegeben'}\n"
            f"- **Eingearbeitet:** {datetime.now().astimezone().isoformat(timespec='seconds')}\n"
            "- **Rohquelle verändert:** nein\n\n"
            "## Kernaussagen\n\n" + "\n".join(f"- {point}" for point in key_points) + "\n\n"
            "## Bezug zum Bestand\n\n" + "\n".join(relation_lines) + "\n\n"
            "## Offene Fragen\n\n" + "\n".join(f"- {question}" for question in questions) + "\n"
        )

    def _run_indexer(self) -> dict[str, Any]:
        indexer = self.vault / "09 Werkzeuge" / "indexer.py"
        if not indexer.is_file():
            raise RuntimeError(f"Indexer fehlt: {indexer}")
        env = dict(os.environ)
        env["SECBRAIN_VAULT"] = str(self.vault)
        env["SECBRAIN_QMD_EMBED"] = "0"
        process = subprocess.run(
            [sys.executable, str(indexer)], capture_output=True, text=True, timeout=600, env=env
        )
        if process.returncode != 0:
            raise RuntimeError((process.stderr or process.stdout or "Indexer fehlgeschlagen.")[-2000:])
        return {"ok": True, "output": process.stdout[-2000:]}

    @staticmethod
    def _title(filename: str) -> str:
        # Preserve intentional brand spelling and natural capitalization from the source filename.
        title = re.sub(r"\s+", " ", Path(filename).stem.replace("_", " ")).strip()
        return title[:1].upper() + title[1:]

    @staticmethod
    def _body(content: str) -> str:
        return re.sub(r"\A---\n.*?\n---\n", "", content, count=1, flags=re.DOTALL).strip()

    @classmethod
    def _key_points(cls, content: str) -> list[str]:
        points: list[str] = []
        for raw in cls._body(content).splitlines():
            line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", raw).strip()
            if not line or line.startswith("#") or line.endswith(":") or line.startswith("[["):
                continue
            if len(line) >= 24 and line not in points:
                points.append(line)
            if len(points) == 5:
                break
        return points or ["Die Rohquelle wurde unverändert archiviert und als neue Quelle erfasst."]

    @classmethod
    def _open_questions(cls, content: str) -> list[str]:
        questions = []
        for raw in cls._body(content).splitlines():
            line = re.sub(r"^\s*[-*]\s+", "", raw).strip()
            if line.endswith("?") and line not in questions:
                questions.append(line)
        return questions or ["Keine ausdrücklich formulierten offenen Fragen in der Rohquelle."]

    def _git_head(self) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(self.vault), "rev-parse", "HEAD"], capture_output=True, text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    @staticmethod
    def _status_bytes(content: bytes, status: str) -> bytes:
        text, count = re.subn(r"(?m)^status: .+$", f"status: {status}", content.decode("utf-8"), count=1)
        if count != 1:
            raise RuntimeError("Vorschlagsstatus fehlt.")
        return text.encode("utf-8")

    @staticmethod
    def _encoded(value: bytes | None) -> str | None:
        return base64.b64encode(value).decode("ascii") if value is not None else None

    @staticmethod
    def _decoded(value: str | None) -> bytes | None:
        return base64.b64decode(value, validate=True) if value is not None else None

    @staticmethod
    def _durable_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(name).unlink(missing_ok=True)

    def _mark_qmd_resync(self) -> None:
        self._durable_write(self.resync_marker, b"Indexer nach Freigabe erneut ausfuehren.\n")

    def _acquire_transaction_lock(self) -> int:
        self.transaction_lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(self.transaction_lock, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(descriptor)
            raise RuntimeError("Ein Watcher-Lauf bearbeitet die Vault bereits.") from exc
        return descriptor

    def _release_transaction_lock(self) -> None:
        if self._transaction_lock_fd is not None:
            os.close(self._transaction_lock_fd)
            self._transaction_lock_fd = None

    def _write_transaction(
        self, original: dict[Path, bytes | None], expected: dict[Path, bytes | None],
        index_before: dict[Path, bytes], git_head: str | None,
    ) -> None:
        self._transaction_lock_fd = self._acquire_transaction_lock()
        try:
            if self.transaction_journal.exists():
                raise RuntimeError("Ein offener Watcher-Lauf muss zuerst wiederhergestellt werden.")
            record = {
                "version": 1, "vault": str(self.vault), "git_head": git_head,
                "commit_oid": None,
                "original": {str(path): self._encoded(value) for path, value in original.items()},
                "expected": {str(path): self._encoded(value) for path, value in expected.items()},
                "index_before": {str(path): self._encoded(value) for path, value in index_before.items()},
            }
            self._durable_write(self.transaction_journal, json.dumps(record, sort_keys=True).encode("utf-8"))
        except Exception:
            self._release_transaction_lock()
            raise

    def _recover_interrupted_apply(self) -> None:
        if not self.transaction_journal.is_file():
            return
        descriptor = self._acquire_transaction_lock()
        try:
            self._recover_interrupted_apply_locked()
        finally:
            os.close(descriptor)

    def _recover_interrupted_apply_locked(self) -> None:
        if not self.transaction_journal.is_file():
            return
        record = json.loads(self.transaction_journal.read_text(encoding="utf-8"))
        if record.get("version") != 1 or record.get("vault") != str(self.vault):
            raise RuntimeError("Watcher-Transaktionsjournal passt nicht zur Vault; manueller Rückweg nötig.")
        allowed_state = self.pending_proposals
        original = {Path(name): self._decoded(value) for name, value in record["original"].items()}
        expected = {Path(name): self._decoded(value) for name, value in record["expected"].items()}
        if original.keys() != expected.keys() or any(
            path != path.resolve() or not (path.is_relative_to(self.vault) or path.is_relative_to(allowed_state))
            for path in original
        ):
            raise RuntimeError("Watcher-Transaktionsjournal enthält ungültige Pfade.")
        index_before = {Path(name): self._decoded(value) for name, value in record["index_before"].items()}
        index_dir = self.knowledge / "_index"
        if any(path.is_absolute() or ".." in path.parts for path in index_before):
            raise RuntimeError("Watcher-Transaktionsjournal enthält ungültige Indexpfade.")
        head = self._git_head()
        self._clear_interrupted_index_lock(head, record.get("commit_oid"))
        if record.get("commit_oid") and head == record["commit_oid"]:
            self._repair_index_after_commit()
            self.transaction_journal.unlink()
            self.resync_marker.unlink(missing_ok=True)
            return
        if head != record.get("git_head"):
            raise RuntimeError("Vault-HEAD änderte sich während eines unterbrochenen Watcher-Laufs; manueller Rückweg nötig.")
        self._rollback_apply(original, expected, index_dir, index_before, head, RuntimeError("Prozessabbruch"), allow_original=True)
        self.transaction_journal.unlink()

    def _check_expected(self, expected: dict[Path, bytes | None]) -> None:
        changed = [path for path, value in expected.items()
                   if (path.read_bytes() if path.is_file() else None) != value]
        if changed:
            raise RuntimeError("Laufdateien wurden während der Anwendung verändert: "
                               + ", ".join(path.name for path in changed[:5]))

    def _rollback_apply(
        self, original: dict[Path, bytes | None], expected: dict[Path, bytes | None],
        index_dir: Path, index_before: dict[Path, bytes], git_head: str | None, error: Exception,
        allow_original: bool = False,
    ) -> None:
        if self._git_head() != git_head:
            raise RuntimeError(f"Fehler nach Commit; Vault-HEAD hat sich geändert. Automatischer Rückweg gestoppt: {error}") from error
        owned = {str(path.relative_to(self.vault)) for path in original if path.is_relative_to(self.vault)}
        staged = subprocess.run(
            ["git", "-C", str(self.vault), "diff", "--cached", "--name-only", "-z"],
            capture_output=True, check=True,
        ).stdout.decode().split("\0") if git_head else []
        index_relative = str(index_dir.relative_to(self.vault))
        staged_owned = [path for path in staged if path in owned or path.startswith(index_relative + "/")]
        if staged_owned:
            raise RuntimeError(
                "Fehler nach Freigabe; fremde gestagte Laufdateien bleiben erhalten: "
                + ", ".join(staged_owned[:5]) + f". Ursache: {error}"
            ) from error
        conflicts = [str(path.relative_to(self.vault) if path.is_relative_to(self.vault) else path.name)
                     for path, value in expected.items()
                     if (path.read_bytes() if path.is_file() else None) not in ((value, original[path]) if allow_original else (value,))]
        if conflicts:
            raise RuntimeError(
                "Fehler nach Freigabe; geänderte Laufdateien wurden nicht überschrieben: "
                + ", ".join(conflicts[:5]) + f". Ursache: {error}"
            ) from error
        for path, value in original.items():
            if value is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)
        self._restore_index(index_dir, index_before)

    def _git_index_path(self) -> Path:
        git_dir = subprocess.run(
            ["git", "-C", str(self.vault), "rev-parse", "--absolute-git-dir"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return Path(git_dir) / "index"

    def _record_commit_oid(self, oid: str, index_hash: str) -> None:
        if not self.transaction_journal.is_file():
            return
        record = json.loads(self.transaction_journal.read_text(encoding="utf-8"))
        record["commit_oid"] = oid
        record["precommit_index_hash"] = index_hash
        self._durable_write(self.transaction_journal, json.dumps(record, sort_keys=True).encode("utf-8"))

    def _clear_interrupted_index_lock(self, head: str | None, commit_oid: str | None) -> None:
        if head is None:
            return
        index_path = self._git_index_path()
        temporary = index_path.with_name(index_path.name + ".watcher-temp")
        lock = index_path.with_name(index_path.name + ".lock")
        if lock.exists():
            if lock.read_bytes() != self.INDEX_LOCK_MARKER:
                raise RuntimeError("Unbekannte Git-Index-Sperre; automatischer Rückweg gestoppt.")
            lock.unlink()
        temporary.unlink(missing_ok=True)

    def _repair_index_after_commit(self) -> None:
        staged = subprocess.run(
            ["git", "-C", str(self.vault), "diff", "--cached", "--name-only", "-z"],
            capture_output=True, check=True,
        ).stdout
        if not staged:
            return
        record = json.loads(self.transaction_journal.read_text(encoding="utf-8"))
        index_path = self._git_index_path()
        lock = index_path.with_name(index_path.name + ".lock")
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        os.write(descriptor, self.INDEX_LOCK_MARKER)
        os.fsync(descriptor)
        temporary = index_path.with_name(index_path.name + ".watcher-temp")
        try:
            current_hash = hashlib.sha256(index_path.read_bytes()).hexdigest() if index_path.exists() else ""
            if current_hash != record.get("precommit_index_hash"):
                raise RuntimeError("Git-Index wurde nach dem Watcher-Commit verändert; gestagte Inhalte bleiben erhalten.")
            env = dict(os.environ, GIT_INDEX_FILE=str(temporary))
            subprocess.run(["git", "-C", str(self.vault), "read-tree", "HEAD"], env=env, check=True)
            os.replace(temporary, index_path)
        finally:
            os.close(descriptor)
            temporary.unlink(missing_ok=True)
            lock.unlink(missing_ok=True)

    def _commit_run(
        self, proposal_stem: str, paths: list[Path], content_bytes: dict[Path, bytes | None] | None = None,
    ) -> dict[str, Any]:
        probe = subprocess.run(
            ["git", "-C", str(self.vault), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True,
        )
        if probe.returncode != 0:
            return {"ok": False, "required": False, "reason": "Vault ist kein Git-Repository."}
        index_path = self._git_index_path()
        lock = index_path.with_name(index_path.name + ".lock")
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        os.write(descriptor, self.INDEX_LOCK_MARKER)
        os.fsync(descriptor)
        temporary = index_path.with_name(index_path.name + ".watcher-temp")
        try:
            staged = subprocess.run(
                ["git", "-C", str(self.vault), "diff", "--cached", "--name-only", "-z"],
                capture_output=True, check=True,
            ).stdout
            if staged:
                raise RuntimeError("Fremde gestagte Vault-Änderungen vor dem Abschluss-Commit erkannt.")
            old_head = self._git_head()
            if not old_head:
                raise RuntimeError("Vault-HEAD fehlt vor dem Abschluss-Commit.")
            index_hash = hashlib.sha256(index_path.read_bytes()).hexdigest() if index_path.exists() else ""
            env = dict(os.environ, GIT_INDEX_FILE=str(temporary))
            subprocess.run(["git", "-C", str(self.vault), "read-tree", "HEAD"], env=env, check=True)
            tracked = set(subprocess.run(
                ["git", "-C", str(self.vault), "ls-files", "-z"],
                capture_output=True, check=True,
            ).stdout.decode().rstrip("\0").split("\0"))
            selected: set[str] = set()
            for path in paths:
                relative = str(path.relative_to(self.vault))
                if path.is_dir():
                    selected.update(str(file.relative_to(self.vault)) for file in path.rglob("*") if file.is_file())
                    selected.update(name for name in tracked if name.startswith(relative + "/"))
                else:
                    selected.add(relative)
            for relative in sorted(selected):
                path = self.vault / relative
                value = content_bytes.get(path) if content_bytes is not None and path in content_bytes else (
                    path.read_bytes() if path.is_file() else None
                )
                if value is None:
                    subprocess.run(
                        ["git", "--literal-pathspecs", "-C", str(self.vault), "update-index", "--force-remove", "--", relative],
                        env=env, check=True,
                    )
                    continue
                oid = subprocess.run(
                    ["git", "-C", str(self.vault), "hash-object", "-w", "--stdin"],
                    input=value, capture_output=True, check=True,
                ).stdout.decode().strip()
                subprocess.run(
                    ["git", "--literal-pathspecs", "-C", str(self.vault), "update-index", "--add", "--cacheinfo", f"100644,{oid},{relative}"],
                    env=env, check=True,
                )
            tree = subprocess.run(
                ["git", "-C", str(self.vault), "write-tree"], env=env,
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            message = f"Loop {proposal_stem}: freigegebene Inbox-Quellen eingepflegt"
            commit = subprocess.run(
                ["git", "-C", str(self.vault), "commit-tree", tree, "-p", old_head],
                input=message + "\n", capture_output=True, text=True,
            )
            if commit.returncode != 0:
                raise RuntimeError((commit.stderr or commit.stdout or "Abschluss-Commit fehlgeschlagen.")[-2000:])
            revision = commit.stdout.strip()
            self._record_commit_oid(revision, index_hash)
            subprocess.run(["git", "-C", str(self.vault), "update-ref", "HEAD", revision, old_head], check=True)
            os.replace(temporary, index_path)
            return {"ok": True, "required": True, "revision": revision[:7]}
        finally:
            os.close(descriptor)
            temporary.unlink(missing_ok=True)
            lock.unlink(missing_ok=True)

    @classmethod
    def _source_title(cls, filename: str, author: str) -> str:
        suffix = f" von {author}" if author else ""
        return f"Quelle — {cls._title(filename)}{suffix}"

    @staticmethod
    def _slug(value: str) -> str:
        value = value.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
        return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value)).strip("-")

    @staticmethod
    def _set_proposal_status(path: Path, status: str) -> None:
        content = path.read_text(encoding="utf-8")
        content, count = re.subn(r"(?m)^status: .+$", f"status: {status}", content, count=1)
        if count != 1:
            raise RuntimeError(f"Vorschlagsstatus fehlt: {path}")
        path.write_text(content, encoding="utf-8")
