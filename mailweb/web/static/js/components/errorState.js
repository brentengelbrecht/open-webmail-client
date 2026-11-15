import { h } from '../util/dom.js';
import { icon } from '../util/icons.js';

// Failures to reach a server get the "cloud off" icon, anything else the "alert" icon.
const CONNECTION_PROBLEM = /cannot connect|no reply|unavailable|timed out|connection|unreachable/i;

export const errorIconName = (message) => (CONNECTION_PROBLEM.test(message) ? 'cloudOff' : 'alert');

// A large grey icon with the error message under it. `compact` is for narrow panes (the folder list).
export function errorState(message, { compact = false } = {}) {
  return h('div', { class: `error-state${compact ? ' compact' : ''}`, role: 'alert' },
    icon(errorIconName(message), compact ? 40 : 96),
    h('p', {}, message));
}
