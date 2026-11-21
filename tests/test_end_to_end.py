"""Drives the web app against the real imap_archive_server.py using a synthetic repository.

Set IMAP_SERVER_PY to the server script (default: ../imap_archive_server.py or /mnt/user-data/uploads).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fake_repo  # noqa: E402
from harness import start_server  # noqa: E402
from mailweb.accounts import AccountRegistry, AccountStore  # noqa: E402
from mailweb.config import load_config  # noqa: E402
from mailweb.web.app import Application  # noqa: E402
from mailweb.web.context import AppContext  # noqa: E402
from mailweb.web.http import Request  # noqa: E402
from mailweb.web.sessions import Authenticator, SessionStore  # noqa: E402
from mailweb.web.static_files import StaticFiles  # noqa: E402


class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        repo = fake_repo.build(tmp)
        cls.repo = repo
        cls.server, port = start_server(tmp, repo)
        cls.port = port
        (tmp / "mailweb.ini").write_text(f"[web]\npassword = webpw\naccounts_file = accounts.json\n")
        os.chmod(tmp / "mailweb.ini", 0o600)
        cls.cfg = load_config(tmp / "mailweb.ini")
        cls.registry = AccountRegistry(AccountStore(cls.cfg.web.accounts_file, cls.cfg.web_password), cls.cfg.mail)
        auth = Authenticator(cls.cfg.web_password, SessionStore(3600), secure_cookie=False)
        cls.app = Application(AppContext(accounts=cls.registry, auth=auth),
                              StaticFiles(ROOT / "mailweb" / "web" / "static"))
        cls.cookie = cls._login(cls, "webpw")
        cls.account = cls._add(cls, "secret")["account"]["id"]

    @classmethod
    def tearDownClass(cls):
        cls.registry.close()
        cls.server.terminate()
        cls.server.wait(5)
        cls.tmp.cleanup()

    def _login(self, password):
        r = self.app.handle(Request("POST", "/api/login", body=json.dumps({"password": password}).encode()))
        return r.cookies[0].split(";")[0] if r.status == 200 else None

    def _add(self, password, **extra):
        body = {"host": "127.0.0.1", "port": self.port, "user": "me", "password": password, **extra}
        r = self.app.handle(Request("POST", "/api/accounts", headers={"cookie": self.cookie},
                                    body=json.dumps(body).encode()))
        return json.loads(r.body) if r.status == 200 else r

    def get(self, path, authed=True, **query):
        headers = {"cookie": self.cookie} if authed else {}
        if path.startswith("/api/") and "account" not in query and path not in ("/api/accounts", "/api/session"):
            query["account"] = self.account
        return self.app.handle(Request("GET", path, query={k: str(v) for k, v in query.items()}, headers=headers))

    def j(self, path, **query):
        r = self.get(path, **query)
        self.assertEqual(r.status, 200, r.body)
        return json.loads(r.body)

    def test_auth_required_and_bad_password(self):
        self.assertEqual(self.get("/api/folders", authed=False).status, 401)
        self.assertIsNone(self._login("wrong"))

    def test_static_index(self):
        self.assertIn(b"Open Webmail Client", self.get("/").body)
        self.assertEqual(self.get("/../../etc/passwd").status, 404)

    def test_brand_assets_are_served_and_prepared_for_the_ui(self):
        icon = self.get("/img/icon.svg", authed=False)
        self.assertEqual((icon.status, icon.headers["Content-Type"]), (200, "image/svg+xml"))
        text = icon.body.decode()
        self.assertNotIn("<rect", text)                                  # no white box behind the plane
        self.assertIn('viewBox="42 29 403 271"', text)                   # cropped to the plane: height == image height
        logo = self.get("/img/owc_logo_name.png", authed=False)
        self.assertEqual((logo.status, logo.headers["Content-Type"]), (200, "image/png"))
        self.assertTrue(logo.body.startswith(b"\x89PNG"))
        self.assertIn(b'rel="icon"', self.get("/", authed=False).body)

    def test_the_policy_allows_the_data_urls_the_icon_picker_uses_and_no_blob_urls(self):
        policy = self.get("/", authed=False).headers["Content-Security-Policy"]
        img_src = next(part for part in policy.split(";") if part.strip().startswith("img-src"))
        self.assertIn("data:", img_src)
        self.assertNotIn("blob:", img_src)
        loader = self.get("/js/util/iconImage.js", authed=False).body.decode()
        self.assertNotIn("createObjectURL", loader)

    def test_folders(self):
        names = [f["name"] for f in self.j("/api/folders")["folders"]]
        self.assertEqual(names, ["INBOX", "Réunions/2023"])

    def test_list_sorted_newest_first(self):
        page = self.j("/api/messages", folder="INBOX")
        self.assertEqual([m["subject"] for m in page["items"]], ["Café ☕ meeting", "Hello world", "Older message"])
        self.assertEqual(page["total"], 3)
        by = {m["subject"]: m for m in page["items"]}
        self.assertTrue(by["Hello world"]["unread"] and by["Hello world"]["starred"])
        self.assertTrue(by["Café ☕ meeting"]["has_attachments"])
        self.assertEqual(by["Hello world"]["sender"]["name"], "Alice")

    def test_non_ascii_folder_and_search(self):
        self.assertEqual(self.j("/api/messages", folder="Réunions/2023")["total"], 1)
        self.assertEqual(self.j("/api/messages", folder="INBOX", q="from:alice")["total"], 1)
        self.assertEqual(self.j("/api/messages", folder="INBOX", q="is:unread")["total"], 2)
        self.assertEqual(self.j("/api/messages", folder="INBOX", q="Café")["total"], 1)

    def test_unknown_folder_and_bad_query(self):
        self.assertEqual(self.get("/api/messages", folder="Nope").status, 404)
        self.assertEqual(self.get("/api/messages", folder="INBOX", q="is:bogus").status, 400)

    def test_detail_body_attachment_raw(self):
        items = self.j("/api/messages", folder="INBOX")["items"]
        uid = next(m["uid"] for m in items if m["subject"].startswith("Café"))
        detail = self.j("/api/message", folder="INBOX", uid=uid)
        self.assertEqual(detail["attachments"][0]["filename"], "report ü.pdf")
        self.assertEqual(len(detail["attachments"]), 1)
        body = self.get("/api/message/body", folder="INBOX", uid=uid)
        self.assertIn(b"<b>there</b>", body.body)
        self.assertIn("default-src 'none'", body.headers["Content-Security-Policy"])
        att = self.get("/api/message/attachment", folder="INBOX", uid=uid, index=0)
        self.assertEqual(att.body, b"%PDF-fake")
        self.assertIn("attachment", att.headers["Content-Disposition"])
        self.assertTrue(self.get("/api/message/raw", folder="INBOX", uid=uid).body.startswith(b"Content-Type")
                        or b"Subject:" in self.get("/api/message/raw", folder="INBOX", uid=uid).body)

    def test_plain_text_linkified(self):
        uid = next(m["uid"] for m in self.j("/api/messages", folder="INBOX")["items"] if m["subject"] == "Hello world")
        body = self.get("/api/message/body", folder="INBOX", uid=uid).body.decode()
        self.assertIn('<a href="http://example.com/x"', body)

    def test_missing_message(self):
        self.assertEqual(self.get("/api/message", folder="INBOX", uid=9999).status, 404)

    def test_survives_server_side_disconnect(self):
        self.j("/api/messages", folder="INBOX")
        gateway = self.registry._services[self.account][0]
        for conn in gateway._idle:
            conn._client.sock.close()               # simulate dropped connections
        self.assertEqual(self.j("/api/messages", folder="INBOX", refresh=1)["total"], 3)

    def test_remote_images_blocked_until_requested(self):
        uid = next(m["uid"] for m in self.j("/api/messages", folder="INBOX")["items"] if m["subject"].startswith("Café"))
        self.assertTrue(self.j("/api/message", folder="INBOX", uid=uid)["remote_images_blocked"])
        blocked = self.get("/api/message/body", folder="INBOX", uid=uid).headers["Content-Security-Policy"]
        allowed = self.get("/api/message/body", folder="INBOX", uid=uid, images=1).headers["Content-Security-Policy"]
        self.assertIn("img-src data:;", blocked)
        self.assertIn("img-src data: http: https:;", allowed)
        plain = next(m["uid"] for m in self.j("/api/messages", folder="INBOX")["items"] if m["subject"] == "Hello world")
        self.assertFalse(self.j("/api/message", folder="INBOX", uid=plain)["remote_images_blocked"])

    def test_load_remote_images_option_allows_images_without_asking(self):
        import dataclasses
        settings = dataclasses.replace(self.cfg.mail, load_remote_images=True)
        registry = AccountRegistry(AccountStore(Path(self.tmp.name) / "opt.json", "webpw"), settings)
        try:
            auth = Authenticator("webpw", SessionStore(60), secure_cookie=False)
            app = Application(AppContext(accounts=registry, auth=auth), StaticFiles(ROOT / "mailweb" / "web" / "static"))
            cookie = app.handle(Request("POST", "/api/login", body=b'{"password": "webpw"}')).cookies[0].split(";")[0]
            account = registry.add({"host": "127.0.0.1", "port": self.port, "user": "me", "password": "secret"}).id
            def get(path, **q):
                return app.handle(Request("GET", path, query={"account": account, "folder": "INBOX", **{k: str(v) for k, v in q.items()}},
                                          headers={"cookie": cookie}))
            uid = next(m["uid"] for m in json.loads(get("/api/messages").body)["items"] if m["subject"].startswith("Café"))
            self.assertFalse(json.loads(get("/api/message", uid=uid).body)["remote_images_blocked"])
            self.assertIn("img-src data: http: https:", get("/api/message/body", uid=uid).headers["Content-Security-Policy"])
        finally:
            registry.close()

    def test_session_endpoint_reports_time_left(self):
        r = json.loads(self.get("/api/session", authed=True).body)
        self.assertTrue(r["authenticated"])
        self.assertTrue(0 < r["expires_in"] <= 3600)

    def test_accounts_api(self):
        listed = self.j("/api/accounts")["accounts"]
        self.assertEqual([a["id"] for a in listed], [self.account])
        self.assertNotIn("password", listed[0])
        self.assertEqual(self.get("/api/folders", account="nope").status, 404)
        self.assertEqual(self.get("/api/folders", account="").status, 400)

    def test_bad_credentials_and_validation_do_not_add(self):
        bad = self._add("wrong")
        self.assertEqual(bad.status, 502)
        self.assertEqual(self._add("x", port="abc").status, 400)
        self.assertEqual(len(self.j("/api/accounts")["accounts"]), 1)

    def test_rename_account(self):
        def patch(body):
            return self.app.handle(Request("PATCH", "/api/accounts", headers={"cookie": self.cookie},
                                           body=json.dumps(body).encode()))
        other = self._add("secret", name="Before")["account"]["id"]
        r = patch({"id": other, "name": "  My   Gmail  "})
        self.assertEqual(r.status, 200)
        info = json.loads(r.body)["account"]
        self.assertEqual(info["name"], "My Gmail")                       # trimmed, whitespace collapsed
        self.assertNotIn("password", info)
        reloaded = AccountRegistry(AccountStore(self.cfg.web.accounts_file, self.cfg.web_password), self.cfg.mail)
        self.assertEqual({a.id: a.name for a in reloaded.list()}[other], "My Gmail")      # persisted (encrypted file)
        reloaded.close()
        self.assertEqual(json.loads(patch({"id": other, "name": "   "}).body)["account"]["name"], "me@127.0.0.1")
        self.assertEqual(patch({"id": other, "name": "x" * 81}).status, 400)
        self.assertEqual(patch({"id": other, "name": 5}).status, 400)
        self.assertEqual(patch({"id": "nope", "name": "x"}).status, 404)
        self.app.handle(Request("DELETE", "/api/accounts", query={"id": other}, headers={"cookie": self.cookie}))

    def _patch(self, body):
        return self.app.handle(Request("PATCH", "/api/accounts", headers={"cookie": self.cookie},
                                       body=json.dumps(body).encode()))

    def _delete(self, account_id):
        self.app.handle(Request("DELETE", "/api/accounts", query={"id": account_id}, headers={"cookie": self.cookie}))

    def test_edit_connection_reconnects_only_when_the_connection_changes(self):
        second, port2 = start_server(Path(self.tmp.name), self.repo, "me", "secret")
        account = self._add("secret", name="Edit me")["account"]["id"]
        try:
            service_before = self.registry.service(account)
            # 1. a new port: the new connection is tried first, then swapped in
            r = self._patch({"id": account, "port": port2})
            body = json.loads(r.body)
            self.assertEqual((r.status, body["reconnected"], body["account"]["port"]), (200, True, port2))
            service_after = self.registry.service(account)
            self.assertIsNot(service_after, service_before)
            self.assertFalse(service_before._indexes.values())                 # the old connection's caches were purged
            self.assertEqual(self.get("/api/folders", account=account).status, 200)
            # 2. only the name: no reconnect, same service object, caches kept
            r = self._patch({"id": account, "name": "Renamed"})
            self.assertEqual(json.loads(r.body)["reconnected"], False)
            self.assertIs(self.registry.service(account), service_after)
            # 3. a blank password keeps the saved one
            self.assertEqual(json.loads(self._patch({"id": account, "password": ""}).body)["reconnected"], False)
            # 4. wrong password: refused, and the working connection is left untouched
            r = self._patch({"id": account, "password": "wrong"})
            self.assertEqual(r.status, 502)
            self.assertEqual(self.get("/api/folders", account=account).status, 200)
            info = {a["id"]: a for a in self.j("/api/accounts")["accounts"]}[account]
            self.assertEqual((info["port"], info["name"]), (port2, "Renamed"))
            self.assertIn("tls_verify", info)
            self.assertNotIn("password", info)
            # 5. an unreachable server: refused with an explanation, nothing changed
            r = self._patch({"id": account, "port": 1})
            self.assertEqual(r.status, 502)
            self.assertIn("127.0.0.1:1", json.loads(r.body)["error"])
            self.assertEqual({a["id"]: a for a in self.j("/api/accounts")["accounts"]}[account]["port"], port2)
            # 6. it was saved, encrypted, with the new settings
            reloaded = AccountRegistry(AccountStore(self.cfg.web.accounts_file, self.cfg.web_password), self.cfg.mail)
            self.assertEqual({a.id: a.port for a in reloaded.list()}[account], port2)
            reloaded.close()
        finally:
            self._delete(account)
            second.terminate()
            second.wait(5)

    def test_default_display_name_follows_host_changes_but_a_custom_one_does_not(self):
        plain = self._add("secret")["account"]["id"]
        custom = self._add("secret", name="Mine")["account"]["id"]
        try:
            for account in (plain, custom):
                self.assertEqual(self._patch({"id": account, "host": "localhost"}).status, 200)
            names = {a["id"]: a["name"] for a in self.j("/api/accounts")["accounts"]}
            self.assertEqual((names[plain], names[custom]), ("me@localhost", "Mine"))
            self.assertEqual(self._patch({"id": plain, "tls": "yes"}).status, 400)         # flags must be real booleans
            self.assertEqual(self._patch({"id": plain, "port": 70000}).status, 400)
        finally:
            self._delete(plain)
            self._delete(custom)

    def test_paging_through_search_results_does_not_search_again(self):
        from unittest import mock
        from mailweb.mail.service import MailService
        service = self.registry.service(self.account)
        original = MailService._search
        calls = []

        def counting(imap, folder, criteria):
            calls.append(criteria)
            return original(imap, folder, criteria)
        with mock.patch.object(MailService, "_search", staticmethod(counting)):
            first = self.j("/api/messages", folder="INBOX", q="Hello")
            self.j("/api/messages", folder="INBOX", q="Hello", page=1)
            self.j("/api/messages", folder="INBOX", q="Hello", page=2)         # beyond the end: clamped, still no new search
            self.assertEqual(len(calls), 1)
            self.j("/api/messages", folder="INBOX", q="Older")                  # a different query does search
            self.assertEqual(len(calls), 2)
            self.j("/api/messages", folder="INBOX", q="Hello", refresh=1)       # refresh forgets cached results
            self.assertEqual(len(calls), 3)
        self.assertEqual(first["total"], 1)
        service.purge()

    def test_account_order_can_be_changed_and_is_saved(self):
        def post(order):
            return self.app.handle(Request("POST", "/api/accounts/order", headers={"cookie": self.cookie},
                                           body=json.dumps({"order": order}).encode()))
        first = self.account
        second = self._add("secret", name="Second")["account"]["id"]
        third = self._add("secret", name="Third")["account"]["id"]
        ids = lambda: [a["id"] for a in self.j("/api/accounts")["accounts"]]       # noqa: E731
        try:
            self.assertEqual(ids(), [first, second, third])
            r = post([third, first, second])
            self.assertEqual([a["id"] for a in json.loads(r.body)["accounts"]], [third, first, second])
            self.assertEqual(ids(), [third, first, second])
            reloaded = AccountRegistry(AccountStore(self.cfg.web.accounts_file, self.cfg.web_password), self.cfg.mail)
            self.assertEqual([a.id for a in reloaded.list()], [third, first, second])      # saved in the encrypted file
            reloaded.close()
            # unknown ids are ignored and accounts that are not mentioned keep their relative order after the others
            post(["nope", second, second])
            self.assertEqual(ids(), [second, third, first])
            self.assertEqual(post("not a list").status, 400)
            self.assertEqual(post([1, 2]).status, 400)
            self.assertEqual(ids(), [second, third, first])
        finally:
            post([first])                                                       # restore the usual order for later tests
            self._delete(second)
            self._delete(third)

    def test_cancel_route(self):
        r = self.app.handle(Request("POST", "/api/accounts/cancel", query={"account": self.account},
                                    headers={"cookie": self.cookie}))
        self.assertEqual((r.status, json.loads(r.body)), (200, {"cancelled": True}))
        self.assertEqual(self.get("/api/folders").status, 200)                    # still usable afterwards
        self.assertEqual(self.app.handle(Request("POST", "/api/accounts/cancel", headers={"cookie": self.cookie})).status, 400)

    def test_removing_an_account_purges_its_caches_and_connections(self):
        second = self._add("secret", name="Temp")["account"]["id"]
        service = self.registry.service(second)
        self.j("/api/messages", folder="INBOX", account=second)
        gateway = self.registry._services[second][0]
        self.assertTrue(service._indexes.values())
        self.app.handle(Request("DELETE", "/api/accounts", query={"id": second}, headers={"cookie": self.cookie}))
        self.assertFalse(service._indexes.values() or service._headers.values() or service._contents.values())
        self.assertEqual(gateway._idle[0]._client, None) if gateway._idle else None
        self.assertNotIn(second, self.registry._services)
        self.assertEqual(self.get("/api/folders", account=second).status, 404)

    def test_persistence_and_removal(self):
        second = self._add("secret", name="Second")["account"]["id"]
        reloaded = AccountRegistry(AccountStore(self.cfg.web.accounts_file, self.cfg.web_password), self.cfg.mail)
        self.assertEqual({a.id for a in reloaded.list()}, {self.account, second})
        self.assertEqual(oct(Path(self.cfg.web.accounts_file).stat().st_mode & 0o777), "0o600")
        reloaded.close()
        r = self.app.handle(Request("DELETE", "/api/accounts", query={"id": second}, headers={"cookie": self.cookie}))
        self.assertEqual(r.status, 200)
        self.assertEqual([a["id"] for a in self.j("/api/accounts")["accounts"]], [self.account])


if __name__ == "__main__":
    unittest.main()
