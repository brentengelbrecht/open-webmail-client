import { h, render } from '../util/dom.js';

export function mountLogin(root, { notice, onSubmit }) {
  const error = h('p', { class: 'form-error', role: 'alert' });
  const password = h('input', { type: 'password', placeholder: 'Password', autocomplete: 'current-password', required: true, autofocus: true });
  const button = h('button', { type: 'submit' }, 'Sign in');
  const form = h('form', {
    class: 'login-card',
    onSubmit: async (event) => {
      event.preventDefault();
      error.textContent = '';
      button.disabled = true;
      button.replaceChildren(h('span', { class: 'spinner small on-accent' }), 'Signing in…');
      try {
        await onSubmit(password.value);
      } catch (e) {
        error.textContent = e.message;
        password.select();
      } finally {
        button.disabled = false;
        button.replaceChildren('Sign in');
      }
    },
  }, h('h1', {}, 'Open Webmail Client'), notice && h('p', { class: 'muted' }, notice), password, button, error);
  render(root, h('div', { class: 'login' }, form));
  password.focus();
}
