# RabbitPulse

RabbitPulse is a small background watcher that keeps an eye on CodeRabbit activity across your GitHub repositories and, optionally, your email inbox.

Instead of leaving browser tabs open or polling at a fixed rate when nothing is happening, RabbitPulse checks every 3 minutes at first and gradually backs off (`3 -> 4 -> 5 ...` up to 60 minutes) during quiet periods. As soon as a new CodeRabbit comment, actionable PR review, repo issue, or inbox alert shows up, it pops a notification and resets back to 3 minutes.

---

## What It Watches

- **Pull request reviews & comments:** Checks inline review comments, PR conversation comments, and top-level review statuses across your repositories and any external PRs you opened. Comments already marked `Addressed in commit` and zero-action summary reviews are recorded quietly without nagging you.
- **Repository issues:** Watches for new issues opened by CodeRabbit as well as open issues where CodeRabbit left a comment.
- **GitHub notifications:** Catches live CodeRabbit notification entries from your GitHub notification feed.
- **Email inbox (optional IMAP):** Connects read-only over IMAP (`imap.gmail.com` by default) to catch unread CodeRabbit email alerts without changing message read flags.
- **Desktop & webhook delivery:** Sends native Windows toast alerts, macOS banners, Linux `notify-send` alerts, and optional Discord or Slack webhooks.

---

## Setup

### Requirements

Install [GitHub CLI](https://cli.github.com/) and make sure you are signed in:

```bash
gh auth status
```

### Install

```bash
git clone https://github.com/ATP0925/rabbit-pulse.git
cd rabbit-pulse
pip install -e .
```

Everything runs on Python's standard library (`3.8+`), with no third-party runtime packages required.

---

## Commands

```bash
# Check daemon status, current interval, email monitor state, and last error
rabbitpulse status

# Run one immediate check without starting the background loop
rabbitpulse scan

# Include previously seen open items during a manual scan
rabbitpulse scan --all

# Start in the foreground or detached in the background
rabbitpulse start
rabbitpulse start --daemon

# Stop the running background process
rabbitpulse stop

# Send a test toast / webhook notification
rabbitpulse test-notify
```

### Windows Auto-Start

Install or remove the hidden Startup launcher (`RabbitPulse.vbs`):

```bash
rabbitpulse autostart install
rabbitpulse autostart remove
```

Or run `scripts\install_autostart.bat` / `scripts\uninstall_autostart.bat`.

---

## Configuration

Settings live in `~/.rabbitpulse/config.json` and can be updated from the CLI:

```bash
# Print current configuration (email_password is masked)
rabbitpulse config

# Change initial polling interval or backoff limits
rabbitpulse config base_interval_minutes 3
rabbitpulse config backoff_step_minutes 1
rabbitpulse config max_interval_minutes 60

# Watch specific repositories only (pass "" to watch all owned repos again)
rabbitpulse config watched_repos "owner/repo1,owner/repo2"
rabbitpulse config watched_repos ""

# Connect a Discord or Slack webhook
rabbitpulse config webhook_url "https://discord.com/api/webhooks/your/webhook"
```

### Optional Email Monitoring (Gmail / IMAP)

Read-only IMAP polling is disabled by default. To turn it on with Gmail (using a Google App Password stored in an environment variable):

```bash
rabbitpulse config email_user "you@gmail.com"
rabbitpulse config email_enabled true
```

Then set `RABBITPULSE_EMAIL_PASSWORD` in your environment before starting RabbitPulse (or change `email_password_env` / `email_imap_host` for another mail provider).

---

## Tests

```bash
python -m unittest discover -s tests -v
```

---

## License

MIT
