import sys
import os
import argparse
import subprocess
from pathlib import Path
from rabbitpulse.config import load_config, save_config, load_state, LOG_FILE
from rabbitpulse.notifier import notify_desktop, send_webhook
from rabbitpulse.monitor import MonitorEngine, LOCK_PORT

def cmd_start(args):
    if args.daemon:
        # Run detached in background
        if sys.platform.startswith("win"):
            DETACHED_PROCESS = 0x00000008
            cmd = [sys.executable, "-m", "rabbitpulse.cli", "start"]
            p = subprocess.Popen(cmd, creationflags=DETACHED_PROCESS, close_fds=True)
            print(f"RabbitPulse started in background (PID: {p.pid}).")
        else:
            p = subprocess.Popen([sys.executable, "-m", "rabbitpulse.cli", "start"], start_new_session=True)
            print(f"RabbitPulse started in background (PID: {p.pid}).")
        return

    engine = MonitorEngine()
    engine.run()

def cmd_stop(args):
    if sys.platform.startswith("win"):
        # Find process holding the lock port and terminate
        cmd = f"Get-NetTCPConnection -LocalPort {LOCK_PORT} -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"
        subprocess.run(["powershell", "-Command", cmd], capture_output=True)
        print("RabbitPulse daemon stopped.")
    else:
        # Kill by port on Unix
        subprocess.run(f"fuser -k {LOCK_PORT}/tcp", shell=True, capture_output=True)
        print("RabbitPulse daemon stopped.")

def cmd_status(args):
    config = load_config()
    state = load_state()

    # Check if process is actively running
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    is_running = False
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.close()
    except socket.error:
        is_running = True

    status_str = "🟢 RUNNING" if is_running else "🔴 STOPPED"
    print("\n=== RabbitPulse Status ===")
    print(f"Service State    : {status_str}")
    print(f"Monitored User   : {config.get('github_user') or '(auto-detect)'}")
    print(f"Current Interval : {state.get('current_interval_minutes', 3)} minutes")
    print(f"Last Checked     : {state.get('last_checked') or 'Never'}")
    print(f"Log File         : {LOG_FILE}")
    print(f"Watched Repos    : {', '.join(config.get('watched_repos', [])) or 'All owned repositories'}\n")

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
    if args.key and args.value:
        key = args.key
        val = args.value
        # Type casts
        if key in ["base_interval_minutes", "backoff_step_minutes", "max_interval_minutes"]:
            val = int(val)
        elif key in ["desktop_notifications"]:
            val = val.lower() in ["true", "1", "yes"]
        elif key in ["watched_repos"]:
            val = [r.strip() for r in val.split(",") if r.strip()]
        config[key] = val
        save_config(config)
        print(f"Updated configuration: {key} = {val}")
    else:
        import json
        print(json.dumps(config, indent=2))

def cmd_autostart(args):
    if not sys.platform.startswith("win"):
        print("Autostart installer currently targets Windows environments.")
        return

    startup_dir = Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup"
    vbs_path = startup_dir / "RabbitPulse.vbs"

    if args.action == "install":
        pythonw = Path(sys.executable).parent / "pythonw.exe"
        if not pythonw.exists():
            pythonw = sys.executable

        vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """{pythonw}"" -m rabbitpulse.cli start", 0, False
'''
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
        description="RabbitPulse: Adaptive background monitor for CodeRabbit reviews and GitHub issues."
    )
    subparsers = parser.add_subparsers(dest="command")

    # start
    p_start = subparsers.add_parser("start", help="Start the monitoring daemon")
    p_start.add_argument("--daemon", "-d", action="store_true", help="Run detached in background")

    # stop
    subparsers.add_parser("stop", help="Stop the monitoring daemon")

    # status
    subparsers.add_parser("status", help="Show current sentinel status")

    # test-notify
    subparsers.add_parser("test-notify", help="Send a test notification")

    # config
    p_config = subparsers.add_parser("config", help="View or update settings")
    p_config.add_argument("key", nargs="?", help="Configuration key to set")
    p_config.add_argument("value", nargs="?", help="New value for configuration key")

    # autostart
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
        "test-notify": cmd_test_notify,
        "config": cmd_config,
        "autostart": cmd_autostart,
    }

    dispatch[args.command](args)

if __name__ == "__main__":
    main()
