import { h, render } from '../util/dom.js';
import { accountForm } from './accountFields.js';

const BLANK = () => ({ host: '', port: '1143', tls: false, tls_verify: true, name: '', user: '', password: '' });

// Two-step "add account" flow in a native <dialog>. Returns { element, open }.
export function createAccountDialog({ onAdd }) {
  const dialog = h('dialog', { class: 'account-dialog' });
  let step = 1;
  let data = BLANK();
  let busy = false;
  let error = '';

  const { field, text, tlsCheckbox, verifyCheckbox } = accountForm(() => data, () => draw());

  function serverStep() {
    return h('form', {
      onSubmit: (e) => { e.preventDefault(); step = 2; error = ''; draw(); },
    },
    h('h2', {}, 'Add account'), h('p', { class: 'muted' }, 'Step 1 of 2 · IMAP server'),
    field('Server address', text('host', { placeholder: 'e.g. 192.168.1.50 or pi.local', required: true, autofocus: true })),
    h('p', { class: 'muted' }, 'Used from the computer running mailweb, not from your browser.'),
    field('Port', text('port', { type: 'number', min: 1, max: 65535, required: true })),
    h('p', { class: 'muted' }, 'imap_archive_server listens on 1143 unless its .ini says otherwise.'),
    tlsCheckbox(),
    verifyCheckbox(),
    h('div', { class: 'actions' },
      h('button', { type: 'button', class: 'text-btn', onClick: () => dialog.close() }, 'Cancel'),
      h('button', { type: 'submit', class: 'primary' }, 'Next')));
  }

  function credentialsStep() {
    return h('form', {
      onSubmit: async (e) => {
        e.preventDefault();
        busy = true; error = ''; draw();
        try {
          await onAdd({ ...data, port: Number(data.port) });
          dialog.close();
        } catch (err) {
          error = err.message;
        } finally {
          busy = false; draw();
        }
      },
    },
    h('h2', {}, 'Add account'), h('p', { class: 'muted' }, `Step 2 of 2 · Sign in to ${data.host}`),
    field('Username', text('user', { required: true, autofocus: true })),
    field('Password', text('password', { type: 'password', required: true, autocomplete: 'new-password' })),
    field('Display name (optional)', text('name', { placeholder: `${data.user || 'user'}@${data.host}` })),
    error && h('p', { class: 'form-error', role: 'alert' }, error),
    h('div', { class: 'actions' },
      h('button', { type: 'button', class: 'text-btn', disabled: busy, onClick: () => { step = 1; error = ''; draw(); } }, 'Back'),
      h('button', { type: 'submit', class: 'primary', disabled: busy }, busy ? 'Connecting…' : 'Add account')));
  }

  function draw() {
    render(dialog, step === 1 ? serverStep() : credentialsStep());
    const first = dialog.querySelector('[autofocus]');
    if (first && !busy) first.focus();
  }

  return {
    element: dialog,
    open() {
      step = 1; data = BLANK(); busy = false; error = '';
      draw();
      dialog.showModal();
    },
  };
}
