"""Adversarial final-review regressions using real files, Git, and app locks."""
import base64
import threading
import subprocess
from pathlib import Path

import pytest

import dashboard_api
import dokulader_service
from loop.vault_loop_executor import VaultLoopExecutor
from loop.test_watcher_loop_orchestrator import test_guard
from scanner.report_store import ScannerReportStore
from scanner.write_guard import RuleBlocked
from test_agents_write_guard import app_env, NEW_RULES, PDF, encoded
from test_dokulader_service import package_bytes, RecordingGuard


@pytest.fixture
def executor(tmp_path):
    vault = tmp_path.resolve() / 'vault'
    for folder in ['01 Inbox', '06 Archiv', '08 KI-Wissensbank', '09 Werkzeuge']:
        (vault / folder).mkdir(parents=True)
    (vault / 'AGENTS.md').write_text('Keep notes sourced.\n')
    (vault / '01 Inbox/eingang.md').write_text('# Input\nOriginal content.\n')
    (vault / '08 KI-Wissensbank/_Log.md').write_text('# Log\n')
    return VaultLoopExecutor(vault, test_guard(vault, tmp_path / 'state'))


@pytest.mark.parametrize('attack', ['archive_symlink', 'parent_symlink', 'source_identity', 'log_symlink'])
def test_watcher_rechecks_mutation_boundary(executor, tmp_path, monkeypatch, attack):
    inputs = executor.snapshot_inbox()
    proposal = executor.create_proposal('BOUNDARY', 'Test', '', inputs, [])
    outside = tmp_path / 'outside'
    outside.mkdir()
    sentinel = outside / 'eingang.md'
    sentinel.write_bytes(b'FOREIGN')
    source = executor.vault / '01 Inbox/eingang.md'
    original = source.read_bytes()
    def interfere():
        if attack == 'archive_symlink':
            (executor.archive / 'eingang.md').symlink_to(sentinel)
        elif attack == 'parent_symlink':
            executor.archive.rmdir()
            executor.archive.symlink_to(outside, target_is_directory=True)
        elif attack == 'source_identity':
            source.rename(source.with_suffix('.saved'))
            source.write_bytes(original)
        else:
            log = executor.knowledge / '_Log.md'
            log.unlink()
            log.symlink_to(sentinel)
    monkeypatch.setattr(executor, '_mark_qmd_resync', interfere)
    monkeypatch.setattr(executor, '_run_indexer', lambda: {'ok': True})
    caught = None
    try:
        executor.apply(inputs, proposal)
    except Exception as exc:
        caught = exc
    assert sentinel.read_bytes() == b'FOREIGN'
    assert (source if source.exists() else executor.archive / "eingang.md").read_bytes() == original
    assert caught is not None, 'Mutation must reject a replaced file identity'
    assert executor.transaction_journal.exists(), 'Unresolved foreign edit retains recovery journal'


@pytest.mark.parametrize('kind', ['url', 'zip', 'pdf'])
@pytest.mark.parametrize('edit', ['bytes', 'identity'])
def test_import_rollback_preserves_foreign_file(app_env, monkeypatch, kind, edit):
    vault, client, auth = app_env
    install = dokulader_service._atomic_new_file
    installed = []
    def interfere(target, content):
        if installed:
            first = installed[0]
            if edit == 'identity':
                old = first.read_bytes()
                first.rename(first.with_name(first.name + '.saved'))
                first.write_bytes(old)
            else:
                first.write_bytes(b'FOREIGN')
            raise OSError('second install failed')
        result = install(target, content)
        installed.append(target)
        return result
    monkeypatch.setattr(dokulader_service, '_atomic_new_file', interfere)
    if kind == 'url':
        route, payload = '/api/dokulader/urls', {'urls': ['https://example.org/one', 'https://example.org/two']}
    elif kind == 'zip':
        route, payload = '/api/dokulader/package', {'filename': 'manual.zip', 'content_base64': encoded(package_bytes())}
    else:
        route, payload = '/api/dokulader/pdf', {'filename': 'manual.pdf', 'content_base64': encoded(PDF)}
    if kind == 'url':
        response = client.post(route, json=payload, headers=auth)
        status, message = response.status_code, response.text
    else:
        method = dokulader_service.import_package if kind == 'zip' else dokulader_service.import_pdf
        try:
            method(vault, payload['filename'], payload['content_base64'], RecordingGuard(vault))
        except Exception as exc:
            status, message = (409 if isinstance(exc, RuleBlocked) else 502), str(exc)
        else:
            status, message = 200, ''
    assert installed and installed[0].exists(), message
    if edit == 'bytes':
        assert installed[0].read_bytes() == b'FOREIGN'
    assert status == 409, message
    assert 'Rückweg' in message or 'Rollback' in message


