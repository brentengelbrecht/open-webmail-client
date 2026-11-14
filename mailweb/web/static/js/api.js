// The only module that talks to the server. Components never call fetch().
export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

const unauthorizedHandlers = [];
export const onUnauthorized = (fn) => unauthorizedHandlers.push(fn);

function queryString(params = {}) {
  const clean = Object.entries(params)
    .filter(([, v]) => v !== null && v !== undefined && v !== '' && v !== false)
    .map(([k, v]) => [k, v === true ? '1' : String(v)]);
  return clean.length ? `?${new URLSearchParams(clean)}` : '';
}

async function request(path, { method = 'GET', params, body } = {}) {
  let response;
  try {
    response = await fetch(path + queryString(params), {
      method,
      credentials: 'same-origin',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    // fetch() only throws when there was no HTTP reply at all (server stopped, connection cut, blocked).
    throw new ApiError('No reply from the mailweb server. Is it still running? Check the terminal where run.py was started.', 0);
  }
  if (!response.ok) {
    let message = response.statusText;
    try { message = (await response.json()).error || message; } catch { /* not JSON */ }
    if (response.status === 401 && path !== '/api/login') unauthorizedHandlers.forEach((fn) => fn());
    throw new ApiError(message, response.status);
  }
  return response.json();
}

export const api = {
  accounts: () => request('/api/accounts'),
  addAccount: (details) => request('/api/accounts', { method: 'POST', body: details }),
  removeAccount: (id) => request('/api/accounts', { method: 'DELETE', params: { id } }),
  session: () => request('/api/session'),
  login: (password) => request('/api/login', { method: 'POST', body: { password } }),
  logout: () => request('/api/logout', { method: 'POST' }),
  folders: ({ account, refresh }) => request('/api/folders', { params: { account, refresh } }),
  messages: ({ account, folder, page, q, refresh }) => request('/api/messages', { params: { account, folder, page, q, refresh } }),
  message: ({ account, folder, uid }) => request('/api/message', { params: { account, folder, uid } }),
};

// URLs the browser loads directly (iframe / downloads).
const link = (path, params) => path + queryString(params);
export const urls = {
  body: (account, folder, uid, images = false) => link('/api/message/body', { account, folder, uid, images }),
  attachment: (account, folder, uid, index) => link('/api/message/attachment', { account, folder, uid, index }),
  raw: (account, folder, uid) => link('/api/message/raw', { account, folder, uid }),
};
