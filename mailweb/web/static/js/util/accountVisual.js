// How an account is drawn when it has no custom icon: a stable colour and its first letter.
export const accountColor = (id) => `hsl(${[...id].reduce((sum, ch) => (sum * 31 + ch.charCodeAt(0)) % 360, 7)} 55% 45%)`;
export const accountInitial = (name) => (name.trim()[0] || '?').toUpperCase();

// Custom icons live in localStorage under one key per account, so removing an account can erase exactly its own.
export const ICON_KEY_PREFIX = 'icon.';
export const iconKey = (accountId) => `${ICON_KEY_PREFIX}${accountId}`;

// Only image data URLs are ever used as an icon source.
export const isIconData = (value) => typeof value === 'string' && value.startsWith('data:image/');
