import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.location = { hash: '', replace() {} };
const { moveItem, dropIndex } = await import('../mailweb/web/static/js/util/reorder.js');
const { attachVerticalReorder } = await import('../mailweb/web/static/js/components/dragReorder.js');
const { createStore } = await import('../mailweb/web/static/js/store.js');
const { createActions } = await import('../mailweb/web/static/js/actions.js');
const { parseHash } = await import('../mailweb/web/static/js/router.js');

test('moveItem and dropIndex', () => {
  assert.deepEqual(moveItem(['a', 'b', 'c', 'd'], 0, 2), ['b', 'c', 'a', 'd']);
  assert.deepEqual(moveItem(['a', 'b', 'c', 'd'], 3, 1), ['a', 'd', 'b', 'c']);
  assert.deepEqual(moveItem(['a', 'b'], 1, 1), ['a', 'b']);
  const centers = [20, 74, 128, 182];                       // 44 px buttons, 10 px apart
  assert.equal(dropIndex(centers, 0, 100), 1);              // first item dragged to between the 2nd and 3rd
  assert.equal(dropIndex(centers, 3, 60), 1);               // last item dragged up between the 1st and 2nd
  assert.equal(dropIndex(centers, 1, 74), 1);               // not moved
  assert.equal(dropIndex(centers, 0, -500), 0);
  assert.equal(dropIndex(centers, 0, 9999), 3);
});

// --- the pointer handling, driven with stand-in buttons ------------------------------------------------------------
function fakeButtons(count, { size = 44, gap = 10, top = 100 } = {}) {
  return Array.from({ length: count }, (_, i) => {
    const listeners = {};
    const classes = new Set();
    return {
      style: {}, listeners, classes, captured: null,
      classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c) },
      addEventListener: (type, fn) => { listeners[type] = fn; },
      getBoundingClientRect: () => ({ top: top + i * (size + gap), height: size }),
      setPointerCapture(id) { this.captured = id; },
      releasePointerCapture() { this.captured = null; },
    };
  });
}
const fire = (button, type, props = {}) => button.listeners[type]({ pointerId: 1, button: 0, preventDefault() {}, ...props });
const container = () => { const classes = new Set(); return { classes, classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c) } }; };

function setupDrag(count = 4) {
  const buttons = fakeButtons(count);
  const moves = [];
  const box = container();
  const reorder = attachVerticalReorder(buttons, { container: box, onMove: (from, to, options) => moves.push([from, to, options.keyboard]) });
  return { buttons, moves, reorder, box };
}

test('a press without movement is a click, not a drag', () => {
  const { buttons, moves, reorder } = setupDrag();
  fire(buttons[1], 'pointerdown', { clientY: 170 });
  fire(buttons[1], 'pointermove', { clientY: 172 });                     // 2 px: under the threshold
  fire(buttons[1], 'pointerup', { clientY: 172 });
  assert.deepEqual(moves, []);
  assert.equal(reorder.justDragged(), false);
  assert.equal(buttons[1].style.transform, undefined);
});

test('dragging down past one neighbour moves the item one place, and the neighbour makes room while dragging', () => {
  const { buttons, moves, box } = setupDrag();
  fire(buttons[0], 'pointerdown', { clientY: 120 });
  fire(buttons[0], 'pointermove', { clientY: 160 });                     // 40 px down: centre 122 -> 162, past item 1 (centre 176)? not yet
  assert.equal(buttons[1].style.transform, '', 'not past it yet: nothing shifts');
  fire(buttons[0], 'pointermove', { clientY: 185 });                     // 65 px down: centre 187, past item 1 (176), not item 2 (230)
  assert.ok(buttons[0].classes.has('dragging') && box.classes.has('reordering'));
  assert.equal(buttons[0].style.transform, 'translateY(65px)');
  assert.equal(buttons[1].style.transform, 'translateY(-54px)', 'the neighbour moves up into the gap');
  assert.equal(buttons[2].style.transform, '');
  fire(buttons[0], 'pointerup', { clientY: 185 });
  assert.deepEqual(moves, [[0, 1, false]]);
  assert.ok(buttons.every((b) => !b.style.transform && !b.classes.has('dragging')), 'visual state is reset on drop');
  assert.equal(box.classes.has('reordering'), false);
});

test('dragging up works the other way round, and the item cannot leave the list', () => {
  const { buttons, moves } = setupDrag();
  fire(buttons[3], 'pointerdown', { clientY: 290 });
  fire(buttons[3], 'pointermove', { clientY: 200 });                     // 90 px up: centre 194, past item 2 (230) but not item 1 (176)
  assert.equal(buttons[2].style.transform, 'translateY(54px)');
  assert.equal(buttons[1].style.transform, '');
  fire(buttons[3], 'pointermove', { clientY: 170 });                     // 120 px up: centre 164, past items 2 and 1, not item 0 (122)
  assert.equal(buttons[1].style.transform, 'translateY(54px)');
  assert.equal(buttons[2].style.transform, 'translateY(54px)');
  assert.equal(buttons[0].style.transform, '');
  fire(buttons[3], 'pointermove', { clientY: -900 });                    // far above the list: clamped to the first slot
  assert.equal(buttons[3].style.transform, `translateY(${100 - 262}px)`);
  fire(buttons[3], 'pointerup', { clientY: -900 });
  assert.deepEqual(moves, [[3, 0, false]]);
});

