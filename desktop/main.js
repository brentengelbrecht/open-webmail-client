'use strict';
/*
 * Desktop shell for mailweb.
 *
 * Starts the frozen Python server (the sidecar, built from run.py) on 127.0.0.1:PORT, then shows
 * your unchanged web UI in a window. The web UI keeps its own sign-in screen; the master password
 * is the same password you type there. It is also what unlocks accounts.json, so the sidecar needs
 * it at start-up: we keep it in the OS keychain via Electron's safeStorage and hand it over through
 * the MAILWEB_WEB_PASSWORD environment variable (no changes to run.py needed for that).
 */
const { app, BrowserWindow, Menu, clipboard, dialog, ipcMain, safeStorage, session, shell } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');

// Fixed on purpose: the UI keeps pane sizes and layout in localStorage, which is per origin
// (host + port). A random port would reset those on every launch.
const PORT = 47831;
const ORIGIN = `http://127.0.0.1:${PORT}`;
const EXTERNAL_OK = /^(https?|mailto):/i;       // what a link in an e-mail may open outside the app
const MIN_PASSWORD = 8;

const DATA = app.getPath('userData');
const FILES = {
  ini: path.join(DATA, 'mailweb.ini'),
  accounts: path.join(DATA, 'accounts.json'),
  master: path.join(DATA, 'master.bin'),
};

const DEFAULT_INI = `# Created by the desktop app. These are the same options as the web version's mailweb.ini.
# Relative paths resolve against this folder. Restart the app after editing.
# Keep the port at ${PORT}: your saved pane sizes and layout are tied to it.
# The login password is NOT set here; the app supplies it from the OS keychain.

[web]
host = 127.0.0.1
port = ${PORT}
session_minutes = 60
accounts_file = accounts.json

[mail]
page_size = 50
message_cache = 32
index_ttl_seconds = 600
imap_timeout = 30
imap_connections = 3
load_remote_images = false

[logging]
level = INFO
file = mailweb.log
`;

let mainWindow = null;
let server = null;          // the sidecar child process
let quitting = false;
let stoppingOnPurpose = false;
let booted = false;        // false while only the password prompt exists, so closing it must not quit via window-all-closed

// ---------------------------------------------------------------- single instance
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });
  app.whenReady().then(boot);
  app.on('before-quit', () => { quitting = true; if (server) server.kill('SIGTERM'); });
  app.on('window-all-closed', () => { if (booted) app.quit(); });
}

// ---------------------------------------------------------------- sidecar
function serverExe() {
  const base = app.isPackaged ? process.resourcesPath : path.join(__dirname, 'build');
  return path.join(base, 'server', process.platform === 'win32' ? 'mailweb-server.exe' : 'mailweb-server');
}

const probe = () => new Promise((resolve) => {
  const s = net.connect({ port: PORT, host: '127.0.0.1' });
  s.once('connect', () => { s.destroy(); resolve(true); });
  s.once('error', () => { s.destroy(); resolve(false); });
});

async function waitForPortFree(ms) {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    if (!(await probe())) return true;
    await new Promise((r) => setTimeout(r, 200));
  }
  return !(await probe());
}

// Resolves { ok: true } once the port answers, or { ok: false, code, stderr } if the server exits first.
function startServer(password) {
  return new Promise((resolve) => {
    if (!fs.existsSync(FILES.ini)) fs.writeFileSync(FILES.ini, DEFAULT_INI, { mode: 0o600 });
    let stderr = '';
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      clearInterval(timer);
      resolve(result);
    };
    const child = spawn(serverExe(), ['--config', FILES.ini], {
      env: { ...process.env, MAILWEB_WEB_PASSWORD: password },
      windowsHide: true,
      stdio: ['ignore', 'ignore', 'pipe'],
    });
    server = child;
    child.stderr.on('data', (d) => { stderr = (stderr + d).slice(-8000); });
    child.once('error', (err) => finish({ ok: false, code: -1, stderr: String(err) }));
    child.on('exit', (code) => {
      if (server === child) server = null;
      if (!settled) return finish({ ok: false, code, stderr });
      if (!quitting && !stoppingOnPurpose) {
        dialog.showErrorBox('The mail server stopped', stderr.trim() || `Exit code ${code}.`);
        app.quit();
      }
    });
    const started = Date.now();
    const timer = setInterval(async () => {
      if (await probe()) finish({ ok: true });
      else if (Date.now() - started > 30000) finish({ ok: false, code: -1, stderr: 'Timed out waiting for the mail server to start.' });
    }, 200);
  });
}

