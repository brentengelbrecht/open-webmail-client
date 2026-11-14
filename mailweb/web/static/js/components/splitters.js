// Drag handles on the pane dividers: sidebar | list, and list | reader (or list / reader when stacked).
// Pointer capture keeps the drag alive over the message iframe; arrow keys and double-click also work.
import { h } from '../util/dom.js';
import { clampPanes } from '../util/panes.js';

const STEP = 16;

function splitter({ area, label, drag, nudge, reset, finish }) {
  const el = h('div', {
    class: `splitter ${area}`, role: 'separator', tabindex: '0', 'aria-label': label,
    title: `${label}. Drag, use arrow keys, or double-click to reset.`,
  });
  el.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    el.setPointerCapture(e.pointerId);
    el.classList.add('dragging');
  });
  el.addEventListener('pointermove', (e) => { if (el.hasPointerCapture(e.pointerId)) drag(e.clientX, e.clientY); });
  const stop = (e) => {
    if (!el.hasPointerCapture(e.pointerId)) return;
    el.releasePointerCapture(e.pointerId);
    el.classList.remove('dragging');
    finish();
  };
  el.addEventListener('pointerup', stop);
  el.addEventListener('pointercancel', stop);
  el.addEventListener('dblclick', reset);
  el.addEventListener('keydown', (e) => {
    const direction = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }[e.key];
    if (!direction) return;
    e.preventDefault();
    nudge(direction * STEP);
    finish();
  });
  return el;
}

export function createSplitters({ sidebar, list }, store, actions) {
  const viewport = () => ({ width: window.innerWidth, height: window.innerHeight });
  const stacked = () => store.get().layout === 'bottom';
  const listKey = () => (stacked() ? 'listHeight' : 'listWidth');
  const effective = (key) => clampPanes(store.get().panes, viewport())[key];
  const set = (key, value) => actions.setPane(key, clampPanes({ ...store.get().panes, [key]: value }, viewport())[key]);

  const sidebarSplitter = splitter({
    area: 'hs', label: 'Resize folder list',
    drag: (x) => set('sidebar', x - sidebar.getBoundingClientRect().left),
    nudge: (delta) => set('sidebar', effective('sidebar') + delta),
    reset: () => actions.resetPane('sidebar'),
    finish: () => actions.savePanes(),
  });

  const listSplitter = splitter({
    area: 'hl', label: 'Resize message list',
    drag: (x, y) => {
      const box = list.getBoundingClientRect();
      set(listKey(), stacked() ? y - box.top : x - box.left);
    },
    nudge: (delta) => set(listKey(), effective(listKey()) + delta),
    reset: () => actions.resetPane(listKey()),
    finish: () => actions.savePanes(),
  });

  // The list/reader divider changes direction with the layout.
  const orient = (layout) => {
    listSplitter.setAttribute('aria-orientation', layout === 'bottom' ? 'horizontal' : 'vertical');
    sidebarSplitter.setAttribute('aria-orientation', 'vertical');
  };
  return { elements: [sidebarSplitter, listSplitter], orient };
}
