import unittest
from unittest.mock import patch, MagicMock
from rabbitpulse import notifier

class TestNotifier(unittest.TestCase):
    @patch("subprocess.Popen")
    def test_notify_desktop_executes(self, mock_popen):
        notifier.notify_desktop("Test Title", "Test Message")
        self.assertTrue(mock_popen.called)

    @patch("urllib.request.urlopen")
    def test_send_webhook_empty_url(self, mock_urlopen):
        notifier.send_webhook("", "Test Title", "Test Message")
        self.assertFalse(mock_urlopen.called)

    @patch("urllib.request.urlopen")
    def test_send_webhook_discord(self, mock_urlopen):
        mock_response = MagicMock()
        mock_urlopen.return_value = mock_response
        notifier.send_webhook("https://discord.com/api/webhooks/123/xyz", "Test Title", "Test Message")
        self.assertTrue(mock_urlopen.called)

if __name__ == "__main__":
    unittest.main()
