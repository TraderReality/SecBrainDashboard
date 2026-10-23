# Excalidraw-Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine ausdrückliche `/excalidraw`-Anfrage im Dashboard erzeugt eine geprüfte, bearbeitbare Datei auf der NAS-Freigabe `Local/Work/excalidraw`.

**Architecture:** Das authentisierte Dashboard reicht Diagrammanfragen an einen nur intern erreichbaren Generator-Dienst weiter. Dieser ruft das lokale Ollama-Modell auf, validiert Excalidraw-JSON und veröffentlicht eine Datei über einen NAS-Bind-Mount. Main und Dev verwenden getrennte Worker, Tokens und Ausgabeordner.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Ollama HTTP API, bestehendes Dashboard-JavaScript, Docker Compose auf Synology.

**Spec:** `docs/superpowers/specs/2026-10-23-excalidraw-generator-design.md`

## Global Constraints

- Produktivziel: NAS `/volume1/Local/Work/excalidraw`, im Worker `/work/excalidraw`, per SMB `Local/Work/excalidraw`; Dev-Ziel: separater Ordner `Local/Work/excalidraw-dev`.
- Ausgabe v1: ausschließlich `.excalidraw` Version 2; kein SVG/PNG, Upload, Kollaborationsserver oder Vault-Commit.
- Nur `/excalidraw ` im bestehenden Chat schreibt eine Datei; normale Nachrichten bleiben lesend. Die Dashboard-API nimmt keinen vom Nutzer bestimmten Zielpfad an.
- Worker hat keinen veröffentlichten Host-Port, benötigt einen eigenen Token pro Profil und schreibt allein in den Work-Mount. Bestehende Vault-/State-Mounts und Watcher-Loop bleiben unverändert.
- Main-Rollout erst nach Code-Review, Sicherung und konkreter Freigabe; zuerst isolierter NAS-Dev-Lauf.
- Tests im Worktree mit Python 3.12 und `PYTHONPATH="$PWD/dashboard/backend:$PWD"`; lokale virtuelle Umgebung aus `requirements-dev.txt` vorbereiten.

## File Map

| Datei | Verantwortung |
| --- | --- |
| `excalidraw_generator/scene.py` | JSON-Enveloppe und Element-/Referenzprüfung |
| `excalidraw_generator/storage.py` | kollisionsfreie atomare Dateiveröffentlichung |
| `excalidraw_generator/ollama.py` | begrenzter Ollama-HTTP-Aufruf und JSON-Antwort |
| `excalidraw_generator/service.py` | Prompt, höchstens zwei Modellversuche, Validierung, Speichern |
| `excalidraw_generator/api.py` | interner FastAPI-Endpunkt, Token und Health |
| `dashboard/backend/excalidraw_client.py` | begrenzter Dashboard-zu-Worker-Aufruf |
| `dashboard/backend/dashboard_api.py` | authentisierte öffentliche Generator-Route |
| `dashboard/frontend/components/ollama-settings.js` | expliziter `/excalidraw`-Befehl im vorhandenen Chat |
| `deploy/synology/Dockerfile.excalidraw-generator`, `deploy/synology/compose.yaml` | isolierte Worker-Builds, Main-/Dev-Mounts und Konfiguration |
| `deploy/synology/README.md`, `docs/README.md`, `docs/entscheidungen.md`, `docs/uebergabe.md` | Betrieb, API, Entscheidung und Übergabe |

## Review Focus

1. Pfadähnliche Texte im Prompt (`../`, absolute Pfade) dürfen den serverseitig erzeugten Dateinamen oder Ausgabeordner nicht beeinflussen (Task 3).
2. HTML- oder Skripttext in Prompt, Modellantwort oder Dateiname darf im Chat nie als HTML interpretiert werden (Task 5).
3. Zwei gleichzeitige erfolgreiche Anfragen dürfen weder dieselbe Datei wählen noch eine bestehende Datei überschreiben (Task 2).
4. Falscher Worker-Token, nicht erreichbarer Worker und fehlender Mount dürfen keine halbe Datei und keine internen Details liefern (Tasks 2–4).
5. Fenced, leere, abgeschnittene oder übergroße Modellantworten dürfen keine veröffentlichte Datei erzeugen; der zweite Versuch ist begrenzt (Tasks 1 und 3).

---

### Task 1: Excalidraw-Szenenvertrag

**Files:**
- Create: `excalidraw_generator/__init__.py`, `excalidraw_generator/scene.py`
- Test: `excalidraw_generator/test_scene.py`

**Interfaces:**
- Produces: `validate_scene(raw: str | dict) -> dict`, raises `SceneValidationError`; returns an Excalidraw-v2 document with `elements`, `appState` and empty `files`.

