"""Report persistence boundaries against real Git repositories."""
import json
import os
from pathlib import Path
import subprocess

import pytest

from dashboard.backend.scanner.report_store import ReportStoreError, ScannerReportStore


def git(vault, *args, data=None):
    return subprocess.run(['git', '-C', str(vault), *args], input=data,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', os.devnull)
    monkeypatch.setenv('GIT_CONFIG_SYSTEM', os.devnull)
    for key in ('GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL', 'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL'):
        monkeypatch.delenv(key, raising=False)
    root = tmp_path / 'vault'
    root.mkdir()
    git(root, 'init', '-q')
    git(root, 'config', 'user.name', 'Scanner Test')
    git(root, 'config', 'user.email', 'scanner@example.invalid')
    (root / 'unrelated.md').write_text('base\n')
    git(root, 'add', 'unrelated.md')
    git(root, 'commit', '-qm', 'base')
    return root


@pytest.fixture
def store(vault, tmp_path):
    return ScannerReportStore(vault, tmp_path / 'state')


INVENTORY = {'files': [{'path': 'unrelated.md', 'kind': 'markdown', 'size': 5,
                        'sha256': 'a' * 64}], 'issues': []}
REPORT = {'rule_status': 'verletzt', 'findings': [{'path': 'unrelated.md', 'status': 'verletzt'}]}


def test_complete_and_incomplete_reports_are_immutable(store, vault, tmp_path):
    result = store.publish('SCAN-1', REPORT, INVENTORY)
    assert result['complete'] is True
    assert result['report_path'] == '09 Werkzeuge/Scanner-Berichte/SCAN-1.json'
    baseline = store.last_complete()
    assert baseline['scan_id'] == 'SCAN-1'
    assert baseline['inventory'] == INVENTORY
    assert store.get_report('SCAN-1')['rule_status'] == 'verletzt'
    result2 = store.publish('SCAN-2', {'rule_status': 'unklar'}, None)
    assert result2['complete'] is False
    assert store.last_complete() == baseline
    assert ScannerReportStore(vault, tmp_path / 'state').get_report('SCAN-2')['complete'] is False
    with pytest.raises(ReportStoreError):
        store.publish('SCAN-1', {'changed': True}, INVENTORY)
    assert store.get_report('SCAN-1')['rule_status'] == 'verletzt'
    assert len(list((vault / '09 Werkzeuge/Scanner-Berichte').glob('*.json'))) == 2


def test_report_commit_preserves_foreign_staging(store, vault):
    (vault / 'unrelated.md').write_text('staged\n')
    (vault / 'added.md').write_text('added staged\n')
    git(vault, 'add', 'unrelated.md', 'added.md')
    staged = git(vault, 'ls-files', '--stage', '-z')
    (vault / 'unrelated.md').write_text('unstaged\n')
    (vault / 'added.md').write_text('added unstaged\n')
    result = store.publish('SCAN-1', REPORT, INVENTORY)
    assert git(vault, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').decode().strip() == result['report_path']
    assert git(vault, 'ls-files', '--stage', '-z', '--', 'unrelated.md', 'added.md') == staged
    assert (vault / 'unrelated.md').read_text() == 'unstaged\n'
    assert (vault / 'added.md').read_text() == 'added unstaged\n'
    assert git(vault, 'diff', '--cached', '--', result['report_path']) == b''


class Crash(BaseException):
    pass


@pytest.mark.parametrize('boundary', ['before_ref', 'after_ref', 'after_state'])
def test_crash_recovery_never_duplicates_or_invents_success(store, vault, tmp_path, monkeypatch, boundary):
    original_git = store._git
    original_state = store._write_state

    def crashing_git(*args, **kwargs):
        if args[0] == 'update-ref' and boundary == 'before_ref':
            raise Crash()
        output = original_git(*args, **kwargs)
        if args[0] == 'update-ref' and boundary == 'after_ref':
            raise Crash()
        return output

    def crashing_state(state):
        original_state(state)
        if boundary == 'after_state':
            raise Crash()

    monkeypatch.setattr(store, '_git', crashing_git)
    monkeypatch.setattr(store, '_write_state', crashing_state)
    with pytest.raises(Crash):
        store.publish('SCAN-1', REPORT, INVENTORY)
    restarted = ScannerReportStore(vault, tmp_path / 'state')
    result = restarted.recover()
    assert result['status'] == ('incomplete' if boundary == 'before_ref' else 'recovered')
    if boundary == 'before_ref':
        assert restarted.last_complete() is None
    else:
        assert restarted.last_complete()['scan_id'] == 'SCAN-1'
        assert git(vault, 'show', 'HEAD:09 Werkzeuge/Scanner-Berichte/SCAN-1.json')
    assert len(list((vault / '09 Werkzeuge/Scanner-Berichte').glob('*.json'))) == 1
    with pytest.raises(ReportStoreError):
        restarted.publish('SCAN-1', REPORT, INVENTORY)


@pytest.mark.parametrize('fault', ['identity', 'repository', 'state'])
def test_failure_preserves_last_good_baseline(store, vault, tmp_path, fault):
    store.publish('SCAN-1', REPORT, INVENTORY)
    baseline = store.last_complete()
    if fault == 'identity':
        git(vault, 'config', '--unset', 'user.email')
        git(vault, 'config', 'user.useConfigOnly', 'true')
    elif fault == 'repository':
        (vault / '.git').rename(vault / 'saved-git')
    else:
        (tmp_path / 'state/scanner-state.json').write_text('{corrupt')
    with pytest.raises(ReportStoreError):
        store.publish('SCAN-2', REPORT, INVENTORY)
    assert ScannerReportStore(vault, tmp_path / 'state').last_complete() == baseline
    if fault == 'state':
        assert store.recover()['status'] == 'error'


@pytest.mark.parametrize('scan_id', ['../secret', '/tmp/secret', '.', '..', 'a/b', 'a\\b', '', 'x' * 129])
def test_invalid_ids_cannot_read_or_write_paths(store, scan_id):
    with pytest.raises(ReportStoreError):
        store.get_report(scan_id)
    with pytest.raises(ReportStoreError):
        store.publish(scan_id, REPORT, INVENTORY)


def test_state_must_be_outside_vault(vault, tmp_path):
    with pytest.raises(ReportStoreError):
        ScannerReportStore(vault, vault / 'state')
    (tmp_path / 'state-link').symlink_to(vault, target_is_directory=True)
    with pytest.raises(ReportStoreError):
        ScannerReportStore(vault, tmp_path / 'state-link' / 'state')


def test_private_state_permissions_and_version(store, tmp_path):
    store.publish('SCAN-1', REPORT, INVENTORY)
    state = tmp_path / 'state'
    for path in state.iterdir():
        if path.is_file():
            assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads((state / 'scanner-state.json').read_text())['version'] == 1


def test_report_directory_symlink_is_never_followed(store, vault, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (vault / '09 Werkzeuge').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ReportStoreError):
        store.publish('SCAN-1', REPORT, INVENTORY)
    assert list(outside.iterdir()) == []


def test_report_file_symlink_is_never_read(store, vault, tmp_path):
    directory = vault / '09 Werkzeuge/Scanner-Berichte'
    directory.mkdir(parents=True)
    secret = tmp_path / 'secret.json'
    secret.write_text('{"secret":"sensitive"}')
    (directory / 'SCAN-1.json').symlink_to(secret)
    with pytest.raises(ReportStoreError):
        store.get_report('SCAN-1')


def test_incomplete_inventory_cannot_be_published_as_complete(store):
    with pytest.raises(ReportStoreError):
        store.publish('SCAN-1', REPORT, {'files': [], 'issues': [{'path': 'bad'}]})
    assert store.last_complete() is None


def test_head_lease_failure_does_not_advance_baseline(store, vault, monkeypatch):
    store.publish('SCAN-1', REPORT, INVENTORY)
    baseline = store.last_complete()
    original = store._git

    def competing_commit(*args, **kwargs):
        if args[0] == 'update-ref':
            git(vault, 'commit', '--allow-empty', '-qm', 'external writer')
        return original(*args, **kwargs)

    monkeypatch.setattr(store, '_git', competing_commit)
    with pytest.raises(ReportStoreError):
        store.publish('SCAN-2', REPORT, INVENTORY)
    assert store.last_complete() == baseline
    assert store.recover()['status'] == 'incomplete'


def test_deleted_report_id_cannot_be_reused(store, vault):
    store.publish('SCAN-1', REPORT, INVENTORY)
    path = '09 Werkzeuge/Scanner-Berichte/SCAN-1.json'
    git(vault, 'rm', '--', path)
    with pytest.raises(ReportStoreError):
        store.publish('SCAN-1', {'rule_status': 'erfüllt'}, INVENTORY)
    assert not (vault / path).exists()


def test_branch_switch_cannot_redirect_report_commit(store, vault, monkeypatch):
    old_head = git(vault, 'rev-parse', 'HEAD')
    original = store._git

    def checkout_before_update(*args, **kwargs):
        if args[0] == 'update-ref':
            git(vault, 'checkout', '-qb', 'other')
        return original(*args, **kwargs)

    monkeypatch.setattr(store, '_git', checkout_before_update)
    with pytest.raises(ReportStoreError):
        store.publish('SCAN-1', REPORT, INVENTORY)
    assert git(vault, 'rev-parse', 'HEAD') == old_head
    assert store.last_complete() is None


def test_pending_report_is_not_exposed_as_complete(store, vault, tmp_path, monkeypatch):
    original = store._git

    def crash(*args, **kwargs):
        output = original(*args, **kwargs)
        if args[0] == 'update-ref':
            raise Crash()
        return output

    monkeypatch.setattr(store, '_git', crash)
    with pytest.raises(Crash):
        store.publish('SCAN-1', REPORT, INVENTORY)
    restarted = ScannerReportStore(vault, tmp_path / 'state')
    assert restarted.get_report('SCAN-1')['complete'] is False
    assert restarted.get_report('SCAN-1')['published'] is False
    assert restarted.recover()['status'] == 'recovered'
    assert restarted.get_report('SCAN-1')['complete'] is True


def test_corrupt_marker_retains_baseline_and_blocks_new_publication(store, vault, tmp_path):
    store.publish('SCAN-1', REPORT, INVENTORY)
    baseline = store.last_complete()
    (tmp_path / 'state/scanner-pending.json').write_text('{bad')
    assert store.recover()['status'] == 'error'
    with pytest.raises(ReportStoreError):
        store.publish('SCAN-2', REPORT, INVENTORY)
    assert store.last_complete() == baseline
    assert not (vault / '09 Werkzeuge/Scanner-Berichte/SCAN-2.json').exists()


def test_pending_marker_and_temporary_index_are_private(store, tmp_path, monkeypatch):
    original = store._git
    modes = []

    def crash(*args, **kwargs):
        if args[0] == 'update-ref':
            modes.extend(path.stat().st_mode & 0o777 for path in (tmp_path / 'state').iterdir()
                         if path.is_file())
            raise Crash()
        return original(*args, **kwargs)

    monkeypatch.setattr(store, '_git', crash)
    with pytest.raises(Crash):
        store.publish('SCAN-1', REPORT, INVENTORY)
    assert modes and all(mode == 0o600 for mode in modes)
    marker = json.loads((tmp_path / 'state/scanner-pending.json').read_text())
    assert marker['version'] == 1
    assert marker['payload']['scan_id'] == 'SCAN-1'
    assert marker['payload']['old_head'] != marker['payload']['commit']


def test_inventory_is_frozen_for_the_transaction(store, monkeypatch):
    inventory = {'files': [dict(INVENTORY['files'][0])], 'issues': []}
    original = store._git

    def mutate_input(*args, **kwargs):
        if args[0] == 'update-ref':
            inventory['files'].clear()
        return original(*args, **kwargs)

    monkeypatch.setattr(store, '_git', mutate_input)
    store.publish('SCAN-1', REPORT, inventory)
    assert store.last_complete()['inventory'] == INVENTORY


@pytest.mark.parametrize('copy_name', ['scanner-state.json', 'scanner-last-good.json'])
def test_state_copy_crash_is_recoverable(store, vault, tmp_path, monkeypatch, copy_name):
    original = store._save

    def crash_after_backup(name, payload):
        original(name, payload)
        if name == copy_name:
            raise Crash()

    monkeypatch.setattr(store, '_save', crash_after_backup)
    with pytest.raises(Crash):
        store.publish('SCAN-1', REPORT, INVENTORY)
    restarted = ScannerReportStore(vault, tmp_path / 'state')
    assert restarted.recover()['status'] == 'recovered'
    assert restarted.last_complete()['scan_id'] == 'SCAN-1'
    assert restarted.get_report('SCAN-1')['published'] is True


def test_guessed_git_identity_is_not_sufficient(store, vault):
    store.publish('SCAN-1', REPORT, INVENTORY)
    baseline = store.last_complete()
    git(vault, 'config', '--unset', 'user.name')
    git(vault, 'config', '--unset', 'user.email')
    git(vault, 'config', 'user.useConfigOnly', 'false')
    with pytest.raises(ReportStoreError):
        store.publish('SCAN-2', REPORT, INVENTORY)
    assert store.last_complete() == baseline


@pytest.mark.parametrize('concurrent_checkout', [False, True])
def test_detached_start_cannot_publish_or_overwrite_checkout(store, vault, tmp_path,
                                                           monkeypatch, concurrent_checkout):
    store.publish('SCAN-1', REPORT, INVENTORY)
    baseline = store.last_complete()
    old_head = git(vault, 'rev-parse', 'HEAD')
    git(vault, 'branch', 'selected')
    git(vault, 'checkout', '--detach', '-q')
    (vault / 'unrelated.md').write_text('foreign staged\n')
    git(vault, 'add', 'unrelated.md')
    staged = git(vault, 'ls-files', '--stage', '-z')
    (vault / 'unrelated.md').write_text('foreign unstaged\n')
    original = store._git

    def checkout_after_detached_observation(*args, **kwargs):
        result = original(*args, **kwargs)
        if concurrent_checkout and args[0] == 'symbolic-ref':
            git(vault, 'checkout', '-q', 'selected')
        return result

    monkeypatch.setattr(store, '_git', checkout_after_detached_observation)
    with pytest.raises(ReportStoreError):
        store.publish('SCAN-2', REPORT, INVENTORY)
    assert git(vault, 'rev-parse', 'HEAD') == old_head
    if concurrent_checkout:
        assert git(vault, 'symbolic-ref', 'HEAD').strip() == b'refs/heads/selected'
    assert git(vault, 'ls-files', '--stage', '-z') == staged
    assert (vault / 'unrelated.md').read_text() == 'foreign unstaged\n'
    assert store.last_complete() == baseline
    assert not (vault / '09 Werkzeuge/Scanner-Berichte/SCAN-2.json').exists()
    assert not (tmp_path / 'state/scanner-pending.json').exists()
