"""Exercise scanner rendering and polling in Node; real scanner supplies API shapes."""
import json
from pathlib import Path
import subprocess
import time

import pytest

import dashboard_api
from loop.watcher_loop_orchestrator import WatcherLoopOrchestrator
from loop.watcher_loop_runtime import WatcherLoopRuntime
from scanner.service import VaultScanner

FRONTEND = Path(__file__).resolve().parents[1] / 'frontend'


@pytest.fixture
def scanner_context(tmp_path, monkeypatch):
    vault = tmp_path / 'vault'
    vault.mkdir()
    (vault / 'AGENTS.md').write_text('Keep notes orderly.\n')
    (vault / 'note.md').write_text('Useful note.\n')
    for args in [('init', '-b', 'main'), ('config', 'user.name', 'Scanner Test'),
                 ('config', 'user.email', 'scanner@example.test'), ('add', '.'),
                 ('commit', '-m', 'initial')]:
        subprocess.run(['git', '-C', str(vault), *args], check=True, capture_output=True)

    def chat(*, messages, model):
        request = json.loads(messages[-1]['content'])
        return {'done': True, 'done_reason': 'stop', 'model': model, 'message': {'content': json.dumps({
            'findings': [{'rule_id': r['id'], 'path': s['path'], 'status': 'erfüllt', 'reason': 'Geprüft.'}
                         for r in request['rules'] for s in request['subjects']]})}}

    monkeypatch.setenv('SECBRAIN_WATCHER_STATE_DIR', str(tmp_path / 'state'))
    service = VaultScanner(vault, tmp_path / 'state', chat, lambda: 'test-model')
    monkeypatch.setattr(dashboard_api, 'vault_scanner', lambda: service)
    orchestrator = WatcherLoopOrchestrator(WatcherLoopRuntime(), chat, str(vault))
    monkeypatch.setattr(dashboard_api, 'watcher_orchestrator', orchestrator)
    return service


def run_scan(service):
    service.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = dashboard_api.scanner_status()
        if state['state'] != 'running':
            return state
        time.sleep(.01)
    pytest.fail('Scanner timeout')


@pytest.fixture
def scanner_status(scanner_context):
    service = scanner_context
    complete = run_scan(service)
    def unavailable(**kwargs):
        raise RuntimeError('model unavailable')
    service.chat = unavailable
    incomplete = run_scan(service)
    return complete, incomplete, service.report(incomplete['last_attempt']['scan_id'])


DOM = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
class Element {
  constructor(tag='div') { this.tagName=tag; this.children=[]; this.hidden=false; this.dataset={}; this.disabled=false; this._text=''; this.attrs={}; }
  set textContent(value) { this._text=String(value); this.children=[]; }
  get textContent() { return this._text + this.children.map(c=>c.textContent).join(' '); }
  set innerHTML(value) { throw new Error('Untrusted rendering must use textContent'); }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this._text=''; this.children=items; }
  setAttribute(key,value) { this.attrs[key]=String(value); }
  removeAttribute(key) { delete this.attrs[key]; }
}
const nodes = new Map();
const document = {addEventListener() {}, getElementById(id) { if(!nodes.has(id)) nodes.set(id,new Element()); return nodes.get(id); }, createElement(tag) {return new Element(tag);} };
let timers=[], requests=[];
const context = {document, window:{}, console, AbortSignal, Date, encodeURIComponent,
  setTimeout(fn,ms) { timers.push(fn); return timers.length; }, clearTimeout() {},
  fetch: async (url, options={}) => { requests.push({url, options}); return response; }};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8').split('\nbindWorkflowControls();')[0], context);
context.updateRuntimeActivity({orchestration:{state:'idle',approval_required:false},app_write_pending:false});
const [complete, incomplete, report, runtime] = JSON.parse(process.argv[2]);
const node = id => document.getElementById(id);
'''


def js_contract(scanner_status, code):
    result = subprocess.run(['node', '-e', DOM + code, str(FRONTEND / 'app.js'),
                             json.dumps(scanner_status)], text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_scanner_menu_and_view_contract(scanner_status):
    html = (FRONTEND / 'index.html').read_text()
    assert 'data-view="scanner"' in html
    for name in ('scanner-view', 'scanner-start', 'scanner-status', 'scanner-baseline',
                 'scanner-attempt', 'scanner-progress', 'scanner-report', 'scanner-new',
                 'scanner-changed', 'scanner-removed', 'scanner-violations', 'scanner-unclear',
                 'scanner-technical'):
        assert f'id="{name}"' in html
    assert scanner_status[1]['last_attempt']['state'] == 'incomplete'
    assert scanner_status[1]['overall'] != 'erfüllt'


def test_new_incomplete_attempt_clears_previous_green_and_keeps_baseline(scanner_status):
    js_contract(scanner_status, r'''
