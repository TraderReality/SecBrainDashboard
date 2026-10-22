"""Immutable reports with a recoverable, report-only Git transaction.

The caller supplies structured report metadata/findings, never raw file contents
or credentials. ``complete`` describes scan coverage, not satisfaction of rules.
A marker is durable before HEAD changes; recovery finishes only commits already
reachable from HEAD. An uncommitted attempt remains a report, never a baseline.
State is private and lives in the caller's SECBRAIN_WATCHER_STATE_DIR outside the
Vault. Corrupt primary state blocks publication; last_complete can still return
its checksummed last-good copy without hiding the recovery error.
"""

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid

from .inventory import _open_root, scan_vault
from .write_guard import vault_write_lock, RuleBlocked


REPORT_DIRECTORY = '09 Werkzeuge/Scanner-Berichte'
_STATE = 'scanner-state.json'
_GOOD = 'scanner-last-good.json'
_MARKER = 'scanner-pending.json'
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z')
_OID = re.compile(r'(?:[a-f0-9]{40}|[a-f0-9]{64})\Z')


class ReportStoreError(RuntimeError):
    """The attempted publication is not a confirmed complete scan."""


def _encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                       separators=(',', ':')) + '\n').encode('utf-8')


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _read(fd, name):
    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        info = os.fstat(child)
        if not stat.S_ISREG(info.st_mode):
            raise ReportStoreError('Expected a regular file.')
        with os.fdopen(child, 'rb', closefd=False) as stream:
            return stream.read()
    finally:
        os.close(child)


def _write(fd, name, data, *, immutable=False):
    temporary = '.scanner-' + uuid.uuid4().hex
    child = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600, dir_fd=fd)
    try:
        with os.fdopen(child, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if immutable:
            os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        else:
            os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=fd)
            os.fsync(fd)
        except FileNotFoundError:
            pass


def _envelope(payload):
    return {'version': 1, 'payload': payload, 'sha256': _digest(_encoded(payload))}


def _unpack(raw):
    value = json.loads(raw)
    if (not isinstance(value, dict) or value.get('version') != 1
            or not isinstance(value.get('payload'), dict)
            or value.get('sha256') != _digest(_encoded(value['payload']))):
        raise ReportStoreError('Corrupt scanner state.')
    return value['payload']


