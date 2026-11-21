// Controller logic test (no browser): node --test tests/actions.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';

const loc = { hash: '', replace(h) { this.hash = h; } };
globalThis.location = loc;
const { createStore } = await import('../mailweb/web/static/js/store.js');
const { createActions } = await import('../mailweb/web/static/js/actions.js');
const { parseHash } = await import('../mailweb/web/static/js/router.js');

const idle = { status: 'idle', data: null, error: null };
function setup(accounts) {
  const calls = [];
  const api = {
    accounts: async () => ({ accounts }),
    folders: async ({ account }) => { calls.push(['folders', account]); return { folders: [{ name: 'Sent', unseen: 0 }, { name: 'INBOX', unseen: 1 }] }; },
    messages: async (r) => { calls.push(['messages', r.account, r.folder]); return { items: [{ uid: 1, subject: `from ${r.account}` }], total: 1, page: 1, pages: 1, page_size: 50, query: '' }; },
    message: async (r) => ({ uid: r.uid, attachments: [], remote_images_blocked: true }),
    addAccount: async (d) => ({ account: { id: 'new1', name: d.name || 'n', host: d.host, user: d.user } }),
    removeAccount: async () => ({}),
    updateAccount: async (id, changes) => ({ account: { id, name: (changes.name ?? '').trim() || 'default@host', host: 'h', user: 'u' }, reconnected: changes.port === 9999 }),
    cancel: async () => ({ cancelled: true }),
    logout: async () => ({}),
  };
  const store = createStore({ authenticated: false, accounts: [], folders: [], foldersError: null,
    route: parseHash(''), list: idle, message: idle, layout: 'right', loginNotice: '',
    panes: { sidebar: 240, listWidth: 480, listHeight: 320 }, booting: true, foldersLoading: false, sidebarCollapsed: false });
  const env = { reloads: 0, scrubDom() {}, storages: () => [], clearUrl() {}, reload() { this.reloads += 1; } };
  const actions = createActions(store, api, env);
  // emulate the browser: after navigate(), the hashchange handler runs applyRoute
  const go = async (hash) => { loc.hash = hash; await actions.applyRoute(parseHash(hash)); };
  return { store, actions, calls, go, env };
}
const A = { id: 'a1', name: 'Alpha' }, B = { id: 'b2', name: 'Beta' };

