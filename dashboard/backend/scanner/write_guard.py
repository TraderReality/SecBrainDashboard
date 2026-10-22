"""Live authorization for app writes; callers must execute exactly the approved diff.

Every app writer for a Vault must use the same external ``state_dir``. Approval
is an opaque, nonempty reference whose authenticity and binding to the exact
change set belongs to the caller (for example, an approved watcher run). It
never overrides a new violation or an incomplete assessment. The lock covers
cooperating app writers, not external editors; use exclusive creation / atomic
replacement in the body as appropriate. This guard does not perform mutations.
"""
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import unicodedata
from typing import Literal

from .inventory import (_DIRECTORY_FLAGS, _FILE_FLAGS, _kind, _open_root,
                        _signature, scan_vault)
from .rules import _readable_text, _safe_path, evaluate_rules


_MAX_CONTENT = 64_000
_LOCK_NAME = "vault-write.lock"


@dataclass(frozen=True)
class PlannedChange:
    relative_path: str
    operation: Literal['create', 'replace', 'delete']
    before_sha256: str | None
    after_bytes: bytes | None


class RuleBlocked(RuntimeError):
    """Safe user-facing reason for an HTTP 409, without source/model content."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class VaultWriteGuard:
    def __init__(self, vault: Path, state_dir: Path, chat: Callable,
                 model: Callable[[], str]):
        self.vault = Path(vault).absolute()
        self.state_dir = Path(state_dir).absolute()
        self.chat = chat
        self.model = model

    def _changes(self, changes, approval):
        if not isinstance(changes, list) or not changes:
            raise RuleBlocked('Kein gültiger Änderungssatz vorhanden.')
        approved = isinstance(approval, str) and bool(approval.strip())
        planned = tuple(changes)
        paths = set()
        for change in planned:
            if not isinstance(change, PlannedChange) or not _safe_path(change.relative_path):
                raise RuleBlocked('Zielpfad ist nicht zulässig.')
            path = change.relative_path
            # Reject portable aliases even on case-sensitive hosts, so a diff
            # cannot become an overwrite when applied on macOS/Windows.
            canonical = unicodedata.normalize('NFC', path).casefold()
            parts = canonical.split('/')
            if (any(part in {'.git', '_index', '__pycache__', '.ds_store'}
                    or part.endswith('.pyc') for part in parts)
                    or canonical == '09 werkzeuge/scanner-berichte'
                    or canonical.startswith('09 werkzeuge/scanner-berichte/')):
                raise RuleBlocked('Systempfade sind keine zulässigen Inhaltsziele.')
            if canonical in paths or any(canonical.startswith(p + '/') or p.startswith(canonical + '/') for p in paths):
                raise RuleBlocked('Änderungsziele sind doppelt oder widersprüchlich.')
            paths.add(canonical)
            if change.operation not in {'create', 'replace', 'delete'}:
                raise RuleBlocked('Dateioperation ist nicht zulässig.')
            if change.operation == 'create':
                if change.before_sha256 is not None:
                    raise RuleBlocked('Neue Dateien dürfen keinen Vorher-Hash besitzen.')
            elif (not approved or not isinstance(change.before_sha256, str)
                  or not re.fullmatch(r'[0-9a-f]{64}', change.before_sha256)):
                raise RuleBlocked('Ersetzen oder Löschen benötigt Freigabe und Vorher-Hash.')
            if change.operation == 'delete':
                if change.after_bytes is not None or path == 'AGENTS.md':
                    raise RuleBlocked('Löschung oder fehlende Regelquelle ist nicht zulässig.')
            elif not isinstance(change.after_bytes, bytes) or len(change.after_bytes) > _MAX_CONTENT:
                raise RuleBlocked('Geplanter Dateiinhalt ist nicht vollständig prüfbar.')
        return planned, approved

    def _check_destination(self, change, rows):
        """Check even absent targets through fresh descriptor-relative parents."""
        fd = _open_root(self.vault)
        info = None
        try:
            parts = change.relative_path.split('/')
            try:
                for part in parts[:-1]:
                    child = os.open(part, _DIRECTORY_FLAGS, dir_fd=fd)
                    os.close(fd)
                    fd = child
                info = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
        finally:
            os.close(fd)
        if change.operation == 'create':
            if info is not None:
                raise RuleBlocked('Neuanlage würde einen vorhandenen Pfad überschreiben.')
        elif (info is None or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
              or rows.get(change.relative_path, {}).get('sha256') != change.before_sha256):
            raise RuleBlocked('Vorher-Datei ist verändert oder nicht sicher ersetzbar.')

    def _read(self, row):
        if row['kind'] not in {'markdown', 'text'} or row['size'] > _MAX_CONTENT:
            raise RuleBlocked('Vault-Inhalt ist nicht vollständig prüfbar.')
        fd = _open_root(self.vault)
        try:
            parts = row['path'].split('/')
            for part in parts[:-1]:
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=fd)
                os.close(fd)
                fd = child
            child = os.open(parts[-1], _FILE_FLAGS, dir_fd=fd)
            try:
                before = os.fstat(child)
                if not stat.S_ISREG(before.st_mode):
                    raise RuleBlocked('Dateityp ist nicht zulässig.')
                with os.fdopen(child, 'rb', closefd=False) as stream:
                    content = stream.read(_MAX_CONTENT + 1)
                after = os.fstat(child)
                named = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
                if (_signature(before) != _signature(after) or _signature(before) != _signature(named)
                        or len(content) != row['size']
                        or hashlib.sha256(content).hexdigest() != row['sha256']):
                    raise RuleBlocked('Datei wurde während der Prüfung verändert.')
                _readable_text(content)
                return content
            finally:
                os.close(child)
        finally:
            os.close(fd)

    def _checked_chat(self, **kwargs):
        response = self.chat(**kwargs)
        if (not isinstance(response, dict) or response.get('done') is not True
                or response.get('done_reason') != 'stop'
                or response.get('model') != kwargs['model']):
            raise ValueError('Incomplete or unavailable model')
        return response

    def _prepare(self, changes, approval):
        planned, approved = self._changes(changes, approval)
        if (self.state_dir.resolve().is_relative_to(self.vault.resolve())
                or self.state_dir.is_relative_to(self.vault)):
            raise RuleBlocked('App-Sperre muss außerhalb der Vault liegen.')
        self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        state_fd = _open_root(self.state_dir)
        os.close(state_fd)
        signatures = {}
        inventory = scan_vault(self.vault, signature_snapshot=signatures)
        if inventory['issues']:
            raise RuleBlocked('Vault ist nicht vollständig und sicher prüfbar.')
        rows = {row['path']: row for row in inventory['files']}
        if 'AGENTS.md' not in rows:
            raise RuleBlocked('Aktuelle AGENTS.md fehlt.')
        for change in planned:
            self._check_destination(change, rows)
        contents = {path: self._read(row) for path, row in rows.items()}
        model = self.model()
        if not isinstance(model, str) or not model.strip():
            raise RuleBlocked('Für die Regelprüfung fehlt ein verfügbares Modell.')
        # Preserve the actual connector budget when wrapping its chat method.
        self.config = getattr(getattr(self.chat, '__self__', None), 'config', {})
        baseline = [{'path': path, 'kind': rows[path]['kind'], 'content': body,
                     'operation': 'Bestandsprüfung'} for path, body in contents.items()]
        before = evaluate_rules(contents['AGENTS.md'], baseline, model, self._checked_chat)
        if before['overall'] == 'unklar':
            raise RuleBlocked('Aktueller Regelzustand ist nicht vollständig geklärt.')
        violations = {row['path'] for row in before['findings'] if row['status'] == 'verletzt'}
        changed_paths = {change.relative_path for change in planned
                         if change.after_bytes != contents.get(change.relative_path)}
        if violations and (not approved or not violations.issubset(changed_paths)):
            raise RuleBlocked('Vorhandene Regelverletzung benötigt eine ausdrücklich freigegebene Korrektur.')

        proposed = {subject['path']: dict(subject) for subject in baseline}
        agents_after = contents['AGENTS.md']
        for change in planned:
            path = change.relative_path
            # Keep deleted preimages and both replacement bodies available to
            # assess the operation as well as the resulting document state.
            before_text = _readable_text(contents[path]) if path in contents else None
            after_text = _readable_text(change.after_bytes) if change.after_bytes is not None else None
            proposed[path] = {'path': path, 'kind': _kind(path), 'operation': change.operation,
                              'content': json.dumps({'before': before_text, 'after': after_text},
                                                    ensure_ascii=False)}
            if path == 'AGENTS.md':
                agents_after = change.after_bytes
        sources = [contents['AGENTS.md']]
        if agents_after != sources[0]:
            sources.append(agents_after)
        for agents in sources:
            after = evaluate_rules(agents, list(proposed.values()), model, self._checked_chat)
            if after['overall'] != 'erfüllt':
                raise RuleBlocked('Geplante Änderung verletzt Regeln oder ist nicht vollständig geklärt.')
        return planned, inventory, signatures

    def _lock(self):
        return vault_write_lock(self.state_dir)

    @contextmanager
    def authorize(self, changes: list[PlannedChange], approval: str | None) -> Iterator[None]:
        try:
            planned, inventory, signatures = self._prepare(changes, approval)
        except RuleBlocked:
            raise
        except Exception:
            raise RuleBlocked('Vault-Eingaben oder Modellprüfung sind nicht vollständig prüfbar.') from None
        with self._lock():
            try:
                current_signatures = {}
                current = scan_vault(self.vault, signature_snapshot=current_signatures)
                if current != inventory or current_signatures != signatures:
                    raise RuleBlocked('Vault oder AGENTS.md wurde seit der Prüfung verändert.')
                rows = {row['path']: row for row in current['files']}
                for change in planned:
                    self._check_destination(change, rows)
            except RuleBlocked:
                raise
            except Exception:
                raise RuleBlocked('Änderungseingaben sind nicht mehr sicher prüfbar.') from None
            yield


@contextmanager
def vault_write_lock(state_dir):
    directory = lock = None
    try:
        directory = _open_root(state_dir)
        lock = os.open(_LOCK_NAME, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                       0o600, dir_fd=directory)
        info = os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Unsafe lock file')
        fcntl.flock(lock, fcntl.LOCK_EX)
        named = os.stat(_LOCK_NAME, dir_fd=directory, follow_symlinks=False)
        if (named.st_dev, named.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError('Lock changed')
    except Exception:
        if lock is not None:
            os.close(lock)
        if directory is not None:
            os.close(directory)
        raise RuleBlocked('Gemeinsame App-Schreibsperre ist nicht verfügbar.') from None
    try:
        yield
    finally:
        os.close(lock)  # Closing the descriptor releases flock, including on body failure.
        os.close(directory)
