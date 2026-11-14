import { h, render } from '../util/dom.js';

// A stable colour per account so the icons are easy to tell apart.
const hue = (id) => [...id].reduce((sum, ch) => (sum * 31 + ch.charCodeAt(0)) % 360, 7);
const initial = (name) => (name.trim()[0] || '?').toUpperCase();

export function mountGutter(root, store, actions, { onAddAccount }) {
  store.select((s) => [s.accounts, s.route.account], ([accounts, current]) => {
    render(root,
      h('button', { class: 'gutter-btn add', title: 'Add account', 'aria-label': 'Add account', onClick: onAddAccount }, '+'),
      accounts.map((account) => h('button', {
        class: `gutter-btn account${account.id === current ? ' active' : ''}`,
        title: `${account.name}\n${account.user}@${account.host}`,
        'aria-label': account.name,
        'aria-current': account.id === current ? 'true' : null,
        style: `background:hsl(${hue(account.id)} 55% 45%)`,
        onClick: () => actions.selectAccount(account.id),
      }, initial(account.name))));
  });
}
