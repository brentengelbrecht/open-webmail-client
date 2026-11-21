import { h, render } from '../util/dom.js';
import { accountColor, accountInitial } from '../util/accountVisual.js';
import { moveItem } from '../util/reorder.js';
import { attachVerticalReorder } from './dragReorder.js';

export function mountGutter(root, store, actions, { onAddAccount }) {
  let refocus = null;          // after a keyboard move the list is redrawn; put focus back on the moved account

  store.select((s) => [s.accounts, s.route.account, s.accountIcons], ([accounts, current, icons]) => {
    const ids = accounts.map((account) => account.id);
    let reorder = null;
    const buttons = accounts.map((account) => h('button', {
      class: `gutter-btn account${account.id === current ? ' active' : ''}${icons[account.id] ? ' custom' : ''}`,
      'data-id': account.id,
      title: `${account.name}\n${account.user}@${account.host}\nDrag to reorder (or Alt+Up / Alt+Down)`,
      'aria-label': account.name,
      'aria-current': account.id === current ? 'true' : null,
      style: icons[account.id] ? null : `background:${accountColor(account.id)}`,
      onClick: () => { if (!reorder?.justDragged()) actions.selectAccount(account.id); },
    }, icons[account.id] ? h('img', { class: 'gutter-icon', src: icons[account.id], alt: '', draggable: 'false' }) : accountInitial(account.name)));

    render(root,
      h('button', { class: 'gutter-btn add', title: 'Add account', 'aria-label': 'Add account', onClick: onAddAccount }, '+'),
      buttons);

    reorder = attachVerticalReorder(buttons, {
      container: root,
      onMove: (from, to, { keyboard }) => {
        if (keyboard) refocus = ids[from];
        actions.reorderAccounts(moveItem(ids, from, to));
      },
    });
    if (refocus) {
      root.querySelector(`[data-id="${refocus}"]`)?.focus();
      refocus = null;
    }
  });
}
