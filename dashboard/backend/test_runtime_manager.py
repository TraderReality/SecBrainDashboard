import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.runtime_manager import RuntimeManager


class RuntimeManagerEnvironmentTest(unittest.TestCase):
    def test_ollama_url_and_observer_model_are_loaded_from_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            repository = root / "repository"
            state = root / "state"
            vault.mkdir()
            repository.mkdir()
            state.mkdir()

            environment = {
                "SECBRAIN_VAULT_PATH": str(vault),
                "SECBRAIN_WATCHER_REPOSITORY": str(repository),
                "SECBRAIN_WATCHER_STATE_DIR": str(state),
                "SECBRAIN_OLLAMA_URL": "http://192.0.2.10:11434/",
                "SECBRAIN_OBSERVER_MODEL": "observer-model",
            }
            with patch.dict(os.environ, environment, clear=False):
                manager = RuntimeManager()

            self.assertEqual(manager.ollama.url, "http://192.0.2.10:11434")
            self.assertEqual(manager.ollama.get_config()["model"], "observer-model")


if __name__ == "__main__":
    unittest.main()
