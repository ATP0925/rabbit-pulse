import email
import imaplib
import json
import os
import re
import subprocess
from email.header import decode_header
from typing import Any, Dict, List, Optional, Set, Tuple

from rabbitpulse.config import get_gh_executable, subprocess_kwargs

_ACTIONABLE_RE = re.compile(r"Actionable comments posted:\s*(\d+)", re.IGNORECASE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _clean_snippet(body: str, limit: int = 140) -> str:
    """Strip HTML comments/tags and markdown chrome into a readable notification snippet."""
    text = _HTML_COMMENT_RE.sub(" ", body or "")
    text = _HTML_TAG_RE.sub(" ", text)
    text = text.replace("```", " ")
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def _is_coderabbit_user(login: str) -> bool:
    return "coderabbit" in (login or "").lower()


def _is_addressed_comment(body: str) -> bool:
    lowered = (body or "").lower()
    return "addressed in commit" in lowered or "<!-- resolved -->" in lowered


def _looks_important_review(state: str, body: str) -> bool:
    if (state or "").upper() == "CHANGES_REQUESTED":
        return True
    match = _ACTIONABLE_RE.search(body or "")
    return bool(match and int(match.group(1)) > 0)


def _decode_mime_header(value: str) -> str:
    if not value:
        return ""
    parts: List[str] = []
    for chunk, encoding in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts).strip()


def _extract_email_preview(raw_bytes: bytes) -> str:
    msg = email.message_from_bytes(raw_bytes)
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")[:500]
        return ""
    payload = msg.get_payload(decode=True)
    if payload:
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")[:500]
    return str(msg.get_payload() or "")[:500]


