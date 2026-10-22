# Validierung des letzten Laufs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Den letzten erfolgreichen Inbox- oder Wissensradar-Lauf dauerhaft belegen und in einer bedienbaren Ansicht erneut lesend prüfen.

**Architecture:** Ein neuer Dienst verwaltet einen versionierten Nachweis und einen dauerhaften Übernahmemarker im getrennten Watcher-State. Der Orchestrator schreibt die Laufereignisse; zwei authentisierte API-Routen liefern Nachweis und aktuelle Prüfung. Die Frontend-Ansicht trennt historische Befunde von der späteren Prüfung.

**Tech Stack:** Python 3, FastAPI, pytest/unittest, JavaScript ohne Framework, bestehendes CSS.

**Spec:** `docs/superpowers/specs/2026-10-22-letzten-lauf-validieren-design.md`

## Global Constraints

- Vault und Watcher-State bleiben getrennt; Nachweis und Marker liegen nur im State.
- Eine erneute Prüfung liest ausschließlich; sie startet keinen Indexer und verändert weder Vault noch State.
- Inbox- und Wissensradar-Läufe zählen; abgelehnte, fehlgeschlagene und abgebrochene Läufe ersetzen den letzten erfolgreichen Nachweis nicht.
- Nachweis enthält keine Rohquellen oder Zugangsdaten; Browserantworten enthalten nur relative Pfade und verständliche Fehler.
- Die bestehende Basic-Authentisierung schützt beide neuen Routen. NAS-Main wird nicht automatisch umgestellt.

## Review Focus

1. Ein manipulierter Nachweis mit `../` oder Symlink außerhalb der Vault darf keine fremde Datei lesen. Task 1 testet beide Fälle.
2. Ein Prozessabbruch nach Vault-Commit und vor Nachweisabschluss darf den alten Nachweis nicht grün anzeigen. Task 1 testet einen liegen gebliebenen Marker.
3. Ein späterer legitimer Lauf darf den alten Index-Hash als „seitdem geändert“ melden, nicht als rückwirkenden Indexer-Fehler. Task 1 testet diese Unterscheidung.
4. Ein Lauf ohne Git-Commit muss den dokumentierten Grund zeigen, ohne einen Commit zu erfinden. Task 1 testet diesen Zustand.
5. Ein beschädigter oder unbekannt versionierter Nachweis darf keinen scheinbaren Erfolg liefern. Task 1 testet beide Eingaben.

---

## Dateistruktur

- Neu `dashboard/backend/loop/run_validation.py`: State-Nachweis, Marker, sichere Pfadprüfung und aktuelle lesende Befunde.
- Neu `dashboard/backend/loop/test_run_validation.py`: isolierte temporäre Vault-/State-Fixtures und die fünf Review-Fälle.
- Ändern `dashboard/backend/loop/vault_loop_executor.py`: freigegebenen Vorschlagspfad im Inbox-Ausführungsergebnis ausgeben.
- Ändern `dashboard/backend/loop/watcher_loop_orchestrator.py`: Marker vor Übernahme, Nachweis nach Erfolg, kontrolliertes Aufräumen nach Fehler; Dienst für API bereitstellen.
- Ändern `dashboard/backend/loop/test_watcher_loop_orchestrator.py`: Integration mit echten temporären Git-Vaults für beide Laufarten und Fehlerfälle.
- Ändern `dashboard/backend/dashboard_api.py`; neu `dashboard/backend/test_run_validation_api.py`: zwei authentisierte Routen und Statusfälle.
- Ändern `dashboard/frontend/index.html`, `dashboard/frontend/app.js`, `dashboard/frontend/style.css`: Menü, Ansicht und lesende Aktualisierung.
- Ändern `docs/uebergabe.md`, `docs/entscheidungen.md`: geprüften Funktionsumfang und Übergabe festhalten.

### Task 1: Dauerhafter Nachweis und lesende Prüflogik

**Files:** Create `dashboard/backend/loop/run_validation.py`, `dashboard/backend/loop/test_run_validation.py`.

**Interfaces:** `RunValidationService(vault_path: Path | str, state_dir: Path | str | None = None)` erzeugt den Dienst. `begin(run_id: str, kind: str) -> None`, `finish(run_id: str, kind: str, execution: dict, inputs: list[dict], proposal: dict | None) -> dict`, `abort(run_id: str) -> None`, `status() -> dict` und `recheck(qmd_status: dict) -> dict` sind die später genutzten Methoden. `kind` ist `inbox` oder `knowledge_radar`. `status()` liefert `available`, `pending`, `evidence` und gegebenenfalls `reason`; `recheck()` ergänzt `checked_at`, `checks` und `overall`.

