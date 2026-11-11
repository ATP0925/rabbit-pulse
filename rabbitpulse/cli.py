import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from rabbitpulse.config import DEFAULT_CONFIG, LOG_FILE, load_config, load_state, save_config, save_state
from rabbitpulse.detector import CodeRabbitDetector
from rabbitpulse.monitor import LOCK_PORT, MonitorEngine, merge_seen_ids
from rabbitpulse.notifier import notify_desktop, send_webhook

_INT_KEYS = {"base_interval_minutes", "backoff_step_minutes", "max_interval_minutes", "email_imap_port"}
_BOOL_KEYS = {"desktop_notifications", "email_enabled", "email_unread_only"}
_LIST_KEYS = {"watched_repos"}


def _is_daemon_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", LOCK_PORT))
            return False
        except OSError:
            return True


def _startup_vbs_path() -> Path:
    return Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup" / "RabbitPulse.vbs"


def cmd_start(args):
    if args.daemon:
        if _is_daemon_running():
            print("RabbitPulse is already running.")
            return
        cmd = [sys.executable, "-m", "rabbitpulse.cli", "start"]
        if sys.platform.startswith("win"):
            creation_flags = 0x08000000 | 0x00000200  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
            p = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
                close_fds=True,
            )
            print(f"RabbitPulse started in background (PID: {p.pid}).")
        else:
            p = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            print(f"RabbitPulse started in background (PID: {p.pid}).")
        return

    engine = MonitorEngine()
    engine.run()


def cmd_stop(args):
    if not _is_daemon_running():
        print("RabbitPulse is not currently running.")
        return
    if sys.platform.startswith("win"):
        cmd = (
            f"Get-NetTCPConnection -LocalPort {LOCK_PORT} -ErrorAction SilentlyContinue "
            "| ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True,
            creationflags=0x08000000,
        )
    else:
        subprocess.run(f"fuser -k {LOCK_PORT}/tcp", shell=True, capture_output=True)
    print("RabbitPulse daemon stopped.")


def cmd_status(args):
    config = load_config()
    state = load_state()
    is_running = _is_daemon_running()

    status_str = "🟢 RUNNING" if is_running else "🔴 STOPPED"
    email_str = (
        f"Enabled ({config.get('email_user') or 'missing user'})"
        if config.get("email_enabled")
        else "Disabled"
    )
    print("\n=== RabbitPulse Status ===")
    print(f"Service State    : {status_str}")
    print(f"Monitored User   : {config.get('github_user') or '(auto-detect)'}")
    print(f"Email Monitor    : {email_str}")
    if sys.platform.startswith("win"):
        autostart_str = "Installed" if _startup_vbs_path().exists() else "Not installed"
        print(f"Windows Autostart: {autostart_str}")
    print(f"Current Interval : {state.get('current_interval_minutes', 3)} minutes")
    print(f"Last Checked     : {state.get('last_checked') or 'Never'}")
    if state.get("last_error"):
        print(f"Last Error       : {state.get('last_error')}")
    print(f"Log File         : {LOG_FILE}")
    print(f"Watched Repos    : {', '.join(config.get('watched_repos', [])) or 'All owned repositories'}\n")


def cmd_scan(args):
    config = load_config()
    state = load_state()
    detector = CodeRabbitDetector(
        github_user=config.get("github_user", ""),
        watched_repos=config.get("watched_repos", []),
        email_config=config,
    )
    seen_order = list(dict.fromkeys(state.get("seen_ids", [])))
    seen_input = set() if args.all else set(seen_order)
    findings, next_seen = detector.scan_all(seen_input)

    if detector.last_email_error:
        print(f"[Email Warning] {detector.last_email_error}", file=sys.stderr)

    if not findings:
        print("No new CodeRabbit updates detected.")
    else:
        print(f"Detected {len(findings)} CodeRabbit update(s):")
        for item in findings:
            url_part = f" ({item['url']})" if item.get("url") else ""
            print(f"- [{item['type']}] {item['summary']}{url_part}")
            if args.notify and config.get("desktop_notifications"):
                notify_desktop(f"{item['type']} - {item['repo']}", item["summary"])
            if args.notify and config.get("webhook_url"):
                send_webhook(config["webhook_url"], f"{item['type']} - {item['repo']}", item["summary"])

    if args.mark_seen and findings:
        state["seen_ids"] = merge_seen_ids(seen_order, next_seen)
        save_state(state)


