"""App routes exercise real authorization, filesystem writes and Basic auth."""
import base64
import json
import subprocess
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

import dashboard_api
import dokulader_service
from scanner.test_write_guard import passing_chat
from scanner.write_guard import RuleBlocked
from test_dokulader_service import package_bytes, RecordingGuard


OLD_RULES = b'Keep notes sourced.\n'
NEW_RULES = b'Keep every note sourced and orderly.\n'
PDF = b'%PDF-1.7\n\xff binary\n%%EOF'


def encoded(content):
    return base64.b64encode(content).decode('ascii')


def files(vault):
    return {p.relative_to(vault).as_posix(): p.read_bytes()
            for p in vault.rglob('*') if p.is_file() and '.git' not in p.parts}


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    vault = root / 'vault'
    vault.mkdir()
    (vault / 'AGENTS.md').write_bytes(OLD_RULES)
    monkeypatch.setattr(dashboard_api.runtime.vault, 'path', vault)
    monkeypatch.setenv('SECBRAIN_WATCHER_STATE_DIR', str(root / 'state'))
    monkeypatch.setenv('SECBRAIN_AUTH_REQUIRED', '1')
    monkeypatch.setenv('SECBRAIN_HTTP_USER', 'test')
    monkeypatch.setenv('SECBRAIN_HTTP_PASSWORD', 'secret')
    class LocalTestModel:
        config = {'context': 32768, 'num_predict': 8192}

        def chat(self, messages, model):
            return passing_chat(messages, model)
    monkeypatch.setattr(dashboard_api.runtime.ollama, 'chat', LocalTestModel().chat)
    monkeypatch.setattr(dashboard_api.runtime.ollama, 'get_config', lambda: {'model': 'local'})
    # Network and PDF parser are the only external work replaced here.
    monkeypatch.setattr(dokulader_service, '_fetch_html_once', lambda url: (
        url, '<html><title>' + url.rsplit('/', 1)[-1] + '</title><main>' + 'Documentation ' * 30 + '</main></html>'))
    def convert(path):
        assert not path.resolve().is_relative_to(vault)
        assert files(vault) == {'AGENTS.md': OLD_RULES}
        return [{'text': '# Page one\nContent', 'metadata': {'page': 1}}]
    monkeypatch.setattr(dokulader_service, '_convert_pdf_to_pages', convert)
    return vault, TestClient(dashboard_api.app), {'Authorization': 'Basic ' + encoded(b'test:secret')}


def rejecting_chat(messages, model):
    response = passing_chat(messages, model)
    rows = json.loads(response['message']['content'])
    for row in rows['findings']:
        row['status'] = 'verletzt'
    response['message']['content'] = json.dumps(rows)
    return response


@pytest.mark.parametrize('route,payload', [
    ('/api/vault/inbox/upload', {'filename': 'note.md', 'content_base64': encoded(b'# Note')}),
    ('/api/dokulader/urls', {'urls': ['https://example.org/one', 'https://example.org/two']}),
    ('/api/dokulader/pdf', {'filename': 'manual.pdf', 'content_base64': encoded(PDF)}),
    ('/api/dokulader/package', {'filename': 'manual.zip', 'content_base64': encoded(package_bytes())}),
])
def test_blocked_import_routes_are_atomic_and_authenticated(app_env, monkeypatch, route, payload):
    vault, client, auth = app_env
    monkeypatch.setattr(dashboard_api.runtime.ollama, 'chat', rejecting_chat)
    assert client.post(route, json=payload).status_code == 401
    response = client.post(route, json=payload, headers=auth)
    assert response.status_code == 409, response.text
    assert response.json()['detail']
    assert files(vault) == {'AGENTS.md': OLD_RULES}
    assert list(vault.iterdir()) == [vault / 'AGENTS.md']


@pytest.mark.parametrize('kind', ['pdf', 'package'])
def test_binary_import_is_explicitly_unprocessable_with_real_guard(app_env, kind):
    vault, client, auth = app_env
    payload = {'filename': 'manual.pdf' if kind == 'pdf' else 'manual.zip',
               'content_base64': encoded(PDF if kind == 'pdf' else package_bytes())}
    response = client.post('/api/dokulader/' + kind, json=payload, headers=auth)
    assert response.status_code == 409, response.text
    assert files(vault) == {'AGENTS.md': OLD_RULES}