- [ ] **Step 1: Tests für State-Lebenszyklus schreiben.** `test_finish_survives_restart` prüft Schema-Version 1, Run-ID, Laufart, relative Pfade, SHA-256, Commit-/Indexer-Daten, Dateimodus 0600 und identisches Lesen nach neuer Dienstinstanz. `test_abort_keeps_previous_evidence` prüft alten Nachweis und entfernten Marker. `test_pending_marker_suppresses_green` lässt den Marker liegen und erwartet `pending=True` sowie `overall != "bestanden"`.
- [ ] **Step 2: Gezielte Tests ausführen.** Run: `.venv/bin/python -m pytest -q dashboard/backend/loop/test_run_validation.py`; erwartetes Ergebnis: FAIL wegen fehlendem Dienst.
- [ ] **Step 3: Minimalen State-Dienst implementieren.** Nachweis und Marker unter `SECBRAIN_WATCHER_STATE_DIR` oder dem bestehenden Standardpfad halten; JSON-Version prüfen; temporäre Datei mit 0600, `fsync` und `os.replace` schreiben. `finish()` lehnt einen nicht passenden Marker ab. Ein fehlender oder ungültiger Nachweis liefert `available=False`, keinen Ausnahme-Trace an die UI.
- [ ] **Step 4: Tests der erneuten Prüfung schreiben.** `test_recheck_detects_changed_missing_and_new_index`, `test_recheck_handles_no_commit`, `test_recheck_rejects_traversal_and_symlink`, `test_recheck_rejects_corrupt_or_future_schema` und `test_recheck_is_read_only` prüfen die Befunde aus dem Spec. Der Read-only-Test vergleicht Dateibaum, Bytes und Git-Status vor/nach der Prüfung.
- [ ] **Step 5: Gezielte Tests erneut ausführen.** Run: `.venv/bin/python -m pytest -q dashboard/backend/loop/test_run_validation.py`; erwartetes Ergebnis: neue Recheck-Tests FAIL.
- [ ] **Step 6: `recheck(qmd_status: dict) -> dict` implementieren.** Relative Pfade und Symlinks vor dem Lesen begrenzen; Dateien per SHA-256 vergleichen; Commit mit lesenden Git-Befehlen prüfen; `graph.json` als JSON und Hash prüfen; QMD als getrennten Live-Befund auswerten. Einzelstatus: `bestanden`, `geändert`, `fehlt`, `nicht prüfbar`; Gesamtstatus nur bei durchgehend bestandenem aktuellen Check grün.
- [ ] **Step 7: Tests ausführen und committen.** Run: `.venv/bin/python -m pytest -q dashboard/backend/loop/test_run_validation.py`; erwartetes Ergebnis: PASS. Commit: `git add dashboard/backend/loop/run_validation.py dashboard/backend/loop/test_run_validation.py && git commit -m "feat: persist and recheck watcher run evidence"`.

### Task 2: Inbox- und Radar-Läufe anbinden

**Files:** Modify `dashboard/backend/loop/vault_loop_executor.py`, `dashboard/backend/loop/watcher_loop_orchestrator.py`, `dashboard/backend/loop/test_watcher_loop_orchestrator.py`.

**Interfaces:** Nutzt Task 1. `WatcherLoopOrchestrator.validation` stellt dieselbe `RunValidationService`-Instanz der API bereit. `VaultLoopExecutor.apply()` ergänzt `proposal_path` im Ergebnis; `apply_research()` behält `target` und `log`.

- [ ] **Step 1: Integrationsfälle als scheiternde Tests ergänzen.** `test_completed_inbox_run_persists_validation_evidence` prüft Archivquelle, Quellenseite, Vorschlag, Log und Commit. `test_completed_radar_run_persists_validation_evidence` prüft Zielseite und Log. `test_failed_apply_keeps_previous_validation` prüft Rückweg und alten Nachweis. `test_evidence_write_failure_leaves_pending_marker` injiziert einen Fehler nach erfolgreichem `apply()` und erwartet keinen grünen Altstatus.
- [ ] **Step 2: Integrationsfälle ausführen.** Run: `.venv/bin/python -m pytest -q dashboard/backend/loop/test_watcher_loop_orchestrator.py -k validation`; erwartetes Ergebnis: FAIL.
- [ ] **Step 3: Orchestrator anbinden.** `begin()` unmittelbar vor der Übernahme, `finish()` nach erfolgreichem Executor-Ergebnis, `abort()` nur nach kontrolliertem Fehler-Rückweg. Bestehenden Laufabschluss bei reinem Nachweisfehler nicht in einen Vault-Rollback umdeuten; Marker stehen lassen und einen Validierungshinweis im Status setzen. Im Inbox-Ergebnis den tatsächlichen freigegebenen Vorschlagspfad ergänzen.
- [ ] **Step 4: Integrationsfälle ausführen und committen.** Run: `.venv/bin/python -m pytest -q dashboard/backend/loop/test_watcher_loop_orchestrator.py`; erwartetes Ergebnis: PASS. Commit: `git add dashboard/backend/loop/vault_loop_executor.py dashboard/backend/loop/watcher_loop_orchestrator.py dashboard/backend/loop/test_watcher_loop_orchestrator.py && git commit -m "feat: record evidence for completed watcher runs"`.

