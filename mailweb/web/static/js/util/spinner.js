import { h } from './dom.js';

// A spinner with an optional label. role="status" lets screen readers announce it.
export const spinner = (label = '', { small = false } = {}) =>
  h('div', { class: 'loading', role: 'status', 'aria-live': 'polite' },
    h('span', { class: `spinner${small ? ' small' : ''}`, 'aria-hidden': 'true' }),
    label && h('span', {}, label));

export const pageSpinner = (label = 'Loading…') => h('div', { class: 'page-loading' }, spinner(label));
