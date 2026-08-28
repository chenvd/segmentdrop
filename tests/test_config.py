import json
import tempfile
import unittest
from pathlib import Path

from app.config import ConfigStore, EmbySettings, Settings, TheIntroDBSettings


class ConfigStoreTests(unittest.TestCase):
    def test_round_trip_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            store = ConfigStore(path)
            expected = Settings(EmbySettings("http://emby.local", "emby-secret"), TheIntroDBSettings("tidb-secret"))
            store.save(expected)
            self.assertEqual(expected, store.load())
            self.assertEqual(0o600, path.stat().st_mode & 0o777)
            self.assertFalse(path.with_suffix(".json.tmp").exists())
            self.assertEqual("emby-secret", json.loads(path.read_text())["emby"]["api_key"])


if __name__ == "__main__":
    unittest.main()

