import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const { normalizeSvg, coverRect } = await import('../mailweb/web/static/js/util/iconImage.js');
const tagOf = (svg) => /<svg\b[^>]*>/i.exec(svg)[0];
const attr = (svg, name) => new RegExp(`\\s${name}="([^"]*)"`).exec(tagOf(svg))?.[1];

test('an SVG with only a viewBox gets a size, keeping its aspect ratio, and the namespace', () => {
  const out = normalizeSvg('<svg viewBox="0 0 200 100"><rect width="200" height="100"/></svg>');
  assert.equal(attr(out, 'width'), '512');
  assert.equal(attr(out, 'height'), '256');
  assert.equal(attr(out, 'viewBox'), '0 0 200 100');
  assert.match(tagOf(out), /xmlns="http:\/\/www\.w3\.org\/2000\/svg"/);
  assert.match(out, /<rect width="200" height="100"\/><\/svg>$/, 'the content is untouched');
});

test('an SVG with only width and height gets a viewBox so its content scales with the new size', () => {
  const out = normalizeSvg('<svg width="24" height="48" xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>');
  assert.equal(attr(out, 'viewBox'), '0 0 24 48');
  assert.equal([attr(out, 'width'), attr(out, 'height')].join('x'), '256x512');
  assert.equal((tagOf(out).match(/xmlns=/g) || []).length, 1, 'xmlns is not duplicated');
});

test('px units and single quotes are understood; percentages are ignored', () => {
  const px = normalizeSvg("<svg width='100px' height='50px'></svg>");
  assert.equal(attr(px, 'viewBox'), '0 0 100 50');
  const pct = normalizeSvg('<svg width="100%" height="100%" viewBox="0 0 10 10"></svg>');
  assert.equal([attr(pct, 'width'), attr(pct, 'height'), attr(pct, 'viewBox')].join('|'), '512|512|0 0 10 10');
});

test('an XML prolog, a doctype and a self-closing root are handled', () => {
  const out = normalizeSvg('<?xml version="1.0"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "x.dtd">\n<svg viewBox="0 0 8 8" />');
  assert.ok(out.startsWith('<?xml version="1.0"?>'));
  assert.match(tagOf(out), /width="512" height="512" viewBox="0 0 8 8" xmlns="http:\/\/www\.w3\.org\/2000\/svg"\/>$/);
});

test('something that is not an SVG is refused with a clear message', () => {
  assert.throws(() => normalizeSvg('<html><body>nope</body></html>'), /does not look like an SVG/);
});

test('the uploaded project icon normalises cleanly', () => {
  const svg = readFileSync(new URL('../mailweb/web/static/img/icon.svg', import.meta.url), 'utf8');
  const out = normalizeSvg(svg);
  assert.equal(attr(out, 'viewBox'), '42 29 403 271');
  assert.equal(attr(out, 'width'), '512');
});

test('the icon loader never uses blob: URLs (the Content-Security-Policy refuses them for images)', () => {
  const source = readFileSync(new URL('../mailweb/web/static/js/util/iconImage.js', import.meta.url), 'utf8');
  const code = source.split('\n').filter((line) => !line.trim().startsWith('//')).join('\n');
  assert.doesNotMatch(code, /createObjectURL|blob:/);
  assert.match(code, /FileReader/);
  assert.deepEqual(coverRect(200, 100), { sx: 50, sy: 0, side: 100 });
});

test('the pencil that opens the file picker has no native title tooltip (browsers re-show those at the pointer when the picker closes)', () => {
  const source = readFileSync(new URL('../mailweb/web/static/js/components/editAccountDialog.js', import.meta.url), 'utf8');
  const pencil = source.slice(source.indexOf("class: 'icon-edit'"), source.indexOf("class: 'sr-only'") + 60);
  assert.doesNotMatch(pencil, /\btitle:/);
  assert.match(pencil, /'data-tip'/);
  assert.doesNotMatch(pencil, /aria-label/, 'no attribute copy of the text that a browser might show as a tooltip');
  assert.match(pencil, /sr-only/, 'the accessible name is real (visually hidden) text');
});