def cmd_test_notify(args):
    print("Sending test notifications...")
    notify_desktop("RabbitPulse Test 🐰", "Desktop notification pipeline is functioning properly!")
    config = load_config()
    if config.get("webhook_url"):
        send_webhook(config["webhook_url"], "RabbitPulse Test 🐰", "Webhook notification test successful!")
        print("Webhook alert dispatched.")
    print("Test notification sent.")


def cmd_config(args):
    config = load_config()
    if args.key is not None and args.value is not None:
        key = args.key
        if key not in DEFAULT_CONFIG:
            print(f"Unknown configuration key: '{key}'.", file=sys.stderr)
            sys.exit(2)
        val = args.value
        if key in _INT_KEYS:
            parsed = int(val)
            if parsed < 1:
                print(f"'{key}' must be >= 1.", file=sys.stderr)
                sys.exit(2)
            val = parsed
        elif key in _BOOL_KEYS:
            lowered = val.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                val = True
            elif lowered in {"false", "0", "no", "off"}:
                val = False
            else:
                print(f"Invalid boolean for '{key}': {val}", file=sys.stderr)
                sys.exit(2)
        elif key in _LIST_KEYS:
            val = [r.strip() for r in val.split(",") if r.strip()]
        config[key] = val
        save_config(config)
        display_val = "***" if key == "email_password" and val else val
        print(f"Updated configuration: {key} = {display_val}")
    else:
        display = dict(config)
        if display.get("email_password"):
            display["email_password"] = "***"
        print(json.dumps(display, indent=2))


def cmd_autostart(args):
    if not sys.platform.startswith("win"):
        print("Autostart installer currently targets Windows environments.")
        return

    vbs_path = _startup_vbs_path()
    vbs_path.parent.mkdir(parents=True, exist_ok=True)

    if args.action == "install":
        pythonw = Path(sys.executable).parent / "pythonw.exe"
        if not pythonw.exists():
            pythonw = sys.executable

        vbs_content = (
            'Set WshShell = CreateObject("WScript.Shell")\n'
            f'WshShell.Run """{pythonw}"" -m rabbitpulse.cli start", 0, False\n'
        )
        with open(vbs_path, "w", encoding="utf-8") as f:
            f.write(vbs_content)
        print(f"Successfully installed startup shortcut to: {vbs_path}")
    elif args.action == "remove":
        if vbs_path.exists():
            vbs_path.unlink()
            print("Removed startup shortcut.")
        else:
            print("No startup shortcut found.")


def main():
    parser = argparse.ArgumentParser(
        prog="rabbitpulse",
        description="RabbitPulse: Adaptive background monitor for CodeRabbit reviews, GitHub issues, and IMAP emails.",
    )
    subparsers = parser.add_subparsers(dest="command")

    p_start = subparsers.add_parser("start", help="Start the monitoring daemon")
    p_start.add_argument("--daemon", "-d", action="store_true", help="Run detached in background")

    subparsers.add_parser("stop", help="Stop the monitoring daemon")
    subparsers.add_parser("status", help="Show current sentinel status")

    p_scan = subparsers.add_parser("scan", help="Run a single immediate scan and print findings")
    p_scan.add_argument("--all", action="store_true", help="Ignore seen_ids and report all open CodeRabbit items")
    p_scan.add_argument("--notify", action="store_true", help="Send desktop/webhook alerts for findings")
    p_scan.add_argument("--mark-seen", action="store_true", help="Record newly discovered IDs into state.json")

    subparsers.add_parser("test-notify", help="Send a test notification")

    p_config = subparsers.add_parser("config", help="View or update settings")
    p_config.add_argument("key", nargs="?", help="Configuration key to set")
    p_config.add_argument("value", nargs="?", help="New value for configuration key")

    p_auto = subparsers.add_parser("autostart", help="Configure system startup")
    p_auto.add_argument("action", choices=["install", "remove"], help="Install or remove autostart")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "scan": cmd_scan,
        "test-notify": cmd_test_notify,
        "config": cmd_config,
        "autostart": cmd_autostart,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()

