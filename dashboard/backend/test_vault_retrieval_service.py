import json
import os
import unittest
from unittest.mock import patch

import vault_retrieval_service as service


class VaultRetrievalServiceTest(unittest.TestCase):
    @patch.dict(os.environ, {"SECBRAIN_QMD_BINARY": "/opt/qmd/bin/qmd"}, clear=False)
    @patch("vault_retrieval_service.shutil.which", return_value=None)
    def test_configured_binary_takes_precedence_over_path(self, _which):
        self.assertEqual(service._binary(), "/opt/qmd/bin/qmd")

    @patch("vault_retrieval_service.shutil.which", return_value="/usr/bin/qmd")
    @patch("vault_retrieval_service.subprocess.run")
    def test_returns_bounded_structured_hits_and_context(self, run, _which):
        run.return_value.returncode = 0
        run.return_value.stdout = json.dumps([{
            "score": 0.82, "file": "qmd://secbrain/02 Projekte/Watcher.md",
            "line": 12, "title": "Watcher", "snippet": "Relevanter Inhalt " * 100,
        }])
        run.return_value.stderr = ""

        result = service.retrieve_vault_context("Watcher Kontext", max_results=99, max_chars=1000)

        self.assertTrue(result["available"])
        self.assertEqual(result["max_results"], 10)
        self.assertLessEqual(result["used_chars"], 1000)
        self.assertEqual(result["hits"][0]["path"], "qmd://secbrain/02 Projekte/Watcher.md")
        self.assertIn("RELEVANZ: 0.820", result["context"])
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["/usr/bin/qmd", "search", "Watcher Kontext"])
        self.assertNotIn("shell", run.call_args.kwargs)

    @patch("vault_retrieval_service.shutil.which", return_value=None)
    def test_missing_qmd_is_a_non_fatal_fallback(self, _which):
        result = service.retrieve_vault_context("Frage")
        self.assertFalse(result["available"])
        self.assertEqual(result["hits"], [])
        self.assertEqual(result["context"], "")
        self.assertIn("nicht gefunden", result["error"])

    @patch("vault_retrieval_service.shutil.which", return_value="/usr/bin/qmd")
    @patch("vault_retrieval_service.subprocess.run")
    def test_invalid_json_is_reported_without_exception(self, run, _which):
        run.return_value.returncode = 0
        run.return_value.stdout = "kein json"
        run.return_value.stderr = ""
        result = service.retrieve_vault_context("Frage")
        self.assertFalse(result["available"])
        self.assertIn("ungültiges JSON", result["error"])


if __name__ == "__main__":
    unittest.main()
