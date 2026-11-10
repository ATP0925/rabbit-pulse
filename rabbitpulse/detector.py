import json
import shutil
import subprocess
from typing import List, Dict, Set, Tuple

def get_gh_executable() -> str:
    which_gh = shutil.which("gh")
    if which_gh:
        return which_gh
    return "gh"

class CodeRabbitDetector:
    def __init__(self, github_user: str, watched_repos: List[str] = None):
        self.github_user = github_user
        self.watched_repos = watched_repos or []
        self.gh_cmd = get_gh_executable()

    def scan_all(self, seen_ids: Set[str]) -> Tuple[List[Dict], Set[str]]:
        findings = []
        new_seen = set(seen_ids)

        # 1. Check live notifications (real-time stream)
        notif_findings, new_seen = self._scan_notifications(new_seen)
        findings.extend(notif_findings)

        # 2. Check live GitHub issues created or commented on by CodeRabbit
        if self.github_user:
            issue_findings, new_seen = self._scan_issues(new_seen)
            findings.extend(issue_findings)

        # 3. Check open PR review comments
        pr_findings, new_seen = self._scan_prs(new_seen)
        findings.extend(pr_findings)

        return findings, new_seen

    def _scan_notifications(self, seen_ids: Set[str]) -> Tuple[List[Dict], Set[str]]:
        findings = []
        try:
            res = subprocess.run(
                [self.gh_cmd, "api", "notifications"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if res.returncode == 0 and res.stdout:
                notifications = json.loads(res.stdout)
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
                                "url": notif.get("subject", {}).get("url")
                            })
        except Exception:
            pass
        return findings, seen_ids

    def _scan_issues(self, seen_ids: Set[str]) -> Tuple[List[Dict], Set[str]]:
        findings = []
        try:
            # Check issues mentioning or created by coderabbit
            res = subprocess.run(
                [
                    self.gh_cmd, "search", "issues",
                    "--owner", self.github_user,
                    "--state", "open",
                    "--json", "number,title,author,repository,url"
                ],
                capture_output=True,
                text=True,
                timeout=12
            )
            if res.returncode == 0 and res.stdout:
                issues = json.loads(res.stdout)
                for iss in issues:
                    num = str(iss.get("number"))
                    repo_full = iss.get("repository", {}).get("nameWithOwner", "")
                    author = iss.get("author", {}).get("login", "").lower()
                    title = iss.get("title", "")

                    if "coderabbit" in author or "coderabbit" in title.lower():
                        key = f"issue:{repo_full}:{num}"
                        if key not in seen_ids:
                            seen_ids.add(key)
                            findings.append({
                                "type": "NEW ISSUE 📌",
                                "repo": repo_full,
                                "id": f"#{num}",
                                "title": title,
                                "summary": f"CodeRabbit issue in {repo_full} #{num}: {title}",
                                "url": iss.get("url")
                            })
        except Exception:
            pass
        return findings, seen_ids

    def _scan_prs(self, seen_ids: Set[str]) -> Tuple[List[Dict], Set[str]]:
        findings = []
        # If specific repos are specified, check them, or query open PRs authored by/on user repos
        repos_to_check = self.watched_repos
        if not repos_to_check and self.github_user:
            try:
                res = subprocess.run(
                    [
                        self.gh_cmd, "search", "prs",
                        "--owner", self.github_user,
                        "--state", "open",
                        "--json", "number,repository"
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if res.returncode == 0 and res.stdout:
                    prs_data = json.loads(res.stdout)
                    for item in prs_data:
                        repo_name = item.get("repository", {}).get("nameWithOwner")
                        if repo_name and repo_name not in repos_to_check:
                            repos_to_check.append(repo_name)
            except Exception:
                pass

        for repo in repos_to_check[:5]:  # Limit to 5 active repos to ensure fast response
            try:
                # Query PR comments
                c_res = subprocess.run(
                    [self.gh_cmd, "pr", "list", "--repo", repo, "--state", "open", "--json", "number"],
                    capture_output=True,
                    text=True,
                    timeout=8
                )
                if c_res.returncode == 0 and c_res.stdout:
                    pr_list = json.loads(c_res.stdout)
                    for pr in pr_list:
                        pr_num = str(pr.get("number"))
                        # Fetch reviews
                        r_res = subprocess.run(
                            [self.gh_cmd, "api", f"repos/{repo}/pulls/{pr_num}/comments"],
                            capture_output=True,
                            text=True,
                            timeout=8
                        )
                        if r_res.returncode == 0 and r_res.stdout:
                            comments = json.loads(r_res.stdout)
                            for c in comments:
                                c_id = str(c.get("id"))
                                user = c.get("user", {}).get("login", "").lower()
                                if "coderabbit" in user:
                                    key = f"pr_comment:{repo}:{pr_num}:{c_id}"
                                    if key not in seen_ids:
                                        seen_ids.add(key)
                                        body = c.get("body", "").strip().replace("\n", " ")[:120]
                                        findings.append({
                                            "type": "PR REVIEW 🐰",
                                            "repo": repo,
                                            "id": f"PR #{pr_num}",
                                            "title": f"Review comment on line {c.get('line')}",
                                            "summary": f"{repo} PR #{pr_num}: {body}",
                                            "url": c.get("html_url")
                                        })
            except Exception:
                pass

        return findings, seen_ids