@pytest.mark.parametrize('rejected_rules', [OLD_RULES, NEW_RULES])
def test_blocked_agents_edit_keeps_old_file_and_backup_state(app_env, monkeypatch, rejected_rules):
    vault, client, auth = app_env
    def chat(messages, model):
        payload = json.loads(messages[-1]['content'])
        if payload['agents'] == rejected_rules.decode() and any(s['operation'] == 'replace' for s in payload['subjects']):
            return rejecting_chat(messages, model)
        return passing_chat(messages, model)
    monkeypatch.setattr(dashboard_api.runtime.ollama, 'chat', chat)
    response = client.put('/api/vault/agents-md', json={'content': NEW_RULES.decode()}, headers=auth)
    assert response.status_code == 409, response.text
    assert files(vault) == {'AGENTS.md': OLD_RULES}


def test_allowed_agents_edit_backs_up_exact_bytes_and_next_write_is_processable(app_env):
    vault, client, auth = app_env
    assert client.put('/api/vault/agents-md', json={'content': NEW_RULES.decode()}).status_code == 401
    response = client.put('/api/vault/agents-md', json={'content': NEW_RULES.decode()}, headers=auth)
    assert response.status_code == 200, response.text
    assert response.json()['success'] is True
    backups = list(vault.glob('AGENTS.md.bak-*.md'))
    assert len(backups) == 1
    assert backups[0].read_bytes() == OLD_RULES
    assert (vault / 'AGENTS.md').read_bytes() == NEW_RULES
    upload = client.post('/api/vault/inbox/upload', json={'filename': 'note.md', 'content_base64': encoded(b'# Note')}, headers=auth)
    assert upload.status_code == 200, upload.text


def test_agents_backup_collision_preserves_existing_files(app_env, monkeypatch):
    vault, client, auth = app_env
    monkeypatch.setattr(dashboard_api.time, 'time', lambda: 123)
    backup = vault / 'AGENTS.md.bak-123000.md'
    backup.write_bytes(b'Previous backup\n')
    response = client.put('/api/vault/agents-md', json={'content': NEW_RULES.decode()}, headers=auth)
    assert response.status_code == 409, response.text
    assert files(vault) == {'AGENTS.md': OLD_RULES, backup.name: b'Previous backup\n'}


@pytest.mark.parametrize('operation', ['upload', 'urls', 'agents'])
def test_concurrent_path_change_aborts_before_mutation(app_env, monkeypatch, operation):
    vault, client, auth = app_env
    changed = False
    def chat(messages, model):
        nonlocal changed
        if not changed:
            (vault / 'external.md').write_bytes(b'External change')
            changed = True
        return passing_chat(messages, model)
    monkeypatch.setattr(dashboard_api.runtime.ollama, 'chat', chat)
    if operation == 'upload':
        response = client.post('/api/vault/inbox/upload', json={'filename': 'note.md', 'content_base64': encoded(b'# Note')}, headers=auth)
    elif operation == 'urls':
        response = client.post('/api/dokulader/urls', json={'urls': ['https://example.org/one']}, headers=auth)
    else:
        response = client.put('/api/vault/agents-md', json={'content': NEW_RULES.decode()}, headers=auth)
    assert response.status_code == 409, response.text
    assert files(vault) == {'AGENTS.md': OLD_RULES, 'external.md': b'External change'}


def test_upload_and_agents_edits_leave_foreign_git_index_and_worktree_untouched(app_env):
    vault, client, auth = app_env
    def git(*args):
        return subprocess.run(['git', '-C', str(vault), *args], check=True, capture_output=True).stdout
    git('init', '-b', 'main')
    (vault / 'foreign.md').write_bytes(b'staged content')
    git('add', 'foreign.md')
    (vault / 'foreign.md').write_bytes(b'unstaged content')
    index_before = (vault / '.git/index').read_bytes()
    response = client.post('/api/vault/inbox/upload', json={'filename': 'note.md', 'content_base64': encoded(b'# Note')}, headers=auth)
    assert response.status_code == 200, response.text
    response = client.put('/api/vault/agents-md', json={'content': NEW_RULES.decode()}, headers=auth)
    assert response.status_code == 200, response.text
    response = client.post('/api/dokulader/urls', json={'urls': ['https://example.org/one']}, headers=auth)
    assert response.status_code == 200, response.text
    assert (vault / '.git/index').read_bytes() == index_before
    assert git('show', ':foreign.md') == b'staged content'
    assert (vault / 'foreign.md').read_bytes() == b'unstaged content'


