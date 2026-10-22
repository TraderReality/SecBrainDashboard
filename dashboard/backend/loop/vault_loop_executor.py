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

from scanner.write_guard import PlannedChange, VaultWriteGuard, vault_write_lock
from scanner.safe_files import FileState, file_state, mutate_file, _atomic_new_file, _parent_directory, _remove_file
from scanner.inventory import _FILE_FLAGS

BUNDLED_INDEXER = Path(__file__).with_name("vault_indexer.py")


class VaultLoopExecutor:
    """Reads Inbox input and applies only code-defined, approved operations."""

    MAX_FILE_BYTES = 512 * 1024
    INDEX_LOCK_MARKER = b"SecBrain Watcher index transaction\n"

    def __init__(self, vault_path: Path | str, guard: VaultWriteGuard) -> None:
        self.vault = Path(vault_path).resolve()
        self.guard = guard
        self.inbox = self.vault / "01 Inbox"
        self.archive = self.vault / "06 Archiv"
        self.knowledge = self.vault / "08 KI-Wissensbank"
        self.proposals = self.knowledge / "_Vorschlaege"
        state_root = guard.state_dir
        self.pending_proposals = state_root.expanduser().resolve() / "loop-proposals"
        self.resync_marker = state_root.expanduser().resolve() / "qmd-resync-required"
        self.transaction_journal = state_root.expanduser().resolve() / "loop-transaction.json"
        self.transaction_lock = state_root.expanduser().resolve() / "loop-transaction.lock"
        self._transaction_lock_fd: int | None = None
        self._file_states: dict[Path, FileState | None] = {}
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
        self._remove_path(self.resync_marker)

    @staticmethod
    def _read_bytes(path: Path) -> bytes | None:
        state = file_state(path)
        return state.data if state is not None else None

    @classmethod
    def _snapshot_index(cls, index_dir: Path) -> dict[Path, bytes]:
        return {p.relative_to(index_dir): cls._read_bytes(p)
                for p in index_dir.rglob("*") if not p.is_dir()} if index_dir.exists() else {}

    @staticmethod
    def _restore_index(index_dir: Path, before: dict[Path, bytes]) -> None:
        current = {p: file_state(p) for p in index_dir.rglob("*") if not p.is_dir()}
        for relative in before:
            current.setdefault(index_dir / relative, file_state(index_dir / relative))
        for path, state in current.items():
            mutate_file(path, before.get(path.relative_to(index_dir)), state)

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
        _atomic_new_file(path, content.encode("utf-8"))
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
        original = {path: self._read_bytes(path) for _, source, target, note in operations for path in (source, target, note)}
        original[approved_path] = None
        original[log_path] = self._read_bytes(log_path)
        original[pending_path] = self._read_bytes(pending_path)
        index_before = self._snapshot_index(index_dir)
        expected: dict[Path, bytes | None] = {path: value for path, value in original.items()}
        for item, source, target, note in operations:
            note_bytes = self._source_note(item, target, author).encode("utf-8")
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
        self._file_states = {path: file_state(path) for path in original}
        changes = self._planned_changes(original, expected)
        with self.guard.authorize(changes, pending_path.stem):
            self._check_expected(original)
            git_head = self._git_head()
            self._write_transaction(original, expected, index_before, git_head, pending_path.stem)
            try:
                self._mark_qmd_resync()
                for item, source, target, note in operations:
                    self._mutate(note, expected[note])
                    self._mutate(target, expected[target])
                    self._mutate(source, None)
                    created.append(str(note))
                    archived.append(str(target))

                self._mutate(approved_path, expected[approved_path])
                self._mutate(log_path, expected[log_path])
                index = self._run_indexer()
                self._mutate(pending_path, expected[pending_path])
                self._check_expected(expected)
                paths = [path for _, source, target, note in operations for path in (source, target, note)]
                paths.extend((approved_path, log_path, index_dir))
                commit = self._commit_run(approved_path.stem, paths, expected)
                self._remove_path(self.transaction_journal)
                self._remove_path(self.resync_marker)
            except Exception as exc:
                self._rollback_apply(original, expected, index_dir, index_before, git_head, exc, allow_original=True)
                self._remove_path(self.transaction_journal)
                raise RuntimeError(
                    f"{exc} Vault auf den Stand vor Freigabe zurückgesetzt; "
                    "QMD wird vor dem nächsten Lauf automatisch neu aufgebaut."
                ) from exc
            finally:
                self._release_transaction_lock()
        return {
            "created": created, "archived": archived, "log": str(log_path),
            "proposal_path": str(approved_path),
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
            target: self._read_bytes(target),
            log_path: self._read_bytes(log_path),
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
        self._file_states = {path: file_state(path) for path in original_bytes}
        changes = self._planned_changes(original_bytes, expected_bytes)
        with self.guard.authorize(changes, proposal["proposal_id"]):
            self._check_expected(original_bytes)
            git_head = self._git_head()
            self._write_transaction(original_bytes, expected_bytes, index_before, git_head, proposal["proposal_id"])
            try:
                self._mark_qmd_resync()
                self._mutate(target, expected_bytes[target])
                self._mutate(log_path, expected_bytes[log_path])
                index = self._run_indexer()
                self._check_expected(expected_bytes)
                commit = self._commit_run(
                    f"Wissensradar-{proposal['proposal_id']}", [target, log_path, index_dir], expected_bytes,
                )
                self._remove_path(self.transaction_journal)
                self._remove_path(self.resync_marker)
            except Exception as exc:
                self._rollback_apply(original_bytes, expected_bytes, index_dir, index_before, git_head, exc, allow_original=True)
                self._remove_path(self.transaction_journal)
                raise RuntimeError(f"{exc} Vault auf den Stand vor Freigabe zurückgesetzt; QMD wird erneut aufgebaut.") from exc
            finally:
                self._release_transaction_lock()
        return {
            "target": str(target), "log": str(log_path), "indexer": index, "commit": commit,
            "verified_hash": proposal["proposed_hash"], "wikilinks": list(proposal.get("wikilinks") or []),
        }

    def _planned_changes(
        self, original: dict[Path, bytes | None], expected: dict[Path, bytes | None],
    ) -> list[PlannedChange]:
        """Authorize Vault content; generated indexes never enter these maps.

        Keep proposed system paths in the plan so the guard rejects them. Only
        the pending proposal in external Watcher state is outside its scope.
        """
        changes = []
        for path, after in expected.items():
            if not path.is_relative_to(self.vault):
                continue
            relative = path.relative_to(self.vault)
            before = original[path]
            changes.append(PlannedChange(
                relative.as_posix(),
                "delete" if after is None else "create" if before is None else "replace",
                hashlib.sha256(before).hexdigest() if before is not None else None,
                after,
            ))
        return changes

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
            if not BUNDLED_INDEXER.is_file():
                raise RuntimeError(f"Indexer fehlt: {indexer}; Paket-Fallback fehlt: {BUNDLED_INDEXER}")
            indexer = BUNDLED_INDEXER
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
    def _remove_path(path: Path) -> None:
        mutate_file(path, None, file_state(path))

    @staticmethod
    def _durable_write(path: Path, data: bytes) -> None:
        mutate_file(path, data, file_state(path))

    @staticmethod
    def _ownership(state: FileState | None) -> dict:
        return {"identity": list(state.identity) if state is not None else None,
                "sha256": hashlib.sha256(state.data).hexdigest() if state is not None else None}

    def _save_progress(self, record: dict) -> None:
        approval = record["recovery_authorization"]["approval"]
        record["recovery_authorization"]["sha256"] = self._recovery_hash(record, approval)
        self._durable_write(self.transaction_journal, json.dumps(record, sort_keys=True).encode("utf-8"))

    def _mutate(self, path: Path, data: bytes | None) -> None:
        def prepare(next_state, temporary):
            record = json.loads(self._read_bytes(self.transaction_journal).decode("utf-8"))
            record["file_identities"] = self._identities()
            # The staged inode is known and durable before the named mutation.
            # Recovery accepts exactly the two ownership states of this transition.
            record["pending_mutation"] = {
                "path": str(path), "before": self._ownership(self._file_states[path]),
                "after": self._ownership(next_state),
                "temporary": str(temporary) if temporary is not None else None,
            }
            self._save_progress(record)

        self._file_states[path] = mutate_file(path, data, self._file_states[path], before_mutation=prepare)
        record = json.loads(self._read_bytes(self.transaction_journal).decode("utf-8"))
        record["file_identities"] = self._identities()
        record.pop("pending_mutation", None)
        self._save_progress(record)

    def _identities(self):
        return {str(path): list(state.identity) if state is not None else None
                for path, state in self._file_states.items()}

    def _mark_qmd_resync(self) -> None:
        self._durable_write(self.resync_marker, b"Indexer nach Freigabe erneut ausfuehren.\n")

    def _acquire_transaction_lock(self) -> int:
        with _parent_directory(self.transaction_lock, create=True) as directory:
            descriptor = os.open(self.transaction_lock.name,
                                 os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 0o600, dir_fd=directory)
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
        index_before: dict[Path, bytes], git_head: str | None, approval: str,
    ) -> None:
        self._transaction_lock_fd = self._acquire_transaction_lock()
        try:
            if self.transaction_journal.exists():
                raise RuntimeError("Ein offener Watcher-Lauf muss zuerst wiederhergestellt werden.")
            record = {
                "version": 1, "vault": str(self.vault), "git_head": git_head,
                "commit_oid": None, "file_identities": self._identities(),
                "original": {str(path): self._encoded(value) for path, value in original.items()},
                "expected": {str(path): self._encoded(value) for path, value in expected.items()},
                "index_before": {str(path): self._encoded(value) for path, value in index_before.items()},
            }
            # Created only inside the original transaction's successful authorization.
            # Bind approval to its full forward/rollback envelope, including state
            # preimages and derived-index restoration. Mutable commit metadata is
            # deliberately outside this binding.
            record["recovery_authorization"] = {
                "approval": approval, "sha256": self._recovery_hash(record, approval),
            }
            self._durable_write(self.transaction_journal, json.dumps(record, sort_keys=True).encode("utf-8"))
        except Exception:
            self._release_transaction_lock()
            raise

    @staticmethod
    def _recovery_hash(record: dict[str, Any], approval: str) -> str:
        envelope = {key: record[key] for key in (
            "version", "vault", "git_head", "original", "expected", "index_before",
        )}
        if "file_identities" in record:
            envelope["file_identities"] = record["file_identities"]
        if "pending_mutation" in record:
            envelope["pending_mutation"] = record["pending_mutation"]
        if "git_artifacts" in record:
            envelope["git_artifacts"] = record["git_artifacts"]
        envelope["approval"] = approval
        return hashlib.sha256(json.dumps(envelope, sort_keys=True).encode("utf-8")).hexdigest()

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
        record = json.loads(self._read_bytes(self.transaction_journal).decode("utf-8"))
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
        authorization = record.get("recovery_authorization")
        if (not isinstance(authorization, dict)
                or not isinstance(authorization.get("approval"), str)
                or not authorization["approval"].strip()
                or authorization.get("sha256") != self._recovery_hash(record, authorization["approval"])):
            raise RuntimeError("Gebundene Freigabe für die Wiederherstellung fehlt; manueller Rückweg nötig.")
        head = self._git_head()
        if record.get("commit_oid") and head == record["commit_oid"]:
            with vault_write_lock(self.guard.state_dir):
                if self._git_head() != head:
                    raise RuntimeError("Vault-HEAD änderte sich während der Wiederherstellung.")
                self._clear_interrupted_index_lock(head, record.get("commit_oid"))
                self._repair_index_after_commit()
                self._remove_path(self.transaction_journal)
                self._remove_path(self.resync_marker)
            return
        if head != record.get("git_head"):
            raise RuntimeError("Vault-HEAD änderte sich während eines unterbrochenen Watcher-Laufs; manueller Rückweg nötig.")
        identities = record.get("file_identities")
        if not isinstance(identities, dict) or set(identities) != {str(path) for path in original}:
            raise RuntimeError("Laufdatei-Identitäten fehlen; manueller Rückweg nötig.")
        pending = record.get("pending_mutation")
        pending_path = None
        if pending is not None:
            pending_path = Path(pending["path"])
            if (pending_path not in original
                    or pending["before"]["identity"] != identities[str(pending_path)]):
                raise RuntimeError("Ungültiger Dateiübergang im Watcher-Journal.")
            for side in ("before", "after"):
                digest = pending[side]["sha256"]
                candidates = (original[pending_path], expected[pending_path])
                if not any((hashlib.sha256(value).hexdigest() if value is not None else None) == digest
                           for value in candidates):
                    raise RuntimeError("Dateiübergang ist nicht an freigegebene Bytes gebunden.")
            temporary = pending.get("temporary")
            if temporary is not None:
                temporary = Path(temporary)
                if (temporary.parent != pending_path.parent
                        or not re.fullmatch(r"\.vault-[0-9a-f]{32}\.tmp", temporary.name)
                        or pending["after"]["identity"] is None):
                    raise RuntimeError("Ungültige temporäre Datei im Watcher-Journal.")
                value = next(value for value in (original[pending_path], expected[pending_path])
                             if value is not None and hashlib.sha256(value).hexdigest() == pending["after"]["sha256"])
                # A crash immediately after exclusive link leaves two links to the
                # owned staged inode. Remove only that exact, authorized scratch
                # file before the Guard inventories content for rollback.
                with vault_write_lock(self.guard.state_dir):
                    try:
                        _remove_file(temporary, FileState(value, tuple(pending["after"]["identity"])), max_links=2, missing_ok=True)
                    except FileNotFoundError:
                        pass
        states = {path: file_state(path) for path in original}
        for path, state in states.items():
            actual = self._ownership(state)
            if path == pending_path:
                valid = actual in (pending["before"], pending["after"])
            else:
                valid = actual["identity"] == identities[str(path)]
            if not valid:
                raise RuntimeError("Laufdatei-Identität geändert; manueller Rückweg nötig.")
        self._file_states = states
        current = {path: state.data if state is not None else None for path, state in states.items()}
        if any(current[path] not in (original[path], expected[path]) for path in original):
            raise RuntimeError("Geänderte Laufdateien werden bei der Wiederherstellung nicht überschrieben.")
        # A partial transaction may already contain some original bytes. Only the
        # actual current→original diff is authorized and restored; no invented
        # approval is granted to legacy journals or foreign byte values.
        restore = {path: value for path, value in original.items() if current[path] != value}
        changes = self._planned_changes(current, restore)
        # No content writes are needed when a crash preceded the first write
        # (or restoration finished before journal cleanup). Keep the validated
        # journal/derived-index cleanup possible even without a usable model.
        authorization_context = self.guard.authorize(changes, authorization["approval"]) if changes else vault_write_lock(self.guard.state_dir)
        with authorization_context:
            if self._git_head() != head:
                raise RuntimeError("Vault-HEAD änderte sich während der Wiederherstellung.")
            self._check_expected(current)
            self._clear_interrupted_index_lock(head, record.get("commit_oid"))
            self._rollback_apply(
                original, expected, index_dir, index_before, head, RuntimeError("Prozessabbruch"),
                allow_original=True, restore_only=set(restore),
            )
            self._remove_path(self.transaction_journal)

    def _check_expected(self, expected: dict[Path, bytes | None]) -> None:
        states = {path: file_state(path) for path in expected}
        changed = [path for path, value in expected.items()
                   if (states[path].data if states[path] is not None else None) != value
                   or (path in self._file_states and states[path] != self._file_states[path])]
        if changed:
            raise RuntimeError("Laufdateien wurden während der Anwendung verändert: "
                               + ", ".join(path.name for path in changed[:5]))

    def _rollback_apply(
        self, original: dict[Path, bytes | None], expected: dict[Path, bytes | None],
        index_dir: Path, index_before: dict[Path, bytes], git_head: str | None, error: Exception,
        allow_original: bool = False, restore_only: set[Path] | None = None,
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
        states = {path: file_state(path) for path in expected}
        conflicts = [str(path.relative_to(self.vault) if path.is_relative_to(self.vault) else path.name)
                     for path, value in expected.items()
                     if (states[path].data if states[path] is not None else None)
                     not in ((value, original[path]) if allow_original else (value,))
                     or states[path] != self._file_states.get(path)]
        if conflicts:
            raise RuntimeError(
                "Fehler nach Freigabe; geänderte Laufdateien wurden nicht überschrieben: "
                + ", ".join(conflicts[:5]) + f". Ursache: {error}"
            ) from error
        for path, value in original.items():
            if restore_only is not None and path not in restore_only:
                continue
            self._mutate(path, value)
        if self.transaction_journal.is_file():
            record = json.loads(self._read_bytes(self.transaction_journal).decode("utf-8"))
            if record.get("git_artifacts"):
                # Preparation can fail after exposing an owned lock but before
                # _commit_run obtains its cleanup token. Keep the journal until
                # every exposed Git artifact is reconciled as well as content.
                self._clear_interrupted_index_lock(git_head, record.get("commit_oid"))
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
        record = json.loads(self._read_bytes(self.transaction_journal).decode("utf-8"))
        record["commit_oid"] = oid
        record["precommit_index_hash"] = index_hash
        self._save_progress(record)

    def _git_mutate(self, path: Path, data: bytes | None, expected: FileState | None):
        """Predeclare every exposed Git artifact's exact before/after ownership."""
        def prepare(next_state, temporary):
            record = json.loads(self._read_bytes(self.transaction_journal).decode("utf-8"))
            record.setdefault("git_artifacts", {})[path.name] = {
                "before": self._ownership(expected), "after": self._ownership(next_state),
                "temporary": str(temporary) if temporary is not None else None,
                "after_bytes": self._encoded(data),
            }
            self._save_progress(record)
        installed = mutate_file(path, data, expected, before_mutation=prepare)
        record = json.loads(self._read_bytes(self.transaction_journal).decode("utf-8"))
        record.setdefault("git_artifacts", {})[path.name] = {
            "before": self._ownership(installed), "after": self._ownership(installed),
            "temporary": None, "after_bytes": self._encoded(data),
        }
        self._save_progress(record)
        return installed

    def _new_git_scratch(self) -> Path:
        # Git replaces its index inode internally. Keep that unjournaled work in
        # a private external directory; only our checked installation reaches .git.
        directory = Path(tempfile.mkdtemp(prefix=".watcher-git-", dir=self.guard.state_dir))
        return directory / "index"

    @staticmethod
    def _clean_git_scratch(temporary: Path, expected: FileState | None) -> None:
        if expected is not None:
            _remove_file(temporary, expected)
        try:
            with _parent_directory(temporary.parent) as directory:
                os.rmdir(temporary.parent.name, dir_fd=directory)
        except OSError:
            # A crashed/changed Git scratch area is never recursively deleted.
            # It lives outside the Vault and cannot block content recovery.
            pass

    def _clear_interrupted_index_lock(self, head: str | None, commit_oid: str | None) -> None:
        if head is None:
            return
        index_path = self._git_index_path()
        legacy_temporary = index_path.with_name(index_path.name + ".watcher-temp")
        lock = index_path.with_name(index_path.name + ".lock")
        record = json.loads(self._read_bytes(self.transaction_journal).decode("utf-8"))
        artifacts = record.get("git_artifacts", {})
        for path in (lock, legacy_temporary, index_path):
            owned = artifacts.get(path.name)
            if path == index_path and owned is None:
                continue
            if owned is not None and owned.get("temporary") is not None:
                temporary = Path(owned["temporary"])
                value = self._decoded(owned["after_bytes"])
                if (temporary.parent != path.parent
                        or not re.fullmatch(r"\.vault-[0-9a-f]{32}\.tmp", temporary.name)
                        or value is None
                        or hashlib.sha256(value).hexdigest() != owned["after"]["sha256"]):
                    raise RuntimeError("Ungültiger Git-Index-Übergang; manueller Rückweg nötig.")
                _remove_file(temporary, FileState(value, tuple(owned["after"]["identity"])),
                             max_links=2, missing_ok=True)
            state = file_state(path)
            if state is None and path != index_path:
                continue  # Already cleaned or crash before exclusive installation.
            if (not owned or self._ownership(state) not in (owned["before"], owned["after"])
                    or (path == lock and state.data != self.INDEX_LOCK_MARKER)):
                raise RuntimeError("Unbekannte Git-Index-Sperre oder temporäre Datei; automatischer Rückweg gestoppt.")
            if path != index_path:
                self._git_mutate(path, None, state)

    def _repair_index_after_commit(self) -> None:
        staged = subprocess.run(
            ["git", "-C", str(self.vault), "diff", "--cached", "--name-only", "-z"],
            capture_output=True, check=True,
        ).stdout
        if not staged:
            return
        record = json.loads(self._read_bytes(self.transaction_journal).decode("utf-8"))
        index_path = self._git_index_path()
        lock = index_path.with_name(index_path.name + ".lock")
        lock_state = self._git_mutate(lock, self.INDEX_LOCK_MARKER, None)
        with _parent_directory(lock) as directory:
            descriptor = os.open(lock.name, _FILE_FLAGS, dir_fd=directory)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        temporary = self._new_git_scratch()
        temporary_state = None
        try:
            index_before = file_state(index_path)
            current_hash = hashlib.sha256(index_before.data).hexdigest() if index_before else ""
            if current_hash != record.get("precommit_index_hash"):
                raise RuntimeError("Git-Index wurde nach dem Watcher-Commit verändert; gestagte Inhalte bleiben erhalten.")
            if file_state(temporary) is not None:
                raise RuntimeError("Unbekannte temporäre Git-Index-Datei; manueller Rückweg nötig.")
            env = dict(os.environ, GIT_INDEX_FILE=str(temporary))
            subprocess.run(["git", "-C", str(self.vault), "read-tree", "HEAD"], env=env, check=True)
            temporary_state = file_state(temporary)
            self._git_mutate(index_path, temporary_state.data, index_before)
        finally:
            os.close(descriptor)
            try:
                self._clean_git_scratch(temporary, temporary_state)
            finally:
                self._git_mutate(lock, None, lock_state)

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
        lock_state = self._git_mutate(lock, self.INDEX_LOCK_MARKER, None)
        with _parent_directory(lock) as directory:
            descriptor = os.open(lock.name, _FILE_FLAGS, dir_fd=directory)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        temporary = self._new_git_scratch()
        temporary_state = None
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
            index_before = file_state(index_path)
            index_hash = hashlib.sha256(index_before.data).hexdigest() if index_before else ""
            if file_state(temporary) is not None:
                raise RuntimeError("Unbekannte temporäre Git-Index-Datei; manueller Rückweg nötig.")
            env = dict(os.environ, GIT_INDEX_FILE=str(temporary))
            subprocess.run(["git", "-C", str(self.vault), "read-tree", "HEAD"], env=env, check=True)
            temporary_state = file_state(temporary)
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
                    self._read_bytes(path)
                )
                if value is None:
                    subprocess.run(
                        ["git", "--literal-pathspecs", "-C", str(self.vault), "update-index", "--force-remove", "--", relative],
                        env=env, check=True,
                    )
                    temporary_state = file_state(temporary)
                    continue
                oid = subprocess.run(
                    ["git", "-C", str(self.vault), "hash-object", "-w", "--stdin"],
                    input=value, capture_output=True, check=True,
                ).stdout.decode().strip()
                subprocess.run(
                    ["git", "--literal-pathspecs", "-C", str(self.vault), "update-index", "--add", "--cacheinfo", f"100644,{oid},{relative}"],
                    env=env, check=True,
                )
                temporary_state = file_state(temporary)
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
            temporary_state = file_state(temporary)
            self._record_commit_oid(revision, index_hash)
            if content_bytes is not None:
                self._check_expected(content_bytes)
            subprocess.run(["git", "-C", str(self.vault), "update-ref", "HEAD", revision, old_head], check=True)
            self._git_mutate(index_path, temporary_state.data, index_before)
            return {"ok": True, "required": True, "revision": revision}
        finally:
            os.close(descriptor)
            try:
                self._clean_git_scratch(temporary, temporary_state)
            finally:
                self._git_mutate(lock, None, lock_state)

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
        before = file_state(path)
        content = before.data.decode("utf-8")
        content, count = re.subn(r"(?m)^status: .+$", f"status: {status}", content, count=1)
        if count != 1:
            raise RuntimeError(f"Vorschlagsstatus fehlt: {path}")
        mutate_file(path, content.encode("utf-8"), before)
