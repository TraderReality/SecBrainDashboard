import tempfile
import unittest
import hashlib
import os
import shutil
import stat
import subprocess
from pathlib import Path
from time import sleep
from unittest.mock import patch

from loop.watcher_loop_orchestrator import WatcherLoopOrchestrator
from loop.watcher_loop_runtime import WatcherLoopRuntime


class WatcherLoopOrchestratorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name)
        self.state = self.vault.parent / (self.vault.name + "-state")
        self.env_patch = patch.dict(os.environ, {"SECBRAIN_WATCHER_STATE_DIR": str(self.state)})
        self.env_patch.start()
        for folder in ("01 Inbox", "06 Archiv", "08 KI-Wissensbank/_Vorschlaege", "09 Werkzeuge"):
            (self.vault / folder).mkdir(parents=True)
        (self.vault / "01 Inbox/eingang.md").write_text("# Echter Eingang\n\nInhalt", encoding="utf-8")
        (self.vault / "09 Werkzeuge/indexer.py").write_text("print('indexiert')\n", encoding="utf-8")

    def tearDown(self):
        self.env_patch.stop()
        self.temp.cleanup()
        shutil.rmtree(self.state, ignore_errors=True)

    @staticmethod
    def wait(orchestrator, state):
        for _ in range(300):
            if orchestrator.status()["state"] == state:
                return
            sleep(0.01)
        raise AssertionError(orchestrator.status())

    @staticmethod
    def retrieval(query, **_):
        return {
            "available": True, "provider": "qmd-bm25", "collection": "secbrain",
            "query": query, "max_results": 6, "max_chars": 14000, "used_chars": 50,
            "hits": [{"path": "qmd://secbrain/02 Projekte/Watcher.md", "title": "Watcher", "line": 1, "score": 0.87, "snippet": "Bestand"}],
            "context": "QUELLE: qmd://secbrain/02 Projekte/Watcher.md\nAUSZUG: Bestand", "error": None,
        }

    def init_git_vault(self, *, identity=True):
        subprocess.run(["git", "init", "-q", str(self.vault)], check=True)
        subprocess.run(["git", "-C", str(self.vault), "add", "-A"], check=True)
        subprocess.run([
            "git", "-C", str(self.vault), "-c", "user.name=Fixture",
            "-c", "user.email=fixture@local.invalid", "commit", "-qm", "Baseline",
        ], check=True)
        if identity:
            subprocess.run(["git", "-C", str(self.vault), "config", "user.name", "Fixture"], check=True)
            subprocess.run(["git", "-C", str(self.vault), "config", "user.email", "fixture@local.invalid"], check=True)

    def git_status(self):
        return subprocess.run(
            ["git", "-C", str(self.vault), "-c", "core.quotepath=false", "status", "--porcelain=v1", "--untracked-files=all"],
            capture_output=True, text=True, check=True,
        ).stdout.splitlines()

    def test_missing_git_identity_is_rejected_before_analysis(self):
        self.init_git_vault(identity=False)
        restricted = {
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "user.useConfigOnly",
            "GIT_CONFIG_VALUE_0": "true",
        }
        with patch.dict(os.environ, restricted):
            for key in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "EMAIL"):
                os.environ.pop(key, None)
            orchestrator = WatcherLoopOrchestrator(
                WatcherLoopRuntime(), lambda **_: {"message": {"content": "Analyse"}}, str(self.vault)
            )
            with self.assertRaisesRegex(RuntimeError, "Git-Autorenkennung"):
                orchestrator.start("Inbox prüfen", "test-model")
        self.assertTrue((self.vault / "01 Inbox/eingang.md").exists())
        self.assertFalse((self.vault / "06 Archiv/eingang.md").exists())
        self.assertFalse((self.state / "loop-proposals").exists())

    def test_indexer_failure_restores_inbox_vault_and_git_state(self):
        index = self.vault / "08 KI-Wissensbank/_index/graph.json"
        index.parent.mkdir()
        index.write_text('old index\n', encoding="utf-8")
        (self.vault / "09 Werkzeuge/indexer.py").write_text(
            "from pathlib import Path\n"
            "p = Path(__file__).resolve().parents[1] / '08 KI-Wissensbank/_index/graph.json'\n"
            "p.write_text('partial index\\n')\n"
            "(p.parent / 'statistics.json').write_text('partial statistics\\n')\n"
            "raise SystemExit(42)\n", encoding="utf-8",
        )
        self.init_git_vault()
        original = (self.vault / "01 Inbox/eingang.md").read_bytes()
        before = self.git_status()
        orchestrator = WatcherLoopOrchestrator(
            WatcherLoopRuntime(), lambda **_: {"message": {"content": "Analyse"}},
            str(self.vault), self.retrieval,
        )
        orchestrator.start("Inbox prüfen", "test-model")
        self.wait(orchestrator, "awaiting_approval")
        orchestrator.approve()
        self.wait(orchestrator, "failed")
        self.assertIn("Vault auf den Stand vor Freigabe zurückgesetzt", orchestrator.status()["error"])
        self.assertIn("QMD", orchestrator.status()["error"])
        self.assertEqual((self.vault / "01 Inbox/eingang.md").read_bytes(), original)
        self.assertFalse((self.vault / "06 Archiv/eingang.md").exists())
        self.assertFalse((self.vault / "08 KI-Wissensbank/Quelle — Eingang.md").exists())
        self.assertFalse((self.vault / "08 KI-Wissensbank/_Log.md").exists())
        self.assertEqual(index.read_text(encoding="utf-8"), 'old index\n')
        self.assertFalse((index.parent / "statistics.json").exists())
        self.assertEqual(self.git_status(), before)
        self.assertTrue((self.state / "qmd-resync-required").is_file())

        (self.vault / "09 Werkzeuge/indexer.py").write_text(
            "from pathlib import Path\n"
            "p = Path(__file__).resolve().parents[1] / '08 KI-Wissensbank/_index/graph.json'\n"
            "p.write_text('resynced index\\n')\n", encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(self.vault), "add", "09 Werkzeuge/indexer.py"], check=True)
        subprocess.run(["git", "-C", str(self.vault), "commit", "-qm", "Indexer repariert"], check=True)
        retry = WatcherLoopOrchestrator(
            WatcherLoopRuntime(), lambda **_: {"message": {"content": "Analyse"}},
            str(self.vault), self.retrieval,
        )
        retry.start("Inbox erneut prüfen", "test-model")
        self.assertFalse((self.state / "qmd-resync-required").exists())
        self.assertEqual(index.read_text(encoding="utf-8"), 'old index\n')
        self.wait(retry, "awaiting_approval")
        retry.approve()
        self.wait(retry, "completed")
        self.assertFalse((self.vault / "01 Inbox/eingang.md").exists())
        self.assertEqual((self.vault / "06 Archiv/eingang.md").read_bytes(), original)
        self.assertEqual(len(list((self.vault / "06 Archiv").glob("eingang.md"))), 1)

    def test_rollback_preserves_unexpected_edit_to_created_note(self):
        (self.vault / "09 Werkzeuge/indexer.py").write_text(
            "from pathlib import Path\n"
            "p = Path(__file__).resolve().parents[1] / '08 KI-Wissensbank/Quelle — Eingang.md'\n"
            "p.write_text(p.read_text() + '\\nFremde Änderung\\n')\n"
            "raise SystemExit(42)\n", encoding="utf-8",
        )
        self.init_git_vault()
        orchestrator = WatcherLoopOrchestrator(
            WatcherLoopRuntime(), lambda **_: {"message": {"content": "Analyse"}},
            str(self.vault), self.retrieval,
        )
        orchestrator.start("Inbox prüfen", "test-model")
        self.wait(orchestrator, "awaiting_approval")
        orchestrator.approve()
        self.wait(orchestrator, "failed")
        self.assertIn("nicht überschrieben", orchestrator.status()["error"])
        self.assertIn("Fremde Änderung", (self.vault / "08 KI-Wissensbank/Quelle — Eingang.md").read_text())

    def test_successful_indexer_cannot_commit_foreign_edit_to_created_note(self):
        (self.vault / "09 Werkzeuge/indexer.py").write_text(
            "from pathlib import Path\n"
            "p = Path(__file__).resolve().parents[1] / '08 KI-Wissensbank/Quelle — Eingang.md'\n"
            "p.write_text(p.read_text() + '\\nFremde Änderung\\n')\n",
            encoding="utf-8",
        )
        self.init_git_vault()
        baseline = subprocess.check_output(["git", "-C", str(self.vault), "rev-parse", "HEAD"], text=True).strip()
        orchestrator = WatcherLoopOrchestrator(
            WatcherLoopRuntime(), lambda **_: {"message": {"content": "Analyse"}},
            str(self.vault), self.retrieval,
        )
        orchestrator.start("Inbox prüfen", "test-model")
        self.wait(orchestrator, "awaiting_approval")
        orchestrator.approve()
        self.wait(orchestrator, "failed")
        self.assertEqual(subprocess.check_output(["git", "-C", str(self.vault), "rev-parse", "HEAD"], text=True).strip(), baseline)
        self.assertIn("Fremde Änderung", (self.vault / "08 KI-Wissensbank/Quelle — Eingang.md").read_text())

    def test_literal_inbox_filename_does_not_commit_matching_new_file(self):
        (self.vault / "01 Inbox/eingang.md").rename(self.vault / "01 Inbox/a*.md")
        self.init_git_vault()
        orchestrator = WatcherLoopOrchestrator(
            WatcherLoopRuntime(), lambda **_: {"message": {"content": "Analyse"}},
            str(self.vault), self.retrieval,
        )
        orchestrator.start("Inbox prüfen", "test-model")
        self.wait(orchestrator, "awaiting_approval")
        foreign = self.vault / "01 Inbox/abc.md"
        foreign.write_text("# Späterer Eingang\n", encoding="utf-8")
        orchestrator.approve()
        self.wait(orchestrator, "completed")
        committed = subprocess.check_output(
            ["git", "-C", str(self.vault), "show", "--pretty=", "--name-only", "HEAD"], text=True,
        ).splitlines()
        self.assertNotIn("01 Inbox/abc.md", committed)
        self.assertTrue(any("01 Inbox/abc.md" in line for line in self.git_status()))

    def test_new_inbox_file_after_analysis_is_not_in_run_commit(self):
        self.init_git_vault()
        orchestrator = WatcherLoopOrchestrator(
            WatcherLoopRuntime(), lambda **_: {"message": {"content": "Analyse"}},
            str(self.vault), self.retrieval,
        )
        orchestrator.start("Inbox prüfen", "test-model")
        self.wait(orchestrator, "awaiting_approval")
        foreign = self.vault / "01 Inbox/spaeter.md"
        foreign.write_text("# Späterer Eingang\n", encoding="utf-8")
        orchestrator.approve()
        self.wait(orchestrator, "completed")
        self.assertTrue(foreign.exists())
        committed = subprocess.run(
            ["git", "-C", str(self.vault), "show", "--pretty=", "--name-only", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        self.assertNotIn("01 Inbox/spaeter.md", committed)
        self.assertEqual(len(self.git_status()), 1)
        self.assertIn("01 Inbox/spaeter.md", self.git_status()[0])

    def test_foreign_staged_change_during_indexing_is_not_committed_or_reset(self):
        foreign = self.vault / "02 Projekte/fremd.md"
        foreign.parent.mkdir()
        foreign.write_text("# Vorher\n", encoding="utf-8")
        (self.vault / "09 Werkzeuge/indexer.py").write_text(
            "import subprocess\nfrom pathlib import Path\n"
            "v = Path(__file__).resolve().parents[1]\n"
            "p = v / '02 Projekte/fremd.md'\n"
            "p.write_text('# Fremde Änderung\\n')\n"
            "subprocess.run(['git', '-C', str(v), 'add', '02 Projekte/fremd.md'], check=True)\n",
            encoding="utf-8",
        )
        self.init_git_vault()
        baseline = subprocess.check_output(["git", "-C", str(self.vault), "rev-parse", "HEAD"], text=True).strip()
        orchestrator = WatcherLoopOrchestrator(
            WatcherLoopRuntime(), lambda **_: {"message": {"content": "Analyse"}},
            str(self.vault), self.retrieval,
        )
        orchestrator.start("Inbox prüfen", "test-model")
        self.wait(orchestrator, "awaiting_approval")
        orchestrator.approve()
        self.wait(orchestrator, "failed")
        self.assertEqual(subprocess.check_output(["git", "-C", str(self.vault), "rev-parse", "HEAD"], text=True).strip(), baseline)
        self.assertEqual(foreign.read_text(encoding="utf-8"), "# Fremde Änderung\n")
        staged = subprocess.check_output(["git", "-C", str(self.vault), "diff", "--cached", "--name-only"], text=True)
        self.assertEqual(staged.strip(), "02 Projekte/fremd.md")
        self.assertTrue((self.vault / "01 Inbox/eingang.md").exists())

    def test_rollback_preserves_foreign_staged_bytes_on_run_path(self):
        (self.vault / "09 Werkzeuge/indexer.py").write_text(
            "import subprocess\nfrom pathlib import Path\n"
            "v = Path(__file__).resolve().parents[1]\n"
            "p = v / '08 KI-Wissensbank/Quelle — Eingang.md'\n"
            "own = p.read_bytes()\n"
            "p.write_text('FREMDE GESTAGTE FASSUNG\\n')\n"
            "subprocess.run(['git', '-C', str(v), 'add', '--', str(p.relative_to(v))], check=True)\n"
            "p.write_bytes(own)\n"
            "raise SystemExit(42)\n",
            encoding="utf-8",
        )
        self.init_git_vault()
        orchestrator = WatcherLoopOrchestrator(
            WatcherLoopRuntime(), lambda **_: {"message": {"content": "Analyse"}},
            str(self.vault), self.retrieval,
        )
        orchestrator.start("Inbox prüfen", "test-model")
        self.wait(orchestrator, "awaiting_approval")
        orchestrator.approve()
        self.wait(orchestrator, "failed")
        staged = subprocess.check_output(
            ["git", "-C", str(self.vault), "show", ":08 KI-Wissensbank/Quelle — Eingang.md"], text=True,
        )
        self.assertEqual(staged, "FREMDE GESTAGTE FASSUNG\n")

    def test_process_exit_recovers_partial_apply_before_next_run(self):
        self.init_git_vault()
        from loop.vault_loop_executor import VaultLoopExecutor
        executor = VaultLoopExecutor(self.vault)
        inputs = executor.snapshot_inbox()
        proposal = executor.create_proposal("CRASH", "Inbox prüfen", "", inputs, [])
        code = (
            "import os\n"
            "from loop.vault_loop_executor import VaultLoopExecutor\n"
            "e = VaultLoopExecutor(os.environ['SECBRAIN_VAULT'])\n"
            "e._run_indexer = lambda: os._exit(42)\n"
            "e.apply(e.snapshot_inbox(), {'path': os.environ['SECBRAIN_PROPOSAL']})\n"
        )
        env = dict(os.environ, SECBRAIN_VAULT=str(self.vault), SECBRAIN_PROPOSAL=proposal["path"])
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        result = subprocess.run([os.sys.executable, "-c", code], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 42, result.stderr)
        self.assertFalse((self.vault / "01 Inbox/eingang.md").exists())
        self.assertTrue((self.state / "qmd-resync-required").exists())
        VaultLoopExecutor(self.vault).ensure_commit_ready()
        self.assertTrue((self.vault / "01 Inbox/eingang.md").exists())
        self.assertFalse((self.vault / "06 Archiv/eingang.md").exists())
        self.assertFalse((self.state / "loop-transaction.json").exists())

    def test_process_exit_after_ref_update_repairs_git_index(self):
        self.init_git_vault()
        from loop.vault_loop_executor import VaultLoopExecutor
        executor = VaultLoopExecutor(self.vault)
        proposal = executor.create_proposal("COMMITCRASH", "Inbox prüfen", "", executor.snapshot_inbox(), [])
        code = (
            "import os\n"
            "from loop import vault_loop_executor as module\n"
            "real_run = module.subprocess.run\n"
            "def crash_after_ref(args, **kwargs):\n"
            "    result = real_run(args, **kwargs)\n"
            "    if 'update-ref' in args and result.returncode == 0:\n"
            "        os._exit(43)\n"
            "    return result\n"
            "module.subprocess.run = crash_after_ref\n"
            "e = module.VaultLoopExecutor(os.environ['SECBRAIN_VAULT'])\n"
            "e.apply(e.snapshot_inbox(), {'path': os.environ['SECBRAIN_PROPOSAL']})\n"
        )
        env = dict(os.environ, SECBRAIN_VAULT=str(self.vault), SECBRAIN_PROPOSAL=proposal["path"])
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        result = subprocess.run([os.sys.executable, "-c", code], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 43, result.stderr)
        self.assertTrue((self.vault / ".git/index.lock").exists())
        VaultLoopExecutor(self.vault).ensure_commit_ready()
        self.assertFalse((self.vault / ".git/index.lock").exists())
        self.assertFalse((self.state / "loop-transaction.json").exists())
        self.assertEqual(self.git_status(), [])

    def test_recovery_keeps_unknown_git_index_lock(self):
        self.init_git_vault()
        from loop.vault_loop_executor import VaultLoopExecutor
        executor = VaultLoopExecutor(self.vault)
        proposal = executor.create_proposal("LOCKCRASH", "Test", "", executor.snapshot_inbox(), [])
        code = (
            "import os\nfrom loop.vault_loop_executor import VaultLoopExecutor\n"
            "e = VaultLoopExecutor(os.environ['SECBRAIN_VAULT'])\n"
            "e._run_indexer = lambda: os._exit(42)\n"
            "e.apply(e.snapshot_inbox(), {'path': os.environ['SECBRAIN_PROPOSAL']})\n"
        )
        env = dict(os.environ, SECBRAIN_VAULT=str(self.vault), SECBRAIN_PROPOSAL=proposal["path"])
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        self.assertEqual(subprocess.run([os.sys.executable, "-c", code], env=env).returncode, 42)
        lock = self.vault / ".git/index.lock"
        lock.write_bytes(b"")  # Git itself creates an empty lock before writing its index.
        with self.assertRaisesRegex(RuntimeError, "Unbekannte Git-Index-Sperre"):
            VaultLoopExecutor(self.vault).ensure_commit_ready()
        self.assertTrue(lock.exists())
        lock.unlink()
        VaultLoopExecutor(self.vault).ensure_commit_ready()
        self.assertTrue((self.vault / "01 Inbox/eingang.md").exists())

    def test_recovery_preserves_index_staged_after_precheck(self):
        self.init_git_vault()
        from loop.vault_loop_executor import VaultLoopExecutor
        executor = VaultLoopExecutor(self.vault)
        proposal = executor.create_proposal("RACECRASH", "Test", "", executor.snapshot_inbox(), [])
        code = (
            "import os\nfrom loop import vault_loop_executor as module\n"
            "real_run = module.subprocess.run\n"
            "def crash_after_ref(args, **kwargs):\n"
            "    result = real_run(args, **kwargs)\n"
            "    if 'update-ref' in args and result.returncode == 0: os._exit(43)\n"
            "    return result\n"
            "module.subprocess.run = crash_after_ref\n"
            "e = module.VaultLoopExecutor(os.environ['SECBRAIN_VAULT'])\n"
            "e.apply(e.snapshot_inbox(), {'path': os.environ['SECBRAIN_PROPOSAL']})\n"
        )
        env = dict(os.environ, SECBRAIN_VAULT=str(self.vault), SECBRAIN_PROPOSAL=proposal["path"])
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        self.assertEqual(subprocess.run([os.sys.executable, "-c", code], env=env).returncode, 43)
        foreign = self.vault / "02 Projekte/fremd.md"
        foreign.parent.mkdir()
        foreign.write_text("NUR FREMD GESTAGT\n", encoding="utf-8")
        real_run = subprocess.run
        injected = False

        def stage_after_precheck(args, **kwargs):
            nonlocal injected
            result = real_run(args, **kwargs)
            if not injected and "diff" in args and "--cached" in args and "--name-only" in args:
                injected = True
                real_run(["git", "-C", str(self.vault), "add", "02 Projekte/fremd.md"], check=True)
            return result

        with patch("loop.vault_loop_executor.subprocess.run", side_effect=stage_after_precheck):
            with self.assertRaisesRegex(RuntimeError, "Git-Index wurde"):
                VaultLoopExecutor(self.vault).ensure_commit_ready()
        self.assertTrue(injected)
        self.assertEqual(
            subprocess.check_output(["git", "-C", str(self.vault), "show", ":02 Projekte/fremd.md"], text=True),
            "NUR FREMD GESTAGT\n",
        )
        self.assertTrue((self.state / "loop-transaction.json").exists())

    def test_changed_inbox_after_analysis_is_not_archived(self):
        self.init_git_vault()
        orchestrator = WatcherLoopOrchestrator(
            WatcherLoopRuntime(), lambda **_: {"message": {"content": "Analyse"}},
            str(self.vault), self.retrieval,
        )
        orchestrator.start("Inbox prüfen", "test-model")
        self.wait(orchestrator, "awaiting_approval")
        source = self.vault / "01 Inbox/eingang.md"
        source.write_text("# Zwischenzeitlich geändert\n", encoding="utf-8")
        orchestrator.approve()
        self.wait(orchestrator, "failed")
        self.assertEqual(source.read_text(encoding="utf-8"), "# Zwischenzeitlich geändert\n")
        self.assertFalse((self.vault / "06 Archiv/eingang.md").exists())

    def test_existing_archive_target_blocks_approval_without_overwrite(self):
        self.init_git_vault()
        orchestrator = WatcherLoopOrchestrator(
            WatcherLoopRuntime(), lambda **_: {"message": {"content": "Analyse"}},
            str(self.vault), self.retrieval,
        )
        orchestrator.start("Inbox prüfen", "test-model")
        self.wait(orchestrator, "awaiting_approval")
        target = self.vault / "06 Archiv/eingang.md"
        target.write_text("# Vorhandenes Archiv\n", encoding="utf-8")
        orchestrator.approve()
        self.wait(orchestrator, "failed")
        self.assertEqual(target.read_text(encoding="utf-8"), "# Vorhandenes Archiv\n")
        self.assertTrue((self.vault / "01 Inbox/eingang.md").exists())

    def test_pauses_for_approval_with_real_inbox_context(self):
        calls = []

        def chat(messages, model):
            calls.append(messages[-1]["content"])
            return {"message": {"content": f"Ergebnis {len(calls)}"}}

        orchestrator = WatcherLoopOrchestrator(WatcherLoopRuntime(), chat, str(self.vault), self.retrieval)
        before = {path.relative_to(self.vault) for path in self.vault.rglob("*")}
        orchestrator.start("Inbox einpflegen", "test-model")
        self.wait(orchestrator, "awaiting_approval")

        state = orchestrator.status()
        self.assertEqual(state["completed_stations"], 5)
        self.assertTrue(state["approval_required"])
        self.assertIn("# Echter Eingang", calls[0])
        self.assertIn("RELEVANTER BESTAND VIA QMD", calls[0])
        self.assertEqual(state["vault_retrieval"]["hits"][0]["score"], 0.87)
        self.assertIn("Vault-Quellen via QMD", state["results"][0]["output"])
        self.assertTrue((self.vault / "01 Inbox/eingang.md").exists())
        self.assertFalse((self.vault / "06 Archiv/eingang.md").exists())
        self.assertEqual(before, {path.relative_to(self.vault) for path in self.vault.rglob("*")})
        self.assertTrue(Path(state["proposal"]["path"]).is_file())
        self.assertEqual(Path(state["proposal"]["path"]).parent, (self.state / "loop-proposals").resolve())
        self.assertEqual(stat.S_IMODE(Path(state["proposal"]["path"]).stat().st_mode), 0o600)
        self.assertEqual(orchestrator._runtime.status()["current_station"], 6)

    def test_context_reads_existing_linked_vault_page(self):
        (self.vault / "02 Projekte").mkdir()
        (self.vault / "02 Projekte/SecBrain Watcher.md").write_text(
            "# SecBrain Watcher\n\nTatsächlicher Projektinhalt", encoding="utf-8"
        )
        (self.vault / "01 Inbox/eingang.md").write_text(
            "# Eingang\n\nBezug zu [[SecBrain Watcher]].", encoding="utf-8"
        )
        executor = WatcherLoopOrchestrator(WatcherLoopRuntime(), lambda **_: {}, str(self.vault))._executor
        context = executor.context(executor.snapshot_inbox())
        self.assertIn("GELESENE VAULT-SEITE: 02 Projekte/SecBrain Watcher.md", context)
        self.assertIn("Tatsächlicher Projektinhalt", context)

    def test_indexer_receives_active_vault_path(self):
        (self.vault / "09 Werkzeuge/indexer.py").write_text(
            "import os\nfrom pathlib import Path\n"
            "assert Path(os.environ['SECBRAIN_VAULT']).resolve() == Path(__file__).resolve().parents[1]\n"
            "assert os.environ['SECBRAIN_QMD_EMBED'] == '0'\n",
            encoding="utf-8",
        )
        executor = WatcherLoopOrchestrator(
            WatcherLoopRuntime(), lambda **_: {}, str(self.vault)
        )._executor
        with patch.dict(os.environ, {"SECBRAIN_VAULT": "/home/secbrain/Dokumente/SecBrain"}):
            self.assertTrue(executor._run_indexer()["ok"])

    def test_pending_proposal_does_not_dirty_git_vault(self):
        subprocess.run(["git", "init", "-q", str(self.vault)], check=True)
        subprocess.run(["git", "-C", str(self.vault), "add", "-A"], check=True)
        subprocess.run([
            "git", "-C", str(self.vault), "-c", "user.name=Test",
            "-c", "user.email=test@example.invalid", "commit", "-qm", "Baseline",
        ], check=True)
        (self.vault / "01 Inbox/eingang.md").write_text("# Neuer Eingang\n", encoding="utf-8")
        orchestrator = WatcherLoopOrchestrator(
            WatcherLoopRuntime(), lambda **_: {"message": {"content": "Analyse"}},
            str(self.vault), self.retrieval,
        )
        orchestrator.start("Inbox prüfen", "test-model")
        self.wait(orchestrator, "awaiting_approval")
        orchestrator._executor.ensure_commit_ready()
        status = subprocess.run(
            ["git", "-C", str(self.vault), "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        self.assertEqual(len(status), 1)
        self.assertIn("01 Inbox/eingang.md", status[0])

    def test_approval_applies_fixed_operations_and_completes(self):
        def chat(messages, model):
            return {"message": {"content": "Geprüfte Analyse"}}

        runtime = WatcherLoopRuntime()
        orchestrator = WatcherLoopOrchestrator(runtime, chat, str(self.vault), self.retrieval)
        orchestrator.start("Inbox einpflegen", "test-model")
        self.wait(orchestrator, "awaiting_approval")
        orchestrator.approve()
        self.wait(orchestrator, "completed")

        self.assertFalse((self.vault / "01 Inbox/eingang.md").exists())
        self.assertTrue((self.vault / "06 Archiv/eingang.md").exists())
        self.assertTrue((self.vault / "08 KI-Wissensbank/Quelle — Eingang.md").exists())
        self.assertEqual(len(list((self.vault / "08 KI-Wissensbank/_Vorschlaege").glob("Watcher-Vorschlag-*.md"))), 1)
        self.assertEqual(orchestrator.status()["completed_stations"], 12)
        self.assertEqual(
            [item["station_id"] for item in orchestrator.status()["results"]],
            list(range(1, 13)),
        )
        self.assertEqual(orchestrator.status()["vault_retrieval"]["provider"], "qmd-bm25")
        self.assertEqual(runtime.status()["current_station"], 1)

    def test_confirmed_author_is_used_in_source_name_and_metadata(self):
        def chat(messages, model):
            return {"message": {"content": "Geprüfte Analyse"}}

        orchestrator = WatcherLoopOrchestrator(WatcherLoopRuntime(), chat, str(self.vault))
        orchestrator.start("Inbox einpflegen", "test-model", "Julian Ivanov")
        self.wait(orchestrator, "awaiting_approval")
        orchestrator.approve()
        self.wait(orchestrator, "completed")

        note = self.vault / "08 KI-Wissensbank/Quelle — Eingang von Julian Ivanov.md"
        self.assertTrue(note.exists())
        content = note.read_text(encoding="utf-8")
        self.assertIn("titel: Quelle — Eingang von Julian Ivanov", content)
        self.assertIn("- **Urheber:** Julian Ivanov", content)
        self.assertIn("## Kernaussagen", content)
        self.assertIn("## Bezug zum Bestand", content)
        self.assertIn("## Offene Fragen", content)
        self.assertNotIn("## Vollständiger Eingang", content)

    def test_source_title_preserves_brand_spelling_and_natural_case(self):
        from loop.vault_loop_executor import VaultLoopExecutor
        title = VaultLoopExecutor._source_title(
            "SecBrain Watcher — Chartanalyse mit Vision und Marktdaten.md", ""
        )
        self.assertEqual(title, "Quelle — SecBrain Watcher — Chartanalyse mit Vision und Marktdaten")

    def test_reject_keeps_inbox_untouched(self):
        def chat(messages, model):
            return {"message": {"content": "Analyse"}}

        orchestrator = WatcherLoopOrchestrator(WatcherLoopRuntime(), chat, str(self.vault))
        before = {path.relative_to(self.vault) for path in self.vault.rglob("*")}
        orchestrator.start("Inbox einpflegen", "test-model")
        self.wait(orchestrator, "awaiting_approval")
        orchestrator.reject()
        self.assertTrue((self.vault / "01 Inbox/eingang.md").exists())
        self.assertEqual(orchestrator.status()["state"], "rejected")
        self.assertEqual(before, {path.relative_to(self.vault) for path in self.vault.rglob("*")})

    def test_error_stops_at_failing_station(self):
        calls = []

        def chat(messages, model):
            calls.append(messages)
            if len(calls) == 2:
                raise RuntimeError("Modellfehler")
            return {"message": {"content": "OK"}}

        runtime = WatcherLoopRuntime()
        orchestrator = WatcherLoopOrchestrator(runtime, chat, str(self.vault))
        orchestrator.start("Inbox prüfen", "test-model")
        self.wait(orchestrator, "failed")
        self.assertEqual(runtime.status()["current_station"], 2)

    def test_research_proposal_continues_through_station_twelve_after_approval(self):
        runtime = WatcherLoopRuntime()
        orchestrator = WatcherLoopOrchestrator(runtime, lambda **_: {}, str(self.vault))
        before = {path.relative_to(self.vault) for path in self.vault.rglob("*")}
        proposed = "# qmd\n\nKontrolliert übernommener Inhalt.\n"
        proposal = {
            "kind": "knowledge_radar", "proposal_id": "proposal-test", "operation": "neue_seite",
            "target": "04 Ressourcen/qmd.md", "confidence": 88, "conflicts": [],
            "target_exists": False, "proposed_markdown": proposed,
            "original_hash": hashlib.sha256(b"").hexdigest(),
            "proposed_hash": hashlib.sha256(proposed.encode("utf-8")).hexdigest(),
            "markdown_diff": "--- a/04 Ressourcen/qmd.md\n+++ b/04 Ressourcen/qmd.md\n+# qmd",
            "wikilinks": ["Second Brain"],
            "candidate": {"title": "qmd evaluieren"},
        }
        state = orchestrator.stage_research_proposal(proposal, "test-model")
        self.assertTrue(state["approval_required"])
        self.assertEqual(runtime.status()["current_station"], 6)
        self.assertEqual(before, {path.relative_to(self.vault) for path in self.vault.rglob("*")})

        approved = orchestrator.approve()
        self.assertEqual(approved["state"], "applying")
        self.wait(orchestrator, "completed")
        self.assertEqual((self.vault / "04 Ressourcen/qmd.md").read_text(encoding="utf-8"), proposed)
        self.assertTrue((self.vault / "08 KI-Wissensbank/_Log.md").is_file())
        self.assertEqual([item["station_id"] for item in orchestrator.status()["results"]], list(range(5, 13)))
        self.assertEqual(runtime.status()["current_station"], 1)

    def test_research_indexer_failure_restores_target_log_and_git(self):
        (self.vault / "09 Werkzeuge/indexer.py").write_text("raise SystemExit(42)\n", encoding="utf-8")
        self.init_git_vault()
        from loop.vault_loop_executor import VaultLoopExecutor
        executor = VaultLoopExecutor(self.vault)
        proposed = "# Radar-Seite\n"
        proposal = {
            "kind": "knowledge_radar", "proposal_id": "failure-test",
            "target": "04 Ressourcen/radar.md", "target_exists": False,
            "proposed_markdown": proposed,
            "original_hash": hashlib.sha256(b"").hexdigest(),
            "proposed_hash": hashlib.sha256(proposed.encode()).hexdigest(),
        }
        baseline = subprocess.check_output(["git", "-C", str(self.vault), "rev-parse", "HEAD"], text=True).strip()
        with self.assertRaises(RuntimeError):
            executor.apply_research(proposal)
        self.assertFalse((self.vault / "04 Ressourcen/radar.md").exists())
        self.assertFalse((self.vault / "08 KI-Wissensbank/_Log.md").exists())
        self.assertEqual(subprocess.check_output(["git", "-C", str(self.vault), "rev-parse", "HEAD"], text=True).strip(), baseline)
        self.assertFalse((self.state / "loop-transaction.json").exists())
        self.assertTrue((self.state / "qmd-resync-required").exists())


if __name__ == "__main__":
    unittest.main()
