# RabbitPulse 🐰

An adaptive, cross-platform background sentinel that watches your GitHub repositories for CodeRabbit reviews, inline findings, and repo issues.

Instead of keeping browser tabs open or constantly refreshing your inbox, RabbitPulse checks GitHub quietly in the background and pops native desktop notifications the moment CodeRabbit leaves a review or reports an issue.

---

## Highlights

- **Dynamic Backoff ($n+1$ Adaptive Polling):** Starts checking every 3 minutes. If no new review is detected, it gently expands the interval ($3 \to 4 \to 5 \to 6$ minutes) to save bandwidth and rate limits. The moment a new comment or issue lands, it resets back to 3 minutes.
- **Issues & PR Coverage:** Watches for both Pull Request reviews and standalone repository issues created or commented on by CodeRabbit.
- **Native OS Alerts:** Fires native desktop notifications across Windows (Action Center toasts), macOS (Notification Center), and Linux (`notify-send`).
- **Webhook Integration:** Optionally routes alerts directly to a Discord or Slack channel.
- **Auto-Detects GitHub User:** Connects directly through your authenticated `gh` CLI session with zero credential setup needed.
- **Auto-Start On Boot:** Can automatically launch quietly when your system logs in.

---

## Quickstart

### Prerequisites
Make sure you have [GitHub CLI](https://cli.github.com/) installed and logged in:
```bash
gh auth status
```

### Installation
Clone and install locally in editable mode:
```bash
git clone https://github.com/ATP0925/rabbit-pulse.git
cd rabbit-pulse
pip install -e .
```

---

## Usage

### 1. Check Service Status
```bash
rabbitpulse status
```
Displays your current polling interval, monitored account, and last check timestamp.

### 2. Start Monitoring
Run in foreground:
```bash
rabbitpulse start
```
Or start detached in the background:
```bash
rabbitpulse start --daemon
```

### 3. Stop the Daemon
```bash
rabbitpulse stop
```

### 4. Send a Test Notification
Verify that your operating system's notification delivery is working:
```bash
rabbitpulse test-notify
```

### 5. Setup Auto-Start on System Boot
On Windows, you can install the background launcher into your Startup folder:
```bash
rabbitpulse autostart install
```
To remove it later:
```bash
rabbitpulse autostart remove
```

---

## Configuration

Settings are saved in `~/.rabbitpulse/config.json`. You can inspect or modify them using the CLI:

```bash
# View active configuration
rabbitpulse config

# Set custom base interval (e.g. 5 minutes)
rabbitpulse config base_interval_minutes 5

# Connect a Discord or Slack webhook for mobile alerts
rabbitpulse config webhook_url "https://discord.com/api/webhooks/your/webhook"

# Focus on specific repositories only
rabbitpulse config watched_repos "owner/repo1,owner/repo2"
```

---

## Running Tests

RabbitPulse has zero heavy dependencies and runs on Python's built-in standard library:

```bash
python -m unittest discover -s tests
```

---

## License

MIT License. Free to use and customize.
