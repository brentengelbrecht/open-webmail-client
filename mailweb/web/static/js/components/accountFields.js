import { h } from '../util/dom.js';

// Form pieces shared by the "add account" and "edit account" dialogs.
// `getData` returns the form's working copy (a plain object); `redraw` re-renders the dialog.
export function accountForm(getData, redraw) {
  const field = (label, input) => h('label', { class: 'field' }, h('span', {}, label), input);
  const text = (key, props = {}) => h('input', {
    value: getData()[key], autocomplete: 'off', ...props, onInput: (e) => { getData()[key] = e.target.value; },
  });
  const check = (key, label, onChange) => h('label', { class: 'check' },
    h('input', { type: 'checkbox', checked: getData()[key] ? true : null, onChange: (e) => { getData()[key] = e.target.checked; onChange?.(); } }),
    label);
  const tlsCheckbox = () => check('tls', 'Use TLS (encrypted, like port 993)', () => {
    const data = getData();
    if (['143', '993'].includes(data.port)) data.port = data.tls ? '993' : '143';   // standard IMAP ports only
    redraw();
  });
  const verifyCheckbox = () => getData().tls && check('tls_verify', 'Verify the server certificate (untick for a self-signed one)');
  return { field, text, check, tlsCheckbox, verifyCheckbox };
}
