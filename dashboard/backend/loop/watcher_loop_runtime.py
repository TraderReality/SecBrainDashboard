"""Read-only runtime for the twelve SECBrain Watcher stations.

The runtime owns the live state of one locally connected model.  It never
modifies the Vault; it only prepares guarded chat work and records the
observable progression of a run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4


STATION_NAMES = (
    "Erfassen",
    "Analysieren",
    "Vergleichen",
    "Einordnen",
    "Vorschlag erstellen",
    "Freigabe abwarten",
    "Übernehmen",
    "Indexieren",
    "Verlinken",
    "Prüfen",
    "Protokollieren",
    "Berichten",
)


@dataclass(frozen=True)
class WatcherRequest:
    """A single, exclusive execution lease for the active station."""

    token: str
    run_id: str
    station_id: int
    model: str


class WatcherLoopRuntime:
    """State machine for one read-only, model-backed Watcher run."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._model = ""
        self._run_id = ""
        self._current_station = 1
        self._in_flight: WatcherRequest | None = None
        self._events: list[dict[str, Any]] = []

    def start(self, model: str) -> dict[str, Any]:
        model = str(model).strip()
        if not model:
            raise ValueError("Für den Watcher-Lauf muss ein Modell gewählt sein.")

        with self._lock:
            self._model = model
            self._run_id = f"WL-{uuid4().hex[:8].upper()}"
            self._current_station = 1
            self._in_flight = None
            self._record("run_started", "Modell startet verbindlich bei Station 01.")
            return self._status_locked()

    def start_at(self, model: str, station_id: int, message: str) -> dict[str, Any]:
        """Start an externally prepared, read-only handoff at a guarded station."""
        model = str(model).strip()
        if not model:
            raise ValueError("Für die Übergabe muss ein Modell gewählt sein.")
        if station_id < 1 or station_id > len(STATION_NAMES):
            raise ValueError("Ungültige Zielstation.")
        with self._lock:
            self._model = model
            self._run_id = f"WL-{uuid4().hex[:8].upper()}"
            self._current_station = station_id
            self._in_flight = None
            self._record("run_handed_off", message)
            return self._status_locked()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._record("run_stopped", "Modellverbindung wurde getrennt.")
            self._model = ""
            self._run_id = ""
            self._current_station = 1
            self._in_flight = None
            return self._status_locked()

    def begin(self, model: str) -> WatcherRequest:
        with self._lock:
            if not self._model:
                raise ValueError("Der Watcher-Lauf ist nicht gestartet.")
            if model and model != self._model:
                raise ValueError("Das Chat-Modell stimmt nicht mit dem aktiven Watcher-Modell überein.")
            if self._in_flight:
                raise RuntimeError(
                    f"Station {self._in_flight.station_id:02d} wird bereits verarbeitet."
                )

            request = WatcherRequest(
                token=uuid4().hex,
                run_id=self._run_id,
                station_id=self._current_station,
                model=self._model,
            )
            self._in_flight = request
            self._record(
                "station_started",
                f"Station {request.station_id:02d} wurde an das Modell übergeben.",
            )
            return request

    def complete(self, request: WatcherRequest, output: str = "") -> dict[str, Any]:
        with self._lock:
            self._assert_current_request(request)
            completed_station = request.station_id
            self._current_station = 1 if completed_station == 12 else completed_station + 1
            self._in_flight = None
            output_preview = " ".join(str(output).split())
            if output_preview:
                output_preview = output_preview[:240]
                if len(" ".join(str(output).split())) > 240:
                    output_preview += "…"

            completion_message = (
                f"Station {completed_station:02d} erfolgreich beendet; weiter mit "
                f"{self._current_station:02d}."
            )
            if output_preview:
                completion_message += f" Ausgabe: {output_preview}"

            self._record(
                "station_completed",
                completion_message,
            )
            return {
                "completed_station": completed_station,
                "next_station": self._current_station,
                "run_id": self._run_id,
            }

    def fail(self, request: WatcherRequest, reason: str) -> dict[str, Any]:
        with self._lock:
            self._assert_current_request(request)
            self._in_flight = None
            self._record(
                "station_failed",
                f"Station {request.station_id:02d} blieb aktiv: {reason}",
            )
            return self._status_locked()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_locked()

    def _status_locked(self) -> dict[str, Any]:
        running = bool(self._model)
        stations = [
            {
                "id": index,
                "name": name,
                "status": (
                    "IN ARBEIT"
                    if running and self._in_flight and index == self._current_station
                    else "AKTIV"
                    if running and index == self._current_station
                    else "READY"
                ),
                "active": running and index == self._current_station,
            }
            for index, name in enumerate(STATION_NAMES, start=1)
        ]
        return {
            "run_id": self._run_id or None,
            "model": self._model or None,
            "current_station": self._current_station,
            "busy": self._in_flight is not None,
            "readonly": self._current_station <= 6,
            "activity": self._activity_locked(),
            "stations": stations,
            "events": self._events[-20:],
        }

    def _activity_locked(self) -> dict[str, str]:
        if not self._model:
            return {
                "state": "offline",
                "title": "Keine KI verbunden",
                "message": "Wähle im KI-Chat ein Modell, um einen Watcher-Lauf zu starten.",
            }

        station_name = STATION_NAMES[self._current_station - 1]
        if self._in_flight:
            return {
                "state": "working",
                "title": f"Station {self._current_station:02d} · {station_name}",
                "message": "Die KI verarbeitet die aktuelle Anfrage mit den Regeln dieser Station.",
            }

        return {
            "state": "ready",
            "title": f"Station {self._current_station:02d} · {station_name}",
                "message": "Bereit für die nächste kontrollierte Station.",
        }

    def _assert_current_request(self, request: WatcherRequest) -> None:
        if self._in_flight != request:
            raise RuntimeError("Ungültiger oder bereits abgeschlossener Watcher-Aufruf.")

    def _record(self, event: str, message: str) -> None:
        self._events.append(
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "message": message,
            }
        )
