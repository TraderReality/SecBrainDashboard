"""Exercise chat command routing in Node against the actual component."""

from pathlib import Path
import subprocess


JS = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const inputs = new Map();
const document = {
  getElementById(id) {
    if (!inputs.has(id)) inputs.set(id, {value: '', disabled: false, textContent: ''});
    return inputs.get(id);
  },
  createElement() { return {set textContent(v) { this.innerHTML = String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}; }
};
const requests = [];
const fetch = async (url, options) => {
  requests.push({url, body: JSON.parse(options.body)});
  if (url === '/api/excalidraw/generate') return {ok: true, json: async () => ({
    filename:'diagram-20261023T120000Z-abcdef123456.excalidraw',
    relative_path:'Local/Work/excalidraw-dev/<script>.excalidraw', element_count: 2,
    model:'gemma4:12b'})};
  return {ok: true, json: async () => ({message: {role:'assistant', content:'Normal answer'}})};
};
const context = {window: {}, document, fetch, console};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8').split('window.OllamaSettings.initializeChatDock();')[0], context);
const chat = context.window.OllamaSettings;
chat.config.model = 'gemma4:12b';
chat.renderFooterModelSelector = () => {};
chat.renderChatDock();
assert(document.getElementById('ollama-chat-dock').innerHTML.includes('/excalidraw'));
assert(document.getElementById('ollama-chat-dock').innerHTML.includes('Local/Work'));
chat.renderChatDock = () => {};
const input = document.getElementById('ollama-chat-input');
(async () => {
  input.value = 'Hello'; await chat.sendChat();
  assert.equal(requests[0].url, '/api/ollama/chat');
  input.value = '/excalidraw draw a flow'; await chat.sendChat();
  assert.equal(requests[1].url, '/api/excalidraw/generate');
  assert.equal(requests[1].body.prompt, 'draw a flow');
  assert.equal(requests[1].body.model, 'gemma4:12b');
  assert(chat.chatMessages.at(-1).content.includes('Local/Work/excalidraw-dev/'));
  assert(chat.chatMessages.at(-1).content.includes('gemma4:12b'));
  assert(chat.escapeHtml(chat.chatMessages.at(-1).content).includes('&lt;script&gt;'));
  const before = requests.length;
  input.value = '/excalidraw '; await chat.sendChat();
  assert.equal(requests.length, before);
  input.value = '/excalidraw draw'; await chat.sendChat();
  input.value = 'Again'; await chat.sendChat();
  assert.equal(requests.at(-1).url, '/api/ollama/chat');
  assert(!requests.at(-1).body.messages.some(m => m.diagram));
})().catch(error => { console.error(error); process.exitCode = 1; });
'''


def test_chat_command_contract():
    component = Path(__file__).resolve().parents[1] / "frontend/components/ollama-settings.js"
    result = subprocess.run(["node", "-e", JS, str(component)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
