"""Mutation-boundary contracts using real files and an injected local-model stand-in."""
import hashlib
import json
import multiprocessing
import os
from pathlib import Path

import pytest

from scanner.write_guard import PlannedChange, RuleBlocked, VaultWriteGuard


def digest(content):
    return hashlib.sha256(content).hexdigest()


def passing_chat(messages, model):
    payload = json.loads(messages[-1]['content'])
    return {'model': model, 'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps({
        'findings': [{'rule_id': rule['id'], 'path': subject['path'],
                      'status': 'erfüllt', 'reason': 'Prüfung abgeschlossen.'}
                     for rule in payload['rules'] for subject in payload['subjects']]})}}


@pytest.fixture
def environment(tmp_path):
    # Resolve pytest's macOS /var alias: the production no-follow policy rejects it.
    root = tmp_path.resolve()
    vault = root / 'vault'
    vault.mkdir()
    (vault / 'AGENTS.md').write_text('Keep every note sourced.\n')
    (vault / 'note.md').write_bytes(b'old note')
    return vault, root / 'state'


def guard_for(environment, chat=passing_chat, model=lambda: 'local'):
    return VaultWriteGuard(*environment, chat=chat, model=model)


def create(path='new.md', content=b'new note'):
    return PlannedChange(path, 'create', None, content)


def replacement(content=b'corrected note', path='note.md', before=b'old note'):
    return PlannedChange(path, 'replace', digest(before), content)


def blocked(guard, changes, approval=None):
    with pytest.raises(RuleBlocked) as error:
        with guard.authorize(changes, approval):
            pytest.fail('mutation started despite failed authorization')
    assert error.value.reason and str(error.value) == error.value.reason


def test_safe_create_allows_actual_mutation(environment):
    vault, _ = environment
    with guard_for(environment).authorize([create()], None):
        (vault / 'new.md').write_bytes(b'new note')
    assert (vault / 'new.md').read_bytes() == b'new note'


@pytest.mark.parametrize('path', ['../escape.md', '/tmp/escape.md', 'a/../escape.md',
                                 'a//b.md', './note.md', 'a\\b.md', 'a\x00.md',
                                 '.git/config', '.GIT/new.md', '09 werkzeuge/scanner-berichte/x.json', 'a/_index/x.md', '__pycache__/x.md',
                                 'note.pyc', '.DS_Store', '09 Werkzeuge/Scanner-Berichte/x.json'])
def test_unsafe_or_reserved_destination_never_enters_body(environment, path):
    blocked(guard_for(environment), [create(path)])


@pytest.mark.parametrize('kind', ['symlink-file', 'symlink-directory', 'fifo', 'directory'])
def test_nonregular_destinations_are_blocked(environment, kind):
    vault, state = environment
    external = state.parent / 'outside.md'
    external.write_bytes(b'outside')
    destination = vault / 'target.md'
    if kind == 'symlink-file':
        destination.symlink_to(external)
    elif kind == 'symlink-directory':
        destination.symlink_to(state.parent, target_is_directory=True)
    elif kind == 'fifo':
        os.mkfifo(destination)
    else:
        destination.mkdir()
    blocked(guard_for(environment), [create('target.md')], 'approved')
    assert external.read_bytes() == b'outside'


def test_new_path_may_have_missing_parent_directories(environment):
    vault, _ = environment
    with guard_for(environment).authorize([create('new/folder/note.md')], None):
        (vault / 'new/folder').mkdir(parents=True)
        (vault / 'new/folder/note.md').write_bytes(b'new note')
    assert (vault / 'new/folder/note.md').exists()


@pytest.mark.parametrize('change', [create('note.md'), replacement(),
                                   PlannedChange('note.md', 'delete', digest(b'old note'), None)])
def test_overwrite_or_delete_requires_explicit_approval(environment, change):
    blocked(guard_for(environment), [change])


def test_approved_replace_and_delete_allow_mutation(environment):
    vault, _ = environment
    with guard_for(environment).authorize([replacement()], 'RUN-1'):
        (vault / 'note.md').write_bytes(b'corrected note')
    with guard_for(environment).authorize([
        PlannedChange('note.md', 'delete', digest(b'corrected note'), None)], 'RUN-2'):
        (vault / 'note.md').unlink()
    assert not (vault / 'note.md').exists()