function stopServer() {
  return new Promise((resolve) => {
    const child = server;
    if (!child) return resolve();
    stoppingOnPurpose = true;
    const force = setTimeout(() => child.kill('SIGKILL'), 3000);
    child.once('exit', () => { clearTimeout(force); stoppingOnPurpose = false; resolve(); });
    child.kill('SIGTERM');
  });
}

// ---------------------------------------------------------------- master password and keychain
// safeStorage keeps its key in Keychain (macOS), DPAPI (Windows) or a Linux secret store. If Linux has no
// secret store it silently falls back to a hard-coded key, which protects nothing, so we refuse to use it.
function keychainOk() {
  try {
    if (!safeStorage.isEncryptionAvailable()) return false;
    if (process.platform === 'linux') return safeStorage.getSelectedStorageBackend() !== 'basic_text';
    return true;
  } catch {
    return false;
  }
}

function loadStoredMaster() {
  if (!keychainOk() || !fs.existsSync(FILES.master)) return null;
  try { return safeStorage.decryptString(fs.readFileSync(FILES.master)); } catch { return null; }
}

function storeMaster(password) {
  if (!keychainOk()) return;       // Linux without a secret store: ask again next launch
  try { fs.writeFileSync(FILES.master, safeStorage.encryptString(password), { mode: 0o600 }); }
  catch (err) { console.error('could not store the master password:', err); }
}

// Small native window (prompt.html) outside the web UI, so the web UI itself stays untouched.
// Resolves { password } | { reset: true } | null (window closed).
function promptPassword(mode, notice) {
  return new Promise((resolve) => {
    const win = new BrowserWindow({
      width: 420, height: mode === 'create' ? 520 : 440,
      resizable: false, minimizable: false, maximizable: false, fullscreenable: false,
      show: false, autoHideMenuBar: true, title: 'Open Webmail Client',
      webPreferences: {
        preload: path.join(__dirname, 'preload.js'),
        contextIsolation: true, sandbox: true, nodeIntegration: false,
      },
    });
    win.removeMenu();
    let done = false;
    const finish = (value) => {
      if (done) return;
      done = true;
      ipcMain.removeListener('prompt:submit', onSubmit);
      ipcMain.removeListener('prompt:reset', onReset);
      resolve(value);
      if (!win.isDestroyed()) win.close();
    };
    const onSubmit = (event, password) => {
      if (event.sender === win.webContents && typeof password === 'string' && password.length >= (mode === 'create' ? MIN_PASSWORD : 1)) {
        finish({ password });
      }
    };
    const onReset = (event) => { if (event.sender === win.webContents) finish({ reset: true }); };
    ipcMain.on('prompt:submit', onSubmit);
    ipcMain.on('prompt:reset', onReset);
    win.on('closed', () => finish(null));
    win.once('ready-to-show', () => win.show());
    win.loadFile(path.join(__dirname, 'prompt.html'), { query: { mode, notice: notice || '', min: String(MIN_PASSWORD) } });
  });
}

async function confirmReset() {
  const { response } = await dialog.showMessageBox({
    type: 'warning',
    buttons: ['Delete accounts and password', 'Cancel'],
    defaultId: 1, cancelId: 1,
    message: 'Reset the master password?',
    detail: 'This deletes the mail accounts saved on this computer and the stored master password. '
          + 'Your mail on the server is not touched. You will choose a new password and add your accounts again.',
  });
  return response === 0;
}

function wipeSecrets() {
  for (const f of [FILES.accounts, FILES.master]) fs.rmSync(f, { force: true });
}

