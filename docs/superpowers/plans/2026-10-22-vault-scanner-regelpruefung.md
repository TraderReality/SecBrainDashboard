# Vault-Scanner und Regelprüfung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Den Scanner für Vault-Änderungen und Regelbefunde bedienbar machen und App-Vault-Schreibwege bei technischen oder unklaren AGENTS-Regelbefunden sperren.

**Architecture:** Eine sichere Vault-Inventur und ein versionierter Vergleichsstand liegen im getrennten Watcher-State. Eine gemeinsame Regel-Engine prüft die vollständige `AGENTS.md` mit lokalem Ollama und feste technische Invarianten. Scannerberichte werden begrenzt in der Vault committed; derselbe Prüfdienst bewacht alle bestehenden App-Schreibwege.

**Tech Stack:** Python 3.12, FastAPI, lokales Ollama, Vault-Git, Vanilla JavaScript/CSS, pytest.

**Spec:** `docs/superpowers/specs/2026-10-22-vault-scanner-regelpruefung-design.md`

## Global Constraints

- Ausführungsbranch startet vom Commit dieses Plans auf `codex/vault-scanner-design`; dieser Stand enthält PR #13 (`codex/validation-last-run-impl`), ohne Merge oder NAS-Rollout.
- Vergleichsbasis ist ausschließlich der letzte vollständig abgeschlossene Scan; der erste Scan ist Inventur, kein pauschaler „neu“-Befund.
- Ausnahmen: `.git/`, jedes `_index/`, `__pycache__/`, `*.pyc`, `.DS_Store`, `09 Werkzeuge/Scanner-Berichte/`. Symlinks niemals folgen; keine fremden Dateien lesen.
- Vollständige Vault-`AGENTS.md` und alle daraus extrahierten Regelabschnitte bewerten; bei fehlendem/unklarem KI-Ergebnis App-Schreibweg sperren. Technische Regeln bleiben unabhängig von KI verbindlich.
- Berichte als unveränderliche JSON-Dateien in `09 Werkzeuge/Scanner-Berichte/`; Scan-State und Sperre außerhalb der Vault unter `SECBRAIN_WATCHER_STATE_DIR`.
- Bericht-Commit umfasst nur den Bericht und bewahrt fremde Git-Änderungen. Abbruch darf weder grünen Status noch doppelte Berichte ergeben.
- Bestehende Basic-Authentisierung schützt Scanner-API. Keine automatische Vault-Reparatur oder produktive NAS-Umschaltung.
- Testbefehle laufen mit der vollständigen Projekt-venv (`.venv/bin/python`, im isolierten Worktree bei Ausführung bereitstellen); System-Python fehlen Projektabhängigkeiten.

## Review Focus

1. Pfad wird während des Scans gegen einen Symlink nach außen ausgetauscht: kein Lesen außerhalb der Vault; Test in Task 1.
2. `AGENTS.md` wird während KI-Prüfung geändert oder Modell liefert nur einen Teil der Regeln: Ergebnis `unklar`, keine Übernahme; Tests in Task 2 und 5.
3. Binärdatei, defektes UTF-8 oder Modellkontext zu groß: niemals stillschweigend `erfüllt`; Test in Task 2.
4. Prozessabbruch nach Bericht-Commit, aber vor State-Austausch: Wiederanlauf erkennt denselben Scan ohne Doppelbericht und ohne falschen Erfolg; Test in Task 3.
5. PDF-/ZIP-Import mit mehreren Zielpfaden und fremden Git-Stagings: ein Regelverstoß verhindert alle neuen Nutzerdaten, Staging bleibt unangetastet; Test in Task 7.

---

### Task 1: Sichere Vault-Inventur und Vergleich

**Files:** Create `dashboard/backend/scanner/__init__.py`, `dashboard/backend/scanner/inventory.py`, `dashboard/backend/scanner/test_inventory.py`.

**Interfaces:** Produce `scan_vault(vault: Path) -> dict` (`files` mit relativen Pfaden, `sha256`, `size`, `kind`; `issues`) und `diff_inventory(previous: dict | None, current: dict) -> list[dict]` (`path`, `status` = `neu|geändert|entfernt|unverändert`). Task 4 consumes both. Use directory descriptors with `O_NOFOLLOW`, file-descriptor `fstat` before reading, and the exact exclusions above.