@pytest.mark.parametrize('changes', [[], [create(), create()],
    [PlannedChange('note.md', 'replace', '0' * 64, b'new')],
    [PlannedChange('missing.md', 'replace', digest(b'old note'), b'new')],
    [PlannedChange('new.md', 'create', digest(b'old note'), b'new')],
    [PlannedChange('note.md', 'delete', digest(b'old note'), b'new')],
    [PlannedChange('new.md', 'move', None, b'new')],
    [PlannedChange('new.md', 'create', None, None)],
    [create('a.md'), create('a.md/b.md')]])
def test_malformed_or_stale_change_sets_fail_closed(environment, changes):
    blocked(guard_for(environment), changes, 'RUN-1')


@pytest.mark.parametrize('status', ['verletzt', 'unklar'])
def test_nonpassing_model_blocks_even_with_approval(environment, status):
    def chat(messages, model):
        response = passing_chat(messages, model)
        rows = json.loads(response['message']['content'])
        for row in rows['findings']:
            row['status'] = status
        response['message']['content'] = json.dumps(rows)
        return response
    blocked(guard_for(environment, chat), [create()], 'RUN-1')


@pytest.mark.parametrize('failure', ['missing-agents', 'empty-agents', 'missing-model',
                                     'model-exception', 'unavailable-model', 'unconfirmed-model',
                                     'binary', 'oversized', 'invalid-utf8', 'invalid-planned'])
def test_incomplete_evaluation_fails_closed_without_leaking_content(environment, failure):
    vault, _ = environment
    chat, model = passing_chat, lambda: 'local'
    changes, approval = [create()], None
    if failure == 'missing-agents':
        (vault / 'AGENTS.md').unlink()
    elif failure == 'empty-agents':
        (vault / 'AGENTS.md').write_bytes(b'')
    elif failure == 'missing-model':
        model = lambda: ''
    elif failure == 'model-exception':
        def model():
            raise RuntimeError('PRIVATE CONTENT')
    elif failure == 'unavailable-model':
        def chat(**kwargs):
            raise RuntimeError('PRIVATE CONTENT')
    elif failure == 'unconfirmed-model':
        def chat(messages, model):
            response = passing_chat(messages, model)
            del response['done']
            return response
    elif failure == 'invalid-planned':
        changes = [create(content=b'PRIVATE \xff')]
    else:
        # A touched preimage must be judged in full; it cannot be skipped.
        filename = 'attachment.bin' if failure == 'binary' else 'unreadable.md'
        preimage = b'\xff' if failure in {'invalid-utf8', 'binary'} else b'x' * 70_000
        (vault / filename).write_bytes(preimage)
        changes, approval = [replacement(b'new', filename, preimage)], 'RUN-1'
    with pytest.raises(RuleBlocked) as error:
        with guard_for(environment, chat, model).authorize(changes, approval):
            pytest.fail('incomplete check permitted write')
    assert 'PRIVATE' not in str(error.value)


def test_unchanged_unreviewable_bestand_neither_blocks_nor_reaches_model(environment):
    vault, _ = environment
    (vault / '07 Anhänge').mkdir()
    (vault / '07 Anhänge/scan.pdf').write_bytes(b'%PDF-1.7 PRIVATE')
    (vault / '07 Anhänge/.gitkeep').write_bytes(b'')
    (vault / 'large.md').write_bytes(b'PRIVATE ' * 10_000)
    (vault / 'latin1.md').write_bytes(b'PRIVATE \xff')
    payloads = []
    def chat(messages, model):
        payloads.append(json.loads(messages[-1]['content']))
        return passing_chat(messages, model)
    with guard_for(environment, chat).authorize([create()], None):
        (vault / 'new.md').write_bytes(b'new note')
    assert [[s['path'] for s in p['subjects']] for p in payloads] == [['new.md']]
    assert 'PRIVATE' not in json.dumps(payloads) and 'old note' not in json.dumps(payloads)


