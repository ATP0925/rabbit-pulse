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

    @patch("subprocess.run")
    def test_scan_prs_skips_addressed_comment_and_flags_actionable_review(self, mock_run):
        def fake_run(cmd, **kwargs):
            joined = " ".join(cmd)
            if "pr list" in joined:
                return MagicMock(returncode=0, stdout=json.dumps([{"number": 5}]))
            if "pulls/5/comments" in joined:
                return MagicMock(returncode=0, stdout=json.dumps([
                    {
                        "id": 901,
                        "user": {"login": "coderabbitai[bot]"},
                        "body": "Major bug.\n\n✅ Addressed in commit 8ff64a9",
                        "html_url": "https://github.com/testuser/test-repo/pull/5#discussion_r901",
                    },
                    {
                        "id": 902,
                        "user": {"login": "coderabbitai[bot]"},
                        "body": "Unaddressed potential issue in config loader.",
                        "html_url": "https://github.com/testuser/test-repo/pull/5#discussion_r902",
                    },
                ]))
            if "issues/5/comments" in joined:
                return MagicMock(returncode=0, stdout=json.dumps([]))
            if "pulls/5/reviews" in joined:
                return MagicMock(returncode=0, stdout=json.dumps([
                    {
                        "id": 701,
                        "user": {"login": "coderabbitai[bot]"},
                        "state": "COMMENTED",
                        "body": "**Actionable comments posted: 0**\nWalkthrough only",
                        "html_url": "https://github.com/testuser/test-repo/pull/5#pullrequestreview-701",
                    },
                    {
                        "id": 702,
                        "user": {"login": "coderabbitai[bot]"},
                        "state": "COMMENTED",
                        "body": "**Actionable comments posted: 1**\nPlease guard against empty strings.",
                        "html_url": "https://github.com/testuser/test-repo/pull/5#pullrequestreview-702",
                    },
                ]))
            return MagicMock(returncode=0, stdout="[]")

        mock_run.side_effect = fake_run
        findings, new_seen = self.detector._scan_prs(set())

        self.assertIn("pr_comment:testuser/test-repo:5:901", new_seen)
        self.assertIn("pr_comment:testuser/test-repo:5:902", new_seen)
        self.assertIn("pr_review:testuser/test-repo:5:701", new_seen)
        self.assertIn("pr_review:testuser/test-repo:5:702", new_seen)
        self.assertEqual(len(findings), 2)
        types = {f["type"] for f in findings}
        self.assertEqual(types, {"PR REVIEW 🐰", "PR ACTION REQUIRED 🔴"})
        review_finding = next(f for f in findings if f["type"] == "PR ACTION REQUIRED 🔴")
        self.assertNotIn("<!--", review_finding["summary"])
        self.assertNotIn("<details>", review_finding["summary"])

    def test_clean_snippet_strips_html_and_comments(self):
        from rabbitpulse.detector import _clean_snippet
        raw = "<!-- coderabbit -->\n<details><summary><img src='x'/></summary>\nMajor bug here.\n</details>"
        cleaned = _clean_snippet(raw, limit=120)
        self.assertEqual(cleaned, "Major bug here.")

    @patch("subprocess.run")
    def test_scan_issues_detects_coderabbit_comment_on_open_issue(self, mock_run):
        def fake_run(cmd, **kwargs):
            joined = " ".join(cmd)
            if "issue list" in joined:
                return MagicMock(returncode=0, stdout=json.dumps([
                    {
                        "number": 12,
                        "title": "Parser crashes on empty input",
                        "author": {"login": "humanuser"},
                        "url": "https://github.com/testuser/test-repo/issues/12",
                    }
                ]))
            if "issues/12/comments" in joined:
                return MagicMock(returncode=0, stdout=json.dumps([
                    {
                        "id": 333,
                        "user": {"login": "coderabbitai[bot]"},
                        "body": "Root cause appears to be missing null check.",
                        "html_url": "https://github.com/testuser/test-repo/issues/12#issuecomment-333",
                    }
                ]))
            return MagicMock(returncode=0, stdout="[]")

        mock_run.side_effect = fake_run
        findings, new_seen = self.detector._scan_issues(set())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["type"], "ISSUE COMMENT 📌")
        self.assertIn("issue_comment:testuser/test-repo:12:333", new_seen)

    @patch("imaplib.IMAP4_SSL")
    def test_scan_email_detects_coderabbit_imap_message(self, mock_imap_cls):
        raw_cr_email = (
            b"Message-ID: <cr-msg-1@coderabbit.ai>\r\n"
            b"From: CodeRabbit <notifications@coderabbit.ai>\r\n"
            b"Subject: [owner/repo] Review summary for PR #8\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
            b"CodeRabbit found 1 potential issue.\r\n"
        )
        raw_other_email = (
            b"Message-ID: <other-2@example.com>\r\n"
            b"From: Newsletter <news@example.com>\r\n"
            b"Subject: Weekly digest\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
            b"Nothing related.\r\n"
        )

        mock_conn = MagicMock()
        mock_conn.select.return_value = ("OK", [b"2"])
        mock_conn.search.return_value = ("OK", [b"1 2"])
        mock_conn.fetch.side_effect = [
            ("OK", [(b"1 (BODY[] {100})", raw_cr_email)]),
            ("OK", [(b"2 (BODY[] {100})", raw_other_email)]),
        ]
        mock_imap_cls.return_value = mock_conn

        detector = CodeRabbitDetector(
            "testuser",
            email_config={
                "email_enabled": True,
                "email_imap_host": "imap.gmail.com",
                "email_imap_port": 993,
                "email_user": "user@gmail.com",
                "email_password": "app-password",
                "email_folder": "INBOX",
                "email_unread_only": True,
            },
        )
        findings, new_seen = detector._scan_email(set())

        mock_conn.select.assert_called_once_with("INBOX", readonly=True)
        self.assertEqual(detector.last_email_error, "")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["type"], "EMAIL ALERT 📧")
        self.assertIn("email:<cr-msg-1@coderabbit.ai>", new_seen)

    def test_scan_email_missing_credentials_records_error(self):
        detector = CodeRabbitDetector(
            "testuser",
            email_config={
                "email_enabled": True,
                "email_user": "user@gmail.com",
                "email_password": "",
                "email_password_env": "NONEXISTENT_RP_ENV_VAR_XYZ",
            },
        )
        findings, new_seen = detector._scan_email(set())
        self.assertEqual(findings, [])
        self.assertEqual(new_seen, set())
        self.assertIn("missing", detector.last_email_error.lower())

if __name__ == "__main__":
    unittest.main()

