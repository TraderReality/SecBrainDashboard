"""Scanner lifecycle against real inventory, rule evaluation, persistence and HTTP."""
import base64
import json
import subprocess
import threading
import time

import pytest
from fastapi.testclient import TestClient

import dashboard_api


def git(vault, *args):
    return subprocess.run(['git', '-C', str(vault), *args], check=True, capture_output=True)


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / 'vault'
    root.mkdir()
    (root / 'AGENTS.md').write_text('Keep notes orderly.\n')
    (root / 'note.md').write_text('A useful note.\n')
    git(root, 'init', '-b', 'main')
    git(root, 'config', 'user.name', 'Scanner Test')
    git(root, 'config', 'user.email', 'scanner@example.test')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'initial')
    return root


def chat(*, messages, model):
    payload = json.loads(messages[-1]['content'])
    return {'model': model, 'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps({
        'findings': [{'rule_id': rule['id'], 'path': item['path'], 'status': 'erfüllt',
                      'reason': 'Die geprüfte Regel ist eingehalten.'}
                     for rule in payload['rules'] for item in payload['subjects']]})}}


def scanner(vault, tmp_path, callback=chat):
    from scanner.service import VaultScanner
    return VaultScanner(vault, tmp_path / 'state', callback, lambda: 'local-model')


def finished(service):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = service.status()
        if result['state'] != 'running':
            return result
        time.sleep(.01)
    pytest.fail('Scanner did not finish')


def run(service):
    scan_id = service.start()['scan_id']
    status = finished(service)
    return scan_id, status, service.report(scan_id)


def test_first_scan_and_changes_use_last_complete_inventory(vault, tmp_path):
    service = scanner(vault, tmp_path)
    first, state, report = run(service)
    assert state['state'] == 'complete'
    assert state['overall'] == 'erfüllt'
    assert state['last_complete']['scan_id'] == first
    assert report['changes'] == []
    assert {f['path'] for f in report['files']} == {'AGENTS.md', 'note.md'}
    (vault / 'note.md').write_text('Changed note.\n')
    (vault / 'new.md').write_text('New note.\n')
    second, state, report = run(service)
    assert second != first
    assert {r['path']: r['status'] for r in report['changes']} == {
        'AGENTS.md': 'unverändert', 'note.md': 'geändert', 'new.md': 'neu'}
    (vault / 'new.md').unlink()
    assert {'path': 'new.md', 'status': 'entfernt'} in run(service)[2]['changes']
    assert scanner(vault, tmp_path).report(first)['complete'] is True


def test_failure_keeps_baseline_and_survives_restart(vault, tmp_path):
    service = scanner(vault, tmp_path)
    first = run(service)[0]
    (vault / 'new.md').write_text('New note.\n')
    def failed(**kwargs):
        raise RuntimeError('SECRET-DO-NOT-STORE')
    service.chat = failed
    attempt, state, report = run(service)
    assert state['state'] == 'incomplete'
    assert state['overall'] == 'unklar'
    assert state['last_complete']['scan_id'] == first
    assert state['last_attempt']['scan_id'] == attempt
    assert state['last_attempt']['state'] == 'incomplete'
    assert 'nicht vollständig geprüft' in state['last_attempt']['message']
    assert report['complete'] is False
    assert 'SECRET-DO-NOT-STORE' not in json.dumps(report)
    restarted = scanner(vault, tmp_path)
    assert restarted.status()['state'] == 'incomplete'
    assert restarted.status()['last_complete']['scan_id'] == first
    assert {'path': 'new.md', 'status': 'neu'} in run(restarted)[2]['changes']


def test_changed_file_during_model_evaluation_does_not_advance(vault, tmp_path):
    service = scanner(vault, tmp_path)
    first = run(service)[0]
    def mutate(**kwargs):
        (vault / 'note.md').write_text('Changed while checking.\n')
        return chat(**kwargs)
    service.chat = mutate
    _, state, report = run(service)
    assert state['state'] == 'incomplete'
    assert state['last_complete']['scan_id'] == first
    assert report['technical_findings']


def test_new_agents_rules_recheck_unchanged_content(vault, tmp_path):
    service = scanner(vault, tmp_path)
    run(service)
    (vault / 'AGENTS.md').write_text('Keep notes orderly.\n\nNever accept an obsolete note.\n')
    def evaluate(**kwargs):
        result = chat(**kwargs)
        rows = json.loads(result['message']['content'])
        for row in rows['findings']:
            if row['path'] == 'note.md' and row['rule_id'] == 'L3':
                row.update(status='verletzt', reason='Die neue Regel ist verletzt.')
        result['message']['content'] = json.dumps(rows)
        return result
    service.chat = evaluate
    scan_id, state, report = run(service)
    assert state['state'] == 'complete'
    assert state['overall'] == 'verletzt'
    assert state['last_complete']['scan_id'] == scan_id
    assert any(r['path'] == 'note.md' and r['rule_id'] == 'L3' and r['status'] == 'verletzt'
               for r in report['findings'])


