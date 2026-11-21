import { h, render } from '../util/dom.js';
import { mask } from '../util/scrub.js';
import { accountForm } from './accountFields.js';

// "Edit account" dialog: display name and connection settings. Returns { element, open(account) }.
// Save closes the dialog and the server then disconnects and reconnects with the new settings;
// Cancel (or Esc) closes it and changes nothing. The saved password is never sent to the browser:
// leaving the password blank keeps it.
export function createEditAccountDialog({ onSave }) {
  const dialog = h('dialog', { class: 'account-dialog' });
  let account = null;
  let data = null;
  let busy = false;
  let error = '';
  const { field, text, tlsCheckbox, verifyCheckbox } = accountForm(() => data, () => draw());

  const connectionChanged = () => data.password !== '' || data.host.trim() !== account.host || Number(data.port) !== account.port
    || data.user.trim() !== account.user || data.tls !== account.tls || (data.tls && data.tls_verify !== account.tls_verify);

  function draw() {
    render(dialog, h('form', {
      onSubmit: async (event) => {
        event.preventDefault();
        busy = true; error = ''; draw();
        const changes = { name: data.name, host: data.host.trim(), port: Number(data.port), user: data.user.trim(), tls: data.tls, tls_verify: data.tls_verify };
        if (data.password) changes.password = data.password;
        try {
          await onSave(account.id, changes);
          dialog.close();
        } catch (e) {
          error = e.message;                               // stays open, nothing was changed on the server
        } finally {
          busy = false; draw();
        }
      },
    },
    h('h2', {}, 'Edit account'),
    field('Display name', text('name', { maxlength: 80, placeholder: `${data.user}@${data.host}` })),
    field('Server address', text('host', { required: true })),
    field('Port', text('port', { type: 'number', min: 1, max: 65535, required: true })),
    tlsCheckbox(),
    verifyCheckbox(),
    field('Username', text('user', { required: true })),
    field('Password', text('password', { type: 'password', autocomplete: 'new-password', placeholder: 'Leave blank to keep the current password' })),
    h('p', { class: 'muted' }, 'Save disconnects and reconnects with these settings. Cancel keeps everything as it is.'),
    error && h('p', { class: 'form-error', role: 'alert' }, error),
    h('div', { class: 'actions' },
      h('button', { type: 'button', class: 'text-btn', disabled: busy, onClick: () => dialog.close() }, 'Cancel'),
      h('button', { type: 'submit', class: 'primary', disabled: busy }, busy ? (connectionChanged() ? 'Reconnecting…' : 'Saving…') : 'Save & reconnect'))));
  }

  // However it closes, do not leave the typed password lying around in the page.
  dialog.addEventListener('close', () => {
    dialog.querySelectorAll('input').forEach((input) => { input.value = mask(input.value); });
    if (data) data.password = mask(data.password);
    dialog.replaceChildren();
    data = account = null;
  });

  return {
    element: dialog,
    open(info) {
      account = info;
      data = { name: info.name, host: info.host, port: String(info.port), user: info.user, tls: info.tls, tls_verify: info.tls_verify !== false, password: '' };
      busy = false; error = '';
      draw();
      dialog.showModal();
      dialog.querySelector('input')?.focus();
    },
  };
}
