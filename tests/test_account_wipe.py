import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mailweb.accounts import Account, AccountStore  # noqa: E402

A = Account("aaaa1111", "One", "one.example", 993, "one@example.com", "pw-one", True, True)
B = Account("bbbb2222", "Two", "two.example", 993, "two@example.com", "pw-two", True, True)


class Wipe(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.path = self.dir / "accounts.json"

    def test_replaced_file_is_overwritten_with_x(self):
        store = AccountStore(self.path, "web-pw")
        store.save([A, B])
        probe = self.dir / "probe"
        os.link(self.path, probe)                     # keeps the *old* file's bytes reachable for inspection
        before = probe.read_bytes()
        store.save([B])                               # removing A rewrites the file
        self.assertEqual(probe.read_bytes(), b"X" * len(before))
        self.assertEqual(AccountStore(self.path, "web-pw").load(), [B])
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["accounts.json", "probe"])   # no .old/.tmp left

    def test_erase_overwrites_then_deletes(self):
        store = AccountStore(self.path, "web-pw")
        store.save([A])
        probe = self.dir / "probe"
        os.link(self.path, probe)
        size = probe.stat().st_size
        store.erase()
        self.assertFalse(self.path.exists())
        self.assertEqual(probe.read_bytes(), b"X" * size)
        store.save([B])                               # starts a fresh file afterwards
        self.assertEqual(AccountStore(self.path, "web-pw").load(), [B])

    def test_leftover_old_link_to_the_live_file_is_not_destroyed(self):
        store = AccountStore(self.path, "web-pw")
        store.save([A])
        os.link(self.path, self.path.with_name("accounts.json.old"))     # as if a crash happened mid-swap
        store.save([A, B])
        self.assertEqual(AccountStore(self.path, "web-pw").load(), [A, B])

    def test_erase_when_missing_is_harmless(self):
        AccountStore(self.path, "web-pw").erase()


if __name__ == "__main__":
    unittest.main()