@pytest.mark.parametrize('metadata', [{'done': False}, {'done': True, 'done_reason': 'length'}, {}])
def test_incomplete_completion_evidence_never_publishes_baseline(vault, tmp_path, metadata):
    from connectors.ollama_connector import OllamaConnector
    connector = OllamaConnector(state_path=tmp_path / 'ollama.json')
    def request(*args, **kwargs):
        result = chat(messages=kwargs['payload']['messages'], model=kwargs['payload']['model'])
        result.pop('done')
        result.pop('done_reason')
        return {**result, **metadata}
    connector._request = request
    _, state, report = run(scanner(vault, tmp_path, connector.chat))
    assert state['state'] == 'incomplete'
    assert state['last_complete'] is None
    assert report['overall'] == 'unklar'


@pytest.mark.parametrize('problem', ['missing_agents', 'binary', 'symlink', 'corrupt_state', 'no_git'])
def test_technical_failures_fail_closed(vault, tmp_path, problem):
    service = scanner(vault, tmp_path)
    if problem == 'missing_agents':
        (vault / 'AGENTS.md').unlink()
    elif problem == 'binary':
        (vault / 'attachment.pdf').write_bytes(b'%PDF\x00body')
    elif problem == 'symlink':
        (vault / 'escape.md').symlink_to(tmp_path / 'private.txt')
        (tmp_path / 'private.txt').write_text('PRIVATE-OUTSIDE-VAULT')
    elif problem == 'corrupt_state':
        (tmp_path / 'state' / 'scanner-state.json').write_text('{broken')
    else:
        git(vault, 'config', '--unset', 'user.email')
        git(vault, 'config', '--unset', 'user.name')
        # Missing HEAD is independent of user/global identity configuration.
        git(vault, 'update-ref', '-d', 'refs/heads/main')
    service.start()
    state = finished(service)
    assert state['state'] == 'incomplete'
    assert state['overall'] == 'unklar'
    assert state['last_complete'] is None


def test_report_has_no_raw_content_or_arbitrary_model_fields(vault, tmp_path):
    (vault / 'note.md').write_text('PRIVATE-SOURCE-BODY')
    service = scanner(vault, tmp_path)
    _, _, report = run(service)
    encoded = json.dumps(report)
    assert 'PRIVATE-SOURCE-BODY' not in encoded
    assert 'Keep notes orderly' not in encoded
    assert set(report['files'][0]) == {'path', 'kind', 'size', 'sha256'}
    assert set(report['findings'][0]) == {'rule_id', 'path', 'status', 'reason', 'source'}


