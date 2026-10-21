import subprocess
import tempfile
import unittest
from pathlib import Path

from connectors.git_connector import GitConnector


class GitConnectorTests(unittest.TestCase):
    def test_scan_uses_configured_repository_independent_of_process_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "watcher"
            repository.mkdir()
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            subprocess.run(
                [
                    "git", "-C", str(repository),
                    "-c", "user.name=SecBrain Test",
                    "-c", "user.email=test@localhost",
                    "commit", "--allow-empty", "-q", "-m", "test baseline",
                ],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repository), "tag", "R1-FROZEN"],
                check=True,
            )

            result = GitConnector(repository).scan()

            self.assertEqual(result["status"], "READY")
            self.assertEqual(result["repository"], str(repository.resolve()))
            self.assertEqual(result["frozen"], ["R1-FROZEN"])

    def test_scan_reports_invalid_repository_without_raising(self):
        with tempfile.TemporaryDirectory() as directory:
            result = GitConnector(directory).scan()

            self.assertEqual(result["status"], "ERROR")
            self.assertEqual(result["repository"], str(Path(directory).resolve()))
            self.assertIn("git", result["error"].lower())


if __name__ == "__main__":
    unittest.main()
