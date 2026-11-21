// Turn a picked image or SVG into a small square icon (a data URL) that fits comfortably in localStorage.
//
// The file is read with FileReader and handled as a data: URL, never a blob: URL: the app's Content-Security-Policy
// allows images from 'self' and data: only, so an <img> pointing at a blob: URL is refused and reports a load error.
export const ICON_SIZE = 128;                 // shown at 44-72 px, so this is sharp on high-density screens
export const MAX_FILE_BYTES = 10 * 1024 * 1024;
const SVG_RENDER_SIZE = 512;                  // SVGs are given this size on their long side before being drawn

// Largest centred square inside a width x height image ("cover" crop).
export function coverRect(width, height) {
  const side = Math.min(width, height);
  return { sx: Math.round((width - side) / 2), sy: Math.round((height - side) / 2), side };
}

// Make an SVG render as a standalone image in every browser: it needs the SVG namespace and a size, and
// many hand-made or exported SVGs have neither. Returns the adjusted SVG text.
export function normalizeSvg(text, target = SVG_RENDER_SIZE) {
  const match = /<svg\b[^>]*>/i.exec(text);
  if (!match) throw new Error('That does not look like an SVG file.');
  const tag = match[0];
  const attribute = (name) => {
    const found = new RegExp(`\\s${name}\\s*=\\s*("([^"]*)"|'([^']*)')`, 'i').exec(tag);
    return found ? (found[2] ?? found[3]) : null;
  };
  const length = (value) => {                                   // only plain or px lengths; "100%" and "2em" do not count
    const found = /^\s*([0-9]*\.?[0-9]+)\s*(px)?\s*$/i.exec(value ?? '');
    return found ? parseFloat(found[1]) : null;
  };
  let viewBox = (attribute('viewBox') ?? '').trim().split(/[\s,]+/).map(Number);
  if (viewBox.length !== 4 || viewBox.some((n) => !Number.isFinite(n)) || viewBox[2] <= 0 || viewBox[3] <= 0) viewBox = null;
  const width = length(attribute('width'));
  const height = length(attribute('height'));
  if (!viewBox && width && height) viewBox = [0, 0, width, height];      // lets the content scale with the new size
  const ratio = viewBox ? viewBox[2] / viewBox[3] : (width && height ? width / height : 1);
  const outWidth = ratio >= 1 ? target : Math.round(target * ratio);
  const outHeight = ratio >= 1 ? Math.round(target / ratio) : target;

  let fresh = tag.replace(/\s(width|height|viewBox)\s*=\s*("[^"]*"|'[^']*')/gi, '');
  const extra = [`width="${outWidth}"`, `height="${outHeight}"`];
  if (viewBox) extra.push(`viewBox="${viewBox.join(' ')}"`);
  if (!/\sxmlns\s*=/i.test(fresh)) extra.push('xmlns="http://www.w3.org/2000/svg"');
  fresh = fresh.replace(/\s*\/?>$/, (end) => ` ${extra.join(' ')}${end.trim()}`);
  return text.replace(tag, fresh);
}

const isSvg = (file) => file.type === 'image/svg+xml' || /\.svg$/i.test(file.name || '');

function read(file, method) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('That file could not be read.'));
    reader[method](file);
  });
}

function loadImage(source, what) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`That ${what} could not be displayed by this browser. Try a PNG, JPEG, WebP or SVG.`));
    image.src = source;
  });
}

// The image as a data: URL the browser can display (an SVG is normalised first).
async function toDataUrl(file) {
  if (isSvg(file)) {
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(normalizeSvg(await read(file, 'readAsText')))}`;
  }
  if (!file.type.startsWith('image/')) throw new Error('Please choose an image or an SVG file.');
  return read(file, 'readAsDataURL');
}

export async function resizeToSquare(file, size = ICON_SIZE) {
  if (file.size > MAX_FILE_BYTES) throw new Error('That file is too large (limit 10 MB).');
  const image = await loadImage(await toDataUrl(file), isSvg(file) ? 'SVG' : 'image');
  const { sx, sy, side } = coverRect(image.naturalWidth || image.width, image.naturalHeight || image.height);
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const context = canvas.getContext('2d');
  context.imageSmoothingQuality = 'high';
  context.drawImage(image, sx, sy, side, side, 0, 0, size, size);        // transparency is kept
  return canvas.toDataURL('image/webp', 0.9);                              // browsers without WebP fall back to PNG
}
