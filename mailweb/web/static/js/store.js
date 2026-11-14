// Minimal observable store. Components subscribe to a slice and re-render only when it changes.
export const shallowEqual = (a, b) =>
  Object.is(a, b) || (Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((v, i) => Object.is(v, b[i])));

export function createStore(initial) {
  let state = initial;
  const subscribers = new Set();
  const store = {
    get: () => state,
    set(patch) {
      state = { ...state, ...patch };
      subscribers.forEach((notify) => notify());
    },
    select(selector, callback, equals = shallowEqual) {
      let last;
      let first = true;
      const notify = () => {
        const value = selector(state);
        if (first || !equals(value, last)) {
          first = false;
          last = value;
          callback(value, state);
        }
      };
      subscribers.add(notify);
      notify();
      return () => subscribers.delete(notify);
    },
    // A view onto the store whose subscriptions can all be dropped at once (dispose()).
    scoped() {
      const unsubscribers = [];
      return {
        get: store.get,
        set: store.set,
        select: (...args) => { const stop = store.select(...args); unsubscribers.push(stop); return stop; },
        dispose: () => unsubscribers.splice(0).forEach((stop) => stop()),
      };
    },
  };
  return store;
}
