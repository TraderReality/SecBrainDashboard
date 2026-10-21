import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import knowledge_research_service


class KnowledgeResearchServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name) / "vault"
        self.workspace = Path(self.temp.name) / "workspace"
        (self.vault / "02 Projekte").mkdir(parents=True)
        (self.vault / "02 Projekte/Watcher.md").write_text(
            "# Watcher\n\n## Offene Fragen\n\n- Wie werden Quellen aktuell gehalten?\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def candidate_id(self):
        radar = knowledge_research_service.analyze_knowledge_gaps(self.vault)
        return radar["candidates"][0]["id"]

    @patch("knowledge_research_service._extract_source")
    @patch("knowledge_research_service._search")
    def test_research_saves_only_to_temporary_workspace(self, search, extract):
        search.return_value = [{"title": "Quelle", "url": "https://example.org", "snippet": ""}]
        extract.return_value = {
            "title": "Offizielle Dokumentation", "url": "https://docs.example.org/guide",
            "date": "2026-08-23", "source_type": "Dokumentation",
            "statement": "Quellen werden mit Versionsständen und regelmäßiger Prüfung aktuell gehalten.",
        }
        before = {path.relative_to(self.vault) for path in self.vault.rglob("*")}
        with patch("knowledge_research_service._workspace_root", return_value=self.workspace):
            self.workspace.mkdir()
            result = knowledge_research_service.research_candidate(self.vault, self.candidate_id())
            proposal = knowledge_research_service.create_integration_proposal(self.vault, result["run_id"])
        after = {path.relative_to(self.vault) for path in self.vault.rglob("*")}
        self.assertEqual(before, after)
        self.assertTrue(result["temporary"])
        self.assertEqual(len(result["sources"]), 1)
        self.assertTrue((Path(result["workspace"]) / "report.md").is_file())
        self.assertTrue((Path(result["workspace"]) / "sources.json").is_file())
        self.assertIn("Offizielle Dokumentation", result["report"])
        self.assertEqual(proposal["kind"], "knowledge_radar")
        self.assertIn(proposal["operation"], {"neue_seite", "bestehende_seite_ergaenzen"})
        self.assertIn("+++ b/", proposal["markdown_diff"])
        self.assertGreaterEqual(proposal["confidence"], 0)
        self.assertEqual(proposal["wikilinks"], [])
        self.assertTrue((Path(result["workspace"]) / "proposal.diff").is_file())

    def test_unknown_candidate_is_rejected_before_search(self):
        with patch("knowledge_research_service._search") as search:
            with self.assertRaises(ValueError):
                knowledge_research_service.research_candidate(self.vault, "invented")
        search.assert_not_called()

    def test_source_type_is_explainable(self):
        self.assertEqual(knowledge_research_service._source_type("https://docs.python.org/3/"), "Dokumentation")
        self.assertEqual(knowledge_research_service._source_type("https://github.com/tobi/qmd"), "Repository")
        self.assertEqual(knowledge_research_service._source_type("https://arxiv.org/abs/123"), "Studie")

    def test_query_quotes_short_technical_identifier(self):
        query, required = knowledge_research_service._build_query({
            "title": "Soll qmd als Suchschicht für SecBrain evaluiert werden?"
        })
        self.assertIn('"qmd"', query)
        self.assertEqual(required, ["qmd"])

    def test_query_ignores_format_acronym_and_auxiliary_verb(self):
        query, required = knowledge_research_service._build_query({
            "title": "Welche Elemente des PDF-Systems sind für SecBrain übertragbar?"
        })
        self.assertEqual(required, [])
        self.assertNotIn('"sind"', query)

    @patch("knowledge_research_service._extract_source")
    @patch("knowledge_research_service._search")
    def test_proposal_extends_existing_nested_topic_page(self, search, extract):
        (self.vault / "04 Ressourcen/qmd").mkdir(parents=True)
        existing = self.vault / "04 Ressourcen/qmd/qmd.md"
        existing.write_text("# qmd\n\nBestehender Vault-Inhalt.\n", encoding="utf-8")
        (self.vault / "02 Projekte/Watcher.md").write_text(
            "# Watcher\n\n## Offene Fragen\n\n- Soll qmd als Suchschicht für SecBrain evaluiert werden?\n",
            encoding="utf-8",
        )
        search.return_value = [{"title": "qmd", "url": "https://github.com/tobi/qmd", "snippet": "qmd"}]
        extract.return_value = {
            "title": "qmd", "url": "https://github.com/tobi/qmd", "date": "2026-08-24",
            "source_type": "Repository", "statement": "qmd kombiniert lokale Volltext- und Vektorsuche.",
        }
        candidate = next(
            item for item in knowledge_research_service.analyze_knowledge_gaps(self.vault)["candidates"]
            if "qmd" in item["title"].casefold()
        )
        with patch("knowledge_research_service._workspace_root", return_value=self.workspace):
            self.workspace.mkdir()
            result = knowledge_research_service.research_candidate(self.vault, candidate["id"])
            proposal = knowledge_research_service.create_integration_proposal(self.vault, result["run_id"])
        self.assertEqual(proposal["operation"], "bestehende_seite_ergaenzen")
        self.assertEqual(proposal["target"], "04 Ressourcen/qmd/qmd.md")
        self.assertTrue(proposal["target_exists"])
        self.assertTrue(proposal["proposed_markdown"].startswith("# qmd\n\nBestehender Vault-Inhalt."))
        self.assertNotIn("+++ b/04 Ressourcen/qmd.md\n", proposal["markdown_diff"])

    @patch("knowledge_research_service._search")
    def test_search_uses_vault_page_context_for_generic_question(self, search):
        search.return_value = [{"title": "Quelle", "url": "https://example.org", "snippet": "PDF"}]
        query, results = knowledge_research_service._search_candidate({
            "title": "Welche Elemente des PDF-Systems sind für SecBrain übertragbar?",
            "source_title": "Second Brain — Bauanleitung",
        })
        self.assertEqual(len(results), 1)
        self.assertEqual(query, 'Second Brain — Bauanleitung')
        search.assert_called_once_with('Second Brain — Bauanleitung', [])

    @patch("knowledge_research_service._search")
    def test_search_retries_strict_technical_query_with_page_context(self, search):
        search.side_effect = [
            RuntimeError("keine Treffer"),
            [{"title": "qmd", "url": "https://example.org/qmd", "snippet": "qmd"}],
        ]
        query, results = knowledge_research_service._search_candidate({
            "title": "Soll qmd als Suchschicht evaluiert werden?",
            "source_title": "Second Brain — Bauanleitung",
        })
        self.assertEqual(len(results), 1)
        self.assertEqual(query, '"qmd" Second Brain — Bauanleitung')
        self.assertEqual(search.call_count, 2)


if __name__ == "__main__":
    unittest.main()
