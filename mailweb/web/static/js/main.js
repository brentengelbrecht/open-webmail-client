import { api, onUnauthorized } from './api.js';
import { createStore } from './store.js';
import { createActions } from './actions.js';
import { parseHash, onRouteChange } from './router.js';
import { mountShell } from './components/shell.js';
import { DEFAULT_PANES } from './util/panes.js';
import { loadPref } from './util/prefs.js';

const idle = { status: 'idle', data: null, error: null };
const store = createStore({
  booting: true, authenticated: false, loginNotice: '', foldersLoading: false, accounts: [], accountIcons: {}, folders: [], foldersError: null,
  route: parseHash(), list: idle, message: idle,
  layout: ['right', 'bottom', 'full'].includes(loadPref('layout', 'right')) ? loadPref('layout', 'right') : 'right',
  sidebarCollapsed: loadPref('sidebarCollapsed', false) === true,
  panes: { ...DEFAULT_PANES, ...loadPref('panes', {}) },
});
const actions = createActions(store, api);

onUnauthorized(() => actions.expire());
onRouteChange((route) => actions.applyRoute(route));
mountShell(document.getElementById('app'), store, actions);

api.session()
  .then(({ authenticated, expires_in: expiresIn }) =>
    (authenticated ? actions.start(parseHash(), expiresIn) : store.set({ booting: false })))
  .catch(() => store.set({ booting: false }));
