// Inline SVG icons (Material-style 24px paths) and the OWC logo. SVG needs its own namespace.
const NS = 'http://www.w3.org/2000/svg';

function svg(attrs, ...children) {
  const el = document.createElementNS(NS, 'svg');
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  el.append(...children);
  return el;
}

function shape(tag, attrs) {
  const el = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  return el;
}

const PATHS = {
  back: 'M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z',
  attachment: 'M16.5 6v11.5c0 2.21-1.79 4-4 4s-4-1.79-4-4V5c0-1.38 1.12-2.5 2.5-2.5s2.5 1.12 2.5 2.5v10.5c0 .55-.45 1-1 1s-1-.45-1-1V6H10v9.5c0 1.38 1.12 2.5 2.5 2.5s2.5-1.12 2.5-2.5V5c0-2.21-1.79-4-4-4S7 2.79 7 5v12.5c0 3.04 2.46 5.5 5.5 5.5s5.5-2.46 5.5-5.5V6h-1.5z',
  trash: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
  signOut: 'M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5-5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z',
};

export function icon(name, size = 20) {
  return svg({ viewBox: '0 0 24 24', width: size, height: size, fill: 'currentColor', 'aria-hidden': 'true' },
    shape('path', { d: PATHS[name] }));
}

// "OWC" (Open Webmail Client) drawn as strokes, so it needs no font and follows the text colour.
export function logo(height = 26) {
  const title = shape('title', {});
  title.textContent = 'Open Webmail Client';
  const stroke = { fill: 'none', stroke: 'currentColor', 'stroke-width': 3, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' };
  return svg({ viewBox: '0 0 78 28', height, width: height * (78 / 28), role: 'img', 'aria-label': 'OWC – Open Webmail Client', class: 'logo' },
    title,
    shape('circle', { cx: 12, cy: 14, r: 10, ...stroke }),                                  // O
    shape('path', { d: 'M27 4 L32.5 24 L39 9 L45.5 24 L51 4', ...stroke }),                  // W
    shape('path', { d: 'M73 7 A10 10 0 1 0 73 21', ...stroke }));                            // C
}
