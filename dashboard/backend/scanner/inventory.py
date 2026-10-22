"""Read-only, descriptor-relative Vault inventory.

``kind`` classifies suffixes only; it makes no promise about encoding or
whether a rule model can interpret the file. All other suffixes are binary.
An issue means the inventory is incomplete and must not become a baseline.
"""

import hashlib
import os
from pathlib import Path
import stat


EXCLUSIONS = (
    ".git/", "_index/", "__pycache__/", "*.pyc", ".DS_Store",
    "09 Werkzeuge/Scanner-Berichte/",
)
MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})
TEXT_SUFFIXES = frozenset({
    ".txt", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".csv", ".tsv",
    ".xml", ".html", ".css", ".js", ".py", ".sh", ".ini", ".cfg", ".rst",
    ".log",
})
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
_CHUNK_SIZE = 1024 * 1024


def _signature(info):
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_size,
        info.st_mtime_ns, info.st_ctime_ns, info.st_nlink,
    )


def _kind(path):
    suffix = Path(path).suffix.lower()
    if suffix in MARKDOWN_SUFFIXES:
        return "markdown"
    return "text" if suffix in TEXT_SUFFIXES else "binary"


def _open_root(vault):
    """Reject symlinks in every component, including the Vault root itself."""
    absolute = Path(os.path.abspath(vault))
    fd = os.open(absolute.anchor, _DIRECTORY_FLAGS)
    try:
        for component in absolute.parts[1:]:
            child_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _excluded(path, info):
    name = path.rsplit("/", 1)[-1]
    if name == ".DS_Store" or name.endswith(".pyc"):
        return True
    return stat.S_ISDIR(info.st_mode) and (
        name in {".git", "_index", "__pycache__"}
        or path == "09 Werkzeuge/Scanner-Berichte"
    )


def _current_stat(root_fd, path):
    """Recheck a path through fresh no-follow directory descriptors."""
    components = path.split("/")
    fd = os.dup(root_fd)
    try:
        for component in components[:-1]:
            child_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child_fd
        return os.stat(components[-1], dir_fd=fd, follow_symlinks=False)
    finally:
        os.close(fd)


def scan_vault(vault: Path, *, signature_snapshot: dict | None = None) -> dict:
    """Return sorted regular file records and non-sensitive incomplete issues.

    Symlinks and unsupported file types are issues, never read targets.
    Descriptors anchor all traversal; pre/post metadata catches replaced and
    changing inputs. No baseline or other file is written by this function.
    Optional signature_snapshot receives private, process-local filesystem
    identities for consistency checks spanning subsequent model evaluation.
    It is separate from public/persisted file records and content comparisons.
    """
    if signature_snapshot is not None:
        signature_snapshot.clear()
    files = {}
    signatures = {}
    directory_signatures = {}
    issues = {}

    def issue(path, reason):
        issues[(path, reason)] = {"path": path, "status": "unklar", "reason": reason}

    def hash_file(parent_fd, name, path, before):
        fd = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode) or _signature(opened) != _signature(before):
                issue(path, "Datei wurde vor dem Lesen verändert.")
                return
            digest = hashlib.sha256()
            count = 0
            while count <= before.st_size:
                chunk = os.read(fd, min(_CHUNK_SIZE, before.st_size - count + 1))
                if not chunk:
                    break
                count += len(chunk)
                digest.update(chunk)
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if count != before.st_size or _signature(after) != _signature(before) or _signature(named) != _signature(before):
                issue(path, "Datei wurde während des Lesens verändert.")
                return
            files[path] = {"path": path, "sha256": digest.hexdigest(), "size": count, "kind": _kind(path)}
            signatures[path] = _signature(after)
        finally:
            os.close(fd)

    def walk(fd, relative):
        before = os.fstat(fd)
        if relative:
            directory_signatures[relative] = _signature(before)
        try:
            names = sorted(os.listdir(fd))
        except OSError:
            issue(relative or ".", "Verzeichnis ist nicht lesbar.")
            return
        for name in names:
            path = f"{relative}/{name}" if relative else name
            try:
                entry = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if _excluded(path, entry):
                    continue
                if stat.S_ISLNK(entry.st_mode):
                    issue(path, "Symlink wird nicht verfolgt.")
                elif stat.S_ISDIR(entry.st_mode):
                    child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=fd)
                    try:
                        if _signature(os.fstat(child_fd)) != _signature(entry):
                            issue(path, "Verzeichnis wurde vor dem Lesen verändert.")
                            continue
                        walk(child_fd, path)
                        named = os.stat(name, dir_fd=fd, follow_symlinks=False)
                        if _signature(named) != _signature(entry):
                            issue(path, "Verzeichnis wurde während des Scans verändert.")
                    finally:
                        os.close(child_fd)
                elif stat.S_ISREG(entry.st_mode):
                    hash_file(fd, name, path, entry)
                else:
                    issue(path, "Dateityp ist nicht unterstützt.")
            except OSError:
                issue(path, "Pfad ist nicht sicher lesbar oder wurde verändert.")
        if _signature(os.fstat(fd)) != _signature(before):
            issue(relative or ".", "Verzeichnis wurde während des Scans verändert.")

    try:
        root_fd = _open_root(vault)
    except OSError:
        issue(".", "Vault ist nicht sicher lesbar.")
    else:
        try:
            root_before = os.fstat(root_fd)
            directory_signatures["."] = _signature(root_before)
            walk(root_fd, "")
            for path, signature in signatures.items():
                try:
                    stable = _signature(_current_stat(root_fd, path)) == signature
                except OSError:
                    stable = False
                if not stable:
                    del files[path]
                    issue(path, "Datei wurde während des Scans verändert.")
            for path, signature in directory_signatures.items():
                try:
                    info = os.fstat(root_fd) if path == "." else _current_stat(root_fd, path)
                    stable = _signature(info) == signature
                except OSError:
                    stable = False
                if not stable:
                    issue(path, "Verzeichnis wurde während des Scans verändert.")
            try:
                fresh_root_fd = _open_root(vault)
                try:
                    same_root = _signature(os.fstat(fresh_root_fd)) == _signature(root_before)
                finally:
                    os.close(fresh_root_fd)
            except OSError:
                same_root = False
            if not same_root:
                issue(".", "Vault-Verzeichnis wurde während des Scans verändert.")
        except OSError:
            issue(".", "Vault konnte nicht vollständig gelesen werden.")
        finally:
            os.close(root_fd)
    if signature_snapshot is not None:
        signature_snapshot.update(directory_signatures)
        signature_snapshot.update(signatures)
    return {
        "files": [files[path] for path in sorted(files)],
        "issues": [issues[key] for key in sorted(issues)],
    }


def diff_inventory(previous: dict | None, current: dict) -> list[dict]:
    """Compare against a complete baseline; the first inventory has no delta."""
    if previous is None:
        return []
    old = {row["path"]: row for row in previous["files"]}
    new = {row["path"]: row for row in current["files"]}
    rows = []
    for path in sorted(old.keys() | new.keys()):
        if path not in old:
            status = "neu"
        elif path not in new:
            status = "entfernt"
        else:
            status = "unverändert" if old[path] == new[path] else "geändert"
        rows.append({"path": path, "status": status})
    return rows
