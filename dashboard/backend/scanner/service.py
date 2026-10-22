"""Single background scanner; incomplete attempts never replace the baseline."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import stat
import tempfile
import threading
import uuid

from .inventory import (EXCLUSIONS, _FILE_FLAGS, _DIRECTORY_FLAGS, _open_root,
                        _signature, diff_inventory, scan_vault)
from .report_store import ReportStoreError, ScannerReportStore
from .rules import evaluate_rules


_RUN_LOCK = threading.Lock()
_MAX_CONTENT = 64_000
_ATTEMPT_FILE = 'scanner-attempt.json'
_INCOMPLETE = 'nicht vollständig geprüft'


class ScannerBusyError(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _finding(path, reason):
    return {'path': path, 'status': 'unklar', 'reason': reason}


def _read_content(vault, row):
    """Read only the inventoried regular file through no-follow descriptors."""
    if row['size'] > _MAX_CONTENT:
        raise ValueError('Content exceeds evaluation budget')
    fd = _open_root(vault)
    try:
        parts = row['path'].split('/')
        if any(part in {'', '.', '..'} for part in parts):
            raise ValueError('Invalid inventory path')
        for part in parts[:-1]:
            child = os.open(part, _DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        child = os.open(parts[-1], _FILE_FLAGS, dir_fd=fd)
        try:
            before = os.fstat(child)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError('Not a regular file')
            with os.fdopen(child, 'rb', closefd=False) as stream:
                content = stream.read(_MAX_CONTENT + 1)
            after = os.fstat(child)
            named = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
            if (_signature(before) != _signature(after) or _signature(before) != _signature(named)
                    or len(content) != row['size']
                    or hashlib.sha256(content).hexdigest() != row['sha256']):
                raise ValueError('Input changed')
            return content
        finally:
            os.close(child)
    finally:
        os.close(fd)


def _public_finding(row):
    # Explicit field construction: no source body or untrusted metadata is copied.
    return {'rule_id': row['rule_id'], 'path': row['path'], 'status': row['status'],
            'reason': row['reason'], 'source': {'path': 'AGENTS.md', 'line': row['source']['line']}}


class VaultScanner:
    def __init__(self, vault: Path, state_dir: Path, chat, model):
        # Keep original vault path for no-follow inventory checks.
        self.vault = Path(vault).absolute()
        self.store = ScannerReportStore(vault, state_dir)
        self.chat = chat
        self.model = model
        self._mutex = threading.RLock()
        self._progress = {'phase': 'idle', 'completed': 0, 'total': 0}
        self._attempt = None
        self._recovery_error = False
        recovery = self.store.recover()
        self._recovery_error = recovery['status'] == 'error'
        try:
            fd = _open_root(self.store.state_dir)
            try:
                child = os.open(_ATTEMPT_FILE, _FILE_FLAGS, dir_fd=fd)
                with os.fdopen(child, 'r', encoding='utf-8') as stream:
                    value = json.loads(stream.read(8193))
            finally:
                os.close(fd)
            if (set(value) != {'vault', 'attempt'} or value['vault'] != str(self.vault)
                    or not isinstance(value['attempt'], dict)):
                raise ValueError('Invalid attempt state')
            self._attempt = self._validated_attempt(value['attempt'])
            if self._attempt['state'] == 'running':
                self._attempt.update(state='incomplete', overall='unklar', message=_INCOMPLETE)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError, ReportStoreError):
            self._recovery_error = True
        if recovery['status'] == 'recovered':
            report = self.report(recovery['scan_id'])
            self._attempt = self._metadata(report)

    def _validated_attempt(self, attempt):
        keys = {'scan_id', 'state', 'overall', 'started_at', 'finished_at', 'message'}
        if set(attempt) != keys:
            raise ValueError('Invalid attempt fields')
        if (not isinstance(attempt['scan_id'], str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', attempt['scan_id'])
                or not isinstance(attempt['state'], str)
                or attempt['state'] not in {'running', 'complete', 'incomplete'}
                or not isinstance(attempt['overall'], str)
                or attempt['overall'] not in {'erfüllt', 'verletzt', 'unklar'}
                or not isinstance(attempt['message'], str)
                or attempt['message'] not in {
                    'vollständig geprüft', _INCOMPLETE,
                    _INCOMPLETE + ': Bericht konnte nicht veröffentlicht werden.'}):
            raise ValueError('Invalid attempt metadata')

        def timestamp(value):
            if not isinstance(value, str) or len(value) > 40:
                raise ValueError('Invalid attempt timestamp')
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                raise ValueError('Missing attempt timezone')
            return parsed

        started = timestamp(attempt['started_at'])
        finished = timestamp(attempt['finished_at']) if attempt['finished_at'] is not None else None
        if finished is not None and finished < started:
            raise ValueError('Invalid attempt time order')
        if attempt['state'] == 'complete':
            if finished is None or attempt != self._metadata(self.report(attempt['scan_id'])):
                raise ValueError('Unconfirmed completed attempt')
        elif (attempt['overall'] != 'unklar' or attempt['message'] == 'vollständig geprüft'
              or (attempt['state'] == 'running' and finished is not None)):
            raise ValueError('Inconsistent incomplete attempt')
        return dict(attempt)

    @staticmethod
    def _metadata(report):
        return {'scan_id': report['scan_id'], 'state': 'complete' if report['complete'] else 'incomplete',
                'overall': report['overall'] if report['complete'] else 'unklar',
                'started_at': report['started_at'], 'finished_at': report['finished_at'],
                'message': 'vollständig geprüft' if report['complete'] else _INCOMPLETE}

    def _persist_attempt(self):
        data = {'vault': str(self.vault), 'attempt': self._attempt}
        descriptor, name = tempfile.mkstemp(prefix='.scanner-attempt-', dir=self.store.state_dir)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump(data, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.store.state_dir / _ATTEMPT_FILE)
            fd = _open_root(self.store.state_dir)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            Path(name).unlink(missing_ok=True)

    def status(self):
        with self._mutex:
            baseline = None
            error = self._recovery_error
            try:
                error = error or self.store.recover()['status'] == 'error'
                complete = self.store.last_complete()
                if complete:
                    baseline = self._metadata(self.report(complete['scan_id']))
            except (ReportStoreError, OSError, KeyError, ValueError):
                error = True
            attempt = deepcopy(self._attempt)
            state = attempt['state'] if attempt else ('complete' if baseline else 'idle')
            overall = attempt['overall'] if attempt else (baseline['overall'] if baseline else 'unklar')
            if error and state != 'running':
                state, overall = 'incomplete', 'unklar'
            return {'state': state, 'last_complete': baseline, 'last_attempt': attempt,
                    'overall': overall, 'progress': deepcopy(self._progress),
                    'message': _INCOMPLETE if error or state == 'incomplete' else ''}

    def start(self):
        if not _RUN_LOCK.acquire(blocking=False):
            raise ScannerBusyError('Ein Scanner-Lauf ist bereits aktiv.')
        try:
            with self._mutex:
                scan_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex
                self._attempt = {'scan_id': scan_id, 'state': 'running', 'overall': 'unklar',
                                 'started_at': _now(), 'finished_at': None, 'message': _INCOMPLETE}
                self._progress = {'phase': 'inventory', 'completed': 0, 'total': 0}
                self._persist_attempt()
                threading.Thread(target=self._run, args=(scan_id,), daemon=True,
                                 name='vault-scanner').start()
            return {'scan_id': scan_id}
        except Exception:
            with self._mutex:
                self._attempt.update(state='incomplete', overall='unklar', message=_INCOMPLETE)
            _RUN_LOCK.release()
            raise ReportStoreError('Scanner-Lauf konnte nicht gestartet werden.') from None

    def _checked_chat(self, **kwargs):
        result = self.chat(**kwargs)
        if not isinstance(result, dict) or result.get('done') is not True or result.get('done_reason') != 'stop':
            raise ValueError('Model did not confirm complete evaluation')
        return result

    def _run(self, scan_id):
        report = {'scan_id': scan_id, 'started_at': self._attempt['started_at'], 'finished_at': None,
                  'vault': str(self.vault), 'agents_sha256': None, 'model': '',
                  'exclusions': list(EXCLUSIONS), 'files': [], 'changes': [],
                  'technical_findings': [], 'findings': [], 'overall': 'unklar', 'complete': False}
        inventory = None
        published = False
        try:
            if self._recovery_error or self.store.recover()['status'] == 'error':
                raise ReportStoreError('Scanner state unavailable')
            baseline = self.store.last_complete()
            original_signatures = {}
            inventory = scan_vault(self.vault, signature_snapshot=original_signatures)
            report['files'] = [{key: row[key] for key in ('path', 'kind', 'size', 'sha256')}
                               for row in inventory['files']]
            report['technical_findings'] = [_finding(row['path'], row['reason']) for row in inventory['issues']]
            report['changes'] = diff_inventory(baseline['inventory'] if baseline else None, inventory)
            agents_row = next((row for row in inventory['files'] if row['path'] == 'AGENTS.md'), None)
            agents = _read_content(self.vault, agents_row) if agents_row else b''
            report['agents_sha256'] = hashlib.sha256(agents).hexdigest() if agents_row else None
            model = self.model()
            report['model'] = model if isinstance(model, str) else ''
            self.config = getattr(getattr(self.chat, '__self__', None), 'config', {})
            operations = {row['path']: row['status'] for row in report['changes']}
            removed = [{**row, 'removed': True} for row in (baseline['inventory']['files'] if baseline else [])
                       if operations.get(row['path']) == 'entfernt']
            subjects_to_check = inventory['files'] + removed
            evaluations_complete = True
            with self._mutex:
                self._progress.update(phase='rules', total=len(subjects_to_check))
            for index, row in enumerate(subjects_to_check or [None]):
                subjects = []
                if row:
                    subject = {'path': row['path'], 'kind': row['kind'],
                               'operation': operations.get(row['path'], 'Bestandsprüfung')}
                    try:
                        if row.get('removed'):
                            # The current state proves absence, not the removed body.
                            subject.update(kind='text', content='')
                        elif row['kind'] == 'binary':
                            raise ValueError('Unsupported binary')
                        else:
                            subject['content'] = _read_content(self.vault, row)
                    except (OSError, ValueError):
                        subject['unreadable'] = True
                        report['technical_findings'].append(_finding(row['path'], 'Datei ist nicht vollständig prüfbar.'))
                    subjects = [subject]
                result = evaluate_rules(agents, subjects, report['model'], self._checked_chat)
                evaluations_complete = evaluations_complete and result['overall'] != 'unklar'
                report['findings'].extend(_public_finding(item) for item in result['findings'])
                with self._mutex:
                    self._progress['completed'] = index + 1 if row else 0
            with self._mutex:
                self._progress['phase'] = 'verify'
            verified_signatures = {}
            verified = scan_vault(self.vault, signature_snapshot=verified_signatures)
            if verified != inventory or verified_signatures != original_signatures:
                report['technical_findings'].append(_finding('.', 'Vault wurde während des Scans verändert.'))
            statuses = {row['status'] for row in report['findings']}
            report['overall'] = ('unklar' if report['technical_findings'] or not evaluations_complete or 'unklar' in statuses
                                 else 'verletzt' if 'verletzt' in statuses else 'erfüllt')
            report['complete'] = report['overall'] != 'unklar'
        except Exception:
            # Filesystem, connector and state errors can embed confidential text.
            report['technical_findings'].append(_finding('.', 'Scanner-Eingaben oder Zustand sind nicht vollständig prüfbar.'))
            report.update(complete=False, overall='unklar')
        try:
            report['finished_at'] = _now()
            with self._mutex:
                self._progress['phase'] = 'publish'
            self.store.publish(
                scan_id, report, inventory if report['complete'] else None,
                expected_signatures=original_signatures if report['complete'] else None,
            )
            published = True
        except Exception:
            report.update(complete=False, overall='unklar')
        finally:
            try:
                with self._mutex:
                    self._attempt = self._metadata(report)
                    if not published:
                        self._attempt['message'] = _INCOMPLETE + ': Bericht konnte nicht veröffentlicht werden.'
                    self._progress['phase'] = 'done'
                    try:
                        self._persist_attempt()
                    except OSError:
                        self._recovery_error = True
                        self._attempt.update(state='incomplete', overall='unklar', message=_INCOMPLETE)
            finally:
                _RUN_LOCK.release()

    def report(self, scan_id):
        report = self.store.get_report(scan_id)
        if not report.get('published'):
            raise ReportStoreError('Scanner-Bericht ist nicht bestätigt.')
        keys = ('scan_id', 'started_at', 'finished_at', 'vault', 'agents_sha256', 'model',
                'exclusions', 'files', 'changes', 'technical_findings', 'findings', 'overall', 'complete', 'published')
        return {key: report[key] for key in keys}