def test_agents_rollback_preserves_changed_backup(app_env, monkeypatch):
    vault, client, auth = app_env
    def fail(target, *_):
        next(vault.glob('AGENTS.md.bak-*.md')).write_bytes(b'FOREIGN')
        raise OSError('replace failed')
    monkeypatch.setattr(dashboard_api, '_atomic_replace_file', fail)
    response = client.put('/api/vault/agents-md', json={'content': NEW_RULES.decode()}, headers=auth)
    assert [p.read_bytes() for p in vault.glob('AGENTS.md.bak-*.md')] == [b'FOREIGN']
    assert response.status_code == 409, response.text


def test_report_waits_for_failed_watcher_transaction(executor, monkeypatch):
    vault = executor.vault
    def git(*args):
        return subprocess.run(['git', '-C', str(vault), *args], check=True, capture_output=True).stdout
    git('init', '-q')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.invalid')
    git('add', '.')
    git('commit', '-qm', 'base')
    head = git('rev-parse', 'HEAD')
    inputs = executor.snapshot_inbox()
    proposal = executor.create_proposal('LOCK', 'Test', '', inputs, [])
    store = ScannerReportStore(vault, executor.guard.state_dir)
    started, finished, publishing = threading.Event(), threading.Event(), threading.Event()
    repository = store._repository
    def entered_publication():
        publishing.set()
        return repository()
    monkeypatch.setattr(store, '_repository', entered_publication)
    observed = []
    result = []
    def publish():
        started.set()
        try:
            result.append(store.publish('CONCURRENT', {'rule_status': 'verletzt'}, None))
        finally:
            finished.set()
    worker = threading.Thread(target=publish)
    def fail_indexer():
        worker.start()
        assert started.wait(2)
        # Publication must remain blocked while the Watcher owns its mutation lock.
        observed.append(publishing.wait(.5))
        if observed[-1]:
            assert finished.wait(5)
        raise RuntimeError('indexer failure')
    monkeypatch.setattr(executor, '_run_indexer', fail_indexer)
    try:
        with pytest.raises(RuntimeError):
            executor.apply(inputs, proposal)
    finally:
        worker.join(5)
    assert observed == [False], 'Scanner entered publication inside Watcher transaction'
    assert not worker.is_alive()
    assert result and result[0]['scan_id'] == 'CONCURRENT'
    assert (vault / '01 Inbox/eingang.md').read_text() == '# Input\nOriginal content.\n'
    assert not (vault / '06 Archiv/eingang.md').exists()
    assert not executor.transaction_journal.exists()


@pytest.mark.parametrize('recovery', [False, True])
def test_watcher_rollback_never_follows_replaced_log(executor, tmp_path, monkeypatch, recovery):
    inputs = executor.snapshot_inbox()
    proposal = executor.create_proposal('ROLLBACK', 'Test', '', inputs, [])
    log = executor.knowledge / '_Log.md'
    sentinel = tmp_path / 'foreign-log'
    foreign = []
    def replace_log(*_):
        foreign.append(log.read_bytes())
        sentinel.write_bytes(foreign[-1])
        log.unlink()
        log.symlink_to(sentinel)
    if recovery:
        class Crash(BaseException):
            pass
        def crash():
            raise Crash()
        monkeypatch.setattr(executor, '_run_indexer', crash)
        with pytest.raises(Crash):
            executor.apply(inputs, proposal)
        monkeypatch.setattr(executor, '_clear_interrupted_index_lock', replace_log)
        action = executor.ensure_commit_ready
    else:
        def fail():
            replace_log()
            raise RuntimeError('Indexer failed')
        monkeypatch.setattr(executor, '_run_indexer', fail)
        action = lambda: executor.apply(inputs, proposal)
    with pytest.raises(RuntimeError):
        action()
    assert sentinel.read_bytes() == foreign[0]
    assert log.is_symlink()
    assert executor.transaction_journal.exists()