@pytest.mark.parametrize('target', ['AGENTS.md', 'note.md', 'new.md', 'unrelated.md'])
def test_input_changes_during_model_call_block_under_lock(environment, target):
    vault, _ = environment
    changed = False
    def chat(messages, model):
        nonlocal changed
        if not changed:
            (vault / target).write_bytes(b'external change')
            changed = True
        return passing_chat(messages, model)
    blocked(guard_for(environment, chat), [create()], 'RUN-1')


def corrective_chat(messages, model):
    response = passing_chat(messages, model)
    payload = json.loads(messages[-1]['content'])
    rows = json.loads(response['message']['content'])
    for row in rows['findings']:
        subject = next(s for s in payload['subjects'] if s['path'] == row['path'])
        if subject['operation'] == 'Bestandsprüfung' and subject['content'] == 'old note':
            row['status'] = 'verletzt'
        elif subject['operation'] != 'Bestandsprüfung':
            after = json.loads(subject['content'])['after']
            if after == 'still invalid':
                row['status'] = 'verletzt'
    response['message']['content'] = json.dumps(rows)
    return response


def test_explicit_correction_can_remove_existing_violation(environment):
    with guard_for(environment, corrective_chat).authorize([replacement()], 'CORRECTION-1'):
        pass


@pytest.mark.parametrize('changes,approval', [([replacement()], None),
    ([replacement(b'still invalid')], 'CORRECTION-1')])
def test_existing_violation_cannot_be_bypassed(environment, changes, approval):
    blocked(guard_for(environment, corrective_chat), changes, approval)


@pytest.mark.parametrize('rule_to_reject', ['Keep every note sourced.\n', 'New rules.\n'])
def test_agents_edit_must_pass_old_and_proposed_rules(environment, rule_to_reject):
    def chat(messages, model):
        response = passing_chat(messages, model)
        payload = json.loads(messages[-1]['content'])
        if payload['agents'] == rule_to_reject and any(s['operation'] == 'replace' for s in payload['subjects']):
            response['message']['content'] = json.dumps({'findings': [
                {**row, 'status': 'verletzt'} for row in json.loads(response['message']['content'])['findings']]})
        return response
    blocked(guard_for(environment, chat), [replacement(b'New rules.\n', 'AGENTS.md',
             b'Keep every note sourced.\n')], 'RULES-1')


def test_agents_edit_judges_only_the_change_against_old_and_new_rules(environment):
    # Re-checking the unchanged Bestand under new rules is the next scan's job.
    payloads = []
    def chat(messages, model):
        payloads.append(json.loads(messages[-1]['content']))
        return passing_chat(messages, model)
    with guard_for(environment, chat).authorize([replacement(b'New rules.\n', 'AGENTS.md',
            b'Keep every note sourced.\n')], 'RULES-1'):
        pass
    assert [p['agents'] for p in payloads] == ['Keep every note sourced.\n', 'New rules.\n']
    assert all([s['path'] for s in p['subjects']] == ['AGENTS.md'] for p in payloads)


def test_deleting_rule_source_is_blocked(environment):
    blocked(guard_for(environment), [PlannedChange('AGENTS.md', 'delete',
            digest(b'Keep every note sourced.\n'), None)], 'RULES-1')


def _writer(vault, state, entered, release, evaluated, errors):
    def chat(messages, model):
        evaluated.set()
        return passing_chat(messages, model)
    try:
        with VaultWriteGuard(Path(vault), Path(state), chat, lambda: 'local').authorize([create()], None):
            entered.set()
            if not release.wait(10):
                raise RuntimeError('test release timeout')
    except BaseException as error:
        errors.put(type(error).__name__)


def test_process_lock_is_held_through_body_but_not_model_evaluation(environment):
    context = multiprocessing.get_context('spawn')
    first_entered, second_entered = context.Event(), context.Event()
    first_release, second_release = context.Event(), context.Event()
    first_evaluated, second_evaluated = context.Event(), context.Event()
    errors = context.Queue()
    args = tuple(map(str, environment))
    first = context.Process(target=_writer, args=(*args, first_entered, first_release, first_evaluated, errors))
    second = context.Process(target=_writer, args=(*args, second_entered, second_release, second_evaluated, errors))
    first.start()
    try:
        assert first_entered.wait(10)
        second.start()
        assert second_evaluated.wait(10), 'AI evaluation should run outside mutation lock'
        assert not second_entered.wait(.3), 'second process entered while first owns lock'
        first_release.set()
        assert second_entered.wait(10)
    finally:
        first_release.set()
        second_release.set()
        first.join(10)
        if second.pid:
            second.join(10)
        for process in (first, second):
            if process.pid and process.is_alive():
                process.terminate()
                process.join()
    assert first.exitcode == second.exitcode == 0
    assert errors.empty()


