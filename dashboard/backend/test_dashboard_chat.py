import unittest

import dashboard_api


class FreeChatIsolationTest(unittest.TestCase):
    def setUp(self):
        dashboard_api.watcher_loop.stop()
        self.original_chat = dashboard_api.runtime.ollama.chat
        self.original_retrieve = dashboard_api.retrieve_vault_context
        dashboard_api.retrieve_vault_context = lambda query: {
            "available": True, "provider": "qmd-bm25", "collection": "secbrain",
            "query": query, "max_results": 5, "max_chars": 12000, "used_chars": 80,
            "hits": [{"path": "qmd://secbrain/02 Projekte/Watcher.md", "title": "Watcher", "line": 1, "score": 0.9, "snippet": "Vault-Wissen"}],
            "context": "QUELLE: qmd://secbrain/02 Projekte/Watcher.md\nAUSZUG: Vault-Wissen", "error": None,
        }

    def tearDown(self):
        dashboard_api.runtime.ollama.chat = self.original_chat
        dashboard_api.retrieve_vault_context = self.original_retrieve
        dashboard_api.watcher_loop.stop()

    def test_free_chat_does_not_advance_watcher_station(self):
        captured = {}

        def fake_chat(messages, model):
            captured["messages"] = messages
            captured["model"] = model
            return {"message": {"role": "assistant", "content": "Hallo"}}

        dashboard_api.runtime.ollama.chat = fake_chat
        dashboard_api.watcher_loop.start("test-model")
        before = dashboard_api.watcher_loop.status()["current_station"]

        result = dashboard_api.ollama_chat({
            "model": "test-model",
            "messages": [{"role": "user", "content": "Bist du online?"}],
        })

        after = dashboard_api.watcher_loop.status()["current_station"]
        self.assertEqual(before, 1)
        self.assertEqual(after, before)
        self.assertEqual(result["message"]["content"], "Hallo")
        self.assertIn("vollständig getrennt", captured["messages"][0]["content"])
        self.assertTrue(any("QMD-Vault-Kontext" in item["content"] for item in captured["messages"]))
        self.assertEqual(result["vault_retrieval"]["hits"][0]["score"], 0.9)
        self.assertNotIn("context", result["vault_retrieval"])
        self.assertNotIn("completed_station", result)

    def test_model_selection_does_not_start_watcher_loop(self):
        original_configure = dashboard_api.runtime.ollama.configure
        try:
            dashboard_api.runtime.ollama.configure = lambda payload: dict(payload)
            dashboard_api.ollama_config_update({"model": "test-model"})
            self.assertIsNone(dashboard_api.watcher_loop.status()["model"])
        finally:
            dashboard_api.runtime.ollama.configure = original_configure


if __name__ == "__main__":
    unittest.main()
