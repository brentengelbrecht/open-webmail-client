// Navigation state lives in the URL hash:  #/<account>/<folder>?page=2&q=text&uid=12
export function parseHash(hash = location.hash) {
  const [path, query = ''] = hash.replace(/^#\/?/, '').split('?');
  const [account = '', folder = ''] = path.split('/');
  const params = new URLSearchParams(query);
  return {
    account: decodeURIComponent(account),
    folder: decodeURIComponent(folder),
    page: Number(params.get('page')) || 1,
    q: params.get('q') || '',
    uid: Number(params.get('uid')) || null,
  };
}

export function buildHash({ account = '', folder = '', page = 1, q = '', uid = null }) {
  const params = new URLSearchParams();
  if (page > 1) params.set('page', page);
  if (q) params.set('q', q);
  if (uid) params.set('uid', uid);
  const query = params.toString();
  return `#/${encodeURIComponent(account)}/${encodeURIComponent(folder)}${query ? `?${query}` : ''}`;
}

export const navigate = (route) => { location.hash = buildHash(route); };
export const replaceRoute = (route) => location.replace(buildHash(route));
export const onRouteChange = (callback) => window.addEventListener('hashchange', () => callback(parseHash()));