context.renderScannerStatus(complete);
assert.equal(node('scanner-status').dataset.tone, 'success');
context.renderScannerStatus(incomplete);
assert.notEqual(node('scanner-status').dataset.tone, 'success');
assert.match(node('scanner-status').textContent, /nicht vollständig geprüft/);
assert.match(node('scanner-baseline').textContent, /\d{4}/);
assert.match(node('scanner-attempt').textContent, /nicht vollständig geprüft/);
const labels=['idle','running','complete','incomplete'].map(state=>{
 context.renderScannerStatus({...incomplete, state, last_attempt: state==='complete'?complete.last_attempt:incomplete.last_attempt});
 return node('scanner-status').textContent;
});
assert.equal(new Set(labels).size,4);
context.renderScannerStatus({...complete, overall:'verletzt'});
assert.equal(node('scanner-status').dataset.tone,'danger');
context.renderScannerStatus({...complete, overall:'unklar'});
assert.notEqual(node('scanner-status').dataset.tone,'success');
''')


def test_report_separates_changes_findings_and_treats_paths_as_text(scanner_status):
    js_contract(scanner_status, r'''
const attack='<img src=x onerror=alert(1)>';
context.renderScannerReport({...report,
 changes:[{path:attack,status:'neu'},{path:'changed.md',status:'geändert'},{path:'gone.md',status:'entfernt'}],
 technical_findings:[{path:'outside',status:'unklar',reason:'Symlink'}],
 findings:[{path:attack,status:'verletzt',rule_id:'L1',reason:attack,source:{path:'AGENTS.md',line:1}},
 {path:'unknown.md',status:'unklar',rule_id:'L2',reason:'Modell fehlt',source:{path:'AGENTS.md',line:2}}]});
assert.match(node('scanner-new').textContent, /<img/);
assert.equal(node('scanner-changed').textContent.includes('changed.md'),true);
assert.equal(node('scanner-removed').textContent.includes('gone.md'),true);
assert.match(node('scanner-violations').textContent, /AGENTS.md:1/);
assert.match(node('scanner-violations').textContent, /<img/);
assert.equal(node('scanner-unclear').textContent.includes('unknown.md'),true);
assert.equal(node('scanner-technical').textContent.includes('Symlink'),true);
''')


def test_polling_is_bounded_stops_on_exit_and_errors_clear_green(scanner_status):
    js_contract(scanner_status, r'''
(async()=>{
 node('scanner-view').hidden=false;
 let calls=0;
 context.fetch=async(url)=>{ calls++; return {ok:true,json:async()=>({...incomplete,state:'running'})}; };
 await context.loadScanner();
 for(let i=0;i<200 && timers.length;i++) { const callback=timers.shift(); await callback(); }
 assert.ok(calls>1 && calls<=125, 'Polling must stop after a finite number of requests');
 assert.match(node('scanner-status').textContent,/automatische Aktualisierung pausiert/);
 await context.loadScanner();
 node('scanner-view').hidden=true;
 const before=calls;
 while(timers.length) await timers.shift()();
 assert.equal(calls,before);
 context.renderScannerStatus(complete);
 node('scanner-view').hidden=false;
 context.fetch=async()=>{throw new Error('offline');};
 await context.loadScanner();
 assert.notEqual(node('scanner-status').dataset.tone,'success');
 assert.match(node('scanner-status').textContent,/nicht verfügbar/);
})().catch(error=>{console.error(error);process.exitCode=1;});
''')


def test_pending_app_approval_removes_green_until_resolved(scanner_status):
    js_contract(scanner_status, r'''
context.renderScannerStatus(complete);
assert.equal(node('scanner-status').dataset.tone,'success');
context.updateRuntimeActivity({orchestration:{state:'awaiting_approval',approval_required:true},app_write_pending:false});
assert.notEqual(node('scanner-status').dataset.tone,'success');
assert.match(node('scanner-status').textContent,/App-Übernahme ausstehend/);
context.updateRuntimeActivity({orchestration:{state:'rejected',approval_required:false},app_write_pending:false});
assert.equal(node('scanner-status').dataset.tone,'success');
''')


def test_stale_async_response_cannot_replace_newer_incomplete_status(scanner_status):
    js_contract(scanner_status, r'''