- [ ] **Step 1: Write failing tests** in `test_inventory.py`: first scan lists regular files but no `neu`; second scan reports one new, one byte-changed, one removed file; excludes each named path; Symlink and a patched path swap never read an external sentinel; file changing during hashing yields `issues`, not a digest claimed as stable.
  ```python
  def test_diff_after_baseline(vault):
      assert diff_inventory(None, scan_vault(vault)) == []
      assert {(row["path"], row["status"]) for row in diff_inventory(before, after)} == {
          ("01 Inbox/new.md", "neu"), ("06 Archiv/old.md", "geändert"), ("07 Anhänge/gone.pdf", "entfernt")
      }
  def test_symlink_swap_does_not_read_external_bytes(vault, outside):
      assert outside.read_bytes() not in captured_vault_reads
      assert scan_vault(vault)["issues"]
  ```
- [ ] **Step 2: Verify RED.** Run `.venv/bin/python -m pytest -q dashboard/backend/scanner/test_inventory.py`; expect missing module/functions or failing assertions.
- [ ] **Step 3: Implement** `scan_vault` and `diff_inventory`; return deterministic sorted relative paths and a non-success issue for changed/unreadable inputs. Do not write a baseline here.
- [ ] **Step 4: Verify GREEN.** Run the same command; expect all task tests passed.
- [ ] **Step 5: Commit.** `git add dashboard/backend/scanner && git commit -m "feat: inventory vault files safely"`.

### Task 2: Vollständige AGENTS-Regelbewertung

**Files:** Create `dashboard/backend/scanner/rules.py`, `dashboard/backend/scanner/test_rules.py`.

**Interfaces:** Produce `parse_rule_units(markdown: str) -> list[dict]` (`id`, `line`, `text`) and `evaluate_rules(agents_bytes: bytes, subjects: list[dict], model: str, chat: Callable) -> dict` (`agents_sha256`, `model`, `findings`, `overall = erfüllt|verletzt|unklar`). Task 4 and 5 consume `evaluate_rules`. `subjects` contain relative path, kind, readable full content or an explicit unreadable/unsupported marker, and proposed operation when present.

- [ ] **Step 1: Write failing tests:** each heading/paragraph/bullet receives a stable line reference; fake Ollama output missing a rule ID or with an extra path yields `unklar`; a rule reported `verletzt` is preserved with its source; missing model, invalid JSON, invalid UTF-8, binary content requiring interpretation and context overflow yield `unklar`.
  ```python
  def test_partial_model_coverage_fails_closed(agents, subjects, partial_chat):
      result = evaluate_rules(agents, subjects, "local-model", partial_chat)
      assert result["overall"] == "unklar"
      assert {f["rule_id"] for f in result["findings"]} == {u["id"] for u in parse_rule_units(agents.decode())}
  def test_unsupported_content_never_passes(agents, binary_subject, good_chat):
      assert evaluate_rules(agents, [binary_subject], "local-model", good_chat)["overall"] == "unklar"
  ```
- [ ] **Step 2: Verify RED.** Run `.venv/bin/python -m pytest -q dashboard/backend/scanner/test_rules.py`; expect failure.
- [ ] **Step 3: Implement** complete, untruncated AGENTS prompt and strict normalized JSON contract. Every parsed rule ID must have exactly one verdict per applicable subject; no unverified `erfüllt` default. Bound output length and forbid raw file bodies in findings.
- [ ] **Step 4: Verify GREEN.** Run the same command; expect all task tests passed.
- [ ] **Step 5: Commit.** `git add dashboard/backend/scanner && git commit -m "feat: evaluate all vault rule units"`.

### Task 3: Dauerhafter Bericht mit begrenztem Vault-Commit

**Files:** Create `dashboard/backend/scanner/report_store.py`, `dashboard/backend/scanner/test_report_store.py`.

**Interfaces:** Produce `ScannerReportStore(vault: Path, state_dir: Path)`, `publish(scan_id: str, report: dict, inventory: dict | None) -> dict`, `recover() -> dict`, `last_complete() -> dict | None`, `get_report(scan_id: str) -> dict`. `inventory=None` means an incomplete attempt; it never replaces `last_complete`. Task 4 consumes these methods. Persist a versioned marker and state with atomic replace/fsync, mode 0600, outside-Vault validation.

