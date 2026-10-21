import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import knowledge_growth_service


class KnowledgeGrowthServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.vault = root / "vault"
        self.state = root / "state"
        (self.vault / "02 Projekte").mkdir(parents=True)
        self.page = self.vault / "02 Projekte/Watcher.md"
        self.page.write_text("# Watcher\n\n## Offene Fragen\n\n- Wie bleibt die Quelle aktuell?\n", encoding="utf-8")
        self.state.mkdir()
        self.state_patch = patch("knowledge_growth_service._state_root", return_value=self.state)
        self.state_patch.start()
        self.workspace_patch = patch("knowledge_growth_service._research_workspace_root", return_value=root / "research")
        self.workspace_patch.start()

    def tearDown(self):
        self.workspace_patch.stop()
        self.state_patch.stop()
        self.temp.cleanup()

    def research_result(self, statement="Erste Fassung", date="2026-08-24"):
        return {
            "run_id": "radar-20260824-120000-12345678", "query": "Quelle aktuell",
            "sources": [{"url": "https://example.org/source", "title": "Quelle", "date": date, "statement": statement}],
        }

    def test_config_validates_schedule_and_budget(self):
        config = knowledge_growth_service.update_growth_config("weekly", 4)
        self.assertEqual(config["schedule"], "weekly")
        self.assertEqual(config["topic_budget"], 4)
        self.assertIsNotNone(config["next_run"])
        with self.assertRaises(ValueError):
            knowledge_growth_service.update_growth_config("daily", 4)
        with self.assertRaises(ValueError):
            knowledge_growth_service.update_growth_config("manual", 0)

    @patch("knowledge_growth_service.research_candidate")
    def test_only_changed_or_stale_topics_are_researched(self, research):
        research.return_value = self.research_result()
        first = knowledge_growth_service.run_growth_radar(self.vault)
        second = knowledge_growth_service.run_growth_radar(self.vault)
        self.page.write_text(self.page.read_text(encoding="utf-8") + "\nNeue Information.\n", encoding="utf-8")
        third = knowledge_growth_service.run_growth_radar(self.vault)
        self.assertEqual(first["processed_topics"], 1)
        self.assertEqual(second["processed_topics"], 0)
        self.assertEqual(second["skipped_unchanged"], 1)
        self.assertEqual(third["processed_topics"], 1)
        self.assertEqual(research.call_count, 2)

    @patch("knowledge_growth_service.research_candidate")
    def test_source_hash_and_date_changes_are_recorded_in_history(self, research):
        research.side_effect = [
            self.research_result("Erste Fassung", "2026-08-23"),
            self.research_result("Geänderte Fassung", "2026-08-24"),
        ]
        first = knowledge_growth_service.run_growth_radar(self.vault)
        self.page.write_text(self.page.read_text(encoding="utf-8") + "\nÄnderung.\n", encoding="utf-8")
        second = knowledge_growth_service.run_growth_radar(self.vault)
        self.assertEqual(first["changed_sources"], 0)
        self.assertEqual(second["changed_sources"], 1)
        self.assertTrue(second["entries"][0]["sources"][0]["changed"])
        self.assertEqual(len(knowledge_growth_service.get_growth_history()), 2)

    @patch("knowledge_growth_service.research_candidate", side_effect=RuntimeError("Netzfehler"))
    def test_failed_topic_remains_due_for_next_run(self, research):
        first = knowledge_growth_service.run_growth_radar(self.vault)
        second = knowledge_growth_service.run_growth_radar(self.vault)
        self.assertEqual(first["status"], "partial")
        self.assertEqual(second["processed_topics"], 1)
        self.assertEqual(research.call_count, 2)

    def test_researched_topics_are_persisted_for_continued_maintenance(self):
        candidate = knowledge_growth_service.analyze_knowledge_gaps(self.vault)["candidates"][0]
        first = knowledge_growth_service.record_research(candidate, self.research_result(), "manual")
        second = knowledge_growth_service.record_research(
            candidate, self.research_result("Zweite Fassung", "2026-08-25"), "manual"
        )
        knowledge_growth_service.record_proposal(second["last_run_id"], {
            "proposal_id": "proposal-1", "operation": "bestehende_seite_ergaenzen",
            "target": "02 Projekte/Watcher.md", "confidence": 91, "created_at": "2026-08-25T10:00:00Z",
        })
        topics = knowledge_growth_service.researched_topics(self.vault)
        self.assertEqual(len(topics), 1)
        self.assertEqual(first["research_count"], 1)
        self.assertEqual(topics[0]["research_count"], 2)
        self.assertEqual(topics[0]["source_count"], 1)
        self.assertEqual(topics[0]["proposal"]["target"], "02 Projekte/Watcher.md")
        self.assertTrue(topics[0]["candidate_available"])


if __name__ == "__main__":
    unittest.main()