(async()=>{
 node('scanner-view').hidden=false;
 let release;
 context.fetch=()=>new Promise(resolve=>{release=resolve;});
 const old=context.loadScanner();
 context.stopScannerPolling();
 context.renderScannerStatus(incomplete);
 release({ok:true,json:async()=>complete});
 await old;
 assert.notEqual(node('scanner-status').dataset.tone,'success');
 assert.match(node('scanner-status').textContent,/nicht vollständig geprüft/);
})().catch(error=>{console.error(error);process.exitCode=1;});
''')


def test_unavailable_app_workflow_status_cannot_leave_green(scanner_status):
    js_contract(scanner_status, r'''
context.renderScannerStatus(complete);
assert.equal(node('scanner-status').dataset.tone,'success');
context.scannerWorkflowUnavailable();
assert.notEqual(node('scanner-status').dataset.tone,'success');
assert.match(node('scanner-status').textContent,/Übernahmestatus nicht verfügbar/);
''')


def test_persisted_pending_with_restarted_idle_orchestrator_suppresses_scan_green(scanner_context, monkeypatch):
    service = scanner_context
    successful = run_scan(service)
    assert successful['overall'] == 'erfüllt'
    dashboard_api.watcher_orchestrator.validation.begin('INTERRUPTED-APPLY', 'inbox')
    restarted = WatcherLoopOrchestrator(WatcherLoopRuntime(), service.chat, str(service.vault))
    assert restarted.status()['state'] == 'idle'
    assert restarted.validation.status()['pending'] is True
    monkeypatch.setattr(dashboard_api, 'watcher_orchestrator', restarted)
    reloaded = VaultScanner(service.vault, service.store.state_dir, service.chat, service.model)
    monkeypatch.setattr(dashboard_api, 'vault_scanner', lambda: reloaded)
    status = dashboard_api.scanner_status()
    assert status['last_complete']['scan_id'] == successful['last_complete']['scan_id']
    assert status['app_write_pending'] is True
    runtime = dashboard_api.watcher_status()
    assert runtime['app_write_pending'] is True
    js_contract((successful, status, reloaded.report(status['last_complete']['scan_id']), runtime), r"""
context.renderScannerStatus(complete);
assert.equal(node('scanner-status').dataset.tone,'success');
context.updateRuntimeActivity(runtime);
assert.notEqual(node('scanner-status').dataset.tone,'success');
assert.match(node('scanner-status').textContent,/App-Übernahme ausstehend/);
context.renderScannerStatus(incomplete);
assert.notEqual(node('scanner-status').dataset.tone,'success');
assert.match(node('scanner-status').textContent,/App-Übernahme ausstehend/);
""")


def test_unavailable_durable_pending_status_never_appears_green(scanner_status):
    js_contract(scanner_status, r"""
context.renderScannerStatus({...complete,app_write_pending:null});
assert.notEqual(node('scanner-status').dataset.tone,'success');
assert.match(node('scanner-status').textContent,/Übernahmestatus nicht verfügbar/);
const legacy={...complete}; delete legacy.app_write_pending;
context.renderScannerStatus(legacy);
assert.notEqual(node('scanner-status').dataset.tone,'success');
""")


def test_empty_change_list_does_not_claim_the_scan_is_first(scanner_status):
    js_contract(scanner_status, r"""
context.renderScannerReport({...report,complete:true,changes:[]});
assert.equal(node('scanner-report-summary').textContent.includes('Erster Scan'),false);
assert.match(node('scanner-report-summary').textContent,/Keine Dateiänderungen/);
""")


def test_durable_pending_read_failure_returns_unknown(scanner_context, monkeypatch):
    successful = run_scan(scanner_context)
    def unreadable():
        raise OSError('state unavailable')
    monkeypatch.setattr(dashboard_api.watcher_orchestrator.validation, 'status', unreadable)
    status = dashboard_api.scanner_status()
    assert status['last_complete'] == successful['last_complete']
    assert status['app_write_pending'] is None
    js_contract((status, status, {}), r"""
context.renderScannerStatus(complete);
assert.notEqual(node('scanner-status').dataset.tone,'success');
assert.match(node('scanner-status').textContent,/Übernahmestatus nicht verfügbar/);
""")
