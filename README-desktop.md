# Desktop app (Electron shell + frozen server)

Your web UI, server code and `mailweb.ini` options are unchanged. The desktop app is a thin Electron
window around the same server, which is frozen with PyInstaller and started on `127.0.0.1:47831`.

```
run.py                       one line changed: HERE also works when frozen (sys._MEIPASS)
requirements-desktop.txt     requirements.txt + pyinstaller
desktop/
  build_server.py            freezes run.py -> desktop/build/server/ (PyInstaller, one-dir)
  main.js                    starts the server, master password + keychain, window, menus
  preload.js, prompt.*       small native window for choosing / entering the master password
  package.json               electron-builder config (dmg, nsis, AppImage, deb)
.github/workflows/desktop-build.yml   builds Linux, Windows, macOS arm64 + Intel
```

Unzip over your project folder (next to `run.py`). Running `python3 run.py` the old way still works.

## Master password

- First run: a native "Choose a master password" window (min. 8 characters, with confirmation).
- It is stored with Electron `safeStorage` (macOS Keychain, Windows DPAPI, Linux secret store) in `master.bin`,
  and handed to the server through `MAILWEB_WEB_PASSWORD`. It is stored only after the server has started with it.
- Your existing sign-in screen is unchanged: you type the same password there. It also unlocks `accounts.json`.
- Linux without a secret store (`basic_text`): nothing is stored; you are asked at every launch (then again on the sign-in screen).
- Wrong or stale password: the app asks again, with a "Reset…" option. File > "Reset master password and accounts…"
  does the same any time. Reset deletes `accounts.json` and `master.bin`; mail on the server is untouched.
- IMAP passwords stay inside the encrypted `accounts.json`, not in the keychain.

## Develop and test locally

```
pip install -r requirements-desktop.txt
python desktop/build_server.py                    # builds desktop/build/server/ and smoke-tests it
cd desktop
npm install --save-dev electron electron-builder  # pins whatever is current into package.json
npm start                                         # run the app
npm run dist                                      # installers into desktop/dist/
```

Build on the OS you are targeting; PyInstaller does not cross-compile. Commit `desktop/package-lock.json` after the
first install.

## Release builds

Push a tag (`git tag v0.1.0 && git push --tags`) or run the workflow by hand; installers appear as run artifacts.
Optional signing secrets (unsigned builds work, with first-launch warnings): `MAC_CERT_P12`, `MAC_CERT_PASSWORD`,
`APPLE_ID`, `APPLE_APP_PASSWORD`, `APPLE_TEAM_ID`, `WIN_CERT_PFX`, `WIN_CERT_PASSWORD`.
Sign the macOS build if you can: keychain access is tied to the app's identity, so unsigned or re-signed builds
may prompt.

Before the first release, edit in `desktop/package.json`: `appId`, `author` (name and email; the `.deb` needs them),
and add a 1024x1024 `desktop/resources/icon.png`.

If your git repository root is a parent of the project folder, add `defaults.run.working-directory` to the workflow.

## Where things live

| OS | Folder |
|---|---|
| macOS | `~/Library/Application Support/Open Webmail Client/` |
| Windows | `%APPDATA%\Open Webmail Client\` |
| Linux | `~/.config/Open Webmail Client/` |

Contains `mailweb.ini` (created on first run; same options as before, restart to apply), `accounts.json`,
`master.bin`, `mailweb.log`, and Electron's own storage (your saved pane sizes and layout). Keep `[web] port = 47831`.
File > "Show data folder" opens it.

## Behaviour checklist (run on each OS before releasing)

- [ ] First run: create password, window opens on the sign-in screen, sign in with that password
- [ ] Add an account with **+**, quit, relaunch: still there, no extra prompt
- [ ] Folder list, paging, search, refresh
- [ ] Drag the splitters, switch layout, quit, relaunch: sizes and layout remembered
- [ ] Open a message; HTML and plain-text bodies; **Download images** toggle
- [ ] Click a link inside an e-mail: opens the system browser, not inside the app
- [ ] Download an attachment and the `.eml`: native Save dialog
- [ ] Right-click: copy, paste in the search box, copy link address
- [ ] Session expiry returns to the sign-in screen
- [ ] Reset flow; Linux without a secret service; second launch focuses the existing window

## Not included / known limits

- **Ctrl/Cmd+F find-in-page** (a browser feature) is not there yet; it needs a small find bar. Zoom and reload are.
- **Change master password**: same as the web version; it makes the old accounts file unreadable. Use Reset.
- **Tested here:** the shell logic (first run, keychain relaunch, wrong/stale password, no keychain, closing the
  prompt, reset, port in use, link filtering) was run against a mocked `electron` with the real Python server, and the
  server's exit codes were checked. The PyInstaller build, installers and real-Electron rendering were not run in
  this environment; the checklist above is how you confirm them.
- macOS notarization may need an entitlements file for the bundled Python if Apple rejects the first build.
