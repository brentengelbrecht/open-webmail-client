// Controller: turns route changes and user intents into API calls and store updates.
import { navigate, parseHash, replaceRoute } from './router.js';
import { DEFAULT_PANES } from './util/panes.js';
import { savePref } from './util/prefs.js';
import { overwriteDeep, overwriteDom, scrubStorage } from './util/scrub.js';

const IDLE = { status: 'idle', data: null, error: null };

const SESSION_ENDED = 'Your session has ended. Please sign in again.';

// The browser pieces the removal flow needs; injectable so the flow can be tested without a browser.
export const browserEnv = () => ({
  scrubDom: () => overwriteDom(document.getElementById('app')),
  storages: () => [window.localStorage, window.sessionStorage],
  clearUrl: () => history.replaceState(null, '', location.pathname),
  reload: () => location.reload(),
});

export function createActions(store, api, env = browserEnv()) {
  let listKey = null;
  let messageKey = null;
  let mailboxAccount = null;       // the account whose mailbox the store currently shows
  let sessionTimer = null;
  let guessedFolder = false;       // the current folder is an assumed INBOX, not one the user chose

  // Forget everything about the current mailbox.
  function clearMailbox() {
    listKey = messageKey = mailboxAccount = null;
    guessedFolder = false;
    store.set({ folders: [], foldersError: null, foldersLoading: false, list: IDLE, message: IDLE });
  }

  const isCurrent = (account) => store.get().route.account === account;

  async function loadFolders(account, refresh = false) {
    store.set({ foldersLoading: true });
    try {
      const { folders } = await api.folders({ account, refresh });
      if (isCurrent(account)) store.set({ folders, foldersError: null });
    } catch (error) {
      if (isCurrent(account)) store.set({ foldersError: error.message });
    } finally {
      if (isCurrent(account)) store.set({ foldersLoading: false });
    }
  }

  async function loadList(route, refresh = false) {
    const key = JSON.stringify([route.account, route.folder, route.page, route.q]);
    if (!refresh && key === listKey) return;
    listKey = key;
    store.set({ list: { ...IDLE, status: 'loading' } });
    try {
      const data = await api.messages({ ...route, refresh });
      if (listKey === key) store.set({ list: { status: 'ready', data, error: null } });
    } catch (error) {
      if (listKey === key) store.set({ list: { status: 'error', data: null, error: error.message } });
    }
  }

  async function loadMessage(route) {
    const key = route.uid ? JSON.stringify([route.account, route.folder, route.uid]) : null;
    if (key === messageKey) return;
    messageKey = key;
    if (!key) { store.set({ message: IDLE }); return; }
    store.set({ message: { ...IDLE, status: 'loading' } });
    try {
      const data = await api.message(route);
      if (messageKey === key) store.set({ message: { status: 'ready', data, error: null, imagesAllowed: false } });
    } catch (error) {
      if (messageKey === key) store.set({ message: { status: 'error', data: null, error: error.message } });
    }
  }

  // Once the folder list arrives: if the assumed INBOX does not exist (an archive without one), open a real folder.
  function checkGuessedFolder() {
    if (!guessedFolder) return;
    const { folders, route } = store.get();
    if (!folders.length) return;
    guessedFolder = false;
    if (!folders.some((f) => f.name === route.folder)) {
      const fallback = folders.find((f) => f.name.toLowerCase() === 'inbox') || folders[0];
      replaceRoute({ ...route, folder: fallback.name });
    }
  }

  const accountId = () => store.get().route.account;

  return {
    // Begin a signed-in session; sign out automatically when the server-side session runs out.
    async start(route, expiresIn) {
      const { accounts } = await api.accounts();
      clearTimeout(sessionTimer);
      if (expiresIn > 0) sessionTimer = setTimeout(() => this.expire(SESSION_ENDED), expiresIn * 1000);
      store.set({ authenticated: true, booting: false, accounts, loginNotice: '', foldersLoading: accounts.length > 0 });
      await this.applyRoute(route);
    },

    async applyRoute(route) {
      const { authenticated, accounts } = store.get();
      if (!authenticated) return;
      if (!accounts.length) {
        clearMailbox();
        store.set({ route });
        return;
      }
      if (!accounts.some((a) => a.id === route.account)) {
        replaceRoute({ account: accounts[0].id });
        return;
      }
      let foldersLoaded = Promise.resolve();
      if (mailboxAccount !== route.account) {          // switching mailbox: start from a clean slate
        clearMailbox();
        mailboxAccount = route.account;
        store.set({ route });
        // Do not wait for the folder list: the message list can load at the same time.
        foldersLoaded = loadFolders(route.account).then(checkGuessedFolder);
      }
      if (!route.folder) {
        const { folders } = store.get();
        const known = folders.find((f) => f.name.toLowerCase() === 'inbox') || folders[0];
        guessedFolder = !known;                       // no folder list yet: assume INBOX, verify once it arrives
        replaceRoute({ ...route, folder: known ? known.name : 'INBOX' });
        return;
      }
      store.set({ route });
      await Promise.all([foldersLoaded, loadList(route), loadMessage(route)]);
    },

    async refresh() {
      const { route } = store.get();
      if (!route.account) return;
      listKey = messageKey = null;
      await Promise.all([loadFolders(route.account, true), route.folder && loadList(route, true), route.folder && loadMessage(route)]);
    },

    // navigation intents
    open: (uid) => navigate({ ...store.get().route, uid }),
    closeMessage: () => navigate({ ...store.get().route, uid: null }),
    goToPage: (page) => navigate({ ...store.get().route, page, uid: null }),
    search: (q) => navigate({ account: accountId(), folder: store.get().route.folder, q, page: 1 }),
    selectAccount: (id) => navigate({ account: id }),

    // accounts
    async addAccount(details) {
      const { account } = await api.addAccount(details);
      store.set({ accounts: [...store.get().accounts, account] });
      navigate({ account: account.id });
    },
    // Remove an account and erase what this page knows about it. The server is asked first; if it fails
    // nothing is wiped here. Order: values -> state -> page -> browser storage -> URL -> new page (new JS heap).
    async removeAccount(id) {
      const state = store.get();
      const account = state.accounts.find((a) => a.id === id);
      if (!account) return;
      await api.removeAccount(id);

      const needles = [account.id, account.name, account.host, account.user];
      const remaining = state.accounts.filter((a) => a.id !== id);
      if (state.route.account === id) {
        [state.folders, state.list.data, state.message.data, state.route].forEach((value) => overwriteDeep(value));
      }
      overwriteDeep(account);
      listKey = messageKey = mailboxAccount = null;
      store.set({ accounts: remaining, folders: [], foldersError: null, foldersLoading: false, list: IDLE, message: IDLE,
                  route: { account: '', folder: '', page: 1, q: '', uid: null } });

      env.scrubDom();
      env.storages().forEach((storage) => scrubStorage(storage, needles));
      env.clearUrl();
      env.reload();
    },

    // view state
    allowImages() {
      const { message } = store.get();
      if (message.status === 'ready') store.set({ message: { ...message, imagesAllowed: true } });
    },
    setLayout(layout) {
      savePref('layout', layout);
      store.set({ layout });
    },
    toggleSidebar() {
      const sidebarCollapsed = !store.get().sidebarCollapsed;
      savePref('sidebarCollapsed', sidebarCollapsed);
      store.set({ sidebarCollapsed });
    },
    setPane(key, value) {
      store.set({ panes: { ...store.get().panes, [key]: value } });
    },
    resetPane(key) {
      this.setPane(key, DEFAULT_PANES[key]);
      this.savePanes();
    },
    savePanes() {
      savePref('panes', store.get().panes);
    },

    // session
    async login(password) {
      const { expires_in: expiresIn } = await api.login(password);
      await this.start(parseHash(), expiresIn);
    },
    async logout() {
      try { await api.logout(); } finally { this.expire(''); }
    },
    expire(notice = SESSION_ENDED) {
      clearTimeout(sessionTimer);
      clearMailbox();
      store.set({ authenticated: false, accounts: [], loginNotice: notice });
    },
  };
}
