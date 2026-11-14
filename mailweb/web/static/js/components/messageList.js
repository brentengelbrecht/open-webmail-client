import { h, render } from '../util/dom.js';
import { fileSize, listDate, senderName } from '../util/format.js';
import { icon } from '../util/icons.js';
import { spinner } from '../util/spinner.js';

function row(item, selectedUid, actions) {
  return h('li', {
    class: `row${item.unread ? ' unread' : ''}${item.uid === selectedUid ? ' selected' : ''}`,
    onClick: () => actions.open(item.uid),
  },
  h('span', { class: 'star', title: item.starred ? 'Starred' : '' }, item.starred ? '★' : ''),
  h('span', { class: 'from' }, senderName(item.sender)),
  h('span', { class: 'subject' }, item.subject || '(no subject)'),
  h('span', { class: 'size', title: `${item.size.toLocaleString()} bytes` }, fileSize(item.size)),
  h('span', { class: 'clip', title: 'Has attachments' }, item.has_attachments && icon('attachment')),
  h('time', { class: 'date' }, listDate(item.date)));
}

function pager(data, actions) {
  const first = data.total ? (data.page - 1) * data.page_size + 1 : 0;
  const last = Math.min(data.total, data.page * data.page_size);
  return h('div', { class: 'pager' },
    h('span', {}, `${first}–${last} of ${data.total}`),
    h('button', { class: 'icon-btn', disabled: data.page <= 1, title: 'Newer', 'aria-label': 'Newer', onClick: () => actions.goToPage(data.page - 1) }, '‹'),
    h('button', { class: 'icon-btn', disabled: data.page >= data.pages, title: 'Older', 'aria-label': 'Older', onClick: () => actions.goToPage(data.page + 1) }, '›'),
    h('button', { class: 'icon-btn', disabled: data.page >= data.pages, title: 'Oldest', 'aria-label': 'Oldest', onClick: () => actions.goToPage(data.pages) }, '»'));
}

export function mountMessageList(root, store, actions, { onAddAccount }) {
  store.select((s) => [s.list, s.route.uid, s.accounts, s.folders, s.foldersLoading, s.foldersError],
    ([list, uid, accounts, folders, foldersLoading, foldersError]) => {
      if (accounts.length === 0) {
        return render(root, h('div', { class: 'placeholder' },
          h('p', {}, 'No mail accounts yet.'),
          h('button', { class: 'primary', onClick: onAddAccount }, 'Add an account')));
      }
      if (list.status === 'ready') {
        const { data } = list;
        return render(root,
          pager(data, actions),
          data.items.length
            ? h('ul', { class: 'rows' }, data.items.map((item) => row(item, uid, actions)))
            : h('p', { class: 'placeholder' }, data.query ? 'No messages match your search.' : 'This folder is empty.'));
      }
      if (list.status === 'error') return render(root, h('p', { class: 'placeholder form-error' }, list.error));
      // idle or loading: the mailbox is still being opened (folders first, then the message list)
      if (foldersError) return render(root, h('p', { class: 'placeholder form-error' }, foldersError));
      if (!foldersLoading && folders.length === 0) return render(root, h('p', { class: 'placeholder' }, 'This account has no folders.'));
      return render(root, spinner('Loading mailbox…'));
    });
}
