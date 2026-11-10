import os
import json
import subprocess
from pathlib import Path

DEFAULT_CONFIG_DIR = Path.home() / ".rabbitpulse"
CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
STATE_FILE = DEFAULT_CONFIG_DIR / "state.json"
LOG_FILE = DEFAULT_CONFIG_DIR / "rabbitpulse.log"

DEFAULT_CONFIG = {
    "github_user": "",
    "base_interval_minutes": 3,
    "backoff_step_minutes": 1,
    "max_interval_minutes": 60,
    "watched_repos": [],
    "desktop_notifications": True,
    "webhook_url": ""
}

def ensure_config_dir():
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def detect_github_user():
    """Detect current authenticated GitHub username using GitHub CLI."""
    try:
        res = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return ""

def load_config():
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

def save_config(config):
    ensure_config_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

def load_state():
    ensure_config_dir()
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "current_interval_minutes": 3,
        "seen_ids": [],
        "last_checked": "",
        "status": "stopped"
    }

def save_state(state):
    ensure_config_dir()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
