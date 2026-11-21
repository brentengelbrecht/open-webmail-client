// Per-browser UI preferences (layout, pane sizes, account icons). Not mail data; failures are harmless.
const PREFIX = 'mailweb.';

export function loadPref(key, fallback) {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

// Returns false when the value could not be stored (storage disabled or full).
export function savePref(key, value) {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function removePref(key) {
  try { localStorage.removeItem(PREFIX + key); } catch { /* storage unavailable */ }
}
