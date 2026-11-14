// Best-effort erasure of account data held by the page. Strings are immutable in JavaScript, so a value can only
// be *replaced* by "XXXX" of the same length; the engine frees the old buffer when it chooses. The strongest step is
// therefore the page reload at the end of the flow, which discards the whole JavaScript heap.
export const mask = (text) => 'X'.repeat(String(text).length);

// Overwrite every string with X's (and numbers with 0) in an object tree, in place.
export function overwriteDeep(value, seen = new WeakSet()) {
  if (value === null || typeof value !== 'object' || seen.has(value)) return;
  seen.add(value);
  for (const key of Object.keys(value)) {
    try {
      const item = value[key];
      if (typeof item === 'string') value[key] = mask(item);
      else if (typeof item === 'number') value[key] = 0;
      else overwriteDeep(item, seen);
    } catch { /* frozen or read-only: skip */ }
  }
}

// Overwrite and remove every web-storage entry whose key or value mentions one of the needles.
export function scrubStorage(storage, needles) {
  const wanted = needles.filter((n) => typeof n === 'string' && n.length >= 4);
  let removed = 0;
  try {
    const keys = Array.from({ length: storage.length }, (_, i) => storage.key(i));
    for (const key of keys) {
      const value = storage.getItem(key) ?? '';
      if (wanted.some((n) => key.includes(n) || value.includes(n))) {
        storage.setItem(key, mask(value));      // overwrite first...
        storage.removeItem(key);                // ...then release
        removed += 1;
      }
    }
  } catch { /* storage unavailable */ }
  return removed;
}

const MASKED_ATTRIBUTES = ['title', 'aria-label', 'alt', 'href', 'placeholder', 'value'];

// Overwrite all text and descriptive attributes under `root`, unload iframes, then empty it.
export function overwriteDom(root) {
  if (!root) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
  for (let node = walker.currentNode; node; node = walker.nextNode()) {
    if (node.nodeType === Node.TEXT_NODE) {
      node.data = mask(node.data);
      continue;
    }
    if (node.tagName === 'IFRAME') node.src = 'about:blank';          // unload the message document
    if ('value' in node && typeof node.value === 'string') node.value = mask(node.value);
    for (const name of MASKED_ATTRIBUTES) {
      if (node.hasAttribute(name)) node.setAttribute(name, mask(node.getAttribute(name)));
    }
  }
  root.replaceChildren();
}
