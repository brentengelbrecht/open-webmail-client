"""Builds a tiny synthetic repository in the importer's layout (for tests only)."""
import hashlib
import json
import sqlite3
from email.message import EmailMessage
from pathlib import Path


def _message(subject, sender, body, html=None, attachment=None, date="Tue, 03 Nov 2026 10:00:00 +0000"):
    m = EmailMessage()
    m["Subject"], m["From"], m["To"], m["Date"] = subject, sender, "me@example.com", date
    m.set_content(body)
    if html:
        m.add_alternative(html, subtype="html")
    if attachment:
        m.add_attachment(attachment, maintype="application", subtype="pdf", filename="report ü.pdf")
    return m.as_bytes(policy=m.policy.clone(linesep="\r\n"))


MESSAGES = [  # (folder names, internal_date_ms, is_read, is_starred, raw)
    (["INBOX"], 1793700000000, 0, 1, _message("Hello world", "Alice <alice@example.com>", "Plain body http://example.com/x.")),
    (["INBOX", "Réunions/2023"], 1793800000000, 1, 0,
     _message("Café ☕ meeting", "Bob <bob@example.com>", "text", html='<p>Hi <b>there</b></p><img src="https://tracker.example/p.png"><script>alert(1)</script>',
              attachment=b"%PDF-fake")),
    (["INBOX"], 1793600000000, 0, 0, _message("Older message", "carol@example.com", "old")),
]


def build(root: Path) -> Path:
    repo = root / "you%40example.com"
    (repo / "messages" / "000001").mkdir(parents=True)
    (repo / "repository.json").write_text(json.dumps({
        "application": "gmail-local-repository", "schema_version": 2, "mailbox": "you@example.com",
        "created_at": "2026-11-04T12:33:04.310412+00:00"}))
    db = sqlite3.connect(repo / "repository.db")
    db.executescript("""
        CREATE TABLE folders(folder_id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE folder_messages(folder_id INTEGER, message_id INTEGER);
        CREATE TABLE message_shards(shard_id INTEGER PRIMARY KEY, directory_name TEXT);
        CREATE TABLE messages(message_id INTEGER PRIMARY KEY, gm_id TEXT, shard_id INTEGER, filename TEXT,
            message_size INTEGER, sha256 TEXT, internal_date TEXT, imported_at TEXT, is_read INTEGER, is_starred INTEGER);
        INSERT INTO message_shards VALUES (1, '000001');
    """)
    folders = {}
    for i, (names, date_ms, read, star, raw) in enumerate(MESSAGES, start=1):
        fname = f"g{i}.eml"
        (repo / "messages" / "000001" / fname).write_bytes(raw)
        db.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (i, f"g{i}", 1, fname, len(raw), hashlib.sha256(raw).hexdigest(), str(date_ms),
                    "2026-11-04T12:00:00+00:00", read, star))
        for name in names:
            if name not in folders:
                folders[name] = len(folders) + 1
                db.execute("INSERT INTO folders VALUES (?,?)", (folders[name], name))
            db.execute("INSERT INTO folder_messages VALUES (?,?)", (folders[name], i))
    db.commit()
    db.close()
    return repo