### Task 3: Authentisierte API für Anzeige und Prüfung

**Files:** Modify `dashboard/backend/dashboard_api.py`; create `dashboard/backend/test_run_validation_api.py`.

**Interfaces:** `GET /api/validation/last` gibt `watcher_orchestrator.validation.status()` zurück. `POST /api/validation/last/recheck` blockiert bei aktiver Übernahme mit HTTP 409 und gibt sonst `validation.recheck(retrieval_status())` zurück. Beide Routen erben die bestehende Basic-Authentisierung.

- [ ] **Step 1: Scheiternde API-Tests schreiben.** TestClient-Fälle prüfen 401 ohne Anmeldung, 200 mit Anmeldung, 409 bei aktiver Übernahme, einen fehlenden/beschädigten Nachweis ohne 500 und eine erfolgreiche Recheck-Antwort mit getrennten historischen und aktuellen Befunden. Den Dienst und QMD-Status durch temporäre Fixtures ersetzen.
- [ ] **Step 2: API-Tests ausführen.** Run: `.venv/bin/python -m pytest -q dashboard/backend/test_run_validation_api.py`; erwartetes Ergebnis: FAIL wegen fehlender Routen.
- [ ] **Step 3: Routen implementieren.** Nur die validierten Dienst-Daten zurückgeben; keine absoluten NAS-Pfade, Rohquellen oder internen Exceptions serialisieren.
- [ ] **Step 4: API-Tests ausführen und committen.** Run: `.venv/bin/python -m pytest -q dashboard/backend/test_run_validation_api.py`; erwartetes Ergebnis: PASS. Commit: `git add dashboard/backend/dashboard_api.py dashboard/backend/test_run_validation_api.py && git commit -m "feat: expose last-run validation API"`.

### Task 4: Validierungsansicht und Gesamtprüfung

**Files:** Modify `dashboard/frontend/index.html`, `dashboard/frontend/app.js`, `dashboard/frontend/style.css`, `docs/uebergabe.md`, `docs/entscheidungen.md`.

**Interfaces:** `data-view="validation"` nutzt die vorhandene Navigation. `loadValidation()` ruft `GET /api/validation/last`; die Schaltfläche `Erneut prüfen` ruft `POST /api/validation/last/recheck`. Nur DOM-Textknoten oder bestehende Escape-Helfer für serverseitige Werte verwenden.

- [ ] **Step 1: UI-Akzeptanzfälle festhalten.** Im isolierten lokalen/Dev-Browser: Menü per Klick und Tastatur öffnen, leeren Nachweis sehen, historischen Nachweis mit Zeitpunkt sehen, Recheck auslösen, geänderte Datei und nicht verfügbares QMD getrennt erkennen, schmale Mobilansicht prüfen. Vor der Änderung ist der Menüpunkt inert.
- [ ] **Step 2: Ansicht minimal implementieren.** Menü verbinden, neue View mit historischem Block und aktuellem Prüfblock einfügen, Lade-/Fehlerzustände und 409-Hinweis anzeigen. Keine automatische Prüfung beim Öffnen; nur expliziter Klick führt `POST` aus.
- [ ] **Step 3: Frontend und Gesamtlauf prüfen.** Run: `find dashboard/frontend -name '*.js' -print0 | xargs -0 -n1 node --check`; erwartet: Exit 0. Run: `.venv/bin/python -m pytest -q`; erwartet: PASS. Run: `git diff --check`; erwartet: keine Ausgabe. Danach UI-Akzeptanzfälle im isolierten Dev prüfen; NAS-Main nicht umstellen.
- [ ] **Step 4: Doku und Commit.** `docs/uebergabe.md` nennt Funktionsumfang, Testnachweise und weiter offene Scanner-/Reports-Menüs; `docs/entscheidungen.md` hält die endgültige Nachweisgrenze fest. Commit: `git add dashboard/frontend/index.html dashboard/frontend/app.js dashboard/frontend/style.css docs/uebergabe.md docs/entscheidungen.md && git commit -m "feat: add last-run validation view"`.

## Abschlussprüfung

- [ ] Alle vier Task-Commits und `git diff --check` prüfen; vollständigen Backend-Testlauf und Frontend-Syntax erneut bestätigen, soweit nach Task 4 noch Code geändert wurde.
- [ ] Branch gegen `origin/main` prüfen und den Pull Request vorbereiten. Produktiver NAS-Rollout bleibt ein eigener, gesicherter Schritt nach Review und Freigabe.