// ---------------------------------------------------------------- boot
async function boot() {
  Menu.setApplicationMenu(buildMenu());
  session.defaultSession.on('will-download', (_event, item) => {
    // Attachments and .eml arrive as Content-Disposition: attachment. Show a native Save dialog in Downloads.
    item.setSaveDialogOptions({ defaultPath: path.join(app.getPath('downloads'), item.getFilename()) });
  });

  if (!(await waitForPortFree(3000))) {
    dialog.showErrorBox('Port already in use',
      `Something is already listening on 127.0.0.1:${PORT}. Close the other copy of this app (or whatever uses that port) and try again.`);
    app.quit();
    return;
  }

  let password = loadStoredMaster();
  let fromKeychain = password !== null;
  let notice = '';
  for (;;) {
    if (password === null) {
      const mode = fs.existsSync(FILES.accounts) ? 'unlock' : 'create';
      const answer = await promptPassword(mode, notice);
      if (!answer) { app.quit(); return; }
      if (answer.reset) {
        if (await confirmReset()) { wipeSecrets(); notice = ''; }
        continue;
      }
      password = answer.password;
      fromKeychain = false;
    }
    const result = await startServer(password);
    if (result.ok) {
      if (!fromKeychain) storeMaster(password);    // only after it demonstrably worked
      break;
    }
    if (result.code === 2 && /cannot decrypt/.test(result.stderr)) {
      if (fromKeychain) fs.rmSync(FILES.master, { force: true });      // stale keychain copy
      notice = 'That password does not open the saved accounts. Try again, or reset to start over.';
      password = null;
      continue;
    }
    dialog.showErrorBox('The mail server could not start', result.stderr.trim() || `Exit code ${result.code}.`);
    app.quit();
    return;
  }
  createWindow();
}

// ---------------------------------------------------------------- main window
function openExternal(url) {
  if (EXTERNAL_OK.test(url)) shell.openExternal(url);
}

function createWindow() {
  booted = true;
  mainWindow = new BrowserWindow({
    width: 1280, height: 820, minWidth: 720, minHeight: 480,
    show: false, autoHideMenuBar: true,           // Alt reveals the menu on Windows/Linux; shortcuts still work
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  const wc = mainWindow.webContents;

  // Links inside e-mail bodies use <base target="_blank"> in a sandboxed iframe: send them to the system browser.
  wc.setWindowOpenHandler(({ url }) => { openExternal(url); return { action: 'deny' }; });
  wc.on('will-navigate', (event, url) => {
    if (new URL(url).origin !== ORIGIN) { event.preventDefault(); openExternal(url); }
  });

  // A browser gives you a right-click menu for free; an Electron window does not.
  wc.on('context-menu', (_event, params) => {
    const items = [];
    if (params.linkURL && EXTERNAL_OK.test(params.linkURL)) {
      items.push({ label: 'Open link in browser', click: () => openExternal(params.linkURL) },
                 { label: 'Copy link address', click: () => clipboard.writeText(params.linkURL) });
    }
    if (params.isEditable) {
      if (items.length) items.push({ type: 'separator' });
      items.push({ role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { type: 'separator' }, { role: 'selectAll' });
    } else if (params.selectionText) {
      if (items.length) items.push({ type: 'separator' });
      items.push({ role: 'copy' });
    }
    if (items.length) Menu.buildFromTemplate(items).popup();
  });

  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.on('closed', () => { mainWindow = null; });
  mainWindow.loadURL(ORIGIN);
}

// ---------------------------------------------------------------- menu
async function onReset() {
  if (!(await confirmReset())) return;
  quitting = true;                 // the server stopping is expected from here on
  await stopServer();
  wipeSecrets();
  app.relaunch();
  app.exit(0);
}

function buildMenu() {
  const isMac = process.platform === 'darwin';
  const tools = [
    { label: 'Show data folder', click: () => shell.showItemInFolder(fs.existsSync(FILES.ini) ? FILES.ini : DATA) },
    { label: 'Reset master password and accounts…', click: onReset },
  ];
  return Menu.buildFromTemplate([
    ...(isMac ? [{ role: 'appMenu' }] : []),
    { label: 'File', submenu: [...tools, ...(isMac ? [] : [{ type: 'separator' }, { role: 'quit' }])] },
    { role: 'editMenu' },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomIn', accelerator: 'CommandOrControl+=', visible: false },   // Ctrl/Cmd + "=" without Shift
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
        ...(app.isPackaged ? [] : [{ type: 'separator' }, { role: 'toggleDevTools' }]),
      ],
    },
    { role: 'windowMenu' },
  ]);
}
