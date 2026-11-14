import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mailweb.accounts import Account, AccountStore  # noqa: E402
from mailweb.config import ConfigError  # noqa: E402

ACCOUNT = Account(id="ab12cd34", name="Pi archive", host="pi.example.lan", port=1143,
                  user="jos\u00e9@example.com", password="hunter2-\u00e4", tls=True, tls_verify=False)


class Store(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "accounts.json"

    def test_roundtrip_and_nothing_readable_on_disk(self):
        AccountStore(self.path, "web-pw").save([ACCOUNT])
        raw = self.path.read_text(encoding="utf-8")
        for secret in ("hunter2", "pi.example.lan", "example.com", "Pi archive"):
            self.assertNotIn(secret, raw)
        self.assertEqual(AccountStore(self.path, "web-pw").load(), [ACCOUNT])
        self.assertEqual(oct(self.path.stat().st_mode & 0o777), "0o600")

    def test_wrong_passphrase_is_refused_with_guidance(self):
        AccountStore(self.path, "web-pw").save([ACCOUNT])
        with self.assertRaisesRegex(ConfigError, "web password has changed"):
            AccountStore(self.path, "other").load()

    def test_tampering_is_detected(self):
        AccountStore(self.path, "web-pw").save([ACCOUNT])
        doc = json.loads(self.path.read_text())
        data = doc["data"]
        doc["data"] = data[:-6] + ("AAAAAA" if not data.endswith("AAAAAA") else "BBBBBB")
        self.path.write_text(json.dumps(doc))
        with self.assertRaises(ConfigError):
            AccountStore(self.path, "web-pw").load()

    def test_salt_is_random_per_file_and_stable_across_saves(self):
        other = self.path.with_name("other.json")
        store = AccountStore(self.path, "web-pw")
        store.save([ACCOUNT])
        first = json.loads(self.path.read_text())
        store.save([ACCOUNT, ACCOUNT])
        self.assertEqual(json.loads(self.path.read_text())["salt"], first["salt"])
        AccountStore(other, "web-pw").save([ACCOUNT])
        self.assertNotEqual(json.loads(other.read_text())["salt"], first["salt"])

    def test_plaintext_file_from_older_version_is_migrated(self):
        from dataclasses import asdict
        self.path.write_text(json.dumps([asdict(ACCOUNT)]))
        self.assertEqual(AccountStore(self.path, "web-pw").load(), [ACCOUNT])
        self.assertNotIn("hunter2", self.path.read_text(encoding="utf-8"))
        self.assertEqual(AccountStore(self.path, "web-pw").load(), [ACCOUNT])

    def test_missing_file_is_empty_and_garbage_is_an_error(self):
        self.assertEqual(AccountStore(self.path, "x").load(), [])
        self.path.write_text("not json")
        with self.assertRaises(ConfigError):
            AccountStore(self.path, "x").load()

    def test_hostile_key_derivation_settings_are_refused(self):
        AccountStore(self.path, "web-pw").save([ACCOUNT])
        doc = json.loads(self.path.read_text())
        doc["kdf"]["n"] = 2 ** 40
        self.path.write_text(json.dumps(doc))
        with self.assertRaises(ConfigError):
            AccountStore(self.path, "web-pw").load()


if __name__ == "__main__":
    unittest.main()
