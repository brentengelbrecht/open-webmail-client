import test from 'node:test';
import assert from 'node:assert/strict';

// errorState.js imports DOM helpers lazily; only the pure icon choice is tested here.
globalThis.document = { createElement: () => ({}), createElementNS: () => ({}) };
const { errorIconName } = await import('../mailweb/web/static/js/components/errorState.js');

test('connection problems get the cloud-off icon, everything else the alert icon', () => {
  for (const message of [
    'Cannot connect to 192.168.0.145:1143: timed out. Check the address and any firewall.',
    'No reply from the mailweb server. Is it still running?',
    'IMAP server unavailable: [Errno 54] Connection reset by peer',
  ]) assert.equal(errorIconName(message), 'cloudOff', message);
  for (const message of ['no such folder: Nope', 'IMAP error: [AUTHENTICATIONFAILED] Invalid credentials'])
    assert.equal(errorIconName(message), 'alert', message);
});
