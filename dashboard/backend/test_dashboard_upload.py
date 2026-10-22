import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dashboard_api
from scanner.write_guard import VaultWriteGuard
from scanner.test_write_guard import passing_chat


class InboxUploadTest(unittest.TestCase):
    def setUp(self):
        self.previous_vault = dashboard_api.runtime.vault.path
        self.temp = tempfile.TemporaryDirectory()
        dashboard_api.runtime.vault.path = Path(self.temp.name).resolve() / "vault"
        dashboard_api.runtime.vault.path.mkdir()
        (dashboard_api.runtime.vault.path / "AGENTS.md").write_text("Keep notes sourced.\n")
        self.guard = VaultWriteGuard(dashboard_api.runtime.vault.path, Path(self.temp.name).resolve() / "state", passing_chat, lambda: "local")

    def tearDown(self):
        dashboard_api.runtime.vault.path = self.previous_vault
        self.temp.cleanup()

    def upload(self, name="Notiz.md", content=b"# Test\n"):
        return dashboard_api.write_inbox_upload(name, base64.b64encode(content).decode("ascii"), self.guard)

    def test_upload_writes_markdown_to_inbox(self):
        result = self.upload()
        target = dashboard_api.runtime.vault.path / "01 Inbox" / "Notiz.md"
        self.assertEqual(target.read_bytes(), b"# Test\n")
        self.assertEqual(result["status"], "uploaded")

    def test_upload_does_not_overwrite_existing_file(self):
        self.upload()
        with self.assertRaises(FileExistsError):
            self.upload(content=b"changed")

    def test_upload_rejects_paths_non_markdown_and_invalid_utf8(self):
        for name, content in (("../Notiz.md", b"ok"), ("Notiz.txt", b"ok"), ("Notiz.md", b"\xff")):
            with self.subTest(name=name, content=content):
                with self.assertRaises(ValueError):
                    self.upload(name, content)

    @patch("dashboard_api.import_pdf")
    def test_pdf_endpoint_uses_active_vault(self, import_pdf):
        import_pdf.return_value = {"status": "uploaded", "pages": 2, "chunks": 1}
        with patch("dashboard_api.vault_write_guard", return_value=self.guard):
            result = dashboard_api.dokulader_pdf({"filename": "manual.pdf", "content_base64": "data"})
        self.assertEqual(result["pages"], 2)
        import_pdf.assert_called_once_with(dashboard_api.runtime.vault.path, "manual.pdf", "data", self.guard)


if __name__ == "__main__":
    unittest.main()
