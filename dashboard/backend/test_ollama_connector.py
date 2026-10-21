import json
import tempfile
import unittest
from pathlib import Path

from connectors.ollama_connector import OllamaConnector


class OllamaDefaultModelTest(unittest.TestCase):
    def test_default_model_is_persisted_and_loaded_as_active_model(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "ollama.json"
            connector = OllamaConnector(state_path=state_path)

            config = connector.configure({"default_model": "qwen3-vl:8b"})

            self.assertEqual(config["default_model"], "qwen3-vl:8b")
            self.assertEqual(config["model"], "qwen3-vl:8b")
            self.assertEqual(
                json.loads(state_path.read_text(encoding="utf-8")),
                {"default_model": "qwen3-vl:8b", "default_vision_model": ""},
            )

            restored = OllamaConnector(state_path=state_path).get_config()
            self.assertEqual(restored["default_model"], "qwen3-vl:8b")
            self.assertEqual(restored["model"], "qwen3-vl:8b")

    def test_temporary_selection_does_not_replace_default_model(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "ollama.json"
            connector = OllamaConnector(state_path=state_path)
            connector.configure({"default_model": "qwen3-vl:8b"})

            config = connector.configure({"model": "qwen3:14b"})

            self.assertEqual(config["model"], "qwen3:14b")
            self.assertEqual(config["default_model"], "qwen3-vl:8b")
            restored = OllamaConnector(state_path=state_path).get_config()
            self.assertEqual(restored["model"], "qwen3-vl:8b")

    def test_default_model_can_be_cleared_without_changing_current_session(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "ollama.json"
            connector = OllamaConnector(state_path=state_path)
            connector.configure({"default_model": "qwen3-vl:8b"})
            connector.configure({"model": "qwen3:14b"})

            config = connector.configure({"default_model": ""})

            self.assertEqual(config["default_model"], "")
            self.assertEqual(config["model"], "qwen3:14b")
            restored = OllamaConnector(state_path=state_path).get_config()
            self.assertEqual(restored["model"], "")

    def test_vision_default_is_persisted_without_changing_active_text_model(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "ollama.json"
            connector = OllamaConnector(state_path=state_path)
            connector.configure({"default_model": "qwen3:14b"})

            config = connector.configure({"default_vision_model": "qwen3-vl:8b"})

            self.assertEqual(config["model"], "qwen3:14b")
            self.assertEqual(config["default_model"], "qwen3:14b")
            self.assertEqual(config["default_vision_model"], "qwen3-vl:8b")
            restored = OllamaConnector(state_path=state_path).get_config()
            self.assertEqual(restored["default_vision_model"], "qwen3-vl:8b")


if __name__ == "__main__":
    unittest.main()
