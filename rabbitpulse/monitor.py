import logging
import signal
import socket
import sys
import time
from datetime import datetime, timezone
from typing import Iterable, List

from rabbitpulse.config import LOG_FILE, load_config, load_state, save_state
from rabbitpulse.detector import CodeRabbitDetector
from rabbitpulse.notifier import notify_desktop, send_webhook

LOCK_PORT = 49159
MAX_SEEN_IDS = 1000


class _FlushFileHandler(logging.FileHandler):
    """File handler that flushes every log line so status tails are always current."""

    def emit(self, record):
        super().emit(record)
        self.flush()


def merge_seen_ids(existing: List[str], updated: Iterable[str], limit: int = MAX_SEEN_IDS) -> List[str]:
    """Preserve insertion order while capping seen IDs to the most recent entries."""
    ordered = list(dict.fromkeys(existing))
    known = set(ordered)
    for item in updated:
        if item not in known:
            ordered.append(item)
            known.add(item)
    return ordered[-limit:]


def _build_detector(cfg: dict) -> CodeRabbitDetector:
    return CodeRabbitDetector(
        github_user=cfg.get("github_user", ""),
        watched_repos=cfg.get("watched_repos", []),
        email_config=cfg,
    )


class MonitorEngine:
    """Adaptive background sentinel loop that backs off on quiet cycles."""

    def __init__(self):
        self.config = load_config()
        self.state = load_state()
        self.running = True
        self.lock_socket = None

        self.logger = logging.getLogger("RabbitPulse")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = _FlushFileHandler(LOG_FILE, encoding="utf-8")
            formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def acquire_lock(self) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", LOCK_PORT))
            s.listen(1)
            self.lock_socket = s
            return True
        except OSError:
            s.close()
            self.logger.warning("Another instance of RabbitPulse is already running.")
            return False

    def handle_signal(self, signum, frame) -> None:
        self.logger.info("Shutdown signal received. Exiting gracefully...")
        self.running = False

    def run_cycle(self, seen_order: List[str], n: int) -> tuple:
        """Execute a single scan cycle and return (next_interval, updated_seen_order, findings)."""
        self.config = load_config()
        base_n = max(1, int(self.config.get("base_interval_minutes", 3)))
        step_n = max(1, int(self.config.get("backoff_step_minutes", 1)))
        max_n = max(base_n, int(self.config.get("max_interval_minutes", 60)))

        detector = _build_detector(self.config)
        self.state["status"] = "running"
        self.state["last_checked"] = datetime.now(timezone.utc).isoformat()
        self.state["current_interval_minutes"] = n

        findings, next_seen_set = detector.scan_all(set(seen_order))
        seen_order = merge_seen_ids(seen_order, next_seen_set)
        self.state["seen_ids"] = seen_order

        if detector.last_email_error:
            self.logger.warning(f"Email scan warning: {detector.last_email_error}")
            self.state["last_error"] = f"Email: {detector.last_email_error}"
        else:
            self.state["last_error"] = ""

        if findings:
            self.logger.info(f"Detected {len(findings)} new CodeRabbit update(s)! Resetting interval to {base_n}m.")
            for item in findings:
                title = f"{item['type']} - {item['repo']}"
                msg = item["summary"]
                if self.config.get("desktop_notifications"):
                    notify_desktop(title, msg)
                if self.config.get("webhook_url"):
                    send_webhook(self.config["webhook_url"], title, msg)
            next_n = base_n
        else:
            next_n = min(n + step_n, max_n)
            self.logger.info(f"No new activity. Incrementing interval: {n}m -> {next_n}m.")

        save_state(self.state)
        return next_n, seen_order, findings

    def run(self, notify_startup: bool = True) -> None:
        if not self.acquire_lock():
            print("RabbitPulse is already running on this machine.", file=sys.stderr)
            sys.exit(0)

        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

        try:
            self.logger.info("=== RabbitPulse Sentinel Engine Started ===")
            print(f"[*] RabbitPulse active. Watching user '{self.config.get('github_user')}'.")

            if notify_startup and self.config.get("desktop_notifications"):
                notify_desktop(
                    "RabbitPulse Active 🐰",
                    f"Monitoring CodeRabbit reviews & issues for {self.config.get('github_user', 'GitHub')}.",
                )

            base_n = max(1, int(self.config.get("base_interval_minutes", 3)))
            n = max(1, int(self.state.get("current_interval_minutes", base_n)))
            seen_order = list(dict.fromkeys(self.state.get("seen_ids", [])))[-MAX_SEEN_IDS:]

            while self.running:
                self.logger.info(f"Scanning GitHub (interval: {n} min)...")
                try:
                    n, seen_order, _ = self.run_cycle(seen_order, n)
                except Exception as e:
                    self.logger.error(f"Error during scan cycle: {e}")
                    self.state["last_error"] = str(e)
                    save_state(self.state)

                sleep_duration = n * 60
                start_sleep = time.time()
                while self.running and (time.time() - start_sleep < sleep_duration):
                    time.sleep(1)
        finally:
            self.state["status"] = "stopped"
            save_state(self.state)
            if self.lock_socket is not None:
                try:
                    self.lock_socket.close()
                except OSError:
                    pass
                self.lock_socket = None
            self.logger.info("RabbitPulse Engine stopped.")

