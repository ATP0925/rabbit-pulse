import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch
from rabbitpulse import config

class TestConfig(unittest.TestCase):
    def test_default_values(self):
        conf = config.DEFAULT_CONFIG
        self.assertEqual(conf["base_interval_minutes"], 3)
        self.assertEqual(conf["backoff_step_minutes"], 1)
        self.assertEqual(conf["max_interval_minutes"], 60)
        self.assertTrue(conf["desktop_notifications"])

    def test_save_and_load_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            with patch.object(config, "DEFAULT_CONFIG_DIR", test_dir), \
                 patch.object(config, "CONFIG_FILE", test_dir / "config.json"):
                test_conf = {
                    "github_user": "testuser",
                    "base_interval_minutes": 5,
                    "backoff_step_minutes": 2,
                    "max_interval_minutes": 30,
                    "watched_repos": ["testuser/repo1"],
                    "desktop_notifications": False,
                    "webhook_url": "https://example.com/webhook"
                }
                config.save_config(test_conf)
                loaded = config.load_config()
                self.assertEqual(loaded["github_user"], "testuser")
                self.assertEqual(loaded["base_interval_minutes"], 5)
                self.assertEqual(loaded["watched_repos"], ["testuser/repo1"])

    def test_state_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            with patch.object(config, "DEFAULT_CONFIG_DIR", test_dir), \
                 patch.object(config, "STATE_FILE", test_dir / "state.json"):
                state = {
                    "current_interval_minutes": 4,
                    "seen_ids": ["notif:123", "issue:repo:1"],
                    "last_checked": "2026-11-10T12:00:00Z",
                    "status": "running"
                }
                config.save_state(state)
                loaded = config.load_state()
                self.assertEqual(loaded["current_interval_minutes"], 4)
                self.assertEqual(len(loaded["seen_ids"]), 2)

if __name__ == "__main__":
    unittest.main()
