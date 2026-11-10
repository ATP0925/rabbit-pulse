import time
import socket
import logging
import signal
import sys
from datetime import datetime, timezone
from rabbitpulse.config import load_config, load_state, save_state, LOG_FILE
from rabbitpulse.detector import CodeRabbitDetector
from rabbitpulse.notifier import notify_desktop, send_webhook

LOCK_PORT = 49159

class MonitorEngine:
    def __init__(self):
        self.config = load_config()
        self.state = load_state()
        self.running = True
        self.lock_socket = None

        # Configure logger
        self.logger = logging.getLogger("RabbitPulse")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
            formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def acquire_lock(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", LOCK_PORT))
            s.listen(1)
            self.lock_socket = s
            return True
        except socket.error:
            self.logger.warning("Another instance of RabbitPulse is already running.")
            return False

    def handle_signal(self, signum, frame):
        self.logger.info("Shutdown signal received. Exiting gracefully...")
        self.running = False

    def run(self, notify_startup: bool = True):
        if not self.acquire_lock():
            print("RabbitPulse is already running on this machine.", file=sys.stderr)
            sys.exit(0)

        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

        self.logger.info("=== RabbitPulse Sentinel Engine Started ===")
        print(f"[*] RabbitPulse active. Watching user '{self.config.get('github_user')}'.")

        if notify_startup and self.config.get("desktop_notifications"):
            notify_desktop(
                "RabbitPulse Active 🐰",
                f"Monitoring CodeRabbit reviews & issues for {self.config.get('github_user', 'GitHub')}."
            )

        n = self.state.get("current_interval_minutes", self.config.get("base_interval_minutes", 3))
        base_n = self.config.get("base_interval_minutes", 3)
        step_n = self.config.get("backoff_step_minutes", 1)
        max_n = self.config.get("max_interval_minutes", 60)
        seen_ids = set(self.state.get("seen_ids", []))

        detector = CodeRabbitDetector(
            github_user=self.config.get("github_user", ""),
            watched_repos=self.config.get("watched_repos", [])
        )

        while self.running:
            self.logger.info(f"Scanning GitHub (interval: {n} min)...")
            self.state["status"] = "running"
            self.state["last_checked"] = datetime.now(timezone.utc).isoformat()
            self.state["current_interval_minutes"] = n

            try:
                findings, seen_ids = detector.scan_all(seen_ids)
                self.state["seen_ids"] = list(seen_ids)[-300:]

                if findings:
                    self.logger.info(f"Detected {len(findings)} new CodeRabbit update(s)! Resetting interval to {base_n}m.")
                    for item in findings:
                        title = f"{item['type']} - {item['repo']}"
                        msg = item['summary']
                        if self.config.get("desktop_notifications"):
                            notify_desktop(title, msg)
                        if self.config.get("webhook_url"):
                            send_webhook(self.config["webhook_url"], title, msg)
                    n = base_n
                else:
                    self.logger.info(f"No new activity. Incrementing interval: {n}m -> {min(n + step_n, max_n)}m.")
                    n = min(n + step_n, max_n)

                save_state(self.state)

            except Exception as e:
                self.logger.error(f"Error during scan cycle: {e}")

            # Sleep in 1-second chunks so signal interrupts happen promptly
            sleep_duration = n * 60
            start_sleep = time.time()
            while self.running and (time.time() - start_sleep < sleep_duration):
                time.sleep(1)

        self.state["status"] = "stopped"
        save_state(self.state)
        self.logger.info("RabbitPulse Engine stopped.")
