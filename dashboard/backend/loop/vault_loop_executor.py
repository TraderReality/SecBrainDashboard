"""Deterministic Vault operations for an explicitly approved Watcher run."""

from __future__ import annotations

import re
import os
import hashlib
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any


class VaultLoopExecutor:
    """Reads Inbox input and applies only code-defined, approved operations."""

    MAX_FILE_BYTES = 512 * 1024

    def __init__(self, vault_path: Path | str) -> None:
        self.vault = Path(vault_path).resolve()
        self.inbox = self.vault / "01 Inbox"
        self.archive = self.vault / "06 Archiv"
        self.knowledge = self.vault / "08 KI-Wissensbank"
        self.proposals = self.knowledge / "_Vorschlaege"

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
        probe = subprocess.run(
            ["git", "-C", str(self.vault), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True,
        )
        if probe.returncode != 0:
            return
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
        self.proposals.mkdir(parents=True, exist_ok=True)
        path = self.proposals / f"Watcher-Vorschlag-{run_id}.md"
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
        path.write_text(content, encoding="utf-8")
        return {"path": str(path), "files": [item["name"] for item in inputs]}

    def reject(self, proposal: dict[str, Any]) -> None:
        self._set_proposal_status(Path(proposal["path"]), "abgelehnt")

    def apply(self, inputs: list[dict[str, Any]], proposal: dict[str, Any], author: str = "") -> dict[str, Any]:
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

        for item, source, target, note in operations:
            note.write_text(self._source_note(item, target, author), encoding="utf-8")
            source.replace(target)
            created.append(str(note))
            archived.append(str(target))

        self._set_proposal_status(Path(proposal["path"]), "umgesetzt")
        log_path = self.knowledge / "_Log.md"
        log_entry = (
            f"\n- {datetime.now().astimezone().isoformat(timespec='seconds')} · Watcher: "
            f"{len(archived)} freigegebene Inbox-Datei(en) unverändert archiviert, "
            f"{len(created)} Quellenseite(n) angelegt; Vorschlag `{Path(proposal['path']).name}` umgesetzt.\n"
        )
        previous_log = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Log\n"
        log_path.write_text(previous_log.rstrip() + "\n" + log_entry, encoding="utf-8")
        index = self._run_indexer()
        commit = self._commit_run(Path(proposal["path"]).stem)
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

        self.knowledge.mkdir(parents=True, exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(proposed)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, target)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

        log_path = self.knowledge / "_Log.md"
        previous_log = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Log\n"
        log_entry = (
            f"\n- {datetime.now().astimezone().isoformat(timespec='seconds')} · Wissensradar: "
            f"Vorschlag `{proposal['proposal_id']}` nach Station-06-Freigabe in "
            f"`{target.relative_to(self.vault)}` übernommen.\n"
        )
        log_path.write_text(previous_log.rstrip() + "\n" + log_entry, encoding="utf-8")
        index = self._run_indexer()
        final_hash = hashlib.sha256(target.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        if final_hash != proposal["proposed_hash"]:
            raise RuntimeError("Die übernommene Zielseite stimmt nach der Indexierung nicht mit dem Vorschlag überein.")
        commit = self._commit_run(f"Wissensradar-{proposal['proposal_id']}")
        return {
            "target": str(target), "log": str(log_path), "indexer": index, "commit": commit,
            "verified_hash": final_hash, "wikilinks": list(proposal.get("wikilinks") or []),
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
        env["SECBRAIN_QMD_EMBED"] = "1"
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

    def _commit_run(self, proposal_stem: str) -> dict[str, Any]:
        probe = subprocess.run(
            ["git", "-C", str(self.vault), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True,
        )
        if probe.returncode != 0:
            return {"ok": False, "required": False, "reason": "Vault ist kein Git-Repository."}
        subprocess.run(["git", "-C", str(self.vault), "add", "-A"], check=True)
        message = f"Loop {proposal_stem}: freigegebene Inbox-Quellen eingepflegt"
        commit = subprocess.run(
            ["git", "-C", str(self.vault), "commit", "-m", message],
            capture_output=True, text=True,
        )
        if commit.returncode != 0:
            raise RuntimeError((commit.stderr or commit.stdout or "Abschluss-Commit fehlgeschlagen.")[-2000:])
        revision = subprocess.run(
            ["git", "-C", str(self.vault), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return {"ok": True, "required": True, "revision": revision}

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
