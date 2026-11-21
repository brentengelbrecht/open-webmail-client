// Pure helpers for drag-to-reorder lists.
export function moveItem(list, from, to) {
  const copy = [...list];
  const [item] = copy.splice(from, 1);
  copy.splice(to, 0, item);
  return copy;
}

// Where a dragged item lands: `centers` are the vertical centres of all items before the drag, `from` is the dragged
// one, and `y` is where its centre is now. It lands after every other item whose centre is above `y`.
export function dropIndex(centers, from, y) {
  return centers.filter((center, index) => index !== from && center < y).length;
}
