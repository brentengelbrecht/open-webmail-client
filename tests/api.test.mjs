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

test('a cancelled request is passed through untouched, and the signal reaches fetch', async () => {
  let seen;
  globalThis.fetch = async (url, options) => { seen = options.signal; throw Object.assign(new Error('The operation was aborted.'), { name: 'AbortError' }); };
  const controller = new AbortController();
  await assert.rejects(api.messages({ account: 'a', folder: 'INBOX', signal: controller.signal }), (error) =>
    error.name === 'AbortError' && !(error instanceof ApiError));
  assert.equal(seen, controller.signal);
});