def test_index_restore_never_follows_foreign_symlink(executor, tmp_path):
    index = executor.knowledge / '_index'
    index.mkdir()
    sentinel = tmp_path / 'foreign-index'
    sentinel.write_bytes(b'FOREIGN')
    (index / 'data.json').symlink_to(sentinel)
    try:
        executor._restore_index(index, {Path('data.json'): b'previous index'})
    except (OSError, RuntimeError):
        pass
    assert sentinel.read_bytes() == b'FOREIGN'
    assert (index / 'data.json').is_symlink()


def test_report_recovery_uses_shared_write_lock(executor, monkeypatch):
    vault = executor.vault
    def git(*args):
        return subprocess.run(['git', '-C', str(vault), *args], check=True, capture_output=True).stdout
    git('init', '-q')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.invalid')
    git('add', '.')
    git('commit', '-qm', 'base')
    store = ScannerReportStore(vault, executor.guard.state_dir)
    class Crash(BaseException):
        pass
    finish = store._finish
    def crash(*_):
        raise Crash()
    monkeypatch.setattr(store, '_finish', crash)
    with pytest.raises(Crash):
        store.publish('RECOVERY', {'rule_status': 'unklar'}, None)
    monkeypatch.setattr(store, '_finish', finish)
    entered = threading.Event()
    confirm = store._confirm
    def confirm_under_lock(*args):
        entered.set()
        return confirm(*args)
    monkeypatch.setattr(store, '_confirm', confirm_under_lock)
    results = []
    worker = threading.Thread(target=lambda: results.append(store.recover()))
    with executor.guard._lock():
        worker.start()
        observed = entered.wait(.5)
    worker.join(5)
    assert observed is False, 'Report recovery mutated Git/state while another writer held the lock'
    assert results[0]['status'] == 'recovered'


@pytest.mark.parametrize('boundary', ['before_publication', 'before_ref'])
def test_scanner_rechecks_inventory_inside_publication_lock(executor, tmp_path, monkeypatch, boundary):
    from test_scanner_api import scanner, finished
    vault = executor.vault
    for args in [('init', '-q'), ('config', 'user.name', 'Test'),
                 ('config', 'user.email', 'test@example.invalid'), ('add', '.'), ('commit', '-qm', 'base')]:
        subprocess.run(['git', '-C', str(vault), *args], check=True, capture_output=True)
    service = scanner(vault, tmp_path)
    if boundary == 'before_publication':
        publish = service.store.publish
        def changed(*args, **kwargs):
            (vault / 'new.md').write_text('New unchecked document')
            return publish(*args, **kwargs)
        monkeypatch.setattr(service.store, 'publish', changed)
    else:
        git = service.store._git
        def changed(*args, **kwargs):
            result = git(*args, **kwargs)
            if args[0] == 'commit-tree':
                (vault / 'new.md').write_text('New unchecked document')
            return result
        monkeypatch.setattr(service.store, '_git', changed)
    service.start()
    state = finished(service)
    assert state['state'] == 'incomplete'
    assert state['last_complete'] is None


