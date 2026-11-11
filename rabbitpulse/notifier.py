import sys
import json
import urllib.request
import subprocess

def notify_desktop(title: str, message: str):
    """Deliver a native desktop notification across Windows, macOS, or Linux."""
    try:
        if sys.platform.startswith("win"):
            _notify_windows(title, message)
        elif sys.platform == "darwin":
            _notify_macos(title, message)
        else:
            _notify_linux(title, message)
    except Exception as e:
        print(f"[Notifier Warning] Desktop notification failed: {e}", file=sys.stderr)

def _notify_windows(title: str, message: str):
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
        ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=0x08000000
    )

def _notify_macos(title: str, message: str):
    script = f'display notification "{message}" with title "{title}" subtitle "CodeRabbit Alert"'
    subprocess.Popen(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

def _notify_linux(title: str, message: str):
    subprocess.Popen(
        ["notify-send", "-a", "RabbitPulse", title, message],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

def send_webhook(webhook_url: str, title: str, message: str):
    """Optionally send alert to Discord, Slack, or a webhook endpoint."""
    if not webhook_url:
        return
    try:
        # Detect Discord webhook vs generic Slack/HTTP
        if "discord.com" in webhook_url:
            payload = {
                "embeds": [{
                    "title": title,
                    "description": message,
                    "color": 0xFF5C00  # CodeRabbit orange
                }]
            }
        else:
            payload = {"text": f"*{title}*\n{message}"}
            
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "RabbitPulse/1.0"}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"[Notifier Warning] Webhook dispatch failed: {e}", file=sys.stderr)