test('dropping where it started, or a cancelled drag, changes nothing — but the following click is still swallowed', () => {
  const { buttons, moves, reorder } = setupDrag();
  fire(buttons[1], 'pointerdown', { clientY: 170 });
  fire(buttons[1], 'pointermove', { clientY: 180 });
  fire(buttons[1], 'pointermove', { clientY: 170 });
  fire(buttons[1], 'pointerup', { clientY: 170 });
  assert.deepEqual(moves, []);
  assert.equal(reorder.justDragged(), true);
  fire(buttons[2], 'pointerdown', { clientY: 230 });
  fire(buttons[2], 'pointermove', { clientY: 300 });
  fire(buttons[2], 'pointercancel', { clientY: 300 });
  assert.deepEqual(moves, []);
  assert.ok(buttons.every((b) => !b.style.transform));
});

test('the click after a drop is ignored only for that moment', async () => {
  const { buttons, reorder } = setupDrag();
  fire(buttons[0], 'pointerdown', { clientY: 120 });
  fire(buttons[0], 'pointermove', { clientY: 190 });
  fire(buttons[0], 'pointerup', { clientY: 190 });
  assert.equal(reorder.justDragged(), true);
  await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(reorder.justDragged(), false, 'a later, real click works again');
});

test('with a single account there is nothing to drag; other mouse buttons and keys are ignored', () => {
  const { buttons, moves } = setupDrag(1);
  fire(buttons[0], 'pointerdown', { clientY: 120 });
  fire(buttons[0], 'pointermove', { clientY: 190 });
  fire(buttons[0], 'pointerup', { clientY: 190 });
  assert.deepEqual(moves, []);
  const many = setupDrag();
  fire(many.buttons[0], 'pointerdown', { clientY: 120, button: 2 });
  fire(many.buttons[0], 'pointermove', { clientY: 190 });
  assert.equal(many.buttons[0].classes.has('dragging'), false);
});

test('Alt+Arrow moves the focused item one place, within the list', () => {
  const { buttons, moves } = setupDrag(3);
  let prevented = 0;
  const key = (button, k, altKey = true) => fire(button, 'keydown', { key: k, altKey, preventDefault: () => { prevented += 1; } });
  key(buttons[1], 'ArrowUp');
  key(buttons[1], 'ArrowDown');
  key(buttons[0], 'ArrowUp');                 // already first
  key(buttons[2], 'ArrowDown');               // already last
  key(buttons[1], 'ArrowUp', false);          // no Alt: left alone
  key(buttons[1], 'Enter');
  assert.deepEqual(moves, [[1, 0, true], [1, 2, true]]);
  assert.equal(prevented, 2);
});

// --- saving the order ---------------------------------------------------------------------------------------------
const acct = (id) => ({ id, name: id.toUpperCase(), host: 'h', user: 'u', port: 1, tls: false, tls_verify: true });
function setupActions({ failSave = false } = {}) {
  const saved = [];
  const api = { reorderAccounts: async (order) => {          // behaves like the server: known ids first, the rest after them
    saved.push(order);
    if (failSave) throw new Error('nope');
    const known = ['a', 'b', 'c'];
    return { accounts: [...order.filter((id) => known.includes(id)), ...known.filter((id) => !order.includes(id))].map(acct) };
  } };
  const idle = { status: 'idle', data: null, error: null };
  const store = createStore({ accounts: ['a', 'b', 'c'].map(acct), accountIcons: {}, route: parseHash(''), list: idle, message: idle, folders: [],
    authenticated: true, panes: {}, layout: 'right' });
  return { store, saved, actions: createActions(store, api, {}) };
}

test('reordering shows the new order at once and saves it', async () => {
  const { store, saved, actions } = setupActions();
  const pending = actions.reorderAccounts(['c', 'a', 'b']);
  assert.deepEqual(store.get().accounts.map((a) => a.id), ['c', 'a', 'b'], 'optimistic');
  await pending;
  assert.deepEqual(saved, [['c', 'a', 'b']]);
  assert.deepEqual(store.get().accounts.map((a) => a.id), ['c', 'a', 'b']);
});

test('if the order cannot be saved, the saved order is shown again', async () => {
  const { store, actions } = setupActions({ failSave: true });
  const originalError = console.error;
  console.error = () => {};
  try {
    await actions.reorderAccounts(['b', 'c', 'a']);
  } finally {
    console.error = originalError;
  }
  assert.deepEqual(store.get().accounts.map((a) => a.id), ['a', 'b', 'c']);
});

test('accounts missing from the new order are kept, unknown ids ignored', async () => {
  const { store, actions } = setupActions();
  await actions.reorderAccounts(['zzz', 'c']);
  assert.deepEqual(store.get().accounts.map((a) => a.id), ['c', 'a', 'b']);
});
