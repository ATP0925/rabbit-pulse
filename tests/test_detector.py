import unittest
import json
from unittest.mock import patch, MagicMock
from rabbitpulse.detector import CodeRabbitDetector

class TestDetector(unittest.TestCase):
    def setUp(self):
        self.detector = CodeRabbitDetector("testuser", ["testuser/test-repo"])

    @patch("subprocess.run")
    def test_scan_notifications_finds_coderabbit(self, mock_run):
        mock_output = [
            {
                "id": "1001",
                "subject": {
                    "title": "CodeRabbit review requested on PR #12",
                    "type": "PullRequest",
                    "url": "https://api.github.com/repos/testuser/test-repo/pulls/12"
                },
                "repository": {"full_name": "testuser/test-repo"}
            },
            {
                "id": "1002",
                "subject": {
                    "title": "Dependabot bump version",
                    "type": "PullRequest",
                    "url": "https://api.github.com/repos/testuser/test-repo/pulls/13"
                },
                "repository": {"full_name": "testuser/test-repo"}
            }
        ]
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_output))
        
        seen_ids = set()
        findings, new_seen = self.detector._scan_notifications(seen_ids)
        
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["id"], "1001")
        self.assertIn("notif:1001", new_seen)

    @patch("subprocess.run")
    def test_scan_issues_finds_coderabbit_issue(self, mock_run):
        mock_issues = [
            {
                "number": 42,
                "title": "CodeRabbit: Memory leak detected in parser",
                "author": {"login": "coderabbitai"},
                "repository": {"nameWithOwner": "testuser/test-repo"},
                "url": "https://github.com/testuser/test-repo/issues/42"
            }
        ]
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_issues))
        
        seen_ids = set()
        findings, new_seen = self.detector._scan_issues(seen_ids)
        
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["id"], "#42")
        self.assertIn("issue:testuser/test-repo:42", new_seen)

    @patch("subprocess.run")
    def test_deduplication(self, mock_run):
        mock_issues = [
            {
                "number": 42,
                "title": "CodeRabbit: Memory leak",
                "author": {"login": "coderabbitai"},
                "repository": {"nameWithOwner": "testuser/test-repo"},
                "url": "https://github.com/testuser/test-repo/issues/42"
            }
        ]
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_issues))
        
        # Already seen
        seen_ids = {"issue:testuser/test-repo:42"}
        findings, new_seen = self.detector._scan_issues(seen_ids)
        
        self.assertEqual(len(findings), 0)

if __name__ == "__main__":
    unittest.main()