def test_body_exception_propagates_and_releases_lock(environment):
    guard = guard_for(environment)
    with pytest.raises(LookupError, match='body error'):
        with guard.authorize([create()], None):
            raise LookupError('body error')
    with guard.authorize([create()], None):
        pass


@pytest.mark.parametrize('paths', [('New.md', 'new.md'), ('café.md', 'cafe\u0301.md'),
                                  ('Folder.md', 'folder.md/note.md')])
def test_portable_filename_collisions_are_blocked_before_mutation(environment, paths):
    blocked(guard_for(environment), [create(path) for path in paths], 'RUN-1')


@pytest.mark.parametrize('status', ['verletzt', 'unklar'])
def test_approval_never_overrides_new_postchange_findings(environment, status):
    def chat(messages, model):
        response = passing_chat(messages, model)
        payload = json.loads(messages[-1]['content'])
        if any(subject['operation'] == 'create' for subject in payload['subjects']):
            rows = json.loads(response['message']['content'])
            rows['findings'][-1]['status'] = status
            response['message']['content'] = json.dumps(rows)
        return response
    blocked(guard_for(environment, chat), [create()], 'APPROVED-1')


def test_correction_cannot_add_a_new_violation(environment):
    def chat(messages, model):
        response = corrective_chat(messages, model)
        payload = json.loads(messages[-1]['content'])
        if any(subject['operation'] == 'create' for subject in payload['subjects']):
            rows = json.loads(response['message']['content'])
            for row in rows['findings']:
                if row['path'] == 'new.md':
                    row['status'] = 'verletzt'
            response['message']['content'] = json.dumps(rows)
        return response
    blocked(guard_for(environment, chat), [replacement(), create()], 'CORRECTION-1')


def test_hardlinked_preimage_is_not_writable(environment):
    vault, state = environment
    os.link(vault / 'note.md', state.parent / 'outside.md')
    blocked(guard_for(environment), [replacement()], 'RUN-1')
    assert (state.parent / 'outside.md').read_bytes() == b'old note'


def test_state_inside_vault_is_rejected(environment):
    vault, _ = environment
    blocked(guard_for((vault, vault / '_index/state')), [create()])


def test_symlink_lock_file_is_rejected(environment):
    vault, state = environment
    state.mkdir()
    outside = state.parent / 'outside'
    outside.write_bytes(b'private state')
    (state / 'vault-write.lock').symlink_to(outside)
    blocked(guard_for(environment), [create()])
    assert outside.read_bytes() == b'private state'


def test_same_content_replacement_during_ai_still_invalidates_snapshot(environment):
    vault, _ = environment
    replaced = False
    def chat(messages, model):
        nonlocal replaced
        if not replaced:
            source = vault / 'note.md'
            staging = vault / 'staging.md'
            staging.write_bytes(source.read_bytes())
            staging.replace(source)
            replaced = True
        return passing_chat(messages, model)
    blocked(guard_for(environment, chat), [create()])


def test_guard_preserves_connector_budget_and_blocks_unprocessable_context(environment):
    class SmallContext:
        config = {'context': 512, 'num_predict': 128}

        def chat(self, messages, model):
            pytest.fail('model called with context beyond its budget')

    blocked(guard_for(environment, SmallContext().chat), [create()])


def test_successful_agents_edit_reaches_mutation(environment):
    vault, _ = environment
    with guard_for(environment).authorize([replacement(b'New rules.\n', 'AGENTS.md',
            b'Keep every note sourced.\n')], 'RULES-1'):
        (vault / 'AGENTS.md').write_bytes(b'New rules.\n')
    assert (vault / 'AGENTS.md').read_bytes() == b'New rules.\n'
