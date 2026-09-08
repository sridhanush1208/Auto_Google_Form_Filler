"""Email notification dispatcher for Google Form submission alerts."""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Dispatches email notifications on form submission events."""

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        recipient_email: Optional[str] = None,
    ):
        from src.db import get_setting
        db_user = get_setting("smtp_user", "")
        db_pass = get_setting("smtp_password", "")
        db_host = get_setting("smtp_host", "smtp.gmail.com")
        db_port = get_setting("smtp_port", "587")

        self.smtp_host = smtp_host or os.getenv("SMTP_HOST") or db_host or "smtp.gmail.com"
        self.smtp_port = int(smtp_port or os.getenv("SMTP_PORT") or db_port or 587)
        self.smtp_user = smtp_user or os.getenv("SMTP_USER") or db_user or ""
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD") or db_pass or ""
        self.recipient_email = recipient_email or os.getenv("ALERT_RECIPIENT_EMAIL", self.smtp_user)
        self.last_error: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        """Check if required SMTP credentials are set."""
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.recipient_email)

    def send_email(self, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
        """Send an email using configured SMTP settings."""
        if not self.is_configured:
            self.last_error = "SMTP credentials (smtp_user, smtp_password) are not configured."
            logger.warning(f"SMTP not configured. Missing: user={'yes' if self.smtp_user else 'no'}, pass={'yes' if self.smtp_password else 'no'}, recipient={'yes' if self.recipient_email else 'no'}")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.smtp_user
        msg["To"] = self.recipient_email

        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))

        try:
            if self.smtp_port == 465:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15) as server:
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            logger.info(f"Notification email sent successfully to {self.recipient_email}")
            return True
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Failed to send email notification: {e}")
            return False

    def notify_success(self, form_url: str, submitted_fields: Dict[str, Any], timestamp: str) -> bool:
        """Send a success alert email."""
        subject = "✅ Google Form Submitted Successfully"
        
        field_rows = "".join(
            f"<tr><td style='padding:6px 12px;border:1px solid #e2e8f0;font-family:monospace;font-size:12px;color:#4a5568;'>{k}</td>"
            f"<td style='padding:6px 12px;border:1px solid #e2e8f0;font-weight:500;color:#1a202c;'>{v}</td></tr>"
            for k, v in submitted_fields.items()
        )

        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f7fafc; padding: 24px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                <div style="background-color: #38a169; color: white; padding: 16px 24px;">
                    <h2 style="margin: 0; font-size: 20px;">✅ Google Form Submission Recorded</h2>
                </div>
                <div style="padding: 24px;">
                    <p style="margin-top: 0; color: #4a5568;">Your scheduled autonomous form submission succeeded.</p>
                    <p><strong>Timestamp:</strong> {timestamp}</p>
                    <p><strong>Form:</strong> <a href="{form_url}" style="color: #3182ce;">View Form</a></p>
                    
                    <h3 style="margin-top: 24px; color: #2d3748; font-size: 15px;">Submitted Field Values:</h3>
                    <table style="width: 100%; border-collapse: collapse; margin-top: 8px;">
                        <thead>
                            <tr style="background-color: #edf2f7; text-align: left;">
                                <th style="padding: 8px 12px; border: 1px solid #e2e8f0; font-size: 12px; color: #4a5568;">Field / Entry ID</th>
                                <th style="padding: 8px 12px; border: 1px solid #e2e8f0; font-size: 12px; color: #4a5568;">Value</th>
                            </tr>
                        </thead>
                        <tbody>
                            {field_rows}
                        </tbody>
                    </table>
                </div>
                <div style="background-color: #edf2f7; padding: 12px 24px; font-size: 12px; color: #718096; text-align: center;">
                    Autonomous Google Form Filler • Runs via GitHub Actions
                </div>
            </div>
        </body>
        </html>
        """

        plain = f"Google Form submitted successfully at {timestamp}.\nForm: {form_url}\n\nSubmitted Values:\n"
        for k, v in submitted_fields.items():
            plain += f"  {k}: {v}\n"

        return self.send_email(subject, plain, html)

    def notify_failure(self, form_url: str, error_message: str, timestamp: str) -> bool:
        """Send a failure alert email."""
        subject = "🚨 Google Form Submission FAILED"

        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f7fafc; padding: 24px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; border: 1px solid #fed7d7; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                <div style="background-color: #e53e3e; color: white; padding: 16px 24px;">
                    <h2 style="margin: 0; font-size: 20px;">🚨 Google Form Submission Failed</h2>
                </div>
                <div style="padding: 24px;">
                    <p style="margin-top: 0; color: #4a5568;">An error occurred during scheduled autonomous form submission.</p>
                    <p><strong>Timestamp:</strong> {timestamp}</p>
                    <p><strong>Target Form:</strong> <a href="{form_url}" style="color: #3182ce;">{form_url}</a></p>
                    
                    <div style="margin-top: 16px; background-color: #fff5f5; border: 1px solid #feb2b2; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 13px; color: #c53030; white-space: pre-wrap;">
{error_message}
                    </div>
                </div>
                <div style="background-color: #edf2f7; padding: 12px 24px; font-size: 12px; color: #718096; text-align: center;">
                    Autonomous Google Form Filler • Check GitHub Actions run logs
                </div>
            </div>
        </body>
        </html>
        """

        plain = f"Google Form submission failed at {timestamp}.\nForm: {form_url}\nError: {error_message}\n"
        return self.send_email(subject, plain, html)
