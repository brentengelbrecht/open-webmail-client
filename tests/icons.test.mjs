// Custom account icons: geometry, storage, load/save/rollback, and erasure on removal.
import test from 'node:test';
import assert from 'node:assert/strict';

class FakeStorage {
  constructor(entries = {}) { this.map = new Map(Object.entries(entries)); this.failWrites = false; this.writes = []; }
  get length() { return this.map.size; }
  key(i) { return [...this.map.keys()][i] ?? null; }
  getItem(k) { return this.map.has(k) ? this.map.get(k) : null; }
  setItem(k, v) {
    if (this.failWrites) throw new Error('QuotaExceededError');
    this.writes.push([k, v]);
    this.map.set(k, v);
  }
  removeItem(k) { this.map.delete(k); }
}
globalThis.localStorage = new FakeStorage();
globalThis.location = { hash: '', replace() {} };

const { coverRect } = await import('../mailweb/web/static/js/util/iconImage.js');
const { savePref, loadPref, removePref } = await import('../mailweb/web/static/js/util/prefs.js');
const { scrubStorage, mask } = await import('../mailweb/web/static/js/util/scrub.js');
const { createStore } = await import('../mailweb/web/static/js/store.js');
const { createActions } = await import('../mailweb/web/static/js/actions.js');
const { parseHash } = await import('../mailweb/web/static/js/router.js');

const PNG = 'data:image/webp;base64,AAAA';
const OTHER = 'data:image/webp;base64,BBBB';
const A = { id: 'a1b2c3d4', name: 'Work', host: 'imap.example.com', user: 'jane@example.com', tls: true, tls_verify: true };
const B = { id: 'b2c3d4e5', name: 'Home', host: 'pi.local', user: 'me', tls: false, tls_verify: true };

test('coverRect takes the largest centred square', () => {
  assert.deepEqual(coverRect(200, 100), { sx: 50, sy: 0, side: 100 });
  assert.deepEqual(coverRect(100, 200), { sx: 0, sy: 50, side: 100 });
  assert.deepEqual(coverRect(64, 64), { sx: 0, sy: 0, side: 64 });
  assert.deepEqual(coverRect(101, 100), { sx: 1, sy: 0, side: 100 });
});

test('savePref reports whether the value was stored', () => {
  localStorage.failWrites = false;
  assert.equal(savePref('x', { a: 1 }), true);
  assert.deepEqual(loadPref('x', null), { a: 1 });
  removePref('x');
  assert.equal(loadPref('x', 'gone'), 'gone');
  localStorage.failWrites = true;
  assert.equal(savePref('x', 1), false);
  localStorage.failWrites = false;
});

function setup({ failServer = false, storage = new FakeStorage() } = {}) {
  globalThis.localStorage = storage;
  const calls = { update: 0 };
  const idle = { status: 'idle', data: null, error: null };
  const api = {
    accounts: async () => ({ accounts: [{ ...A }, { ...B }] }),      // copies: the app overwrites removed accounts in place
    folders: async () => ({ folders: [{ name: 'INBOX', unseen: 0 }] }),
    messages: async () => ({ items: [], total: 0, page: 1, pages: 1, page_size: 50, query: '' }),
    message: async () => ({ attachments: [] }),
    cancel: async () => ({}),
    updateAccount: async (id, changes) => { calls.update += 1; if (failServer) throw new Error('server said no'); return { account: { ...A, ...changes, id }, reconnected: false }; },
    removeAccount: async () => ({}),
  };
  const store = createStore({ booting: false, authenticated: false, loginNotice: '', accounts: [], accountIcons: {}, folders: [],
    foldersError: null, foldersLoading: false, route: parseHash(''), list: idle, message: idle, layout: 'right', sidebarCollapsed: false,
    panes: { sidebar: 240, listWidth: 480, listHeight: 320 } });
  const env = { reloads: 0, scrubDom() {}, storages: () => [storage], clearUrl() {}, reload() { this.reloads += 1; } };
  return { store, actions: createActions(store, api, env), calls, storage, env };
}

test('icons are loaded at sign-in, but only valid image data for known accounts', async () => {
  const storage = new FakeStorage({
    [`mailweb.icon.${A.id}`]: JSON.stringify(PNG),
    [`mailweb.icon.${B.id}`]: JSON.stringify('javascript:alert(1)'),          // never used as an image source
    'mailweb.icon.zzzzzzzz': JSON.stringify(OTHER),                           // an account that no longer exists
  });
  const { store, actions } = setup({ storage });
  await actions.start(parseHash(`#/${A.id}/INBOX`));
  assert.deepEqual(store.get().accountIcons, { [A.id]: PNG });
});

