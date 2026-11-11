import json
import subprocess
import sys
import urllib.parse
import urllib.request


def notify_desktop(title: str, message: str) -> None:
    """Deliver a native desktop notification across Windows, macOS, or Linux."""
    clean_title = (title or "RabbitPulse").strip()[:120]
    clean_message = (message or "").strip()[:400]
    try:
        if sys.platform.startswith("win"):
            _notify_windows(clean_title, clean_message)
        elif sys.platform == "darwin":
            _notify_macos(clean_title, clean_message)
        else:
            _notify_linux(clean_title, clean_message)
    except Exception as e:
        print(f"[Notifier Warning] Desktop notification failed: {e}", file=sys.stderr)


def _notify_windows(title: str, message: str) -> None:
    """Show a Windows Action Center toast with a silent WScript fallback."""
    safe_title = title.replace("'", "''")
    safe_msg = message.replace("'", "''")
    ps_cmd = f"""
    try {{
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $toastXml = [xml]$template.GetXml()
        $toastXml.GetElementsByTagName('text')[0].AppendChild($toastXml.CreateTextNode('{safe_title}')) | Out-Null
        $toastXml.GetElementsByTagName('text')[1].AppendChild($toastXml.CreateTextNode('{safe_msg}')) | Out-Null
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml($toastXml.OuterXml)
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('RabbitPulse').Show($toast)
    }} catch {{
        $wshell = New-Object -ComObject Wscript.Shell
        $wshell.Popup('{safe_msg}', 5, '{safe_title}', 64) | Out-Null
    }}
    """
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=0x08000000,
    )


def _notify_macos(title: str, message: str) -> None:
    """Show a macOS Notification Center banner via AppleScript."""
    safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
    safe_msg = message.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{safe_msg}" with title "{safe_title}" subtitle "CodeRabbit Alert"'
    subprocess.Popen(
        ["osascript", "-e", script],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _notify_linux(title: str, message: str) -> None:
    """Show a Linux desktop notification via notify-send."""
    subprocess.Popen(
        ["notify-send", "-a", "RabbitPulse", title, message],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def send_webhook(webhook_url: str, title: str, message: str) -> None:
    """Optionally send alert to Discord, Slack, or a generic HTTP webhook."""
    if not webhook_url:
        return
    parsed = urllib.parse.urlparse(webhook_url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        print("[Notifier Warning] Skipping invalid webhook URL scheme.", file=sys.stderr)
        return
    try:
        if "discord.com" in parsed.netloc.lower() or "discordapp.com" in parsed.netloc.lower():
            payload = {
                "embeds": [{
                    "title": title[:250],
                    "description": message[:2000],
                    "color": 0xFF5C00,  # CodeRabbit orange
                }]
            }
        else:
            payload = {"text": f"*{title}*\n{message}"}

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url.strip(),
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "RabbitPulse/1.1"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"[Notifier Warning] Webhook dispatch failed: {e}", file=sys.stderr)

