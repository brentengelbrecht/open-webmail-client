import { h, render } from '../util/dom.js';

// "Rename account" dialog. Returns { element, open(account) }.
export function createRenameDialog({ onRename }) {
  const dialog = h('dialog', { class: 'account-dialog' });

  function open(account) {
    let busy = false;
    let error = '';
    const input = h('input', { value: account.name, maxlength: 80, autocomplete: 'off', 'aria-label': 'Display name' });

    const draw = () => {
      input.disabled = busy;
      render(dialog, h('form', {
        onSubmit: async (event) => {
          event.preventDefault();
          busy = true; error = ''; draw();
          try {
            await onRename(account.id, input.value);
            dialog.close();
          } catch (e) {
            error = e.message;
          } finally {
            busy = false; draw();
          }
        },
      },
      h('h2', {}, 'Rename account'),
      h('p', { class: 'muted' }, `${account.user}@${account.host}`),
      h('label', { class: 'field' }, h('span', {}, 'Display name'), input),
      h('p', { class: 'muted' }, `Leave blank to use ${account.user}@${account.host}.`),
      error && h('p', { class: 'form-error', role: 'alert' }, error),
      h('div', { class: 'actions' },
        h('button', { type: 'button', class: 'text-btn', disabled: busy, onClick: () => dialog.close() }, 'Cancel'),
        h('button', { type: 'submit', class: 'primary', disabled: busy }, busy ? 'Saving…' : 'Save'))));
      if (!busy) { input.focus(); input.select(); }
    };

    draw();
    dialog.showModal();
    input.focus();
    input.select();
  }

  return { element: dialog, open };
}
