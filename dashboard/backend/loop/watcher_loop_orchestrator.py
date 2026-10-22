"""Guarded coordination for the twelve Watcher stations."""

from __future__ import annotations

from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Callable

from guardian_rules import chat_context
from loop.run_validation import RunValidationService
from loop.vault_loop_executor import VaultLoopExecutor
from loop.watcher_loop_runtime import STATION_NAMES, WatcherLoopRuntime
from scanner.write_guard import VaultWriteGuard
from vault_retrieval_service import public_retrieval, retrieve_vault_context


class WatcherLoopOrchestrator:
    """Analyzes real Inbox files, pauses for approval, then applies safe actions."""

    def __init__(
        self, runtime: WatcherLoopRuntime, chat: Callable[..., dict[str, Any]], vault_path: str,
        retriever: Callable[..., dict[str, Any]] = retrieve_vault_context,
    ) -> None:
        self._runtime, self._chat = runtime, chat
        self._retriever = retriever
        self.validation = RunValidationService(vault_path)
        guard = VaultWriteGuard(
            Path(vault_path).resolve(), self.validation.state, chat, lambda: self._model,
        )
        self._executor = VaultLoopExecutor(vault_path, guard)
        self._lock, self._stop = Lock(), Event()
        self._thread: Thread | None = None
        self._state, self._goal, self._author, self._model, self._error = "idle", "", "", "", ""
        self._inputs: list[dict[str, Any]] = []
        self._results: list[dict[str, Any]] = []
        self._proposal: dict[str, Any] | None = None
        self._execution: dict[str, Any] | None = None
        self._retrieval: dict[str, Any] = {}
        self._validation_error = ""

    def start(self, goal: str, model: str, author: str = "") -> dict[str, Any]:
        goal, model = " ".join(str(goal).split()), str(model).strip()
        author = " ".join(str(author).split())
        if len(author) > 120 or any(char in author for char in "<>/\\"):
            raise ValueError("Der Urhebername enthält ungültige Zeichen oder ist zu lang.")
        if not goal:
            raise ValueError("Für den autonomen Lauf wird eine Aufgabe benötigt.")
        if not model:
            raise ValueError("Für den autonomen Lauf muss ein Modell gewählt sein.")
        with self._lock:
            if self._active_locked() or self._state == "awaiting_approval":
                raise RuntimeError("Ein Watcher-Lauf ist bereits aktiv oder wartet auf Freigabe.")
            self._model = model
            self._executor.ensure_commit_ready()
            inputs = self._executor.snapshot_inbox()
            self._runtime.start(model)
            self._stop.clear()
            self._state, self._goal, self._author, self._model = "running", goal, author, model
            self._inputs, self._results = inputs, []
            self._proposal = self._execution = None
            self._retrieval = {}
            self._error = ""
            self._validation_error = ""
            self._thread = Thread(target=self._run_analysis, daemon=True)
            self._thread.start()
            return self._status_locked()

    def approve(self) -> dict[str, Any]:
        with self._lock:
            if self._state != "awaiting_approval" or not self._proposal:
                raise RuntimeError("Es liegt kein freizugebender Vorschlag vor.")
            self._state = "applying"
            self._stop.clear()
            target = self._run_approved_research if self._proposal.get("kind") == "knowledge_radar" else self._run_approved
            self._thread = Thread(target=target, daemon=True)
            self._thread.start()
            return self._status_locked()

    def reject(self) -> dict[str, Any]:
        with self._lock:
            if self._state != "awaiting_approval" or not self._proposal:
                raise RuntimeError("Es liegt kein ablehnbarer Vorschlag vor.")
            proposal = dict(self._proposal)
        if proposal.get("kind") != "knowledge_radar":
            self._executor.reject(proposal)
        with self._lock:
            self._state = "rejected"
            self._runtime.stop()
            return self._status_locked()

    def stage_research_proposal(self, proposal: dict[str, Any], model: str) -> dict[str, Any]:
        if proposal.get("kind") != "knowledge_radar" or not proposal.get("proposal_id"):
            raise ValueError("Ungültiger Wissensradar-Vorschlag.")
        model = str(model).strip()
        if not model:
            raise ValueError("Für den autonomen Lauf muss ein Modell gewählt sein.")
        with self._lock:
            if self._active_locked() or self._state == "awaiting_approval":
                raise RuntimeError("Ein Watcher-Lauf ist bereits aktiv oder wartet auf Freigabe.")
            self._model = model
            self._executor.ensure_commit_ready()
            self._runtime.start_at(model, 6, "Kontrollierter Wissensradar-Vorschlag wurde direkt an Station 06 übergeben.")
            self._state, self._goal, self._author, self._model = (
                "awaiting_approval", proposal["candidate"]["title"], "Wissensradar", model
            )
            self._inputs = []
            self._proposal = dict(proposal)
            self._execution = None
            self._error = ""
            self._validation_error = ""
            self._results = [{
                "station_id": 5, "station": STATION_NAMES[4], "next_station": 6,
                "output": (
                    f"Wissensradar-Vorschlag {proposal['proposal_id']}\n"
                    f"Operation: {proposal['operation']}\nZiel: {proposal['target']}\n"
                    f"Vertrauen: {proposal['confidence']} %\nKonflikte: {len(proposal['conflicts'])}\n\n"
                    f"{proposal['markdown_diff']}"
                ),
            }]
            return self._status_locked()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._active_locked():
                self._state = "stopping"
                self._stop.set()
            return self._status_locked()

    def is_active(self) -> bool:
        with self._lock:
            return self._active_locked()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_locked()

    def _run_analysis(self) -> None:
        try:
            context = self._executor.context(self._inputs)
            retrieval_query = self._goal + " " + " ".join(
                str(item.get("content") or "")[:2_500] for item in self._inputs
            )
            retrieval = self._retriever(retrieval_query, max_results=6, max_chars=14_000)
            with self._lock:
                self._retrieval = public_retrieval(retrieval)
            if retrieval.get("context"):
                context += (
                    "\n\nRELEVANTER BESTAND VIA QMD (READ-ONLY):\n"
                    + retrieval["context"]
                )
            for station_id in range(1, 6):
                if self._stop.is_set():
                    self._finish("stopped")
                    return
                self._run_model_station(station_id, context)
            run_id = str(self._runtime.status()["run_id"])
            proposal = self._executor.create_proposal(run_id, self._goal, self._author, self._inputs, self._results)
            with self._lock:
                self._proposal, self._state = proposal, "awaiting_approval"
        except Exception as exc:
            self._fail(exc)

    def _run_approved(self) -> None:
        try:
            self._complete_code_station(6, "Freigabe wurde ausdrücklich über die Watcher-Oberfläche erteilt.")
            run_id = str(self._runtime.status()["run_id"])
            self.validation.begin(run_id, "inbox")
            try:
                execution = self._executor.apply(self._inputs, self._proposal or {}, self._author)
            except Exception:
                if not self._executor.transaction_journal.exists():
                    self.validation.abort(run_id)
                raise
            with self._lock:
                self._execution = execution
            try:
                self.validation.finish(run_id, "inbox", execution, self._inputs, self._proposal)
            except Exception:
                with self._lock:
                    self._validation_error = "Der Lauf wurde übernommen, aber der Prüfnachweis konnte nicht gespeichert werden."
            self._complete_code_station(7, f"{len(execution['archived'])} Rohdatei(en) archiviert und {len(execution['created'])} Quellenseite(n) angelegt.")
            self._complete_code_station(8, "Indexer erfolgreich ausgeführt; abgeleitete Sichten erneuert.")
            self._complete_code_station(9, "Quellenseiten mit Herkunft und Pflege-Loop verknüpft.")
            self._complete_code_station(10, "Fixierte Quellen, Zielkonflikte und Indexer-Rückgabe geprüft.")
            self._complete_code_station(11, "Umsetzung im freigegebenen Vorschlag und im Vault-Log protokolliert.")
            commit = execution["commit"]
            commit_note = (
                f" Abschluss-Commit: {commit['revision']}." if commit.get("ok")
                else f" Kein Commit erforderlich: {commit.get('reason', 'nicht anwendbar')}"
            )
            self._complete_code_station(12, "Übernahme abgeschlossen: " + ", ".join(item["name"] for item in self._inputs) + "." + commit_note)
            self._finish("completed")
        except Exception as exc:
            self._fail(exc)

    def _run_approved_research(self) -> None:
        try:
            self._complete_code_station(6, "Radar-Einpflegevorschlag wurde ausdrücklich freigegeben.")
            run_id = str(self._runtime.status()["run_id"])
            self.validation.begin(run_id, "knowledge_radar")
            try:
                execution = self._executor.apply_research(self._proposal or {})
            except Exception:
                if not self._executor.transaction_journal.exists():
                    self.validation.abort(run_id)
                raise
            with self._lock:
                self._execution = execution
            try:
                self.validation.finish(run_id, "knowledge_radar", execution, [], self._proposal)
            except Exception:
                with self._lock:
                    self._validation_error = "Der Lauf wurde übernommen, aber der Prüfnachweis konnte nicht gespeichert werden."
            target = execution["target"]
            self._complete_code_station(7, f"Freigegebenen Markdown-Inhalt atomar in {target} übernommen.")
            self._complete_code_station(8, "Indexer erfolgreich ausgeführt; abgeleitete Sichten erneuert.")
            self._complete_code_station(9, f"{len(execution['wikilinks'])} vorgeschlagene Wikilink(s) im freigegebenen Inhalt berücksichtigt.")
            self._complete_code_station(10, f"Zielinhalt gegen Prüf-Hash {execution['verified_hash'][:12]} verifiziert.")
            self._complete_code_station(11, "Radar-Übernahme im Vault-Log protokolliert.")
            commit = execution["commit"]
            commit_note = (
                f"Abschluss-Commit: {commit['revision']}." if commit.get("ok")
                else f"Kein Commit erforderlich: {commit.get('reason', 'nicht anwendbar')}"
            )
            self._complete_code_station(12, f"Radar-Einpflege vollständig abgeschlossen. {commit_note}")
            self._finish("completed")
        except Exception as exc:
            self._fail(exc)

    def _run_model_station(self, station_id: int, context: str) -> None:
        request = self._runtime.begin(self._model)
        prior = "\n\n".join(f"Station {item['station_id']:02d}: {item['output']}" for item in self._results)[-16000:]
        try:
            result = self._chat(messages=chat_context(station_id) + [{
                "role": "user", "content": self._station_prompt(station_id, context, prior)
            }], model=self._model)
            output = str(result.get("message", {}).get("content", "")).strip()
            if not output:
                raise RuntimeError(f"Station {station_id:02d} lieferte keine Antwort.")
            if station_id == 1 and self._retrieval.get("hits"):
                sources = "\n".join(
                    f"- {hit['path']} (Relevanz {hit['score']:.3f})"
                    for hit in self._retrieval["hits"]
                )
                output += "\n\nVault-Quellen via QMD (read-only):\n" + sources
            transition = self._runtime.complete(request, output)
            self._add_result(station_id, output, transition["next_station"])
        except Exception:
            self._runtime.fail(request, "Stationsverarbeitung fehlgeschlagen.")
            raise

    def _complete_code_station(self, station_id: int, output: str) -> None:
        request = self._runtime.begin(self._model)
        if request.station_id != station_id:
            self._runtime.fail(request, "Unerwartete Stationsreihenfolge.")
            raise RuntimeError(f"Erwartet Station {station_id:02d}, erhalten {request.station_id:02d}.")
        transition = self._runtime.complete(request, output)
        self._add_result(station_id, output, transition["next_station"])

    def _station_prompt(self, station_id: int, context: str, prior: str) -> str:
        return (
            "SECBrain-Watcher-Analyse. Verwende ausschließlich die nachfolgend tatsächlich gelesenen Dateien; "
            "erfinde keine Dateinamen, IDs, Anzahlen oder Aktionen. Du analysierst nur und führst selbst keine "
            f"Schreib- oder Systemaktion aus.\nAufgabe: {self._goal}\n"
            f"Vom Menschen bestätigter Urheber: {self._author or 'nicht angegeben'}\n"
            f"Station {station_id:02d} – {STATION_NAMES[station_id - 1]}\n\n"
            f"ECHTER VAULT-KONTEXT:\n{context}\n\nBISHERIGE STATIONSERGEBNISSE:\n{prior or '(keine)'}\n\n"
            "Liefere eine kurze, prüfbare Arbeitsnotiz. Kennzeichne Unsicherheit ausdrücklich."
            " Eine im Abschnitt 'GELESENE VAULT-SEITE' enthaltene Seite ist direkt einsehbar und muss in "
            "Station 02 bis 04 inhaltlich berücksichtigt werden. Eine fehlende Software, ein fehlendes Modell "
            "oder eine noch nicht gebaute Funktion ist eine Lücke beziehungsweise Abhängigkeit, aber nur dann "
            "ein Konflikt, wenn zwei vorhandene Aussagen einander widersprechen. Station 05 darf ausschließlich "
            "die fest programmierte Umsetzung vorschlagen: Rohquelle archivieren, eine kuratierte Quellenseite "
            "mit Herkunft, Kernaussagen, Bestandsbezug und offenen Fragen anlegen, indexieren und committen."
        )

    def _add_result(self, station_id: int, output: str, next_station: int) -> None:
        with self._lock:
            self._results.append({"station_id": station_id, "station": STATION_NAMES[station_id - 1], "next_station": next_station, "output": output})

    def _fail(self, exc: Exception) -> None:
        with self._lock:
            self._error, self._state = str(exc), "failed"

    def _finish(self, state: str) -> None:
        with self._lock:
            self._state = state

    def _active_locked(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _status_locked(self) -> dict[str, Any]:
        return {
            "state": self._state, "active": self._active_locked(),
            "approval_required": self._state == "awaiting_approval",
            "goal": self._goal or None, "author": self._author or None,
            "inputs": [item["name"] for item in self._inputs],
            "proposal": self._proposal, "execution": self._execution,
            "completed_stations": len(self._results), "results": self._results[-12:],
            "vault_retrieval": self._retrieval,
            "error": self._error or None,
            "validation_error": self._validation_error or None,
        }
