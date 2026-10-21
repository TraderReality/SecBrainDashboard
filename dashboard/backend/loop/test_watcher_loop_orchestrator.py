import tempfile
import unittest
import hashlib
from pathlib import Path
from time import sleep

from loop.watcher_loop_orchestrator import WatcherLoopOrchestrator
from loop.watcher_loop_runtime import WatcherLoopRuntime


class WatcherLoopOrchestratorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name)
        for folder in ("01 Inbox", "06 Archiv", "08 KI-Wissensbank/_Vorschlaege", "09 Werkzeuge"):
            (self.vault / folder).mkdir(parents=True)
        (self.vault / "01 Inbox/eingang.md").write_text("# Echter Eingang\n\nInhalt", encoding="utf-8")
        (self.vault / "09 Werkzeuge/indexer.py").write_text("print('indexiert')\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

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

    def test_pauses_for_approval_with_real_inbox_context(self):
        calls = []

        def chat(messages, model):
            calls.append(messages[-1]["content"])
            return {"message": {"content": f"Ergebnis {len(calls)}"}}

        orchestrator = WatcherLoopOrchestrator(WatcherLoopRuntime(), chat, str(self.vault), self.retrieval)
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
        orchestrator.start("Inbox einpflegen", "test-model")
        self.wait(orchestrator, "awaiting_approval")
        orchestrator.reject()
        self.assertTrue((self.vault / "01 Inbox/eingang.md").exists())
        self.assertEqual(orchestrator.status()["state"], "rejected")

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


if __name__ == "__main__":
    unittest.main()