@pytest.mark.parametrize('kind', ['urls', 'pdf', 'package'])
def test_import_prepares_all_bytes_then_writes_declared_files_under_guard(app_env, monkeypatch, kind):
    vault, _, _ = app_env
    recording = RecordingGuard(vault)
    original_write = dokulader_service._atomic_new_file
    def write(target, content):
        assert recording.active, 'write escaped authorization lock'
        assert any(c.relative_path == target.relative_to(vault).as_posix() and c.after_bytes == content for c in recording.calls[0])
        return original_write(target, content)
    monkeypatch.setattr(dokulader_service, '_atomic_new_file', write)
    if kind == 'urls':
        result = dokulader_service.import_urls(vault, ['https://example.org/one', 'https://example.org/two'], recording)
        assert len(result['imported']) == 2
        expected_count = 2
    elif kind == 'pdf':
        result = dokulader_service.import_pdf(vault, 'manual.pdf', encoded(PDF), recording)
        expected_count = 3
    else:
        result = dokulader_service.import_package(vault, 'manual.zip', encoded(package_bytes()), recording)
        expected_count = 2
    assert len(recording.calls) == 1
    assert len(recording.calls[0]) == expected_count
    assert len(files(vault)) == 1 + expected_count


@pytest.mark.parametrize('kind', ['pdf', 'package'])
def test_manifest_failure_rolls_back_package_under_lock(app_env, monkeypatch, kind):
    vault, _, _ = app_env
    recording = RecordingGuard(vault)
    original_write = dokulader_service._atomic_new_file
    def fail_manifest(target, content):
        assert recording.active
        if target.parent.name == '01 Inbox':
            raise OSError('manifest disk failure')
        return original_write(target, content)
    monkeypatch.setattr(dokulader_service, '_atomic_new_file', fail_manifest)
    with pytest.raises(OSError, match='manifest disk failure'):
        if kind == 'pdf':
            dokulader_service.import_pdf(vault, 'manual.pdf', encoded(PDF), recording)
        else:
            dokulader_service.import_package(vault, 'manual.zip', encoded(package_bytes()), recording)
    assert files(vault) == {'AGENTS.md': OLD_RULES}


def test_api_guard_shares_watcher_state_directory(app_env):
    vault, _, _ = app_env
    guard = dashboard_api.vault_write_guard()
    assert guard.state_dir == vault.parent / 'state'
    assert guard.vault == vault


def test_dokulader_metadata_does_not_read_symlink_targets(app_env):
    vault, _, _ = app_env
    outside = vault.parent / 'outside.md'
    outside.write_text('---\nid: private-outside-id\nquelle: https://private.example.org/\n---\nPrivate content\n')
    (vault / 'linked.md').symlink_to(outside)
    ids, sources, _ = dokulader_service.existing_vault_metadata(vault)
    assert 'private-outside-id' not in ids
    assert 'https://private.example.org/' not in sources


@pytest.mark.parametrize('kind', ['upload', 'pdf', 'package'])
def test_parent_symlink_swap_after_authorization_cannot_write_outside(app_env, kind):
    vault, _, _ = app_env
    outside = vault.parent / 'outside'
    outside.mkdir()
    class SwapParent:
        @contextmanager
        def authorize(self, changes, approval):
            parent = '01 Inbox' if kind == 'upload' else '07 Anhänge'
            (vault / parent).symlink_to(outside, target_is_directory=True)
            yield
    with pytest.raises((RuleBlocked, OSError)):
        if kind == 'upload':
            dashboard_api.write_inbox_upload('note.md', encoded(b'# Note'), SwapParent())
        elif kind == 'pdf':
            dokulader_service.import_pdf(vault, 'manual.pdf', encoded(PDF), SwapParent())
        else:
            dokulader_service.import_package(vault, 'manual.zip', encoded(package_bytes()), SwapParent())
    assert list(outside.iterdir()) == []


def test_agents_replacement_failure_removes_only_new_backup(app_env, monkeypatch):
    vault, client, auth = app_env
    prior = vault / 'AGENTS.md.bak-earlier.md'
    prior.write_bytes(b'Earlier rules\n')
    def fail_replace(*args, **kwargs):
        raise OSError('replace failed')
    monkeypatch.setattr(dashboard_api.os, 'replace', fail_replace)
    response = client.put('/api/vault/agents-md', json={'content': NEW_RULES.decode()}, headers=auth)
    assert response.status_code == 502, response.text
    assert files(vault) == {'AGENTS.md': OLD_RULES, prior.name: b'Earlier rules\n'}