def test_api_auth_concurrency_progress_and_report_bounds(vault, tmp_path, monkeypatch):
    monkeypatch.setenv('SECBRAIN_AUTH_REQUIRED', '1')
    monkeypatch.setenv('SECBRAIN_HTTP_USER', 'tester')
    monkeypatch.setenv('SECBRAIN_HTTP_PASSWORD', 'test-password')
    monkeypatch.setenv('SECBRAIN_WATCHER_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setattr(dashboard_api.runtime.vault, 'path', vault)
    entered, release = threading.Event(), threading.Event()
    def blocked(**kwargs):
        entered.set()
        assert release.wait(10)
        return chat(**kwargs)
    monkeypatch.setattr(dashboard_api.runtime.ollama, 'chat', blocked)
    monkeypatch.setitem(dashboard_api.runtime.ollama.config, 'model', 'local-model')
    auth = {'Authorization': 'Basic ' + base64.b64encode(b'tester:test-password').decode()}
    client = TestClient(dashboard_api.app)
    for method, url in [('get', '/api/scanner/status'), ('post', '/api/scanner/scan'),
                        ('get', '/api/scanner/reports/not-a-report')]:
        assert getattr(client, method)(url).status_code == 401
    try:
        response = client.post('/api/scanner/scan', headers=auth)
        assert response.status_code == 200
        scan_id = response.json()['scan_id']
        assert entered.wait(5)
        assert client.post('/api/scanner/scan', headers=auth).status_code == 409
        from scanner.service import ScannerBusyError
        with pytest.raises(ScannerBusyError):
            scanner(vault, tmp_path).start()
        state = client.get('/api/scanner/status', headers=auth).json()
        assert state['state'] == 'running'
        assert state['overall'] == 'unklar'
        assert state['progress']['total'] == 2
    finally:
        release.set()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = client.get('/api/scanner/status', headers=auth).json()
        if state['state'] != 'running':
            break
        time.sleep(.01)
    assert state['state'] == 'complete'
    assert client.get('/api/scanner/reports/' + scan_id, headers=auth).json()['complete']
    assert client.get('/api/scanner/reports/missing', headers=auth).status_code == 404
    assert client.get('/api/scanner/reports/..%2Fprivate', headers=auth).status_code == 404


def test_incomplete_rule_coverage_with_only_violations_stays_incomplete(vault, tmp_path):
    def invalid(**kwargs):
        result = chat(**kwargs)
        data = json.loads(result['message']['content'])
        for row in data['findings']:
            row.update(status='verletzt', reason='Ein Verstoß wurde erkannt.')
        data['findings'].append({'rule_id': 'unknown', 'path': 'note.md',
                                 'status': 'erfüllt', 'reason': 'Unbelegte Zusatzantwort.'})
        result['message']['content'] = json.dumps(data)
        return result
    _, state, report = run(scanner(vault, tmp_path, invalid))
    assert state['state'] == 'incomplete'
    assert state['last_complete'] is None
    assert report['overall'] == 'unklar'
    assert any(row['status'] == 'verletzt' for row in report['findings'])


def test_status_detects_state_corruption_after_success(vault, tmp_path):
    service = scanner(vault, tmp_path)
    first = run(service)[0]
    (tmp_path / 'state' / 'scanner-state.json').write_text('{broken')
    state = service.status()
    assert state['state'] == 'incomplete'
    assert state['overall'] == 'unklar'
    assert state['last_complete']['scan_id'] == first


def test_deleted_file_is_evaluated_as_a_change(vault, tmp_path):
    service = scanner(vault, tmp_path)
    run(service)
    (vault / 'note.md').unlink()
    def deletion(**kwargs):
        result = chat(**kwargs)
        payload = json.loads(kwargs['messages'][-1]['content'])
        data = json.loads(result['message']['content'])
        for subject in payload['subjects']:
            if subject.get('operation') == 'entfernt':
                for row in data['findings']:
                    row.update(status='verletzt', reason='Die Entfernung verletzt die Regel.')
        result['message']['content'] = json.dumps(data)
        return result
    service.chat = deletion
    _, state, report = run(service)
    assert state['overall'] == 'verletzt'
    assert any(row['path'] == 'note.md' and row['status'] == 'verletzt' for row in report['findings'])


def test_model_budget_failure_is_visible_without_new_baseline(vault, tmp_path):
    (vault / 'note.md').write_text('x' * 9000)
    _, state, report = run(scanner(vault, tmp_path))
    assert state['state'] == 'incomplete'
    assert state['last_complete'] is None
    assert any('Modellbudget' in row['reason'] for row in report['findings'])


def test_tampered_report_is_not_served_or_used_as_status(vault, tmp_path):
    service = scanner(vault, tmp_path)
    scan_id = run(service)[0]
    path = vault / '09 Werkzeuge' / 'Scanner-Berichte' / (scan_id + '.json')
    report = json.loads(path.read_text())
    report['started_at'] = 'PRIVATE-RAW-SOURCE'
    path.write_text(json.dumps(report))
    from scanner.report_store import ReportStoreError
    with pytest.raises(ReportStoreError):
        service.report(scan_id)
    state = service.status()
    assert state['state'] == 'incomplete'
    assert 'PRIVATE-RAW-SOURCE' not in json.dumps(state)


@pytest.mark.parametrize('mutation', ['rewrite_restore', 'replace_identical'])
def test_input_identity_changes_with_identical_final_bytes_keep_baseline(vault, tmp_path, mutation):
    import os
    service = scanner(vault, tmp_path)
    first = run(service)[0]
    note = vault / 'note.md'
    original = note.read_bytes()
    before = note.stat()
    def mutate_after_read(**kwargs):
        payload = json.loads(kwargs['messages'][-1]['content'])
        if any(subject['path'] == 'note.md' for subject in payload['subjects']):
            if mutation == 'rewrite_restore':
                note.write_bytes(b'Temporary different content')
                note.write_bytes(original)
                # Restoring mtime must not hide the change; ctime also matters.
                os.utime(note, ns=(before.st_atime_ns, before.st_mtime_ns))
            else:
                replacement = vault / 'replacement.tmp'
                replacement.write_bytes(original)
                os.replace(replacement, note)
        return chat(**kwargs)
    service.chat = mutate_after_read
    _, state, report = run(service)
    assert note.read_bytes() == original
    assert state['state'] == 'incomplete'
    assert state['overall'] == 'unklar'
    assert state['last_complete']['scan_id'] == first
    assert report['complete'] is False
    assert report['technical_findings']


@pytest.mark.parametrize('bad_metadata', [
    {'state': 'invented'}, {'overall': 'invented'}, {'overall': []},
    {'scan_id': '../private'}, {'started_at': []}, {'finished_at': 'not-a-date'},
    {'finished_at': '2000-01-01T00:00:00+00:00'}, {'message': {'raw': 'secret'}},
    {'state': 'incomplete', 'overall': 'erfüllt'}, {'extra': 'untrusted'},
])
def test_invalid_persisted_attempt_metadata_fails_closed(vault, tmp_path, bad_metadata):
    service = scanner(vault, tmp_path)
    first = run(service)[0]
    attempt_path = tmp_path / 'state' / 'scanner-attempt.json'
    value = json.loads(attempt_path.read_text())
    value['attempt'].update(bad_metadata)
    attempt_path.write_text(json.dumps(value))
    state = scanner(vault, tmp_path).status()
    assert state['state'] == 'incomplete'
    assert state['overall'] == 'unklar'
    assert state['last_attempt'] is None
    assert state['last_complete']['scan_id'] == first