class CodeRabbitDetector:
    """Polls GitHub notifications, issues, PR reviews/comments, and optional IMAP email."""

    def __init__(
        self,
        github_user: str,
        watched_repos: Optional[List[str]] = None,
        email_config: Optional[Dict[str, Any]] = None,
    ):
        self.github_user = github_user
        self.watched_repos = list(watched_repos) if watched_repos else []
        self.email_config = dict(email_config) if email_config else {}
        self.gh_cmd = get_gh_executable()
        self.last_email_error = ""

    def _run_gh_json(self, args: List[str], timeout: int = 10) -> Any:
        try:
            res = subprocess.run(
                [self.gh_cmd, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                **subprocess_kwargs(),
            )
            if res.returncode == 0 and res.stdout:
                return json.loads(res.stdout)
        except Exception:
            pass
        return None

    def scan_all(self, seen_ids: Set[str]) -> Tuple[List[Dict[str, Any]], Set[str]]:
        """Run all enabled detectors and return new findings plus updated seen IDs."""
        findings: List[Dict[str, Any]] = []
        new_seen = set(seen_ids)

        notif_findings, new_seen = self._scan_notifications(new_seen)
        findings.extend(notif_findings)

        if self.github_user or self.watched_repos:
            issue_findings, new_seen = self._scan_issues(new_seen)
            findings.extend(issue_findings)

        pr_findings, new_seen = self._scan_prs(new_seen)
        findings.extend(pr_findings)

        if self.email_config.get("email_enabled"):
            email_findings, new_seen = self._scan_email(new_seen)
            findings.extend(email_findings)

        return findings, new_seen

    def _scan_notifications(self, seen_ids: Set[str]) -> Tuple[List[Dict[str, Any]], Set[str]]:
        findings: List[Dict[str, Any]] = []
        notifications = self._run_gh_json(["api", "notifications"], timeout=10)
        if not isinstance(notifications, list):
            return findings, seen_ids

        for notif in notifications:
            notif_id = str(notif.get("id"))
            title = notif.get("subject", {}).get("title", "")
            repo = notif.get("repository", {}).get("full_name", "")
            sub_type = notif.get("subject", {}).get("type", "Notification")

            if "coderabbit" in title.lower():
                key = f"notif:{notif_id}"
                if key not in seen_ids:
                    seen_ids.add(key)
                    findings.append({
                        "type": f"ALERT ({sub_type})",
                        "repo": repo,
                        "id": notif_id,
                        "title": title,
                        "summary": f"[{repo}] {title}",
                        "url": notif.get("subject", {}).get("url"),
                    })
        return findings, seen_ids

    def _collect_open_issues(self) -> List[Tuple[str, Dict[str, Any]]]:
        collected: List[Tuple[str, Dict[str, Any]]] = []
        seen_keys: Set[Tuple[str, str]] = set()

        if self.watched_repos:
            for repo in self.watched_repos:
                issues = self._run_gh_json(
                    ["issue", "list", "--repo", repo, "--state", "open", "--limit", "30", "--json", "number,title,author,url"],
                    timeout=10,
                )
                if isinstance(issues, list):
                    for iss in issues:
                        num = str(iss.get("number"))
                        if (repo, num) not in seen_keys:
                            seen_keys.add((repo, num))
                            collected.append((repo, iss))
            return collected

        if not self.github_user:
            return collected

        for extra_flags in ([], ["--commenter", "coderabbitai[bot]"]):
            issues = self._run_gh_json(
                [
                    "search", "issues",
                    "--owner", self.github_user,
                    *extra_flags,
                    "--state", "open",
                    "--limit", "50",
                    "--json", "number,title,author,repository,url",
                ],
                timeout=12,
            )
            if isinstance(issues, list):
                for iss in issues:
                    repo_full = iss.get("repository", {}).get("nameWithOwner", "")
                    num = str(iss.get("number"))
                    if repo_full and (repo_full, num) not in seen_keys:
                        seen_keys.add((repo_full, num))
                        collected.append((repo_full, iss))
        return collected

    def _scan_issues(self, seen_ids: Set[str]) -> Tuple[List[Dict[str, Any]], Set[str]]:
        findings: List[Dict[str, Any]] = []
        for repo_full, iss in self._collect_open_issues():
            num = str(iss.get("number"))
            author = (iss.get("author") or {}).get("login", "")
            title = iss.get("title", "")

            if _is_coderabbit_user(author) or "coderabbit" in title.lower():
                key = f"issue:{repo_full}:{num}"
                if key not in seen_ids:
                    seen_ids.add(key)
                    findings.append({
                        "type": "NEW ISSUE 📌",
                        "repo": repo_full,
                        "id": f"#{num}",
                        "title": title,
                        "summary": f"CodeRabbit issue in {repo_full} #{num}: {title}",
                        "url": iss.get("url"),
                    })
                continue

            # If CodeRabbit commented on an open issue opened by someone else
            comments = self._run_gh_json(["api", f"repos/{repo_full}/issues/{num}/comments"], timeout=8)
            if isinstance(comments, list):
                for c in comments:
                    c_id = str(c.get("id"))
                    c_user = (c.get("user") or {}).get("login", "")
                    if _is_coderabbit_user(c_user):
                        key = f"issue_comment:{repo_full}:{num}:{c_id}"
                        if key not in seen_ids:
                            seen_ids.add(key)
                            snippet = _clean_snippet(c.get("body") or "", limit=120)
                            findings.append({
                                "type": "ISSUE COMMENT 📌",
                                "repo": repo_full,
                                "id": f"#{num}",
                                "title": f"CodeRabbit comment on {repo_full} #{num}",
                                "summary": f"{repo_full} issue #{num}: {snippet}",
                                "url": c.get("html_url") or iss.get("url"),
                            })

        return findings, seen_ids

    def _collect_open_prs(self) -> List[Tuple[str, str]]:
        pr_targets: List[Tuple[str, str]] = []
        seen_targets: Set[Tuple[str, str]] = set()

        if self.watched_repos:
            for repo in self.watched_repos:
                prs = self._run_gh_json(
                    ["pr", "list", "--repo", repo, "--state", "open", "--limit", "30", "--json", "number"],
                    timeout=8,
                )
                if isinstance(prs, list):
                    for pr in prs:
                        target = (repo, str(pr.get("number")))
                        if target not in seen_targets:
                            seen_targets.add(target)
                            pr_targets.append(target)
        elif self.github_user:
            for flag in ("--owner", "--author"):
                prs = self._run_gh_json(
                    [
                        "search", "prs",
                        flag, self.github_user,
                        "--state", "open",
                        "--limit", "50",
                        "--json", "number,repository",
                    ],
                    timeout=10,
                )
                if isinstance(prs, list):
                    for item in prs:
                        repo_name = item.get("repository", {}).get("nameWithOwner")
                        pr_num = str(item.get("number"))
                        target = (repo_name, pr_num)
                        if repo_name and target not in seen_targets:
                            seen_targets.add(target)
                            pr_targets.append(target)

        return pr_targets[:30]

    def _scan_prs(self, seen_ids: Set[str]) -> Tuple[List[Dict[str, Any]], Set[str]]:
        findings: List[Dict[str, Any]] = []

        for repo, pr_num in self._collect_open_prs():
            # 1. Inline review comments and PR issue comments
            for endpoint, skip_addressed in (
                (f"repos/{repo}/pulls/{pr_num}/comments", True),
                (f"repos/{repo}/issues/{pr_num}/comments", False),
            ):
                comments = self._run_gh_json(["api", endpoint], timeout=8)
                if not isinstance(comments, list):
                    continue
                for c in comments:
                    c_id = str(c.get("id"))
                    user = (c.get("user") or {}).get("login", "")
                    if not _is_coderabbit_user(user):
                        continue
                    key = f"pr_comment:{repo}:{pr_num}:{c_id}"
                    if key in seen_ids:
                        continue
                    seen_ids.add(key)
                    raw_body = c.get("body", "")
                    if skip_addressed and _is_addressed_comment(raw_body):
                        continue
                    snippet = _clean_snippet(raw_body, limit=120)
                    findings.append({
                        "type": "PR REVIEW 🐰",
                        "repo": repo,
                        "id": f"PR #{pr_num}",
                        "title": f"CodeRabbit feedback on {repo} #{pr_num}",
                        "summary": f"{repo} PR #{pr_num}: {snippet}",
                        "url": c.get("html_url"),
                    })

            # 2. Top-level PR reviews (actionable review status / pre-merge check warnings)
            reviews = self._run_gh_json(["api", f"repos/{repo}/pulls/{pr_num}/reviews"], timeout=8)
            if not isinstance(reviews, list):
                continue
            for rev in reviews:
                rev_id = str(rev.get("id"))
                user = (rev.get("user") or {}).get("login", "")
                if not _is_coderabbit_user(user):
                    continue
                key = f"pr_review:{repo}:{pr_num}:{rev_id}"
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                state = rev.get("state", "")
                body = rev.get("body", "")
                if _looks_important_review(state, body):
                    snippet = _clean_snippet(body, limit=120)
                    findings.append({
                        "type": "PR ACTION REQUIRED 🔴",
                        "repo": repo,
                        "id": f"PR #{pr_num}",
                        "title": f"Actionable CodeRabbit review on {repo} #{pr_num}",
                        "summary": f"{repo} PR #{pr_num} ({state}): {snippet}",
                        "url": rev.get("html_url"),
                    })

        return findings, seen_ids

    def _scan_email(self, seen_ids: Set[str]) -> Tuple[List[Dict[str, Any]], Set[str]]:
        """Read recent inbox emails read-only via IMAP to catch CodeRabbit alerts."""
        findings: List[Dict[str, Any]] = []
        self.last_email_error = ""

        host = self.email_config.get("email_imap_host") or "imap.gmail.com"
        port = int(self.email_config.get("email_imap_port") or 993)
        user = self.email_config.get("email_user") or ""
        pwd_env = self.email_config.get("email_password_env") or "RABBITPULSE_EMAIL_PASSWORD"
        password = os.environ.get(pwd_env) or self.email_config.get("email_password") or ""
        folder = self.email_config.get("email_folder") or "INBOX"
        unread_only = bool(self.email_config.get("email_unread_only", True))

        if not user or not password:
            self.last_email_error = "Email monitoring enabled, but email_user or password is missing."
            return findings, seen_ids

        conn = None
        selected = False
        try:
            conn = imaplib.IMAP4_SSL(host, port, timeout=15)
            conn.login(user, password)
            status, _ = conn.select(folder, readonly=True)
            if status != "OK":
                self.last_email_error = f"Unable to open IMAP folder '{folder}'."
                return findings, seen_ids
            selected = True

            criteria = "UNSEEN" if unread_only else "ALL"
            search_status, msg_nums = conn.search(None, criteria)
            if search_status != "OK" or not msg_nums or not msg_nums[0]:
                return findings, seen_ids

            ids = msg_nums[0].split()[-25:]
            for num in ids:
                fetch_status, msg_data = conn.fetch(num, "(BODY.PEEK[])")
                if fetch_status != "OK" or not msg_data:
                    continue
                raw_bytes = None
                for part in msg_data:
                    if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], (bytes, bytearray)):
                        raw_bytes = bytes(part[1])
                        break
                if not raw_bytes:
                    continue

                msg = email.message_from_bytes(raw_bytes)
                msg_id = (msg.get("Message-ID") or f"imap-{folder}-{num.decode('ascii', errors='ignore')}").strip()
                sender = _decode_mime_header(msg.get("From", ""))
                subject = _decode_mime_header(msg.get("Subject", ""))
                preview = _extract_email_preview(raw_bytes)
                combined = f"{sender}\n{subject}\n{preview}".lower()

                if "coderabbit" not in combined:
                    continue

                key = f"email:{msg_id}"
                if key not in seen_ids:
                    seen_ids.add(key)
                    findings.append({
                        "type": "EMAIL ALERT 📧",
                        "repo": sender or "Email Inbox",
                        "id": msg_id[:40],
                        "title": subject or "CodeRabbit email notification",
                        "summary": f"[Email] {subject or preview[:100]}",
                        "url": None,
                    })
        except Exception as e:
            self.last_email_error = str(e)
        finally:
            if conn is not None:
                try:
                    if selected:
                        conn.close()
                except Exception:
                    pass
                try:
                    conn.logout()
                except Exception:
                    pass

        return findings, seen_ids
