import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG_DIR = Path.home() / ".rabbitpulse"
CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
STATE_FILE = DEFAULT_CONFIG_DIR / "state.json"
LOG_FILE = DEFAULT_CONFIG_DIR / "rabbitpulse.log"

DEFAULT_CONFIG: Dict[str, Any] = {
    "github_user": "",
    "base_interval_minutes": 3,
    "backoff_step_minutes": 1,
    "max_interval_minutes": 60,
    "watched_repos": [],
    "desktop_notifications": True,
    "webhook_url": "",
    "email_enabled": False,
    "email_imap_host": "imap.gmail.com",
    "email_imap_port": 993,
    "email_user": "",
    "email_password": "",
    "email_password_env": "RABBITPULSE_EMAIL_PASSWORD",
    "email_folder": "INBOX",
    "email_unread_only": True,
}


def subprocess_kwargs(detach_stdin: bool = True) -> Dict[str, Any]:
    """Return platform-safe subprocess options that avoid flashing console windows on Windows."""
    kwargs: Dict[str, Any] = {}
    if detach_stdin:
        kwargs["stdin"] = subprocess.DEVNULL
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return kwargs


def get_gh_executable() -> str:
    """Resolve the GitHub CLI binary, including standard Windows install paths."""
    which_gh = shutil.which("gh")
    if which_gh:
        return which_gh
    if sys.platform.startswith("win"):
        fallback = r"C:\Program Files\GitHub CLI\gh.exe"
        if os.path.exists(fallback):
            return fallback
    return "gh"


def ensure_config_dir() -> None:
    """Create the RabbitPulse state directory if it does not exist."""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Write JSON atomically via a same-directory temp file to avoid partial reads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".{path.name}.{os.getpid()}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, path)


def detect_github_user() -> str:
    """Detect the currently authenticated GitHub username via GitHub CLI."""
    try:
        res = subprocess.run(
            [get_gh_executable(), "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            timeout=5,
            **subprocess_kwargs(),
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return ""


def load_config() -> Dict[str, Any]:
    """Load user configuration merged with defaults, auto-detecting the GitHub user once."""
    ensure_config_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                config = DEFAULT_CONFIG.copy()
                config.update(saved)
                if not config["github_user"]:
                    config["github_user"] = detect_github_user()
                return config
        except Exception:
            pass

    config = DEFAULT_CONFIG.copy()
    config["github_user"] = detect_github_user()
    save_config(config)
    return config


def save_config(config: Dict[str, Any]) -> None:
    """Persist configuration to disk."""
    ensure_config_dir()
    _atomic_write_json(CONFIG_FILE, config)


def load_state() -> Dict[str, Any]:
    """Load persisted monitor state (polling interval, seen IDs, last check timestamp)."""
    ensure_config_dir()
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
                state.setdefault("current_interval_minutes", 3)
                state.setdefault("seen_ids", [])
                state.setdefault("last_checked", "")
                state.setdefault("status", "stopped")
                return state
        except Exception:
            pass
    return {
        "current_interval_minutes": 3,
        "seen_ids": [],
        "last_checked": "",
        "status": "stopped",
        "last_error": "",
    }


def save_state(state: Dict[str, Any]) -> None:
    """Persist monitor state to disk."""
    ensure_config_dir()
    _atomic_write_json(STATE_FILE, state)

