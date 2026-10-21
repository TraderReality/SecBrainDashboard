import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import knowledge_ai_service


class KnowledgeAIServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name)
        (self.vault / "02 Projekte").mkdir()
        (self.vault / "02 Projekte/Watcher.md").write_text(
            "# Watcher\n\n## Offene Fragen\n\n- Soll qmd als Suchschicht evaluiert werden?\n", encoding="utf-8"
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_candidate_evaluation_is_validated_and_advisory_only(self):
        candidate = knowledge_ai_service.analyze_knowledge_gaps(self.vault)["candidates"][0]
        calls = []

        def chat(messages, model):
            calls.append((messages, model))
            return {"message": {"content": """```json
            {"summary":"Relevant", "reasoning":"Vault-Bezug", "duplicates":["ähnliche Frage"],
             "conflicts":[], "confidence":88, "recommendation":"aktualisieren",
             "proposed_target":"04 Ressourcen/qmd/qmd.md", "wikilinks":["qmd"]}
            ```"""}}

        result = knowledge_ai_service.evaluate_candidate(self.vault, candidate["id"], "qwen3:14b", chat)
        self.assertEqual(result["model"], "qwen3:14b")
        self.assertEqual(result["rule_score"], candidate["score"])
        self.assertEqual(result["recommendation"], "aktualisieren")
        self.assertTrue(result["advisory_only"])
        self.assertFalse(result["vault_changed"])
        self.assertEqual(len(calls), 1)
        self.assertIn("nichts schreiben", calls[0][0][0]["content"])

    @patch("knowledge_ai_service.load_research_run")
    def test_research_evaluation_uses_separate_one_shot_context(self, load):
        load.return_value = {
            "candidate": {"title": "qmd", "score": 92},
            "sources": [{"title": "Quelle", "statement": "Aussage", "vault_comparison": {"classification": "neu"}}],
        }
        chat = lambda **_: {"message": {"content": '{"summary":"S","reasoning":"R","confidence":75,"recommendation":"erweitern","duplicates":[],"conflicts":[],"wikilinks":[]}'}}
        result = knowledge_ai_service.evaluate_research(self.vault, "radar-20260824-120000-12345678", "model", chat)
        self.assertEqual(result["phase"], "recherche")
        self.assertEqual(result["confidence"], 75)


if __name__ == "__main__":
    unittest.main()
