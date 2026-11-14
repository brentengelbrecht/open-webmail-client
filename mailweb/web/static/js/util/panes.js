// Pane sizes: defaults and the rules that keep every pane usable. Pure, so it is easy to test.
export const DEFAULT_PANES = { sidebar: 240, listWidth: 480, listHeight: 320 };

const GUTTER = 64;          // account gutter width (px), keep in sync with app.css
const TOPBAR = 56;          // top bar height (px)
const MIN = { sidebar: 150, listWidth: 260, listHeight: 110, readerWidth: 320, readerHeight: 140 };
const MAX_SIDEBAR = 420;

const clamp = (value, lo, hi) => Math.round(Math.min(Math.max(value, lo), Math.max(lo, hi)));
const numberOr = (value, fallback) => (Number.isFinite(value) ? value : fallback);

export function clampPanes(panes, { width, height }) {
  const sidebar = clamp(numberOr(panes.sidebar, DEFAULT_PANES.sidebar), MIN.sidebar, MAX_SIDEBAR);
  return {
    sidebar,
    listWidth: clamp(numberOr(panes.listWidth, DEFAULT_PANES.listWidth), MIN.listWidth, width - GUTTER - sidebar - MIN.readerWidth),
    listHeight: clamp(numberOr(panes.listHeight, DEFAULT_PANES.listHeight), MIN.listHeight, height - TOPBAR - MIN.readerHeight),
  };
}
