"""Tests for EmailNotifier alert dispatcher."""
from unittest.mock import MagicMock, patch
from src.utils.notifier import EmailNotifier


def test_notifier_configuration():
    notifier = EmailNotifier(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_user="test@example.com",
        smtp_password="app_password",
        recipient_email="alert@example.com"
    )
    assert notifier.is_configured is True
    assert notifier.smtp_user == "test@example.com"
    assert notifier.recipient_email == "alert@example.com"


def test_notify_success_message_dispatch():
    notifier = EmailNotifier(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_user="test@example.com",
        smtp_password="app_password",
        recipient_email="alert@example.com"
    )

    with patch("smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        success = notifier.notify_success(
            form_url="https://docs.google.com/forms/d/e/1FAIpQLSeXXXX/viewform",
            submitted_fields={
                "entry.123456": "Option A",
                "entry.654321": ["Check 1", "Check 2"],
                "entry.999999": 10
            },
            timestamp="2026-09-08 23:59:00 IST"
        )

        assert success is True
        mock_server.ehlo.assert_called()
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("test@example.com", "app_password")
        mock_server.send_message.assert_called_once()

        # Verify sent message properties
        call_args = mock_server.send_message.call_args
        msg = call_args[0][0]
        assert "Succeeded" in str(msg["Subject"])
        assert call_args[1]["from_addr"] == "test@example.com"
        assert call_args[1]["to_addrs"] == ["alert@example.com"]


def test_notify_failure_message_dispatch():
    notifier = EmailNotifier(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_user="test@example.com",
        smtp_password="app_password",
        recipient_email="alert@example.com"
    )

    with patch("smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        success = notifier.notify_failure(
            form_url="https://docs.google.com/forms/d/e/1FAIpQLSeXXXX/viewform",
            error_message="Server returned HTTP status 400 Bad Request",
            timestamp="2026-09-08 23:59:00 IST"
        )

        assert success is True
        mock_server.ehlo.assert_called()
        mock_server.starttls.assert_called_once()
        mock_server.send_message.assert_called_once()

        call_args = mock_server.send_message.call_args
        msg = call_args[0][0]
        assert "Failed" in str(msg["Subject"])
        assert call_args[1]["from_addr"] == "test@example.com"
        assert call_args[1]["to_addrs"] == ["alert@example.com"]


def test_notify_success_with_none_fields():
    notifier = EmailNotifier(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_user="test@example.com",
        smtp_password="app_password",
        recipient_email="alert@example.com"
    )

    with patch("smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        # When submitted_fields is None, it should not raise an error
        success = notifier.notify_success(
            form_url="https://docs.google.com/forms/d/e/1FAIpQLSeXXXX/viewform",
            submitted_fields=None,
            timestamp="2026-09-08 23:59:00 IST"
        )
        assert success is True