class ScannerReportStore:
    def __init__(self, vault: Path, state_dir: Path):
        self.vault = Path(vault).resolve()
        self.state_dir = Path(state_dir).resolve()
        if self.state_dir.is_relative_to(self.vault):
            raise ReportStoreError('Scanner state must be outside the Vault.')
        try:
            self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = _open_root(self.state_dir)
            os.close(fd)
        except OSError as exc:
            raise ReportStoreError('Scanner state directory is unavailable.') from exc

    @staticmethod
    def _scan_id(scan_id):
        if not isinstance(scan_id, str) or not _ID.fullmatch(scan_id):
            raise ReportStoreError('Invalid scan ID.')
        return scan_id

    @contextmanager
    def _locked(self):
        fd = None
        lock = None
        try:
            fd = _open_root(self.state_dir)
            lock = os.open('scanner.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                           0o600, dir_fd=fd)
            if not stat.S_ISREG(os.fstat(lock).st_mode):
                raise ReportStoreError('Invalid scanner lock.')
            os.fchmod(lock, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            self._state_fd = fd
            yield
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
            raise ReportStoreError('Scanner persistence failed: ' + str(exc)) from exc
        finally:
            if lock is not None:
                os.close(lock)
            if fd is not None:
                os.close(fd)

    def _load(self, name):
        try:
            return _unpack(_read(self._state_fd, name))
        except FileNotFoundError:
            return None
        except (ValueError, TypeError, KeyError) as exc:
            raise ReportStoreError('Corrupt scanner state: ' + name) from exc

    def _save(self, name, payload):
        _write(self._state_fd, name, _encoded(_envelope(payload)))

    def _state(self):
        state = self._load(_STATE)
        if state is None:
            if self._load(_GOOD) is not None:
                raise ReportStoreError('Scanner state is missing; last-good baseline retained.')
            return {'vault': str(self.vault), 'last_complete': None}
        if state.get('vault') != str(self.vault) or 'last_complete' not in state:
            raise ReportStoreError('Scanner state belongs to another Vault or is corrupt.')
        return state

    def _write_state(self, state):
        # Both files contain confirmed state only. A crash between these replaces
        # is repaired from the pending transaction, never from an uncommitted scan.
        self._save(_STATE, state)
        self._save(_GOOD, state)

    def _git(self, *args, data=None, index=None, check=True):
        env = os.environ.copy()
        # Ignore inherited Git repository/index overrides; never commit elsewhere.
        for key in list(env):
            if key.startswith('GIT_') and key not in {'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_SYSTEM'}:
                del env[key]
        env['GIT_TERMINAL_PROMPT'] = '0'
        env['GIT_NO_REPLACE_OBJECTS'] = '1'
        if index is not None:
            env['GIT_INDEX_FILE'] = str(index)
        result = subprocess.run(['git', '-c', 'core.fsync=all', '-c', 'core.fsyncMethod=fsync',
                                 '-c', 'user.useConfigOnly=true', '-C', str(self.vault), *args], input=data,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, umask=0o077)
        if check and result.returncode:
            # Git errors may include source text/paths; keep the public error bounded.
            raise ReportStoreError('Vault Git operation failed: ' + args[0])
        return result.stdout if check else result

    def _repository(self):
        top = self._git('rev-parse', '--show-toplevel').decode().strip()
        if Path(top).resolve() != self.vault:
            raise ReportStoreError('Vault must be the Git repository root.')
        return self._git('rev-parse', '--verify', 'HEAD').decode().strip()

    @contextmanager
    def _report_dir(self, create=False):
        fd = _open_root(self.vault)
        try:
            for component in REPORT_DIRECTORY.split('/'):
                if create:
                    try:
                        os.mkdir(component, 0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        pass
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd
        finally:
            os.close(fd)

    def _remove_marker(self):
        os.unlink(_MARKER, dir_fd=self._state_fd)
        os.fsync(self._state_fd)

    def _confirm(self, transaction):
        scan_id = self._scan_id(transaction['scan_id'])
        path = f'{REPORT_DIRECTORY}/{scan_id}.json'
        if (transaction.get('vault') != str(self.vault)
                or transaction.get('report_path') != path
                or not _OID.fullmatch(transaction.get('old_head', ''))
                or not _OID.fullmatch(transaction.get('commit', ''))
                or not _OID.fullmatch(transaction.get('blob', ''))):
            raise ReportStoreError('Invalid scanner transaction.')
        with self._report_dir() as fd:
            data = _read(fd, scan_id + '.json')
        if _digest(data) != transaction['report_hash']:
            raise ReportStoreError('Immutable scanner report changed.')
        self._repository()
        reachable = self._git('merge-base', '--is-ancestor', transaction['commit'], 'HEAD', check=False)
        if reachable.returncode == 1:
            return False
        if reachable.returncode != 0:
            raise ReportStoreError('Cannot confirm report commit.')
        committed = self._git('show', transaction['commit'] + ':' + path)
        parent = self._git('rev-parse', transaction['commit'] + '^').decode().strip()
        changes = self._git('diff-tree', '--no-commit-id', '--name-only', '-r', '-z', transaction['commit'])
        if committed != data or parent != transaction['old_head'] or changes != path.encode() + b'\0':
            raise ReportStoreError('Report commit does not match its transaction.')
        return True

    def _finish(self, transaction, state):
        path = transaction['report_path']
        entry = self._git('ls-files', '--stage', '-z', '--', path)
        expected = f"100644 {transaction['blob']} 0\t{path}\0".encode()
        if entry and entry != expected:
            raise ReportStoreError('Report path has conflicting staged changes.')
        # Git takes index.lock; only the system-owned report entry is changed.
        self._git('update-index', '--add', '--cacheinfo', '100644', transaction['blob'], path)
        result = {key: transaction[key] for key in ('scan_id', 'report_path', 'commit')}
        result['complete'] = transaction['inventory'] is not None
        if result['complete']:
            state = {'vault': str(self.vault), 'last_complete': {
                **result, 'inventory': transaction['inventory']}}
        self._write_state(state)
        self._save('scanner-receipt-' + transaction['scan_id'] + '.json', {
            **result, 'report_hash': transaction['report_hash'], 'vault': str(self.vault)})
        self._remove_marker()
        return result

    def _recover(self):
        state = self._state()
        marker = self._load(_MARKER)
        if marker is None:
            return {'status': 'idle'}
        if not self._confirm(marker):
            self._remove_marker()
            return {'status': 'incomplete', 'scan_id': marker['scan_id'], 'complete': False}
        return {'status': 'recovered', **self._finish(marker, state)}

    def recover(self) -> dict:
        """Finish a committed transaction; never retry an uncommitted ref update."""
        try:
            with vault_write_lock(self.state_dir), self._locked():
                return self._recover()
        except (ReportStoreError, RuleBlocked) as exc:
            return {'status': 'error', 'complete': False, 'error': str(exc)}

    def _check_inventory(self, inventory, expected_signatures, *, report_created=False):
        if expected_signatures is None:
            return
        signatures = {}
        current = scan_vault(self.vault, signature_snapshot=signatures)
        expected_signatures = dict(expected_signatures)
        if report_created:
            # Creating the fixed report folder changes only these parent directory
            # metadata fields. Keep their identity/mode and every content signature.
            for path in (".", "09 Werkzeuge"):
                before = expected_signatures.pop(path, None)
                after = signatures.pop(path, None)
                if before is not None and (after is None or before[:3] != after[:3]):
                    raise ReportStoreError('Vault directory changed before scanner publication.')
        if current != inventory or signatures != expected_signatures:
            raise ReportStoreError('Vault changed before scanner publication.')

    def publish(self, scan_id: str, report: dict, inventory: dict | None, *,
                expected_signatures: dict | None = None) -> dict:
        self._scan_id(scan_id)
        if not isinstance(report, dict):
            raise ReportStoreError('Report must be a structured object.')
        if inventory is not None and (not isinstance(inventory, dict)
                or not isinstance(inventory.get('files'), list) or inventory.get('issues') != []):
            raise ReportStoreError('Incomplete inventory cannot replace the baseline.')
        with vault_write_lock(self.state_dir), self._locked():
            # Lock order: app mutation lock, then scanner lock, through state publication.
            # Freeze caller-owned objects before persisting the transaction.
            inventory = json.loads(_encoded(inventory))
            report = json.loads(_encoded(report))
            self._recover()
            self._check_inventory(inventory, expected_signatures)
            state = self._state()
            old_head = self._repository()
            symbolic = self._git('symbolic-ref', '-q', 'HEAD', check=False)
            if symbolic.returncode == 1:
                raise ReportStoreError('Scanner publication requires a checked-out Vault branch.')
            if symbolic.returncode != 0:
                raise ReportStoreError('Cannot determine the Vault HEAD reference.')
            head_ref = symbolic.stdout.decode().strip()
            self._git('var', 'GIT_AUTHOR_IDENT')
            self._git('var', 'GIT_COMMITTER_IDENT')
            path = f'{REPORT_DIRECTORY}/{scan_id}.json'
            if (self._load('scanner-receipt-' + scan_id + '.json') is not None
                    or self._git('ls-files', '--stage', '-z', '--', path)
                    or self._git('ls-tree', '-z', old_head, '--', path)):
                raise ReportStoreError('Report ID has already been used.')
            data = _encoded({**report, 'scan_id': scan_id, 'complete': inventory is not None})
            with self._report_dir(create=True) as fd:
                _write(fd, scan_id + '.json', data, immutable=True)
            index = self.state_dir / ('.scanner-index-' + uuid.uuid4().hex)
            try:
                self._git('read-tree', old_head, index=index)
                blob = self._git('hash-object', '-w', '--stdin', data=data).decode().strip()
                self._git('update-index', '--add', '--cacheinfo', '100644', blob, path, index=index)
                tree = self._git('write-tree', index=index).decode().strip()
                commit = self._git('commit-tree', tree, '-p', old_head,
                                   data=f'Scanner report {scan_id}\n'.encode()).decode().strip()
                transaction = {'vault': str(self.vault), 'scan_id': scan_id, 'report_path': path,
                               'report_hash': _digest(data), 'old_head': old_head, 'head_ref': head_ref,
                               'commit': commit, 'blob': blob, 'inventory': inventory}
                self._save(_MARKER, transaction)
                self._check_inventory(inventory, expected_signatures, report_created=True)
                self._git('update-ref', '--no-deref', '-m', f'Scanner report {scan_id}',
                          head_ref, commit, old_head)
                if not self._confirm(transaction):
                    raise ReportStoreError('Report commit is no longer reachable.')
                return self._finish(transaction, state)
            finally:
                for candidate in (index, Path(str(index) + '.lock')):
                    try:
                        candidate.unlink()
                    except FileNotFoundError:
                        pass

    def last_complete(self) -> dict | None:
        """Return the last durable baseline, including when primary state is corrupt.

        Call recover/status as well to surface corruption; this fallback does not
        authorize publishing over corrupt state and makes no new success claim.
        """
        with self._locked():
            try:
                state = self._state()
            except ReportStoreError:
                state = self._load(_GOOD)
                if state is None or state.get('vault') != str(self.vault) or 'last_complete' not in state:
                    raise ReportStoreError('No valid scanner baseline is available.')
            return state['last_complete']

    def get_report(self, scan_id: str) -> dict:
        self._scan_id(scan_id)
        with self._locked():
            with self._report_dir() as fd:
                data = _read(fd, scan_id + '.json')
            report = json.loads(data)
            if not isinstance(report, dict) or report.get('scan_id') != scan_id:
                raise ReportStoreError('Invalid scanner report.')
            receipt = self._load('scanner-receipt-' + scan_id + '.json')
            confirmed = bool(receipt and receipt.get('vault') == str(self.vault)
                             and receipt.get('report_hash') == _digest(data))
            report['complete'] = bool(confirmed and receipt.get('complete'))
            report['published'] = confirmed
            return report
