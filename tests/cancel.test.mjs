// Switching mailbox / clearing a search must stop in-flight work at once (browser and server), and editing
// a connection must reload the mailbox. Run: node --test tests/cancel.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';

const loc = { hash: '', replace(h) { this.hash = h; } };
globalThis.location = loc;
const { createStore } = await import('../mailweb/web/static/js/store.js');
const { createActions } = await import('../mailweb/web/static/js/actions.js');
const { parseHash } = await import('../mailweb/web/static/js/router.js');

const A = { id: 'a1', name: 'Alpha' }, B = { id: 'b2', name: 'Beta' };
const idle = { status: 'idle', data: null, error: null };
const abortError = () => Object.assign(new Error('The operation was aborted.'), { name: 'AbortError' });

// A fake API whose slow calls stay pending until their AbortSignal fires (like fetch does).
function setup({ hang = [], cancelDelay = 0 } = {}) {
  const log = [];
  const pending = (label, signal) => new Promise((_, reject) => {
    log.push(`${label}:start`);
    signal.addEventListener('abort', () => { log.push(`${label}:aborted`); reject(abortError()); });
  });
  const api = {
    accounts: async () => ({ accounts: [A, B] }),
    folders: ({ account, signal }) => (hang.includes(`folders:${account}`) ? pending(`folders:${account}`, signal)
      : (log.push(`folders:${account}:done`), Promise.resolve({ folders: [{ name: 'INBOX', unseen: 0 }] }))),
    messages: ({ account, q, signal }) => (hang.includes(`messages:${account}${q ? ':q' : ''}`) ? pending(`messages:${account}${q ? ':q' : ''}`, signal)
      : (log.push(`messages:${account}:${q || 'all'}:done`), Promise.resolve({ items: [], total: 0, page: 1, pages: 1, page_size: 50, query: q || '' }))),
    message: ({ signal }) => pending('message', signal),
    cancel: async (account) => { log.push(`cancel:${account}:sent`); await new Promise((r) => setTimeout(r, cancelDelay)); log.push(`cancel:${account}:confirmed`); return {}; },
    updateAccount: async (id, changes) => ({ account: { id, name: 'Edited', host: changes.host ?? 'h', user: 'u' }, reconnected: 'host' in changes }),
  };
  const store = createStore({ booting: false, authenticated: true, loginNotice: '', accounts: [A, B], folders: [], foldersError: null,
    foldersLoading: false, route: parseHash(''), list: idle, message: idle, layout: 'right', sidebarCollapsed: false,
    panes: { sidebar: 240, listWidth: 480, listHeight: 320 } });
  const env = { scrubDom() {}, storages: () => [], clearUrl() {}, reload() {} };
  const actions = createActions(store, api, env);
  const go = async (hash) => { loc.hash = hash; await actions.applyRoute(parseHash(hash)); };
  return { store, actions, log, go };
}

const tick = (ms = 10) => new Promise((r) => setTimeout(r, ms));

test('switching mailbox aborts everything in flight for the old one and cancels it on the server', async () => {
  const { store, log, go } = setup({ hang: ['folders:a1', 'messages:a1'] });
  const loading = go('#/a1/INBOX?uid=7');                              // folders, list and message all hang
  await tick();
  assert.deepEqual(['folders:a1:start', 'messages:a1:start', 'message:start'].filter((e) => log.includes(e)).length, 3);
  assert.equal(store.get().list.status, 'loading');

  await go('#/b2/');                                                     // switch to the other mailbox
  await loading;
  for (const entry of ['folders:a1:aborted', 'messages:a1:aborted', 'message:aborted']) assert.ok(log.includes(entry), entry);
  assert.ok(log.includes('cancel:a1:sent'), 'the server was told to stop the old account\'s work');
  assert.ok(!log.includes('cancel:b2:sent'), 'and only the old account');
  const state = store.get();
  assert.equal(state.list.status === 'error' || state.foldersError !== null, false, 'an abort is not an error');
  assert.equal(state.message.status, 'idle');
  assert.equal(state.route.account, 'b2');
});

test('an aborted load can never overwrite the new mailbox with old data', async () => {
  const { store, go } = setup({ hang: ['messages:a1'] });
  go('#/a1/INBOX');
  await tick();
  await go('#/b2/INBOX');
  await go('#/b2/INBOX');
  await tick();
  assert.equal(store.get().route.account, 'b2');
  assert.equal(store.get().list.status, 'ready');
});

test('the search X aborts the running search, waits for the server to confirm, then reloads the unfiltered list', async () => {
  const { store, actions, log, go } = setup({ hang: ['messages:a1:q'], cancelDelay: 30 });
  await go('#/a1/INBOX');
  await tick();
  const searching = go('#/a1/INBOX?q=invoice');
  await tick();
  assert.equal(store.get().list.status, 'loading');

  const clearing = actions.clearSearch();
  assert.ok(log.includes('messages:a1:q:aborted'), 'the browser request is aborted synchronously');
  assert.ok(log.includes('cancel:a1:sent'));
  assert.match(loc.hash, /q=invoice/, 'still waiting for the server to confirm the cancel');
  await clearing;
  assert.ok(log.includes('cancel:a1:confirmed'), 'navigation only happened after the server confirmed');
  assert.doesNotMatch(loc.hash, /q=/);
  await searching;
  await actions.applyRoute(parseHash(loc.hash));
  assert.equal(store.get().list.status, 'ready');
  assert.equal(store.get().list.data.query, '');
});

test('the X does nothing when no search was submitted', async () => {
  const { actions, log, go } = setup();
  await go('#/a1/INBOX');
  const before = log.length;
  await actions.clearSearch();
  assert.equal(log.length, before);
});

test('editing connection settings drops the old mailbox and loads it again, without cancelling the new connection', async () => {
  const { store, actions, log, go } = setup();
  await go('#/a1/INBOX');
  await tick();
  const loadsBefore = log.filter((e) => e === 'folders:a1:done').length;
  await actions.updateAccount('a1', { host: 'new.example.com', name: 'x' });
  await tick(20);
  assert.equal(log.filter((e) => e === 'folders:a1:done').length, loadsBefore + 1, 'folders were loaded again');
  assert.ok(!log.includes('cancel:a1:sent'), 'the server already dropped the old connection itself');
  assert.equal(store.get().accounts.find((a) => a.id === 'a1').name, 'Edited');
});

test('signing out stops loads in flight', async () => {
  const { store, actions, log, go } = setup({ hang: ['messages:a1'] });
  go('#/a1/INBOX');
  await tick();
  actions.expire('');
  assert.ok(log.includes('messages:a1:aborted'));
  assert.equal(store.get().authenticated, false);
});
