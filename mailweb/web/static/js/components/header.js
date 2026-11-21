import { h, render } from '../util/dom.js';
import { icon } from '../util/icons.js';

const LAYOUTS = [
  ['right', 'Reading pane on the right'],
  ['bottom', 'Reading pane below the list'],
  ['full', 'Full-width list; messages slide in over it'],
];

// On phones the folder list is an overlay; elsewhere it collapses out of the layout.
const phone = window.matchMedia('(max-width: 700px)');
const toggleFolders = (actions) => (phone.matches ? document.body.classList.toggle('sidebar-open') : actions.toggleSidebar());

export function mountHeader(root, store, actions) {
  const updateClear = () => { clearButton.hidden = input.value === ''; };
  // The X: empties the box and, if a search is running or showing, interrupts it at once (browser and server).
  const clear = () => { input.value = ''; updateClear(); input.focus(); actions.clearSearch(); };
  const input = h('input', {
    type: 'search', class: 'search', 'aria-label': 'Search mail', onInput: updateClear,
    onKeydown: (e) => { if (e.key === 'Escape' && input.value) { e.preventDefault(); clear(); } },
  });
  const clearButton = h('button', { type: 'button', class: 'search-clear', title: 'Clear search', 'aria-label': 'Clear search', hidden: true, onClick: clear },
    icon('close', 18));
  const layoutButtons = LAYOUTS.map(([layout, title]) => h('button', {
    class: 'icon-btn', title, 'aria-label': title, onClick: () => actions.setLayout(layout),
  }, h('span', { class: `pane-icon ${layout}` })));

  render(root,
    h('button', { class: 'icon-btn menu', 'aria-label': 'Toggle folder list', onClick: () => toggleFolders(actions) }, '☰'),
    h('span', { class: 'brand' },
      h('img', { class: 'brand-icon', src: '/img/icon.svg', alt: '' }),
      h('img', { class: 'brand-name', src: '/img/owc_logo_name.png', alt: 'Open Webmail Client' })),
    h('form', { class: 'search-form', onSubmit: (e) => { e.preventDefault(); actions.search(input.value.trim()); } },
      h('div', { class: 'search-box' }, input, clearButton)),
    h('button', { class: 'icon-btn', title: 'Refresh', onClick: () => actions.refresh() }, '↻'),
    h('div', { class: 'topbar-end' },
      h('div', { class: 'layout-switch' }, layoutButtons),
      h('button', { class: 'icon-btn', title: 'Sign out', 'aria-label': 'Sign out', onClick: () => actions.logout() }, icon('signOut'))));

  store.select((s) => [s.route.folder, s.route.q], ([folder, q]) => {
    input.placeholder = folder ? `Search in ${folder}` : 'Search mail';
    input.value = q;
    updateClear();
  });
  const menu = root.querySelector('.menu');
  store.select((s) => s.sidebarCollapsed, (collapsed) => {
    menu.title = collapsed ? 'Show folders' : 'Hide folders';
    menu.setAttribute('aria-expanded', String(!collapsed));
  });
  store.select((s) => s.layout, (current) =>
    layoutButtons.forEach((button, i) => button.setAttribute('aria-pressed', String(LAYOUTS[i][0] === current))));
}