- [ ] **Step 0: Prepare test environment:** create `.venv` with Python 3.12, install `requirements-dev.txt`, then verify `fastapi` and `pytest` import.
- [ ] **Step 1: Write failing tests** for valid rectangle/text/arrow scene, duplicate IDs, missing bound target, unsupported element, nonfinite coordinates, oversized text, empty/fenced/oversized JSON and `files` content. Assert exact accepted envelope and rejection category.
- [ ] **Step 2: Run red tests:** `PYTHONPATH="$PWD/dashboard/backend:$PWD" .venv/bin/python -m pytest -q excalidraw_generator/test_scene.py`; expect failures from missing validator.
- [ ] **Step 3: Implement** `SceneValidationError` and `validate_scene(raw: str | dict) -> dict` in `scene.py`: at most 80 elements and 256 KiB serialized JSON; only rectangle, ellipse, diamond, arrow, line and text; unique string IDs; finite numeric `x`, `y`, `width`, `height`; valid `containerId`, `boundElements` and arrow bindings; each text at most 500 characters. Enforce `type="excalidraw"`, `version=2`, white default background and `files={}`. Parse only pure JSON, with no Markdown fence extraction.
- [ ] **Step 4: Run green tests** with the same command; expect all scene tests to pass.
- [ ] **Step 5: Commit** scene validator and tests: `git commit -m "feat: validate bounded Excalidraw scenes"`.

### Task 2: Sichere Ausgabe im Work-Ordner

**Files:**
- Create: `excalidraw_generator/storage.py`
- Test: `excalidraw_generator/test_storage.py`

**Interfaces:**
- Consumes: validated scene from Task 1.
- Produces: `publish_scene(scene: dict, output_dir: Path, share_prefix: str) -> dict` with `filename`, `relative_path`, `element_count`; raises `StorageError`.

- [ ] **Step 1: Write failing tests** for one output file, JSON roundtrip, configured `Local/Work/excalidraw/<filename>` or Dev-prefix response, traversal-like prompt excluded from name, two concurrent writers, existing target, missing mount, symlink target directory and simulated write failure with no published partial file.
- [ ] **Step 2: Run red tests:** `PYTHONPATH="$PWD/dashboard/backend:$PWD" .venv/bin/python -m pytest -q excalidraw_generator/test_storage.py`; expect missing publisher.
- [ ] **Step 3: Implement** `publish_scene(scene: dict, output_dir: Path, share_prefix: str) -> dict`: server-generated UTC timestamp plus random ID, no user text in name, temp file in same directory, flush and `fsync`, exclusive publication without overwrite, directory `fsync` where supported, cleanup of own temp on error. Reject absent or symlink output directory; never create the target root implicitly.
- [ ] **Step 4: Run green tests** with the same command; expect all storage tests to pass.
- [ ] **Step 5: Commit** storage and tests: `git commit -m "feat: publish Excalidraw files atomically"`.

### Task 3: Lokaler KI-Generator

**Files:**
- Create: `excalidraw_generator/ollama.py`, `excalidraw_generator/service.py`
- Test: `excalidraw_generator/test_service.py`

**Interfaces:**
- Consumes: `validate_scene(raw: str | dict) -> dict`, `publish_scene(scene: dict, output_dir: Path, share_prefix: str) -> dict`.
- Produces: `generate_diagram(prompt: str, model: str, ollama_url: str, output_dir: Path, share_prefix: str) -> dict`; raises `GenerationError` with a public error code.

- [ ] **Step 1: Write failing tests** using a fake Ollama endpoint for valid JSON, empty prompt, prompt over 4000 characters, path-like prompt, no model, timeout, empty/truncated/oversized/fenced response, one malformed response followed by valid retry and two malformed responses. Assert no output on every error.
- [ ] **Step 2: Run red tests:** `PYTHONPATH="$PWD/dashboard/backend:$PWD" .venv/bin/python -m pytest -q excalidraw_generator/test_service.py`; expect missing generator.
- [ ] **Step 3: Implement** `generate_diagram(...)`: send bounded system instruction based on the documented Hermes element rules to Ollama `/api/chat` with `stream:false`, `think:false`, selected local model and 120-second timeout; read at most 256 KiB content, validate via Task 1, retry once with concise validator feedback, then publish via Task 2. Do not use Hermes upload script, arbitrary shell commands or external URLs.
- [ ] **Step 4: Run green tests** with the same command; expect all service tests to pass.
- [ ] **Step 5: Commit** service and tests: `git commit -m "feat: generate Excalidraw JSON with local Ollama"`.

### Task 4: Interner Worker und Dashboard-API

**Files:**
- Create: `excalidraw_generator/api.py`, `excalidraw_generator/test_api.py`, `dashboard/backend/excalidraw_client.py`, `dashboard/backend/test_excalidraw_api.py`
- Modify: `dashboard/backend/dashboard_api.py`

**Interfaces:**
- Worker: `POST /generate` receives `prompt`, `model`; `GET /healthz` reports only readiness. The worker reads `SECBRAIN_EXCALIDRAW_SHARE_PREFIX` for its profile. `X-Worker-Token` must equal `SECBRAIN_EXCALIDRAW_TOKEN` with constant-time comparison.
- Dashboard: `POST /api/excalidraw/generate` receives `prompt`, optional `model`; delegates to `request_diagram(prompt: str, model: str) -> dict`. Existing Basic Auth applies.

