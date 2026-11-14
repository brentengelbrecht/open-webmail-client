import { h, render } from '../util/dom.js';
import { icon, logo } from '../util/icons.js';

const LAYOUTS = [
  ['right', 'Reading pane on the right'],
  ['bottom', 'Reading pane below the list'],
  ['full', 'Full-width list; messages slide in over it'],
];

// On phones the folder list is an overlay; elsewhere it collapses out of the layout.
const phone = window.matchMedia('(max-width: 700px)');
const toggleFolders = (actions) => (phone.matches ? document.body.classList.toggle('sidebar-open') : actions.toggleSidebar());

export function mountHeader(root, store, actions) {
  const input = h('input', { type: 'search', class: 'search', 'aria-label': 'Search mail' });
  const layoutButtons = LAYOUTS.map(([layout, title]) => h('button', {
    class: 'icon-btn', title, 'aria-label': title, onClick: () => actions.setLayout(layout),
  }, h('span', { class: `pane-icon ${layout}` })));

  render(root,
    h('button', { class: 'icon-btn menu', 'aria-label': 'Toggle folder list', onClick: () => toggleFolders(actions) }, '☰'),
    h('span', { class: 'brand' }, logo()),
    h('form', { class: 'search-form', onSubmit: (e) => { e.preventDefault(); actions.search(input.value.trim()); } }, input),
    h('button', { class: 'icon-btn', title: 'Refresh', onClick: () => actions.refresh() }, '↻'),
    h('div', { class: 'topbar-end' },
      h('div', { class: 'layout-switch' }, layoutButtons),
      h('button', { class: 'icon-btn', title: 'Sign out', 'aria-label': 'Sign out', onClick: () => actions.logout() }, icon('signOut'))));

  store.select((s) => [s.route.folder, s.route.q], ([folder, q]) => {
    input.placeholder = folder ? `Search in ${folder}` : 'Search mail';
    input.value = q;
  });
  const menu = root.querySelector('.menu');
  store.select((s) => s.sidebarCollapsed, (collapsed) => {
    menu.title = collapsed ? 'Show folders' : 'Hide folders';
    menu.setAttribute('aria-expanded', String(!collapsed));
  });
  store.select((s) => s.layout, (current) =>
    layoutButtons.forEach((button, i) => button.setAttribute('aria-pressed', String(LAYOUTS[i][0] === current))));
}