test('setAccountIcon stores, replaces and removes an icon, and refuses non-images or a full storage', async () => {
  const { store, actions, storage } = setup();
  await actions.start(parseHash(`#/${A.id}/INBOX`));
  actions.setAccountIcon(A.id, PNG);
  assert.equal(store.get().accountIcons[A.id], PNG);
  assert.equal(storage.getItem(`mailweb.icon.${A.id}`), JSON.stringify(PNG));
  actions.setAccountIcon(A.id, OTHER);
  assert.equal(store.get().accountIcons[A.id], OTHER);
  actions.setAccountIcon(A.id, null);
  assert.equal(store.get().accountIcons[A.id], undefined);
  assert.equal(storage.getItem(`mailweb.icon.${A.id}`), null);
  assert.throws(() => actions.setAccountIcon(A.id, 'https://evil.example/x.png'), /could not be stored/);
  storage.failWrites = true;
  assert.throws(() => actions.setAccountIcon(A.id, PNG), /storage is full or disabled/);
  assert.equal(store.get().accountIcons[A.id], undefined, 'the state does not claim an icon that was not stored');
});

test('saving the dialog applies the icon after the server accepts the change', async () => {
  const { store, actions, calls } = setup();
  await actions.start(parseHash(`#/${A.id}/INBOX`));
  await actions.updateAccount(A.id, { name: 'Work' }, { icon: PNG });
  assert.equal(calls.update, 1);
  assert.equal(store.get().accountIcons[A.id], PNG);
});

test('if the server refuses the change, the previous icon is put back', async () => {
  const storage = new FakeStorage({ [`mailweb.icon.${A.id}`]: JSON.stringify(PNG) });
  const { store, actions } = setup({ failServer: true, storage });
  await actions.start(parseHash(`#/${A.id}/INBOX`));
  await assert.rejects(actions.updateAccount(A.id, { name: 'x' }, { icon: OTHER }), /server said no/);
  assert.equal(store.get().accountIcons[A.id], PNG);
  assert.equal(storage.getItem(`mailweb.icon.${A.id}`), JSON.stringify(PNG));
});

test('an icon that cannot be stored stops the save before anything is sent to the server', async () => {
  const { actions, calls, storage } = setup();
  await actions.start(parseHash(`#/${A.id}/INBOX`));
  storage.failWrites = true;
  await assert.rejects(actions.updateAccount(A.id, { name: 'x' }, { icon: PNG }), /storage is full or disabled/);
  assert.equal(calls.update, 0);
});

test('not touching the icon leaves it alone, "use default" removes it', async () => {
  const storage = new FakeStorage({ [`mailweb.icon.${A.id}`]: JSON.stringify(PNG) });
  const { store, actions } = setup({ storage });
  await actions.start(parseHash(`#/${A.id}/INBOX`));
  await actions.updateAccount(A.id, { name: 'y' }, { icon: undefined });
  assert.equal(store.get().accountIcons[A.id], PNG);
  await actions.updateAccount(A.id, { name: 'y' }, { icon: null });
  assert.equal(store.get().accountIcons[A.id], undefined);
  assert.equal(storage.getItem(`mailweb.icon.${A.id}`), null);
});

test('removing an account overwrites and deletes its icon, and only its own', async () => {
  const storage = new FakeStorage({
    [`mailweb.icon.${A.id}`]: JSON.stringify(PNG),
    [`mailweb.icon.${B.id}`]: JSON.stringify(OTHER),
    'mailweb.layout': JSON.stringify('right'),
  });
  const { store, actions, env } = setup({ storage });
  await actions.start(parseHash(`#/${A.id}/INBOX`));
  const held = store.get().accountIcons;
  await actions.removeAccount(A.id);
  assert.equal(storage.getItem(`mailweb.icon.${A.id}`), null);
  assert.deepEqual([...storage.map.keys()].sort(), [`mailweb.icon.${B.id}`, 'mailweb.layout']);
  assert.ok(storage.writes.some(([k, v]) => k === `mailweb.icon.${A.id}` && v === mask(JSON.stringify(PNG))), 'overwritten with X first');
  assert.equal(held[A.id], mask(PNG), 'the copy held in memory was overwritten too');
  assert.deepEqual(store.get().accountIcons, { [B.id]: OTHER });
  assert.equal(env.reloads, 1);
});

test('image data of another account is never matched by an account name or host', () => {
  const storage = new FakeStorage({
    [`mailweb.icon.${A.id}`]: JSON.stringify(PNG),
    [`mailweb.icon.${B.id}`]: JSON.stringify('data:image/png;base64,xxWorkxxpi.localxx'),     // base64 that happens to contain "Work"
  });
  const removed = scrubStorage(storage, [A.id, 'Work', 'pi.local']);
  assert.equal(removed, 1);
  assert.ok(storage.getItem(`mailweb.icon.${B.id}`));
});
