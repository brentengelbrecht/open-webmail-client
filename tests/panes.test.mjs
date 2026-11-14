import test from 'node:test';
import assert from 'node:assert/strict';
import { clampPanes, DEFAULT_PANES } from '../mailweb/web/static/js/util/panes.js';

const big = { width: 1600, height: 900 };

test('defaults pass through on a large window', () => {
  assert.deepEqual(clampPanes(DEFAULT_PANES, big), DEFAULT_PANES);
});

test('sidebar and list stay within limits', () => {
  assert.equal(clampPanes({ ...DEFAULT_PANES, sidebar: 10 }, big).sidebar, 150);
  assert.equal(clampPanes({ ...DEFAULT_PANES, sidebar: 9999 }, big).sidebar, 420);
  assert.equal(clampPanes({ ...DEFAULT_PANES, listWidth: 5 }, big).listWidth, 260);
});

test('the reader always keeps room', () => {
  const p = clampPanes({ sidebar: 240, listWidth: 5000, listHeight: 5000 }, { width: 1200, height: 700 });
  assert.equal(p.listWidth, 1200 - 64 - 240 - 320);       // reader keeps 320px
  assert.equal(p.listHeight, 700 - 56 - 140);              // reader keeps 140px
});

test('bad stored values fall back to defaults', () => {
  assert.deepEqual(clampPanes({ sidebar: 'x', listWidth: null }, big),
    { sidebar: 240, listWidth: 480, listHeight: 320 });
});

test('a shrinking window re-clamps without going below the minimums', () => {
  const p = clampPanes(DEFAULT_PANES, { width: 700, height: 400 });
  assert.ok(p.listWidth >= 260 && p.listHeight >= 110);
});