test('start picks first account and its INBOX', async () => {
  const { store, actions, go } = setup([A, B]);
  await actions.start(parseHash(''));
  assert.match(loc.hash, /^#\/a1\//);                       // redirected to first account
  await go('#/a1/');                                        // ...then to INBOX
  assert.match(loc.hash, /^#\/a1\/INBOX/);
  await go(loc.hash);
  assert.equal(store.get().list.data.items[0].subject, 'from a1');
});

test('switching account clears the old mailbox before loading the new one', async () => {
  const { store, actions, go } = setup([A, B]);
  await actions.start(parseHash('#/a1/INBOX?uid=1'));
  assert.equal(store.get().message.status, 'ready');
  const seen = [];
  store.select((s) => [s.folders.length, s.list.status, s.message.status], (v) => seen.push(v), (a, b) => a.join() === b.join());
  await go('#/b2/');
  assert.deepEqual(seen.find(([f]) => f === 0), [0, 'idle', 'idle']);   // cleared state was observable
  await go(loc.hash);
  assert.equal(store.get().route.account, 'b2');
  assert.equal(store.get().list.data.items[0].subject, 'from b2');
  assert.equal(store.get().message.status, 'idle');
});

test('adding an account navigates to it; removing one erases it and reloads the page', async () => {
  const { store, actions, env } = setup([A]);
  await actions.start(parseHash('#/a1/INBOX'));
  await actions.addAccount({ host: 'h', user: 'u' });
  assert.equal(store.get().accounts.length, 2);
  assert.match(loc.hash, /^#\/new1\//);
  await actions.applyRoute(parseHash(loc.hash));
  await actions.removeAccount('new1');
  assert.deepEqual(store.get().accounts.map((a) => a.id), ['a1']);
  assert.equal(env.reloads, 1);                       // a fresh page picks the remaining account
});

test('no accounts: mailbox empty, no API calls', async () => {
  const { store, actions, calls } = setup([]);
  await actions.start(parseHash(''));
  assert.deepEqual(calls, []);
  assert.equal(store.get().folders.length, 0);
});

test('images are blocked until allowImages', async () => {
  const { store, actions } = setup([A]);
  await actions.start(parseHash('#/a1/INBOX?uid=1'));
  assert.equal(store.get().message.imagesAllowed, false);
  actions.allowImages();
  assert.equal(store.get().message.imagesAllowed, true);
});

test('session timer signs out with a notice when the session runs out', async () => {
  const { store, actions } = setup([A]);
  await actions.start(parseHash('#/a1/INBOX'), 0.05);          // 50 ms session
  assert.equal(store.get().authenticated, true);
  await new Promise((resolve) => setTimeout(resolve, 120));
  assert.equal(store.get().authenticated, false);
  assert.match(store.get().loginNotice, /session has ended/i);
  assert.equal(store.get().accounts.length, 0);
});

test('manual sign out shows no notice; signing in again clears it', async () => {
  const { store, actions } = setup([A]);
  await actions.start(parseHash('#/a1/INBOX'));
  await actions.logout();
  assert.equal(store.get().loginNotice, '');
  actions.expire();
  assert.notEqual(store.get().loginNotice, '');
  await actions.start(parseHash('#/a1/INBOX'));
  assert.equal(store.get().loginNotice, '');
});

test('pane sizes can be set and reset', async () => {
  const { store, actions } = setup([A]);
  actions.setPane('sidebar', 300);
  assert.equal(store.get().panes.sidebar, 300);
  actions.resetPane('sidebar');
  assert.equal(store.get().panes.sidebar, 240);
});

test('loading flags: booting ends at sign-in; folders report loading until they arrive', async () => {
  const { store, actions } = setup([A]);
  assert.equal(store.get().booting, true);
  const seen = [];
  store.select((s) => s.foldersLoading, (v) => seen.push(v), Object.is);
  await actions.start(parseHash('#/a1/INBOX'));
  assert.equal(store.get().booting, false);
  assert.ok(seen.includes(true), 'folders were reported as loading');
  assert.equal(store.get().foldersLoading, false);
});

test('no accounts: nothing is reported as loading', async () => {
  const { store, actions } = setup([]);
  await actions.start(parseHash(''));
  assert.equal(store.get().foldersLoading, false);
});

test('hamburger toggles the folder list collapsed/expanded', () => {
  const { store, actions } = setup([A]);
  actions.toggleSidebar();
  assert.equal(store.get().sidebarCollapsed, true);
  actions.toggleSidebar();
  assert.equal(store.get().sidebarCollapsed, false);
});

test('the message list loads without waiting for the folder list', async () => {
  const { store } = setup([A]);
  let releaseFolders;
  const folderGate = new Promise((resolve) => { releaseFolders = resolve; });
  const calls = [];
  const gatedApi = {
    accounts: async () => ({ accounts: [A] }),
    folders: async () => { calls.push('folders:start'); await folderGate; calls.push('folders:done'); return { folders: [{ name: 'INBOX', unseen: 0 }] }; },
    messages: async () => { calls.push('messages'); return { items: [], total: 0, page: 1, pages: 1, page_size: 50, query: '' }; },
    message: async () => ({}),
  };
  const s2 = createStore({ ...store.get(), authenticated: true, accounts: [A], route: parseHash('') });
  const a2 = createActions(s2, gatedApi);
  await a2.applyRoute(parseHash('#/a1/'));           // folder unknown: INBOX is assumed immediately
  assert.match(loc.hash, /^#\/a1\/INBOX/);
  const pending = a2.applyRoute(parseHash(loc.hash));
  await new Promise((r) => setTimeout(r, 20));
  assert.ok(calls.includes('messages'), 'messages were requested');
  assert.ok(!calls.includes('folders:done'), 'while the folder list was still loading');
  releaseFolders();
  await pending;
});

test('an assumed INBOX that does not exist is replaced by a real folder', async () => {
  const { store } = setup([A]);
  const api2 = {
    accounts: async () => ({ accounts: [A] }),
    folders: async () => ({ folders: [{ name: 'Archive', unseen: 0 }, { name: 'Sent', unseen: 0 }] }),
    messages: async () => ({ items: [], total: 0, page: 1, pages: 1, page_size: 50, query: '' }),
    message: async () => ({}),
  };
  const s2 = createStore({ ...store.get(), authenticated: true, accounts: [A], route: parseHash('') });
  const a2 = createActions(s2, api2);
  await a2.applyRoute(parseHash('#/a1/'));
  assert.match(loc.hash, /^#\/a1\/INBOX/);          // guessed first
  await a2.applyRoute(parseHash(loc.hash));
  await new Promise((r) => setTimeout(r, 20));
  assert.match(loc.hash, /^#\/a1\/Archive/);        // corrected once the folder list arrived
});

test('the third layout can be selected, and closing a message clears the route uid', async () => {
  const { store, actions } = setup([A]);
  await actions.start(parseHash('#/a1/INBOX?uid=1'));
  actions.setLayout('full');
  assert.equal(store.get().layout, 'full');
  actions.closeMessage();
  assert.equal(parseHash(loc.hash).uid, null);
});

test('editing only the name updates that account in the store and keeps the mailbox', async () => {
  const { store, actions, calls } = setup([A, B]);
  await actions.start(parseHash('#/a1/INBOX'));
  const loadsBefore = calls.length;
  await actions.updateAccount('b2', { name: '  Family  ' });
  const names = Object.fromEntries(store.get().accounts.map((a) => [a.id, a.name]));
  assert.deepEqual(names, { a1: 'Alpha', b2: 'Family' });
  assert.equal(calls.length, loadsBefore, 'nothing was reloaded');
});

