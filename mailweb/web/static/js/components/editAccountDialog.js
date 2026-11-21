import { h, render } from '../util/dom.js';
import { icon } from '../util/icons.js';
import { accountColor, accountInitial } from '../util/accountVisual.js';
import { resizeToSquare } from '../util/iconImage.js';
import { mask } from '../util/scrub.js';
import { accountForm } from './accountFields.js';

// "Edit account" dialog: icon, display name and connection settings. Returns { element, open(account, currentIcon) }.
// Save closes the dialog and the server then disconnects and reconnects with the new settings;
// Cancel (or Esc) closes it and changes nothing, icon included. The saved password is never sent to the
// browser: leaving the password blank keeps it.
export function createEditAccountDialog({ onSave }) {
  const dialog = h('dialog', { class: 'account-dialog' });
  let account = null;
  let data = null;
  let currentIcon = null;     // the icon stored for this account now (data URL) or null for the default letter icon
  let stagedIcon;             // undefined = not touched; a data URL = chosen but not saved yet; null = "use default"
  let busy = false;
  let error = '';
  const { field, text, tlsCheckbox, verifyCheckbox } = accountForm(() => data, () => draw());

  const shownIcon = () => (stagedIcon === undefined ? currentIcon : stagedIcon);

  const connectionChanged = () => data.password !== '' || data.host.trim() !== account.host || Number(data.port) !== account.port
    || data.user.trim() !== account.user || data.tls !== account.tls || (data.tls && data.tls_verify !== account.tls_verify);

  // One persistent file input, opened by the pencil on the icon.
  const fileInput = h('input', {
    type: 'file', accept: 'image/*,.svg', hidden: true, tabindex: '-1',
    onChange: async () => {
      const file = fileInput.files[0];
      fileInput.value = '';                                    // allows choosing the same file again
      if (!file) return;
      try {
        stagedIcon = await resizeToSquare(file);
        error = '';
      } catch (e) {
        error = e.message;
      }
      draw();
    },
  });

  function iconPicker() {
    const current = shownIcon();
    return h('div', { class: 'icon-picker-row' },
      h('div', { class: 'icon-picker' },
        current
          ? h('img', { class: 'icon-preview', src: current, alt: 'Account icon' })
          : h('div', { class: 'icon-preview letter', style: `background:${accountColor(account.id)}`, role: 'img', 'aria-label': 'Default account icon' },
            accountInitial(data.name || `${data.user}`)),
        // No native `title` here: the browser would re-show it at the pointer, away from the pencil, when the file picker closes.
        // The tooltip is drawn by the page (CSS, from data-tip) and stays attached to the pencil.
        h('button', {
          type: 'button', class: 'icon-edit', 'data-tip': 'Change icon (image or SVG)', disabled: busy,
          onClick: (event) => {
            event.currentTarget.setAttribute('data-picking', '');               // hides the tooltip while the picker is open
            event.currentTarget.blur();
            fileInput.click();
          },
          onPointerleave: (event) => event.currentTarget.removeAttribute('data-picking'),
        }, icon('edit', 16), h('span', { class: 'sr-only' }, 'Change icon (image or SVG)'))),     // the button's accessible name, as page text
      current && h('button', { type: 'button', class: 'text-btn', disabled: busy, onClick: () => { stagedIcon = null; draw(); } }, 'Use default icon'));
  }

  function draw() {
    render(dialog, h('form', {
      onSubmit: async (event) => {
        event.preventDefault();
        busy = true; error = ''; draw();
        const changes = { name: data.name, host: data.host.trim(), port: Number(data.port), user: data.user.trim(), tls: data.tls, tls_verify: data.tls_verify };
        if (data.password) changes.password = data.password;
        try {
          await onSave(account.id, changes, { icon: stagedIcon });
          dialog.close();
        } catch (e) {
          error = e.message;                               // stays open, nothing was changed on the server
        } finally {
          busy = false; draw();
        }
      },
    },
    h('h2', {}, 'Edit account'),
    iconPicker(),
    fileInput,
    field('Display name', text('name', { maxlength: 80, placeholder: `${data.user}@${data.host}` })),
    field('Server address', text('host', { required: true })),
    field('Port', text('port', { type: 'number', min: 1, max: 65535, required: true })),
    tlsCheckbox(),
    verifyCheckbox(),
    field('Username', text('user', { required: true })),
    field('Password', text('password', { type: 'password', autocomplete: 'new-password', placeholder: 'Leave blank to keep the current password' })),
    h('p', { class: 'muted' }, 'Save disconnects and reconnects with these settings. Cancel keeps everything as it is. The icon is kept in this browser only.'),
    error && h('p', { class: 'form-error', role: 'alert' }, error),
    h('div', { class: 'actions' },
      h('button', { type: 'button', class: 'text-btn', disabled: busy, onClick: () => dialog.close() }, 'Cancel'),
      h('button', { type: 'submit', class: 'primary', disabled: busy }, busy ? (connectionChanged() ? 'Reconnecting…' : 'Saving…') : 'Save & reconnect'))));
  }

  // However it closes, do not leave the typed password (or a not-yet-saved icon) lying around in the page.
  dialog.addEventListener('close', () => {
    dialog.querySelectorAll('input').forEach((input) => { if (input.type !== 'file') input.value = mask(input.value); });
    if (data) data.password = mask(data.password);
    dialog.replaceChildren();
    data = account = currentIcon = null;
    stagedIcon = undefined;
  });

  return {
    element: dialog,
    open(info, icon = null) {
      account = info;
      currentIcon = icon;
      stagedIcon = undefined;
      data = { name: info.name, host: info.host, port: String(info.port), user: info.user, tls: info.tls, tls_verify: info.tls_verify !== false, password: '' };
      busy = false; error = '';
      draw();
      dialog.showModal();
      dialog.querySelector('input:not([type=file])')?.focus();
    },
  };
}