def test_agents_change_after_backup_creation_aborts_replacement(app_env, monkeypatch):
    vault, client, auth = app_env
    original = dashboard_api._atomic_new_file
    def create_then_external_edit(target, content):
        installed = original(target, content)
        (vault / 'AGENTS.md').write_bytes(b'External rule change\n')
        return installed
    monkeypatch.setattr(dashboard_api, '_atomic_new_file', create_then_external_edit)
    response = client.put('/api/vault/agents-md', json={'content': NEW_RULES.decode()}, headers=auth)
    assert response.status_code == 409, response.text
    assert files(vault) == {'AGENTS.md': b'External rule change\n'}


def test_oversized_markdown_upload_fails_closed(app_env):
    vault, client, auth = app_env
    response = client.post('/api/vault/inbox/upload', json={
        'filename': 'large.md', 'content_base64': encoded(b'a' * 64_001)}, headers=auth)
    assert response.status_code == 409, response.text
    assert files(vault) == {'AGENTS.md': OLD_RULES}


@pytest.mark.parametrize('kind', ['pdf', 'package'])
def test_configured_temp_directory_inside_vault_is_rejected_without_writes(app_env, monkeypatch, kind):
    vault, _, _ = app_env
    monkeypatch.setattr(dokulader_service.tempfile, 'gettempdir', lambda: str(vault))
    guard = RecordingGuard(vault)
    with pytest.raises(RuleBlocked):
        if kind == 'pdf':
            dokulader_service.import_pdf(vault, 'manual.pdf', encoded(PDF), guard)
        else:
            dokulader_service.import_package(vault, 'manual.zip', encoded(package_bytes()), guard)
    assert files(vault) == {'AGENTS.md': OLD_RULES}


@pytest.mark.parametrize('failure', [OSError, RuleBlocked])
def test_url_batch_second_install_failure_rolls_back_under_real_lock(app_env, monkeypatch, failure):
    import fcntl

    vault, client, auth = app_env
    def git(*args):
        return subprocess.run(['git', '-C', str(vault), *args], check=True, capture_output=True).stdout
    git('init', '-b', 'main')
    (vault / 'foreign.md').write_bytes(b'staged content')
    git('add', 'foreign.md')
    (vault / 'foreign.md').write_bytes(b'unstaged content')
    before = files(vault)
    index_before = (vault / '.git/index').read_bytes()
    original_fetch = dokulader_service._fetch_html_once
    original_write = dokulader_service._atomic_new_file
    original_remove = dokulader_service._remove_file
    attempts = []
    removed = []

    def fetch(url):
        if url.endswith('/unavailable'):
            raise ValueError('source unavailable')
        return original_fetch(url)

    def install(target, content):
        attempts.append(target.name)
        if len(attempts) == 2:
            raise failure('second installation failed')
        return original_write(target, content)

    def remove(target, expected):
        with (vault.parent / 'state/vault-write.lock').open('rb') as lock:
            with pytest.raises(BlockingIOError):
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        original_remove(target, expected)
        removed.append(target.name)

    monkeypatch.setattr(dokulader_service, '_fetch_html_once', fetch)
    monkeypatch.setattr(dokulader_service, '_atomic_new_file', install)
    monkeypatch.setattr(dokulader_service, '_remove_file', remove)
    urls = ['https://example.org/' + slug for slug in ['one', 'unavailable', 'two', 'three']]
    response = client.post('/api/dokulader/urls', json={'urls': urls}, headers=auth)
    assert files(vault) == before
    assert removed == ['one.md']
    assert attempts == ['one.md', 'two.md']
    assert (vault / '.git/index').read_bytes() == index_before
    assert git('show', ':foreign.md') == b'staged content'
    if failure is RuleBlocked:
        assert response.status_code == 409, response.text
        assert response.json()['detail'] == 'second installation failed'
    else:
        assert response.status_code == 200, response.text
        result = response.json()
        assert set(result) == {'status', 'imported', 'skipped', 'errors'}
        assert result['status'] == 'completed'
        assert result['imported'] == []
        assert result['skipped'] == []
        assert {'url': urls[1], 'reason': 'source unavailable'} in result['errors']
        assert {error['url'] for error in result['errors']} == set(urls)
