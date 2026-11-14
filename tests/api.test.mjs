import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.fetch = async () => { throw new TypeError('Failed to fetch'); };
const { api, ApiError } = await import('../mailweb/web/static/js/api.js');

test('a network failure becomes an explanatory ApiError', async () => {
  await assert.rejects(api.addAccount({ host: 'h' }), (error) =>
    error instanceof ApiError && /No reply from the mailweb server/.test(error.message) && !/Failed to fetch/.test(error.message));
});

test('server errors keep their own message', async () => {
  globalThis.fetch = async () => ({ ok: false, status: 502, statusText: 'Bad Gateway', json: async () => ({ error: 'IMAP error: x' }) });
  await assert.rejects(api.accounts(), /IMAP error: x/);
});