- [ ] **Step 1: Write failing tests:** complete and incomplete attempts create distinct immutable JSON reports; report commit changes only its path while staged and unstaged foreign bytes remain intact; simulated crash after report commit before state publication recovers without duplicate report or green result; missing Git identity/repository and corrupted state preserve prior complete baseline; invalid scan ID cannot read arbitrary paths.
  ```python
  def test_report_commit_preserves_foreign_staging(store, vault):
      before = staged_bytes(vault, "unrelated.md")
      result = store.publish("SCAN-1", complete_report, complete_inventory)
      assert result["report_path"] == "09 Werkzeuge/Scanner-Berichte/SCAN-1.json"
      assert staged_bytes(vault, "unrelated.md") == before
  def test_crash_after_commit_is_not_false_success(store):
      store.recover()
      assert count_reports("SCAN-1") == 1
      assert store.last_complete() is None or store.last_complete()["scan_id"] == "SCAN-1"
  ```
- [ ] **Step 2: Verify RED.** Run `.venv/bin/python -m pytest -q dashboard/backend/scanner/test_report_store.py`; expect failure.
- [ ] **Step 3: Implement** report-only Git commit with an isolated index or a proven `--only` path and a lease on HEAD. Record scan ID, report hash, old/new HEAD in the durable marker before reference update; reconcile marker on startup. Exclude report folder from inventory and indexer. Never replace complete state until report commit is confirmed.
- [ ] **Step 4: Verify GREEN.** Run the same command; expect all task tests passed.
- [ ] **Step 5: Commit.** `git add dashboard/backend/scanner && git commit -m "feat: persist bounded scanner reports"`.

### Task 4: Scanner-Lauf und authentisierte API

**Files:** Create `dashboard/backend/scanner/service.py`, `dashboard/backend/test_scanner_api.py`; modify `dashboard/backend/dashboard_api.py`.

**Interfaces:** Produce `VaultScanner(vault: Path, state_dir: Path, chat: Callable, model: Callable[[], str])` with `start() -> dict` (`scan_id`), `status() -> dict` (`state`, `last_complete`, `last_attempt`, `overall`, `progress`), `report(scan_id: str) -> dict`. `state` is `idle|running|complete|incomplete`; `overall` is `erfüllt|verletzt|unklar`. Add `GET /api/scanner/status`, `POST /api/scanner/scan`, `GET /api/scanner/reports/{scan_id}`. Task 8 consumes these JSON shapes.

- [ ] **Step 1: Write failing API/service tests:** unauthenticated requests get 401; first scan inventories, second scan classifies changes; concurrent start gets 409; status exposes progress and `nicht vollständig geprüft` after model failure; a file modified during scan does not advance baseline; changed `AGENTS.md` re-evaluates all scanned content.
  ```python
  def test_scanner_routes_require_auth(client):
      assert client.get("/api/scanner/status").status_code == 401
      assert client.post("/api/scanner/scan").status_code == 401
  def test_incomplete_scan_keeps_baseline(client, auth):
      assert client.post("/api/scanner/scan", headers=auth).json()["scan_id"]
      assert client.get("/api/scanner/status", headers=auth).json()["last_complete"]["scan_id"] == "SCAN-1"
      assert client.get("/api/scanner/status", headers=auth).json()["last_attempt"]["state"] == "incomplete"
  ```
- [ ] **Step 2: Verify RED.** Run `.venv/bin/python -m pytest -q dashboard/backend/test_scanner_api.py`; expect failure.
- [ ] **Step 3: Implement** a single background scan with process-wide lock, progress state, fixed response schema and report publication through Task 3. Load the current complete baseline, never use the latest incomplete attempt as comparison. Catch expected IO/model errors as findings rather than HTTP 500.
- [ ] **Step 4: Verify GREEN.** Run the same command; expect all task tests passed.
- [ ] **Step 5: Commit.** `git add dashboard/backend/scanner/service.py dashboard/backend/dashboard_api.py dashboard/backend/test_scanner_api.py && git commit -m "feat: expose vault scanner runs"`.

### Task 5: Gemeinsamer VaultWriteGuard

**Files:** Create `dashboard/backend/scanner/write_guard.py`, `dashboard/backend/scanner/test_write_guard.py`.

**Interfaces:** Produce `PlannedChange(relative_path: str, operation: Literal["create", "replace", "delete"], before_sha256: str | None, after_bytes: bytes | None)` and `RuleBlocked(RuntimeError)` with a non-sensitive `reason`; a move is represented by delete plus create. Produce `VaultWriteGuard(vault: Path, state_dir: Path, chat: Callable, model: Callable[[], str])`; `authorize(changes: list[PlannedChange], approval: str | None) -> ContextManager[None]`. Task 6/7 use `with guard.authorize(...):` around mutation. A successful context holds a process-crossing file lock until its body completes; expensive AI evaluation occurs before lock, then live AGENTS/input hashes are rechecked under it.

