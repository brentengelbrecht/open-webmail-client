import { h, render } from '../util/dom.js';
import { buildHash } from '../router.js';
import { icon } from '../util/icons.js';
import { spinner } from '../util/spinner.js';

export function mountSidebar(root, store, actions) {
  store.select((s) => [s.folders, s.route.account, s.route.folder, s.foldersError, s.accounts, s.foldersLoading],
    ([folders, accountId, current, error, accounts, loading]) => {
      const account = accounts.find((a) => a.id === accountId);
      render(root,
        account && h('div', { class: 'account-bar' },
          h('span', { class: 'account-name', title: `${account.user}@${account.host}` }, account.name),
          h('button', {
            class: 'icon-btn remove-account',
            title: 'Remove this account from the client (mail on the server is untouched)',
            'aria-label': `Remove account ${account.name}`,
            onClick: () => confirm(`Remove “${account.name}” from this client?\n\nIts saved login and everything cached for it will be erased. Mail on the server is not touched.`) && actions.removeAccount(account.id),
          }, icon('trash', 18))),
        loading && folders.length === 0 && spinner('Loading folders…', { small: true }),
        error && h('p', { class: 'form-error' }, error),
        h('nav', {}, folders.map((folder) => {
          const parts = folder.name.split('/');
          return h('a', {
            class: `folder${folder.name === current ? ' active' : ''}`,
            href: buildHash({ account: accountId, folder: folder.name }),
            style: `padding-left:${12 + (parts.length - 1) * 14}px`,
            onClick: () => document.body.classList.remove('sidebar-open'),
          }, h('span', { class: 'folder-name' }, parts[parts.length - 1]),
          folder.unseen > 0 && h('span', { class: 'count' }, String(folder.unseen)));
        })));
    });
}
