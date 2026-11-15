import { h, render } from '../util/dom.js';
import { urls } from '../api.js';
import { errorState } from './errorState.js';
import { icon } from '../util/icons.js';
import { spinner } from '../util/spinner.js';
import { addressLabel, fileSize, fullDate, senderName } from '../util/format.js';

const people = (label, list) => list.length > 0 && h('div', { class: 'meta-line' }, `${label}: ${list.map(addressLabel).join(', ')}`);

function view(account, m, imagesAllowed, actions) {
  return [
    h('div', { class: 'reader-head' },
      h('button', { class: 'icon-btn back', title: 'Back to list', 'aria-label': 'Back to list', onClick: () => actions.closeMessage() }, icon('back', 22)),
      h('h2', {}, m.subject || '(no subject)')),
    h('div', { class: 'meta' },
      h('div', { class: 'meta-line' }, h('strong', {}, senderName(m.sender)), m.sender && m.sender.name ? ` <${m.sender.email}>` : ''),
      people('To', m.to), people('Cc', m.cc),
      h('div', { class: 'meta-line muted' }, fullDate(m.date), ' · ', h('a', { href: urls.raw(account, m.folder, m.uid) }, 'Download .eml'))),
    m.remote_images_blocked && !imagesAllowed && h('div', { class: 'notice' },
      'Images in this message are not displayed. ',
      h('a', { href: '#', onClick: (e) => { e.preventDefault(); actions.allowImages(); } }, 'Download images')),
    m.attachments.length > 0 && h('div', { class: 'attachments' }, m.attachments.map((a) =>
      h('a', { class: 'chip', href: urls.attachment(account, m.folder, m.uid, a.index) }, `📎 ${a.filename} (${fileSize(a.size)})`))),
    // Untrusted HTML lives in a sandboxed iframe; the server also sends a locked-down CSP.
    h('iframe', { class: 'body', title: 'Message body', src: urls.body(account, m.folder, m.uid, imagesAllowed), sandbox: 'allow-popups allow-popups-to-escape-sandbox' }),
  ];
}

export function mountReader(root, store, actions) {
  store.select((s) => [s.message, s.layout], ([message, layout]) => {
    // Full-width layout: the panel slides out over the list, so leave its last content in place until it is gone.
    if (layout === 'full' && message.status === 'idle') return;
    if (message.status === 'loading') return render(root, spinner('Loading message…'));
    if (message.status === 'error') return render(root, errorState(message.error));
    if (!message.data) return render(root, h('p', { class: 'placeholder' }, 'Select a message to read'));
    render(root, view(store.get().route.account, message.data, Boolean(message.imagesAllowed), actions));
  });
}