- [ ] **Step 1: Write failing tests:** traversal/symlink and unauthorized overwrite fail before body; `verletzt`, `unklar`, missing AGENTS or unavailable model fail closed; AGENTS or input hash changed during AI call fails under lock; two app writers cannot enter concurrently; explicit corrective approved diff may pass only when it removes a prior violation without adding another.
  ```python
  def test_changed_agents_blocks_before_mutation(guard, change):
      with pytest.raises(RuleBlocked):
          with guard.authorize([change], approval="RUN-1"):
              raise AssertionError("mutation must not start")
  def test_unknown_model_blocks(guard_with_unavailable_model, change):
      with pytest.raises(RuleBlocked):
          with guard_with_unavailable_model.authorize([change], approval=None):
              pass
  ```
- [ ] **Step 2: Verify RED.** Run `.venv/bin/python -m pytest -q dashboard/backend/scanner/test_write_guard.py`; expect failure.
- [ ] **Step 3: Implement** deterministic path/operation checks and a live inventory/rule evaluation independent of a stored scanner success. Recheck rules and all affected preimages before yielding. Return a typed `RuleBlocked` with non-sensitive reason for API mapping to 409.
- [ ] **Step 4: Verify GREEN.** Run the same command; expect all task tests passed.
- [ ] **Step 5: Commit.** `git add dashboard/backend/scanner && git commit -m "feat: fail closed on unsafe vault writes"`.

### Task 6: Watcher-Übernahmen bewachen

**Files:** Modify `dashboard/backend/loop/vault_loop_executor.py`, `dashboard/backend/loop/watcher_loop_orchestrator.py`, `dashboard/backend/loop/test_watcher_loop_orchestrator.py`.

**Interfaces:** Consume Task 5 `VaultWriteGuard.authorize`; add required `guard: VaultWriteGuard` to `VaultLoopExecutor.__init__(vault_path, guard)` and inject one guard from the orchestrator. Build `PlannedChange` entries from the already computed Vault-local `original`/`expected` maps for both `apply()` and `apply_research()` before `_write_transaction` and hold authorization through commit/rollback. Generated `_index` paths remain derived outputs, not user-content proposals.

- [ ] **Step 1: Write failing tests:** approved Inbox and Radar with `verletzt`/`unklar` leave Inbox, targets, log, proposal, journal and Git HEAD unchanged; a permitted run retains the existing 12-station behavior and validation evidence; stale preimage after approval aborts before mutation; a failed rollback still leaves the Punkt-1 pending marker visible.
  ```python
  def test_rule_blocked_inbox_preserves_vault(orchestrator, vault):
      before = vault_bytes_and_head(vault)
      run_approved_with_rule_verdict(orchestrator, "verletzt")
      assert orchestrator.status()["state"] == "failed"
      assert vault_bytes_and_head(vault) == before
  def test_rule_blocked_radar_preserves_vault(orchestrator, vault):
      before = vault_bytes_and_head(vault)
      run_radar_with_rule_verdict(orchestrator, "unklar")
      assert vault_bytes_and_head(vault) == before
  ```
- [ ] **Step 2: Verify RED.** Run `.venv/bin/python -m pytest -q dashboard/backend/loop/test_watcher_loop_orchestrator.py -k 'guard or validation'`; expect new tests to fail.
- [ ] **Step 3: Implement** the guard at the Executor's last pre-mutation boundary; preserve its existing transaction journal and rollback. Do not let a guard rejection masquerade as successful completion.
- [ ] **Step 4: Verify GREEN.** Run `.venv/bin/python -m pytest -q dashboard/backend/loop/test_watcher_loop_orchestrator.py`; expect all tests passed.
- [ ] **Step 5: Commit.** `git add dashboard/backend/loop && git commit -m "feat: guard approved watcher writes"`.

### Task 7: Upload, DokuLader und AGENTS-Editor bewachen

**Files:** Modify `dashboard/backend/dashboard_api.py`, `dashboard/backend/dokulader_service.py`, `dashboard/backend/test_dashboard_upload.py`, `dashboard/backend/test_dokulader_service.py`; create `dashboard/backend/test_agents_write_guard.py`.

**Interfaces:** Consume Task 5 `VaultWriteGuard.authorize`. Add required guard parameters to `write_inbox_upload(filename, content_base64, guard)`, `import_urls(vault, urls, guard)`, `import_pdf(vault, filename, content_base64, guard)`, and `import_package(vault, filename, content_base64, guard)`; update direct callers/tests. For each DokuLader operation prepare all target bytes outside the Vault first, then authorize the whole `PlannedChange` list before the first Vault write. Keep existing response shapes. Guard the proposed AGENTS edit against both old and new rule versions.

