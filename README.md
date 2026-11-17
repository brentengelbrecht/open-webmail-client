<p align="center">
  <img src="docs/logo.png" alt="Open Webmail Client" width="420">
</p>

# Open Webmail Client

A read-only, Gmail-style web client for [`imap_archive_server.py`](../imap_archive_server.py).
Python standard library plus `cryptography` (for the accounts file) on the server, plain ES modules in the browser. No build step.

## Run

Requires Python 3.10+ and one package, used only to encrypt the accounts file:
the simplest way, on any system, is a virtual environment:

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
```

On Raspberry Pi OS / Debian, `sudo apt install python3-cryptography` also works.
**macOS + Homebrew:** `brew install cryptography` installs into Homebrew's Python, not Apple's `/usr/bin/python3`
(which is 3.9 and can't see it). Use the venv above, creating it with Homebrew's Python
(`$(brew --prefix)/bin/python3 -m venv .venv`). If mailweb reports it cannot import `cryptography`, the message names
the Python it is running; install into that one.

1. Start your archive server as usual.
2. Edit `mailweb.ini`: set a login password for the web UI
   (`[web] password_file` recommended, or `MAILWEB_WEB_PASSWORD`). No mail account is configured here.
3. `chmod 600 mailweb.ini`, then `python3 run.py` and open http://127.0.0.1:8080.
4. Sign in, click **+** in the left gutter and follow the two-step dialog (server, then username and password).
   The connection is tested before the account is saved.

Accounts are stored in `accounts.json` (path: `[web] accounts_file`), created with mode 600 and **encrypted as a whole**
(hosts, user names and passwords). IMAP passwords have to be sent to the mail server as-is on every login, so they
cannot be hashed; they are encrypted with Fernet (AES + HMAC, tamper-evident) under a key derived from the web password
with salted scrypt. An accounts file from an earlier version is encrypted automatically on first start.
Consequences: changing the web password makes the file unreadable (the server stops with an explanation; restore the
old password or delete the file and re-add the accounts), and the protection is only as good as keeping the web password
away from the file, e.g. via `MAILWEB_WEB_PASSWORD` or a `password_file` elsewhere rather than in `mailweb.ini`
next to a copy of `accounts.json`.
Because anyone who can sign in to this web UI can make the server connect to any host and port, keep it
on a trusted network or behind HTTPS and a strong web password.

To use it from other devices set `[web] host = 0.0.0.0` and enable HTTPS (`cert`/`key`):
the login password and your mail otherwise cross the network in clear text.

Tests: `python3 -m unittest discover -s tests` spawns the real archive server on a synthetic repository
(set `IMAP_SERVER_PY` if the script is not in the parent folder); `node --test tests/actions.test.mjs tests/panes.test.mjs` checks the
front-end controller logic (account switching, routing, session expiry, pane sizing) without a browser.

## Features

Multiple accounts (gutter with **+** and one icon per account; pencil and trash icons appear when you hover the account
name above the folder list, to rename or remove it; switching clears the old mailbox and loads the new one),
folder list with unread counts, newest-first message list with paging, message view (HTML or plain text),
attachment download, `.eml` download, reading pane to the right of the list, below it, or slid in over a full-width list Gmail style (three icons at the
far right of the top bar; in the third layout the back arrow or Esc slides the message out again), a hamburger button that slides the folder list away and back (remembered; an overlay on phones), drag handles on the pane dividers (also arrow keys when focused; double-click resets; sizes and
layout are remembered in the browser), per-message remote images (or always, with `[mail] load_remote_images = true`),
errors shown as a large pale icon with the message in the pane that failed, automatic sign-out when the session ends (`[web] session_minutes`, default 60), search with Gmail-style operators
(`from: to: cc: subject: is:unread|read|starred after:YYYY-MM-DD before:YYYY-MM-DD`, quoted phrases, free words).
Search is per folder. Free words match subject and raw message text; the server's `TEXT` search looks at
undecoded bytes, so non-ASCII words are only found in subjects.

## Layout and responsibilities

```
run.py                     composition root: wires config -> gateway -> service -> app -> server
mailweb.ini                documented configuration
mailweb/
  config.py                dataclasses ARE the schema; generic validating loader
  errors.py                domain errors (web layer maps them to HTTP statuses)
  cache.py                 thread-safe LRU/TTL cache, used by the service
  accounts/                accounts added at runtime
    models.py              Account / AccountInfo (no password) + validation of user input
    crypto.py              scrypt key derivation + Fernet (the only module importing `cryptography`)
    store.py               encrypted accounts.json (atomic write, mode 600, plaintext migration)
    registry.py            add (tests the connection first) / remove / one MailService per account
  imap/                    the ONLY code that speaks IMAP
    connection.py          ImapEndpoint, ImapConnection (typed commands), ImapGateway (lock, reconnect-once)
    responses.py           parsers for LIST / STATUS / FETCH shapes
    utf7.py                modified UTF-7 folder names
  mail/                    the domain; knows nothing about HTTP
    service.py             MailService: the single API the web layer calls
    index.py               per-folder date/flags index (cheap, drives sort + paging)
    search.py              query string -> IMAP criteria (OPERATORS table)
    headers.py             header decoding shared by list and detail views
    body.py                MIME -> body document + attachments
    folders.py             folder ordering rules
    models.py              frozen dataclasses (serialised as-is to JSON)
  web/
    server.py              http.server adapter (only module touching sockets)
    app.py                 dispatch, auth gate, error->status mapping, security headers
    router.py, http.py     tiny router; Request/Response + response helpers
    sessions.py            session store + password check + cookies
    static_files.py        safe static serving
    routes/                one module per feature: auth, accounts, folders, messages
    static/img/            icon.svg (app icon + favicon, cropped to the plane, no background) and owc_logo_name.png
                           (transparent, cropped to the text; both are shown at the same height in the top bar)
    static/js/             util/ (dom, format, icons+OWC logo, prefs, panes)
                           api.js (only fetch user) · store.js · router.js · actions.js (controller)
                           components/* (views: gutter, accountDialog, splitters, header, sidebar, list, reader)
tests/                     synthetic repository + end-to-end tests
```

Data flow: component -> `actions.js` -> `api.js` -> route -> `AccountRegistry` -> `MailService` -> `ImapGateway`.
Every mail endpoint takes `?account=<id>`; `AppContext.mail_for(request)` is the single place that resolves it.
The URL hash is `#/<account>/<folder>?page=&q=&uid=`, so links and the back button work across accounts.
Each arrow crosses exactly one boundary, so a feature change touches few files.

## Speed

* Each account keeps a small pool of IMAP connections (`[mail] imap_connections`, default 3), so loading the folder
  list does not block the message list, and the browser asks for both at the same time.
* If the server supports `LIST-STATUS` (Gmail does), the folder list and every folder's counts arrive in one round trip.
* IMAP operations that take longer than a second are logged at INFO (`IMAP MailService._index... took 4.20s`); run with
  `-v` to log every one. That shows which step is slow on a given account.

## How the list stays fast

The archive server can answer `UID FLAGS INTERNALDATE RFC822.SIZE` for a whole folder from its database,
without reading message files. The client fetches that once per folder (cached, `index_ttl_seconds`),
sorts by date, and only fetches headers for the 50 messages on screen (cached forever; the archive is immutable).

## Security notes

* Message HTML is untrusted. It is served from its own endpoint with a CSP of `default-src 'none'`
  (no scripts, no remote images or fonts, no network), the CSP `sandbox` directive, and is shown in a sandboxed
  `<iframe>`. Inline `cid:` images are embedded as data URIs. Remote images are blocked by default (tracking pixels). If a message has any, a **Download images** link under
  the headers reloads just that message with `img-src` opened to http/https; nothing is remembered.
* Attachments are always sent as downloads, never rendered in the app's origin.
* Sessions are random tokens in an `HttpOnly; SameSite=Lax` cookie (`Secure` when HTTPS is on); failed logins are delayed 1 s.
  A session lasts `[web] session_minutes` from sign-in (not extended by activity). The server tells the browser how long
  is left, so the browser signs itself out at that moment; restarting the server also ends all sessions.
* The login password is compared in constant time. There is one shared account, matching the archive server.

## Removing an account (trash icon)

Order of operations, and what each step really guarantees:

1. **Server first.** The account is dropped from `accounts.json`: the replaced file's bytes are overwritten with `X` and
   fsynced before being released (the file is erased the same way when the last account goes), open IMAP connections
   are closed, and the cached folder list, indexes, headers and parsed messages are dropped. If this fails, the browser
   is left untouched.
2. **Browser memory.** Everything the page holds for the account (folders, message list, open message, route, the account
   record) is overwritten in place with `X` (numbers with 0), then replaced by empty state.
3. **Page.** Every text node and descriptive attribute is overwritten, the message iframe is unloaded, the DOM is emptied.
4. **Browser storage.** localStorage and sessionStorage entries whose key or value mention the account's id, name, host or
   user name are overwritten with `X`, then removed. mailweb itself keeps no account data there, only layout and pane-size
   preferences, which are left alone. API responses are `no-store`, so the browser's HTTP cache holds none either.
5. **URL and history.** The current address is rewritten. Earlier history entries cannot be edited by a page.
6. **Reload.** The page is reloaded, which discards the old JavaScript heap entirely.

Limits you should know about: strings are immutable in both JavaScript and Python, so "overwrite with X" replaces the
value held by a variable or property; the engine frees the old buffer later and nothing can force it to zero it. The
reload (browser) and a server restart (server) are what actually return that memory. On SSDs and journaling or
copy-on-write filesystems, overwriting a file does not guarantee the old blocks are physically erased; that needs
full-disk encryption, which also protects against everything else. Swap files and OS caches are outside the app's control.

## Extending

| To add...                       | Touch                                                                                          |
|---------------------------------|------------------------------------------------------------------------------------------------|
| a search operator               | one entry in `mail/search.py` `OPERATORS`                                                      |
| a config option                 | a field in `config.py`, a line in `mailweb.ini`                                                |
| an endpoint                     | a function in (or a new module under) `web/routes/`; list new modules in `routes/__init__.py` |
| a UI panel                      | a file in `static/js/components/`, mounted in `shell.js`; data via `actions.js` + `api.js`     |
| special folder handling         | `mail/folders.py`                                                                              |
| another icon                    | one path in `static/js/util/icons.js`                                                          |
| write features (star, labels)   | new `ImapConnection` methods (+ drop `EXAMINE` for `SELECT`), a `MailService` method, a POST route; the server must support STORE first |
| inline attachment preview, remote-image toggle | `routes/messages.py` (and a per-request CSP) |
| per-sender "always load images" | a setting read in `routes/messages.py` `_body_headers`                                         |
| account editing / reordering    | `accounts/registry.py` + `routes/accounts.py`; icons render in `components/gutter.js`          |

Known limits: one IMAP connection per account (fine for one user; requests are serialised);
the message index is rebuilt when stale or on refresh, and a large folder takes one extra round trip the first time;
list order is by the archive's internal date, as Gmail does.