@pytest.mark.parametrize('operation', ['create', 'delete', 'replace'])
def test_watcher_recovers_crash_before_postmutation_journal(executor, monkeypatch, operation):
    from loop import vault_loop_executor as module
    inputs = executor.snapshot_inbox()
    proposal = executor.create_proposal('WINDOW', 'Test', '', inputs, [])
    original_files = {p.relative_to(executor.vault): p.read_bytes()
                      for p in executor.vault.rglob('*') if p.is_file()}
    mutation = module.mutate_file
    class Crash(BaseException):
        pass
    def crash_after_mutation(path, content, expected, **kwargs):
        result = mutation(path, content, expected, **kwargs)
        match = (operation == 'create' and path.parent == executor.archive
                 or operation == 'delete' and path.parent == executor.inbox
                 or operation == 'replace' and path.name == '_Log.md')
        if match:
            raise Crash()
        return result
    with monkeypatch.context() as patch:
        patch.setattr(module, 'mutate_file', crash_after_mutation)
        with pytest.raises(Crash):
            executor.apply(inputs, proposal)
    restarted = VaultLoopExecutor(executor.vault, executor.guard)
    monkeypatch.setattr(restarted, '_run_indexer', lambda: {'ok': True})
    restarted.ensure_commit_ready()
    assert {p.relative_to(executor.vault): p.read_bytes()
            for p in executor.vault.rglob('*') if p.is_file()} == original_files
    assert not restarted.transaction_journal.exists()


def test_watcher_recovers_process_exit_after_exclusive_link(executor, monkeypatch):
    import os
    import sys
    proposal = executor.create_proposal('LINKWINDOW', 'Test', '', executor.snapshot_inbox(), [])
    code = '''
import os
from pathlib import Path
from loop.vault_loop_executor import VaultLoopExecutor
from loop.test_watcher_loop_orchestrator import test_guard
from scanner import safe_files
vault, state = Path(os.environ['TEST_VAULT']), Path(os.environ['TEST_STATE'])
original = safe_files.os.link
def crash_after_link(source, target, **kwargs):
    original(source, target, **kwargs)
    if target == 'eingang.md':
        os._exit(71)
safe_files.os.link = crash_after_link
executor = VaultLoopExecutor(vault, test_guard(vault, state))
executor.apply(executor.snapshot_inbox(), {'path': os.environ['TEST_PROPOSAL']})
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env={
        **os.environ, 'TEST_VAULT': str(executor.vault), 'TEST_STATE': str(executor.guard.state_dir),
        'TEST_PROPOSAL': proposal['path']})
    assert result.returncode == 71, result.stderr
    assert (executor.archive / 'eingang.md').stat().st_nlink == 2
    monkeypatch.setattr(executor, '_run_indexer', lambda: {'ok': True})
    executor.ensure_commit_ready()
    assert (executor.inbox / 'eingang.md').read_text() == '# Input\nOriginal content.\n'
    assert not (executor.archive / 'eingang.md').exists()
    assert not list(executor.vault.rglob('.vault-*.tmp'))
    assert not executor.transaction_journal.exists()


def _git_crash_window(executor, phase):
    import os
    import sys
    vault = executor.vault
    for args in [('init', '-q'), ('config', 'user.name', 'Test'),
                 ('config', 'user.email', 'test@example.invalid'), ('add', '.'), ('commit', '-qm', 'base')]:
        subprocess.run(['git', '-C', str(vault), *args], check=True, capture_output=True)
    proposal = executor.create_proposal('GITWINDOW', 'Test', '', executor.snapshot_inbox(), [])
    code = '''
import os
from pathlib import Path
from loop import vault_loop_executor as module
from loop.test_watcher_loop_orchestrator import test_guard
from scanner import safe_files
vault, state = Path(os.environ['TEST_VAULT']), Path(os.environ['TEST_STATE'])
phase = os.environ['TEST_PHASE']
run = module.subprocess.run
mutation = module.mutate_file
link = safe_files.os.link
def crashing_link(source, target, **kwargs):
    link(source, target, **kwargs)
    if phase.endswith('lock_link') and target == 'index.lock':
        os._exit(73)
safe_files.os.link = crashing_link
def crashing_run(args, **kwargs):
    result = run(args, **kwargs)
    boundary = 'read-tree' if phase.endswith('read_tree') else 'update-index'
    if phase == 'prepare_repair' and 'update-ref' in args:
        os._exit(72)
    if not phase.endswith('index_replace') and phase != 'prepare_repair' and boundary in args:
        os._exit(73)
    return result
def crashing_mutation(path, *args, **kwargs):
    result = mutation(path, *args, **kwargs)
    if phase.endswith('index_replace') and path == vault / '.git/index':
        os._exit(73)
    return result