- [ ] **Step 1: Write failing tests:** blocked Inbox upload creates no file; blocked URL, PDF and ZIP import creates neither archive/chunks nor manifest; a permitted multi-file import writes only declared paths; foreign staged Git content remains unchanged; AGENTS edit with unsafe new rules leaves old file and backup state untouched; concurrent path change aborts.
  ```python
  def test_blocked_pdf_is_atomic(client, auth, vault):
      response = client.post("/api/dokulader/pdf", json=valid_pdf, headers=auth)
      assert response.status_code == 409
      assert not list((vault / "07 Anhänge/Dokumentationspakete").glob("*"))
      assert not list((vault / "01 Inbox").glob("*.md"))
  def test_blocked_agents_edit_keeps_old_rule_file(client, auth, vault):
      assert client.put("/api/vault/agents-md", json={"content": unsafe_rules}, headers=auth).status_code == 409
      assert (vault / "AGENTS.md").read_bytes() == old_rules
  ```
- [ ] **Step 2: Verify RED.** Run `.venv/bin/python -m pytest -q dashboard/backend/test_dashboard_upload.py dashboard/backend/test_dokulader_service.py dashboard/backend/test_agents_write_guard.py`; expect new tests to fail.
- [ ] **Step 3: Implement** staged preparation outside Vault and one guarded mutation boundary per operation. Keep DokuLader's existing duplicate and rollback behavior, and map `RuleBlocked` to HTTP 409 with a concise finding. Do not let direct API routes bypass the guard.
- [ ] **Step 4: Verify GREEN.** Run the same command; expect all task tests passed.
- [ ] **Step 5: Commit.** `git add dashboard/backend/dashboard_api.py dashboard/backend/dokulader_service.py dashboard/backend/test_dashboard_upload.py dashboard/backend/test_dokulader_service.py dashboard/backend/test_agents_write_guard.py && git commit -m "feat: guard app imports and rule edits"`.

### Task 8: Scanner-Ansicht, Dokumentation und Gesamtprüfung

**Files:** Modify `dashboard/frontend/index.html`, `dashboard/frontend/app.js`, `dashboard/frontend/style.css`, `docs/entscheidungen.md`, `docs/uebergabe.md`; create `dashboard/backend/test_scanner_frontend_contract.py`.

**Interfaces:** Consume Task 4 API. The menu gets `data-view="scanner"`; the view shows baseline time, current attempt/progress, separated `neu|geändert|entfernt` and `verletzt|unklar`, and report link by scan ID. Render untrusted paths/reasons with `textContent`, not HTML concatenation.

- [ ] **Step 1: Write the failing contract test** for menu/view IDs and API fields; assert that every status has distinct text and that no stale green state remains after an incomplete attempt.
  ```python
  def test_scanner_menu_and_view_contract(frontend_html, scanner_status):
      assert 'data-view="scanner"' in frontend_html
      assert 'id="scanner-view"' in frontend_html
      assert scanner_status["last_attempt"]["state"] == "incomplete"
      assert scanner_status["overall"] != "erfüllt"
  ```
- [ ] **Step 2: Verify RED.** Run `.venv/bin/python -m pytest -q dashboard/backend/test_scanner_frontend_contract.py`; expect failure.
- [ ] **Step 3: Implement** the view, scan button, bounded status polling, responsive layout and clear error states. Document the Vault report folder, Git behavior, fail-closed rule boundary and PR-1 dependency.
- [ ] **Step 4: Verify GREEN.** Run `.venv/bin/python -m pytest -q`, `node --check dashboard/frontend/app.js`, and `git diff --check`; expect all green. In an isolated local Vault, inspect first scan, second scan, model failure and narrow viewport in a browser. Do not touch NAS-Main.
- [ ] **Step 5: Commit.** `git add dashboard/frontend docs/entscheidungen.md docs/uebergabe.md dashboard/backend/test_scanner_frontend_contract.py && git commit -m "feat: show vault scanner and rule findings"`.

## Final review and handoff

After Task 8, compare every requirement in the spec with an implemented task, run the full suite again, and request one independent branch review. Fix Critical/Important findings with a failing regression test and one correction pass. Preserve the isolated worktree and present merge/PR/keep options only after a green final verification.
