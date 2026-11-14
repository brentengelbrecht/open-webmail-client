import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mailweb.config import ConfigError, load_config  # noqa: E402
from mailweb.web.sessions import SessionStore  # noqa: E402


class Sessions(unittest.TestCase):
    def test_expiry_and_remaining(self):
        now = [1000.0]
        store = SessionStore(60, clock=lambda: now[0])
        token = store.create()
        self.assertTrue(store.is_valid(token))
        now[0] += 45
        self.assertEqual(store.remaining(token), 15)
        now[0] += 16
        self.assertFalse(store.is_valid(token))
        self.assertEqual(store.remaining(token), 0)
        self.assertEqual(store.remaining("unknown"), 0)


class Config(unittest.TestCase):
    def load(self, text):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path = Path(d.name) / "m.ini"
        path.write_text(text)
        path.chmod(0o600)
        return load_config(path)

    def test_defaults(self):
        cfg = self.load("[web]\npassword = x\n")
        self.assertEqual(cfg.web.session_minutes, 60)
        self.assertFalse(cfg.mail.load_remote_images)

    def test_overrides_and_validation(self):
        cfg = self.load("[web]\npassword = x\nsession_minutes = 15\n[mail]\nload_remote_images = true\n")
        self.assertEqual((cfg.web.session_minutes, cfg.mail.load_remote_images), (15, True))
        with self.assertRaises(ConfigError):
            self.load("[web]\npassword = x\nsession_minutes = 0\n")
        with self.assertRaises(ConfigError):       # the old option name is rejected, not ignored
            self.load("[web]\npassword = x\nsession_hours = 12\n")


if __name__ == "__main__":
    unittest.main()
