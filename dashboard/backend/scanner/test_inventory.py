"""Contract tests for a read-only inventory of untrusted Vault entries."""

import hashlib
import os
from pathlib import Path

import pytest

from scanner import inventory
from scanner.inventory import diff_inventory, scan_vault


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    return root


def put(root, relative, content=b"content"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def paths(result):
    return [row["path"] for row in result["files"]]


def test_first_scan_inventories_regular_files_without_new_findings(vault):
    put(vault, "07 Anhänge/file.pdf", b"\x00\xff")
    put(vault, "01 Inbox/note.md", b"hello")
    put(vault, "settings.json", b"\xff")

    result = scan_vault(vault)

    assert result["issues"] == []
    assert result["files"] == [
        {"path": "01 Inbox/note.md", "sha256": hashlib.sha256(b"hello").hexdigest(), "size": 5, "kind": "markdown"},
        {"path": "07 Anhänge/file.pdf", "sha256": hashlib.sha256(b"\x00\xff").hexdigest(), "size": 2, "kind": "binary"},
        {"path": "settings.json", "sha256": hashlib.sha256(b"\xff").hexdigest(), "size": 1, "kind": "text"},
    ]
    assert diff_inventory(None, result) == []


def test_diff_reports_added_changed_removed_and_unchanged_files(vault):
    put(vault, "06 Archiv/old.md", b"old")
    removed = put(vault, "07 Anhänge/gone.pdf")
    put(vault, "AGENTS.md")
    before = scan_vault(vault)
    put(vault, "06 Archiv/old.md", b"NEW")  # Same size still changes the digest.
    put(vault, "01 Inbox/new.md")
    removed.unlink()

    assert diff_inventory(before, scan_vault(vault)) == [
        {"path": "01 Inbox/new.md", "status": "neu"},
        {"path": "06 Archiv/old.md", "status": "geändert"},
        {"path": "07 Anhänge/gone.pdf", "status": "entfernt"},
        {"path": "AGENTS.md", "status": "unverändert"},
    ]


@pytest.mark.parametrize("relative", [
    ".git/objects/ignored", "nested/.git/ignored", "_index/ignored.md",
    "nested/_index/ignored.md", "__pycache__/ignored", "nested/__pycache__/ignored",
    "module.pyc", "nested/module.pyc", ".DS_Store", "nested/.DS_Store",
    "09 Werkzeuge/Scanner-Berichte/SCAN-1.json",
])
def test_exact_exclusions_do_not_enter_the_inventory(vault, relative):
    put(vault, relative)
    put(vault, "visible.md")

    result = scan_vault(vault)

    assert paths(result) == ["visible.md"]
    assert result["issues"] == []


def test_similarly_named_paths_and_other_file_types_are_included(vault):
    included = [".gitignore", "nested/_index.md", "nested/Scanner-Berichte/note.md", "unknown.data", "09 Werkzeuge/Scanner-Berichte-old/note.md"]
    for relative in included:
        put(vault, relative)

    assert paths(scan_vault(vault)) == sorted(included)


def capture_reads(monkeypatch):
    captured = []
    real_read = os.read

    def read(fd, size):
        data = real_read(fd, size)
        captured.append(data)
        return data

    monkeypatch.setattr(inventory.os, "read", read)
    return captured


def test_symlinks_are_issues_without_reading_their_targets(vault, tmp_path, monkeypatch):
    sentinel = b"EXTERNAL SECRET sentinel"
    outside = put(tmp_path, "outside/secret.md", sentinel)
    (vault / "file-link").symlink_to(outside)
    (vault / "directory-link").symlink_to(outside.parent, target_is_directory=True)
    captured = capture_reads(monkeypatch)

    result = scan_vault(vault)

    assert result["files"] == []
    assert {issue["path"] for issue in result["issues"]} == {"directory-link", "file-link"}
    assert all(issue["status"] == "unklar" for issue in result["issues"])
    assert sentinel not in b"".join(captured)


@pytest.mark.parametrize("swap_directory", [False, True])
def test_symlink_swap_never_reads_external_bytes(vault, tmp_path, monkeypatch, swap_directory):
    sentinel = b"EXTERNAL SECRET swapped sentinel"
    outside = put(tmp_path, "outside/secret.md", sentinel)
    target = vault / "victim" if swap_directory else put(vault, "victim", b"local")
    if swap_directory:
        target.mkdir()
    captured = capture_reads(monkeypatch)
    real_open = os.open

    def swap_then_open(path, flags, *args, **kwargs):
        if path == "victim" and kwargs.get("dir_fd") is not None:
            target.rmdir() if swap_directory else target.unlink()
            target.symlink_to(outside.parent if swap_directory else outside, target_is_directory=swap_directory)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(inventory.os, "open", swap_then_open)

    result = scan_vault(vault)

    assert result["files"] == []
    assert result["issues"]
    assert sentinel not in b"".join(captured)


def test_vault_root_symlink_never_reads_target(tmp_path, monkeypatch):
    sentinel = b"EXTERNAL SECRET root sentinel"
    outside = put(tmp_path, "outside/secret.md", sentinel)
    root = tmp_path / "vault-link"
    root.symlink_to(outside.parent, target_is_directory=True)
    captured = capture_reads(monkeypatch)

    result = scan_vault(root)

    assert result["files"] == []
    assert result["issues"]
    assert sentinel not in b"".join(captured)


@pytest.mark.parametrize("replace_path", [False, True])
def test_mutation_during_hashing_produces_issue_without_stable_digest(vault, monkeypatch, replace_path):
    target = put(vault, "note.md", b"original")
    real_read = os.read
    changed = False

    def mutate_on_read(fd, size):
        nonlocal changed
        data = real_read(fd, size)
        if data and not changed:
            changed = True
            if replace_path:
                target.unlink()
            target.write_bytes(b"modified")
        return data

    monkeypatch.setattr(inventory.os, "read", mutate_on_read)

    result = scan_vault(vault)

    assert result["files"] == []
    assert any(issue["path"] == "note.md" and issue["status"] == "unklar" for issue in result["issues"])


def test_unreadable_file_is_an_issue(vault, monkeypatch):
    put(vault, "locked.md")
    real_open = os.open

    def deny_file(path, flags, *args, **kwargs):
        if path == "locked.md":
            raise PermissionError("not readable")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(inventory.os, "open", deny_file)

    result = scan_vault(vault)

    assert result["files"] == []
    assert result["issues"][0]["path"] == "locked.md"
    assert result["issues"][0]["status"] == "unklar"


def test_fifo_is_rejected_without_reading_or_blocking(vault):
    os.mkfifo(vault / "pipe")

    result = scan_vault(vault)

    assert result["files"] == []
    assert result["issues"][0]["path"] == "pipe"


def test_already_visited_directory_changed_later_makes_scan_incomplete(vault, monkeypatch):
    put(vault, "a-directory/first.md", b"first")
    put(vault, "z-last.md", b"last")
    real_read = os.read

    def add_to_visited_directory(fd, size):
        data = real_read(fd, size)
        if data == b"last":
            put(vault, "a-directory/late.md", b"late")
        return data

    monkeypatch.setattr(inventory.os, "read", add_to_visited_directory)

    result = scan_vault(vault)

    assert any(issue["path"] == "a-directory" for issue in result["issues"])


def test_missing_vault_returns_issue(tmp_path):
    result = scan_vault(tmp_path / "missing")

    assert result["files"] == []
    assert result["issues"][0]["path"] == "."
