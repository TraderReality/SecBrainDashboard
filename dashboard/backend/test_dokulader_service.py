import base64
import io
import tempfile
import unittest
import zipfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import dokulader_service


class FakeResponse:
    def __init__(self, html, url="https://docs.example.org/start"):
        self.content = html.encode("utf-8")
        self.url = url
        self.encoding = "utf-8"
        self.status_code = 200
        self.headers = {"Content-Type": "text/html; charset=utf-8"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def raise_for_status(self):
        return None

    def close(self):
        return None

    def iter_content(self, _size):
        yield self.content


def package_bytes(files=100, unsafe=False):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for index in range(files):
            name = "../escape.md" if unsafe and index == 0 else f"3.10/library/page-{index}.md"
            archive.writestr(name, f"# Page {index}\n\nContent")
    return output.getvalue()


class RecordingGuard:
    """Verify the writer contract without pretending binary AI support exists."""
    def __init__(self, vault):
        self.vault = vault
        self.calls = []
        self.active = False

    @contextmanager
    def authorize(self, changes, approval):
        before = {p.relative_to(self.vault).as_posix(): p.read_bytes()
                  for p in self.vault.rglob("*") if p.is_file()}
        assert all(c.operation == "create" and c.before_sha256 is None for c in changes)
        assert not any(c.relative_path in before for c in changes)
        self.calls.append(changes)
        self.active = True
        try:
            yield
            after = {p.relative_to(self.vault).as_posix(): p.read_bytes()
                     for p in self.vault.rglob("*") if p.is_file()}
            assert after == {**before, **{c.relative_path: c.after_bytes for c in changes}}
        finally:
            self.active = False


class DokuLaderServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name).resolve()
        self.guard = RecordingGuard(self.vault)

    def tearDown(self):
        self.temp.cleanup()

    def test_package_creates_one_manifest_and_preserves_archive(self):
        raw = package_bytes()
        result = dokulader_service.import_package(
            self.vault, "python3.10-docs.zip", base64.b64encode(raw).decode("ascii"), self.guard
        )
        manifests = list((self.vault / "01 Inbox").glob("*.md"))
        self.assertEqual(len(manifests), 1)
        self.assertEqual(result["markdown_files"], 100)
        self.assertEqual((self.vault / result["archive"]).read_bytes(), raw)
        self.assertIn("paket_version: '3.10'", manifests[0].read_text(encoding="utf-8"))

    def test_package_duplicate_and_unsafe_path_are_rejected(self):
        raw = package_bytes()
        encoded = base64.b64encode(raw).decode("ascii")
        dokulader_service.import_package(self.vault, "docs.zip", encoded, self.guard)
        with self.assertRaises(FileExistsError):
            dokulader_service.import_package(self.vault, "docs-copy.zip", encoded, self.guard)
        with self.assertRaises(ValueError):
            dokulader_service.import_package(
                self.vault, "unsafe.zip", base64.b64encode(package_bytes(unsafe=True)).decode("ascii"), self.guard
            )

    @patch("dokulader_service._convert_pdf_to_pages")
    def test_pdf_creates_one_manifest_original_and_page_chunks(self, convert):
        convert.return_value = [
            {"text": f"# Seite {page}\n\nInhalt {page}", "metadata": {"page": page}}
            for page in range(1, 102)
        ]
        raw = b"%PDF-1.7\nTest PDF\n%%EOF"
        encoded = base64.b64encode(raw).decode("ascii")
        result = dokulader_service.import_pdf(self.vault, "python-3.14-reference.pdf", encoded, self.guard)

        manifests = list((self.vault / "01 Inbox").glob("*.md"))
        package = self.vault / result["archive"]
        self.assertEqual(len(manifests), 1)
        self.assertEqual(result["pages"], 101)
        self.assertEqual(result["chunks"], 3)
        self.assertEqual((package / "python-3.14-reference.pdf").read_bytes(), raw)
        self.assertEqual(len(list((package / "Kapitel").glob("*.md"))), 3)
        manifest_text = manifests[0].read_text(encoding="utf-8")
        self.assertIn("paket_version: '3.14'", manifest_text)
        self.assertIn("**PDF-Seiten:** 101", manifest_text)

        with self.assertRaises(FileExistsError):
            dokulader_service.import_pdf(self.vault, "duplicate.pdf", encoded, self.guard)

    def test_pdf_rejects_wrong_extension_and_invalid_magic(self):
        encoded = base64.b64encode(b"not a pdf").decode("ascii")
        with self.assertRaises(ValueError):
            dokulader_service.import_pdf(self.vault, "manual.pdf", encoded, self.guard)
        valid = base64.b64encode(b"%PDF-1.7\n%%EOF").decode("ascii")
        with self.assertRaises(ValueError):
            dokulader_service.import_pdf(self.vault, "../manual.pdf", valid, self.guard)

    @patch("dokulader_service._validated_web_url", side_effect=lambda url: url)
    @patch("dokulader_service.requests.get")
    def test_url_import_uses_one_request_and_blocks_duplicate(self, get, _validate):
        html = "<html><title>Python Test</title><main>" + ("Dokumentation " * 30) + "</main></html>"
        get.return_value = FakeResponse(html)
        first = dokulader_service.import_urls(self.vault, ["https://docs.example.org/start"], self.guard)
        second = dokulader_service.import_urls(self.vault, ["https://docs.example.org/start"], self.guard)
        self.assertEqual(len(first["imported"]), 1)
        self.assertEqual(len(second["skipped"]), 1)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(len(list((self.vault / "01 Inbox").glob("*.md"))), 1)

    def test_private_url_is_rejected(self):
        with self.assertRaises(ValueError):
            dokulader_service._validated_web_url("http://127.0.0.1/secret")


if __name__ == "__main__":
    unittest.main()
