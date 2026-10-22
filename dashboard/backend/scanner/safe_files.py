"""Descriptor-relative, no-follow file mutations with checked ownership.

App locks serialize cooperating writers. External editors can still race; every
replace/delete checks the named inode and full bytes immediately before mutation.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import errno
import hashlib
import os
from pathlib import Path
import secrets
import stat

from .inventory import _DIRECTORY_FLAGS, _FILE_FLAGS, _signature
from .write_guard import RuleBlocked


@contextmanager
def _parent_directory(target: Path, *, create: bool = False):
    """Anchor operations without following any substituted parent symlink."""
    absolute = target.absolute()
    directory = os.open(absolute.anchor, _DIRECTORY_FLAGS)
    try:
        for part in absolute.parts[1:-1]:
            try:
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=directory)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, dir_fd=directory)
                except FileExistsError:
                    pass
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=directory)
            os.close(directory)
            directory = child
        yield directory
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise RuleBlocked("Zielpfad wurde verändert oder enthält einen Symlink.") from None
        raise
    finally:
        os.close(directory)


@contextmanager
def _staged_bytes(directory: int, content: bytes):
    """Atomic installation scratch space, used only inside authorization."""
    name = f".vault-{secrets.token_hex(16)}.tmp"
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=directory)
    owned = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        yield name
    finally:
        try:
            named = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (named.st_dev, named.st_ino) == (owned.st_dev, owned.st_ino):
                _verify(directory, name, FileState(content, (owned.st_dev, owned.st_ino)), max_links=2)
                os.unlink(name, dir_fd=directory)
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class FileState:
    data: bytes
    identity: tuple[int, int]


def _read_at(directory, name, *, max_links=1):
    descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory)
    with os.fdopen(descriptor, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_nlink <= max_links:
            raise RuleBlocked("Datei ist nicht sicher lesbar oder ersetzbar.")
        data = handle.read()
        after = os.fstat(handle.fileno())
    named = os.stat(name, dir_fd=directory, follow_symlinks=False)
    if _signature(before) != _signature(after) or _signature(after) != _signature(named):
        raise RuleBlocked("Datei wurde während des Zugriffs verändert.")
    return FileState(data, (after.st_dev, after.st_ino))


def file_state(target: Path) -> FileState | None:
    try:
        with _parent_directory(target) as directory:
            return _read_at(directory, target.name)
    except FileNotFoundError:
        return None


def _verify(directory, name, expected, *, max_links=1, missing_ok=False):
    try:
        current = _read_at(directory, name, max_links=max_links)
    except FileNotFoundError:
        if missing_ok:
            return False
        current = None
    if current != expected:
        raise RuleBlocked("Datei wurde verändert; automatischer Rückweg bleibt offen.")
    return True


def _atomic_new_file(target: Path, content: bytes, *, before_mutation=None) -> FileState:
    with _parent_directory(target, create=True) as directory:
        with _staged_bytes(directory, content) as temporary_name:
            info = os.stat(temporary_name, dir_fd=directory, follow_symlinks=False)
            if before_mutation is not None:
                before_mutation(FileState(content, (info.st_dev, info.st_ino)), target.with_name(temporary_name))
            os.link(temporary_name, target.name, src_dir_fd=directory,
                    dst_dir_fd=directory, follow_symlinks=False)
        installed = FileState(content, (info.st_dev, info.st_ino))
        _verify(directory, target.name, installed)
        os.fsync(directory)
        return installed


def replace_file(target: Path, content: bytes, expected: FileState, *, before_mutation=None) -> FileState:
    with _parent_directory(target) as directory:
        with _staged_bytes(directory, content) as temporary_name:
            info = os.stat(temporary_name, dir_fd=directory, follow_symlinks=False)
            if before_mutation is not None:
                before_mutation(FileState(content, (info.st_dev, info.st_ino)), target.with_name(temporary_name))
            _verify(directory, target.name, expected)
            os.replace(temporary_name, target.name, src_dir_fd=directory, dst_dir_fd=directory)
        installed = FileState(content, (info.st_dev, info.st_ino))
        _verify(directory, target.name, installed)
        os.fsync(directory)
        return installed


def _atomic_replace_file(target: Path, content: bytes, before_sha256: str) -> FileState:
    expected = file_state(target)
    if expected is None or hashlib.sha256(expected.data).hexdigest() != before_sha256:
        raise RuleBlocked("Vorher-Datei wurde seit der Freigabe verändert.")
    return replace_file(target, content, expected)


def _remove_file(target: Path, expected: FileState, *, before_mutation=None, max_links=1, missing_ok=False) -> None:
    with _parent_directory(target) as directory:
        if before_mutation is not None:
            before_mutation(None, None)
        if not _verify(directory, target.name, expected, max_links=max_links, missing_ok=missing_ok):
            return
        os.unlink(target.name, dir_fd=directory)
        os.fsync(directory)


def mutate_file(target: Path, content: bytes | None, expected: FileState | None, *, before_mutation=None):
    if content is None:
        if expected is not None:
            _remove_file(target, expected, before_mutation=before_mutation)
        elif file_state(target) is not None:
            raise RuleBlocked("Unerwartete Datei; Rückweg bleibt offen.")
        return None
    if expected is None:
        return _atomic_new_file(target, content, before_mutation=before_mutation)
    if content == expected.data:
        with _parent_directory(target) as directory:
            _verify(directory, target.name, expected)
        return expected
    return replace_file(target, content, expected, before_mutation=before_mutation)