module.subprocess.run = crashing_run
module.mutate_file = crashing_mutation
executor = module.VaultLoopExecutor(vault, test_guard(vault, state))
executor._run_indexer = lambda: {'ok': True}
if phase.startswith('repair_'):
    executor.ensure_commit_ready()
else:
    executor.apply(executor.snapshot_inbox(), {'path': os.environ['TEST_PROPOSAL']})
'''
    env = {**os.environ, 'TEST_VAULT': str(vault), 'TEST_STATE': str(executor.guard.state_dir),
           'TEST_PROPOSAL': proposal['path']}
    if phase.startswith('repair_'):
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                                env={**env, 'TEST_PHASE': 'prepare_repair'})
        assert result.returncode == 72, result.stderr
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                            env={**env, 'TEST_PHASE': phase})
    assert result.returncode == 73, result.stderr


@pytest.mark.parametrize('phase', ['commit_lock_link', 'commit_read_tree', 'commit_update_index',
                                  'commit_index_replace', 'repair_lock_link', 'repair_read_tree',
                                  'repair_index_replace'])
def test_git_artifact_crash_windows_recover_automatically(executor, monkeypatch, phase):
    _git_crash_window(executor, phase)
    monkeypatch.setattr(executor, '_run_indexer', lambda: {'ok': True})
    executor.ensure_commit_ready()
    committed = phase in {'commit_index_replace', 'repair_lock_link', 'repair_read_tree', 'repair_index_replace'}
    assert (executor.archive / 'eingang.md').exists() is committed
    assert (executor.inbox / 'eingang.md').exists() is not committed
    assert not executor.transaction_journal.exists()
    assert not (executor.vault / '.git/index.lock').exists()
    status = subprocess.check_output(['git', '-C', str(executor.vault), 'status', '--porcelain'])
    assert status == b''


@pytest.mark.parametrize('foreign', ['bytes', 'identity'])
def test_git_crash_recovery_preserves_foreign_lock(executor, monkeypatch, foreign):
    _git_crash_window(executor, 'commit_read_tree')
    lock = executor.vault / '.git/index.lock'
    if foreign == 'identity':
        original = lock.read_bytes()
        lock.rename(lock.with_suffix('.saved'))
        lock.write_bytes(original)
    else:
        lock.write_bytes(b'FOREIGN GIT LOCK')
    before = lock.read_bytes()
    monkeypatch.setattr(executor, '_run_indexer', lambda: {'ok': True})
    with pytest.raises(RuntimeError, match='Git-Index'):
        executor.ensure_commit_ready()
    assert lock.read_bytes() == before
    assert executor.transaction_journal.exists()
    assert (executor.archive / 'eingang.md').exists()


@pytest.mark.parametrize('failure', ['scratch_creation', 'lock_journal_completion'])
def test_git_preparation_error_does_not_orphan_owned_lock(executor, monkeypatch, failure):
    vault = executor.vault
    for args in [('init', '-q'), ('config', 'user.name', 'Test'),
                 ('config', 'user.email', 'test@example.invalid'), ('add', '.'), ('commit', '-qm', 'base')]:
        subprocess.run(['git', '-C', str(vault), *args], check=True, capture_output=True)
    proposal = executor.create_proposal('GITERROR', 'Test', '', executor.snapshot_inbox(), [])
    monkeypatch.setattr(executor, '_run_indexer', lambda: {'ok': True})
    if failure == 'scratch_creation':
        def fail():
            raise OSError('scratch creation failed')
        monkeypatch.setattr(executor, '_new_git_scratch', fail)
    else:
        save = executor._save_progress
        failed = False
        def fail(record):
            nonlocal failed
            lock = record.get('git_artifacts', {}).get('index.lock')
            if lock and lock['temporary'] is None and lock['after']['identity'] is not None and not failed:
                failed = True
                raise OSError('journal completion failed')
            return save(record)
        monkeypatch.setattr(executor, '_save_progress', fail)
    with pytest.raises(RuntimeError):
        executor.apply(executor.snapshot_inbox(), proposal)
    assert (executor.inbox / 'eingang.md').exists()
    assert not (vault / '.git/index.lock').exists()
    assert not executor.transaction_journal.exists()
