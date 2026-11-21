import { dropIndex } from '../util/reorder.js';

const THRESHOLD = 5;      // pixels of movement before a press counts as a drag (less is still a click)

// Lets the user drag each of `buttons` up and down to put them in a new order, with the others making room as it
// moves. `onMove(from, to, { keyboard })` is called once, on drop (or for Alt+Up / Alt+Down). Returns
// { justDragged() }: true right after a drag, so the click that follows the drop can be ignored.
export function attachVerticalReorder(buttons, { container, onMove }) {
  let justDragged = false;

  buttons.forEach((button, index) => {
    let press = null;

    button.addEventListener('pointerdown', (event) => {
      if (event.button !== 0 || buttons.length < 2) return;
      press = { pointerId: event.pointerId, startY: event.clientY, rects: buttons.map((b) => b.getBoundingClientRect()), dragging: false, to: index };
      try { button.setPointerCapture(event.pointerId); } catch { /* not capturable: moves still arrive while over the button */ }
    });

    button.addEventListener('pointermove', (event) => {
      if (!press || event.pointerId !== press.pointerId) return;
      const dy = event.clientY - press.startY;
      if (!press.dragging) {
        if (Math.abs(dy) < THRESHOLD) return;
        press.dragging = true;
        button.classList.add('dragging');
        container?.classList.add('reordering');
      }
      // Follow the pointer, but stay between the first and the last slot.
      const { rects } = press;
      const clamped = Math.min(Math.max(dy, rects[0].top - rects[index].top), rects[rects.length - 1].top - rects[index].top);
      button.style.transform = `translateY(${clamped}px)`;

      const centers = rects.map((rect) => rect.top + rect.height / 2);
      const to = dropIndex(centers, index, centers[index] + clamped);
      press.to = to;
      const slot = centers[1] - centers[0];                          // distance from one item to the next
      buttons.forEach((other, i) => {
        if (i === index) return;
        let shift = 0;
        if (index < i && i <= to) shift = -slot;                     // dragged downwards past this one: it moves up
        else if (to <= i && i < index) shift = slot;                 // dragged upwards past this one: it moves down
        other.style.transform = shift ? `translateY(${shift}px)` : '';
      });
    });

    const finish = (event, cancelled) => {
      if (!press || event.pointerId !== press.pointerId) return;
      const { dragging, to } = press;
      press = null;
      try { button.releasePointerCapture(event.pointerId); } catch { /* already released */ }
      if (!dragging) return;
      justDragged = true;
      setTimeout(() => { justDragged = false; }, 0);                 // the click that follows the drop is ignored
      buttons.forEach((b) => { b.style.transform = ''; b.classList.remove('dragging'); });
      container?.classList.remove('reordering');
      if (!cancelled && to !== index) onMove(index, to, { keyboard: false });
    };
    button.addEventListener('pointerup', (event) => finish(event, false));
    button.addEventListener('pointercancel', (event) => finish(event, true));

    // Keyboard: Alt+Up / Alt+Down moves the focused item one place.
    button.addEventListener('keydown', (event) => {
      if (!event.altKey || (event.key !== 'ArrowUp' && event.key !== 'ArrowDown')) return;
      const to = index + (event.key === 'ArrowUp' ? -1 : 1);
      if (to < 0 || to >= buttons.length) return;
      event.preventDefault();
      onMove(index, to, { keyboard: true });
    });
  });

  return { justDragged: () => justDragged };
}
