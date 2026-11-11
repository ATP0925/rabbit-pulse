import logging
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rabbitpulse import cli, config, monitor


class TestMonitorAndCLI(unittest.TestCase):
    def test_merge_seen_ids_preserves_fifo_order(self):
        existing = ["id1", "id2", "id3"]
        merged = monitor.merge_seen_ids(existing, ["id2", "id4", "id5"], limit=4)
        self.assertEqual(merged, ["id2", "id3", "id4", "id5"])

    def test_run_cycle_backoff_and_reset(self):
        logger = logging.getLogger("RabbitPulse")
        for h in list(logger.handlers):
            logger.removeHandler(h)
            h.close()

        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            with patch.object(config, "DEFAULT_CONFIG_DIR", test_dir), \
                 patch.object(config, "CONFIG_FILE", test_dir / "config.json"), \
                 patch.object(config, "STATE_FILE", test_dir / "state.json"), \
                 patch.object(monitor, "LOG_FILE", test_dir / "rabbitpulse.log"):
                config.save_config({
                    **config.DEFAULT_CONFIG,
                    "github_user": "testuser",
                    "base_interval_minutes": 3,
                    "backoff_step_minutes": 1,
                    "max_interval_minutes": 60,
                    "desktop_notifications": False,
                })
                engine = monitor.MonitorEngine()
                try:
                    with patch.object(monitor.CodeRabbitDetector, "scan_all", return_value=([], set())):
                        next_n, seen, findings = engine.run_cycle([], 3)
                        self.assertEqual(next_n, 4)
                        self.assertEqual(findings, [])

                    fake_finding = [{
                        "type": "PR REVIEW 🐰",
                        "repo": "testuser/repo",
                        "id": "PR #1",
                        "title": "Feedback",
                        "summary": "Fix null check",
                        "url": "https://example.com",
                    }]
                    with patch.object(monitor.CodeRabbitDetector, "scan_all", return_value=(fake_finding, {"pr_comment:1"})):
                        next_n, seen, findings = engine.run_cycle(seen, 7)
                        self.assertEqual(next_n, 3)
                        self.assertEqual(seen, ["pr_comment:1"])
                        self.assertEqual(len(findings), 1)
                finally:
                    for h in list(logger.handlers):
                        logger.removeHandler(h)
                        h.close()

    def test_cli_config_clear_list_and_mask_password(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            with patch.object(config, "DEFAULT_CONFIG_DIR", test_dir), \
                 patch.object(config, "CONFIG_FILE", test_dir / "config.json"):
                config.save_config({
                    **config.DEFAULT_CONFIG,
                    "github_user": "testuser",
                    "watched_repos": ["testuser/a"],
                    "email_password": "secret-app-password",
                })
                with redirect_stdout(io.StringIO()):
                    cli.cmd_config(SimpleNamespace(key="watched_repos", value=""))
                    cli.cmd_config(SimpleNamespace(key="email_enabled", value="true"))
                loaded = config.load_config()
                self.assertEqual(loaded["watched_repos"], [])
                self.assertTrue(loaded["email_enabled"])

                buf = io.StringIO()
                with redirect_stdout(buf):
                    cli.cmd_config(SimpleNamespace(key=None, value=None))
                printed = json.loads(buf.getvalue())
                self.assertEqual(printed["email_password"], "***")


if __name__ == "__main__":
    unittest.main()
