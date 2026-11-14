import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.location = { hash: '', replace() {} };
const { mask, overwriteDeep, scrubStorage } = await import('../mailweb/web/static/js/util/scrub.js');
const { createStore } = await import('../mailweb/web/static/js/store.js');
const { createActions } = await import('../mailweb/web/static/js/actions.js');
const { parseHash } = await import('../mailweb/web/static/js/router.js');

class FakeStorage {
  constructor(entries) { this.map = new Map(Object.entries(entries)); }
  get length() { return this.map.size; }
  key(i) { return [...this.map.keys()][i] ?? null; }
  getItem(k) { return this.map.has(k) ? this.map.get(k) : null; }
  setItem(k, v) { this.writes.push([k, v]); this.map.set(k, v); }
  removeItem(k) { this.map.delete(k); }
  writes = [];
}

test('overwriteDeep replaces strings with X (same length) and numbers with 0, in place', () => {
  const tree = { subject: 'Tax return', size: 1234, ok: true, from: { name: 'Alice', email: 'a@b.c' }, tags: ['one', 'two'] };
  const from = tree.from;
  overwriteDeep(tree);
  assert.deepEqual(tree, { subject: 'XXXXXXXXXX', size: 0, ok: true, from: { name: 'XXXXX', email: 'XXXXX' }, tags: ['XXX', 'XXX'] });
  assert.equal(tree.from, from, 'overwritten in place, not copied');
});

test('overwriteDeep survives cycles and frozen objects', () => {
  const a = { name: 'loop' }; a.self = a;
  overwriteDeep(a);
  assert.equal(a.name, 'XXXX');
  assert.doesNotThrow(() => overwriteDeep(Object.freeze({ name: 'frozen' })));
});

test('scrubStorage overwrites matching entries before removing them, and leaves others alone', () => {
  const storage = new FakeStorage({
    'mailweb.layout': '"right"',
    'cache.a1b2c3d4': 'secret subject',
    'note': 'mail for jane@example.com',
    'unrelated': 'keep me',
  });
  const removed = scrubStorage(storage, ['a1b2c3d4', 'jane@example.com', 'x']);       // 'x' is too short to count
  assert.equal(removed, 2);
  assert.deepEqual([...storage.map.keys()].sort(), ['mailweb.layout', 'unrelated']);
  assert.deepEqual(storage.writes.map(([, v]) => v).sort(), [mask('mail for jane@example.com'), mask('secret subject')].sort());
});

function setup({ failServer = false } = {}) {
  const order = [];
  const account = { id: 'a1b2c3d4', name: 'Work mail', host: 'imap.example.com', user: 'jane@example.com' };
  const api = {
    accounts: async () => ({ accounts: [account] }),
    folders: async () => ({ folders: [{ name: 'INBOX', unseen: 1 }] }),
    messages: async () => ({ items: [{ uid: 1, subject: 'Private subject', sender: { name: 'Bob', email: 'bob@x.org' }, size: 99 }], total: 1, page: 1, pages: 1, page_size: 50, query: '' }),
    message: async () => ({ uid: 1, subject: 'Private subject', to: [], cc: [], attachments: [{ filename: 'plan.pdf' }] }),
    removeAccount: async () => { order.push('server'); if (failServer) throw new Error('server said no'); },
  };
  const idle = { status: 'idle', data: null, error: null };
  const store = createStore({ booting: false, authenticated: false, loginNotice: '', accounts: [], folders: [], foldersError: null,
    foldersLoading: false, route: parseHash(''), list: idle, message: idle, layout: 'right', sidebarCollapsed: false,
    panes: { sidebar: 240, listWidth: 480, listHeight: 320 } });
  const storage = new FakeStorage({ [`k.${account.id}`]: 'x', pref: '1' });
  const env = {
    scrubDom: () => order.push('dom'),
    storages: () => [storage],
    clearUrl: () => order.push('url'),
    reload: () => order.push('reload'),
  };
  return { store, actions: createActions(store, api, env), order, storage, account };
}

test('removing an account: server first, then values, DOM, storage, URL, and finally a reload', async () => {
  const { store, actions, order, storage } = setup();
  await actions.start(parseHash('#/a1b2c3d4/INBOX?uid=1'));
  const { folders, list, message } = store.get();
  const held = { folders, items: list.data.items, detail: message.data };          // what the page was holding
  await actions.removeAccount('a1b2c3d4');
  assert.deepEqual(order, ['server', 'dom', 'url', 'reload']);
  assert.equal(held.items[0].subject, mask('Private subject'));                         // overwritten in place
  assert.equal(held.items[0].sender.email, 'XXXXXXXXX');
  assert.equal(held.detail.attachments[0].filename, 'XXXXXXXX');
  assert.equal(held.folders[0].name, 'XXXXX');
  assert.deepEqual([...storage.map.keys()], ['pref']);                           // account entry gone, others kept
  const state = store.get();
  assert.equal(state.accounts.length, 0);
  assert.equal(state.list.data, null);
  assert.equal(state.message.data, null);
  assert.equal(state.route.account, '');
});

test('if the server cannot remove the account, nothing is wiped in the browser', async () => {
  const { store, actions, order } = setup({ failServer: true });
  await actions.start(parseHash('#/a1b2c3d4/INBOX?uid=1'));
  const items = store.get().list.data.items;
  await assert.rejects(actions.removeAccount('a1b2c3d4'), /server said no/);
  assert.deepEqual(order, ['server']);
  assert.equal(items[0].subject, 'Private subject');
  assert.equal(store.get().accounts.length, 1);
});
