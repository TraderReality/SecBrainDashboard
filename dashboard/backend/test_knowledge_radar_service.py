import tempfile
import unittest
from pathlib import Path

from knowledge_radar_service import analyze_knowledge_gaps


class KnowledgeRadarServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name)
        (self.vault / "02 Projekte").mkdir(parents=True)
        (self.vault / "03 Bereiche").mkdir()
        (self.vault / "01 Inbox").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_questions_rank_before_thin_pages_and_inbox_is_excluded(self):
        (self.vault / "02 Projekte/Watcher.md").write_text(
            "# Watcher\n\n[[KI]]\n\n## Offene Fragen\n\n- Wie erkennen wir veraltete Quellen?\n",
            encoding="utf-8",
        )
        (self.vault / "03 Bereiche/KI.md").write_text("# KI\n\nKurz.", encoding="utf-8")
        (self.vault / "01 Inbox/ignorieren.md").write_text(
            "# Eingang\n\n## Offene Fragen\n\n- Nicht auswerten?", encoding="utf-8"
        )
        result = analyze_knowledge_gaps(self.vault)
        self.assertTrue(result["read_only"])
        self.assertEqual(result["documents_scanned"], 2)
        self.assertEqual(result["candidates"][0]["type"], "offene_frage")
        self.assertIn("veraltete Quellen", result["candidates"][0]["title"])
        self.assertTrue(any(item["type"] == "duennes_thema" for item in result["candidates"]))

    def test_analysis_does_not_write_files(self):
        page = self.vault / "02 Projekte/Test.md"
        page.write_text("# Test\n\nKurz.", encoding="utf-8")
        before = {path.relative_to(self.vault) for path in self.vault.rglob("*")}
        analyze_knowledge_gaps(self.vault)
        after = {path.relative_to(self.vault) for path in self.vault.rglob("*")}
        self.assertEqual(before, after)

    def test_system_schema_questions_are_not_candidates(self):
        (self.vault / "03 Bereiche/SCHEMA.md").write_text(
            "---\ntyp: system\ntags: [system, schema]\n---\n\n# Schema\n\n## Offene Fragen\n\n- Platzhalter?\n",
            encoding="utf-8",
        )
        result = analyze_knowledge_gaps(self.vault)
        self.assertEqual(result["documents_scanned"], 1)
        self.assertEqual(result["candidate_count"], 0)


if __name__ == "__main__":
    unittest.main()