- [ ] **Step 1: Write failing tests** for valid request, missing/wrong worker token, missing token configuration, concurrent request rejected with 429, worker timeout, malformed worker result, missing model, unauthenticated dashboard request, ordinary `/api/ollama/chat` isolation and response without internal URL/path/token.
- [ ] **Step 2: Run red tests:** `PYTHONPATH="$PWD/dashboard/backend:$PWD" .venv/bin/python -m pytest -q excalidraw_generator/test_api.py dashboard/backend/test_excalidraw_api.py`; expect missing routes/client.
- [ ] **Step 3: Implement** worker API and Dashboard client/route. Worker has no CORS or published port; health returns no secrets. A one-request semaphore rejects overlapping generation with 429. Dashboard uses `SECBRAIN_EXCALIDRAW_WORKER_URL` and `SECBRAIN_EXCALIDRAW_TOKEN`, validates worker response shape, maps unavailable worker to 503 and invalid generation to 422 without raw model text.
- [ ] **Step 4: Run green tests** with the same command plus `dashboard/backend/test_dashboard_chat.py`; expect all selected tests to pass.
- [ ] **Step 5: Commit** API and tests: `git commit -m "feat: connect Dashboard to private diagram worker"`.

### Task 5: Expliziter Chat-Befehl

**Files:**
- Modify: `dashboard/frontend/components/ollama-settings.js`
- Test: `dashboard/backend/test_excalidraw_frontend_contract.py`

**Interfaces:**
- Consumes: Task-4 Dashboard endpoint.
- Produces: `/excalidraw <Beschreibung>` in the existing chat dock; displays `Local/Work/excalidraw/<filename>` as escaped text.

- [ ] **Step 1: Write failing frontend-contract tests** for normal chat unchanged, explicit `/excalidraw ` routing, empty diagram prompt rejected before request, writing notice visible before sending, safe escaped output for `<script>` text and a helpful failure message.
- [ ] **Step 2: Run red tests:** `PYTHONPATH="$PWD/dashboard/backend:$PWD" .venv/bin/python -m pytest -q dashboard/backend/test_excalidraw_frontend_contract.py`; expect routing contract failure.
- [ ] **Step 3: Implement** the command branch inside `sendChat()` and the existing escaped message rendering. Preserve ordinary chat and selected-model behavior; show only SMB-relative output path and element count, never worker URL or token.
- [ ] **Step 4: Run green tests** with the same command and `node --check dashboard/frontend/components/ollama-settings.js`.
- [ ] **Step 5: Commit** frontend and tests: `git commit -m "feat: request Excalidraw diagrams from Dashboard chat"`.

### Task 6: Compose, Dev-Nachweis und Übergabe

**Files:**
- Create: `deploy/synology/Dockerfile.excalidraw-generator`, `deploy/synology/requirements-excalidraw-lock.txt`
- Modify: `deploy/synology/compose.yaml`, `deploy/synology/README.md`, `docs/README.md`, `docs/entscheidungen.md`, `docs/uebergabe.md`
- Test: `deploy/synology/test_excalidraw_compose.py`

**Interfaces:**
- Services `excalidraw-main` and `excalidraw-dev` mount `${SECBRAIN_MAIN_EXCALIDRAW_DIR}:/work/excalidraw` and `${SECBRAIN_DEV_EXCALIDRAW_DIR}:/work/excalidraw`; their share prefixes are `Local/Work/excalidraw` and `Local/Work/excalidraw-dev`.
- Main/Dev each pass their matching worker URL (`http://excalidraw-main:8090` or `http://excalidraw-dev:8090`) and token to their Dashboard service; worker port 8090 stays private. Secret values live only in protected NAS env files.

- [ ] **Step 1: Write failing Compose-contract tests** for separate Main/Dev worker URL, token and target mount; no worker host port; read-only worker root, dropped capabilities, numeric UID/GID, memory limit and writable `/tmp`; missing token must fail `docker compose config`.
- [ ] **Step 2: Run red tests:** `PYTHONPATH="$PWD/dashboard/backend:$PWD" .venv/bin/python -m pytest -q deploy/synology/test_excalidraw_compose.py`; expect missing services/config.
- [ ] **Step 3: Implement** the worker image and two profiled Compose services, environment requirements and deployment docs. Use pinned FastAPI/Uvicorn dependencies; preserve current Main/Dev mounts and existing HTTPS proxy. Document folder creation, permissions, isolated Dev output, SMB check, rollback and the stopped static Excalidraw image.
- [ ] **Step 4: Run** selected tests, complete backend suite, JS syntax check and `docker compose --profile dev config --quiet` with test-only env values; expect passes and no Main container change. Build/start only Dev on NAS with a separate Work test folder and protected credentials, submit one marked local-model request, read the output JSON and compare file bytes through the SMB view. Record image digest, health, test path and cleanup in `docs/uebergabe.md`.
- [ ] **Step 5: Commit** Compose/docs/tests: `git commit -m "deploy: prepare isolated Excalidraw generator"`. Request whole-branch review. Prepare a concrete Main backup/rollout diff and obtain the separately required Main-Rollout-Freigabe before changing NAS-Main.
