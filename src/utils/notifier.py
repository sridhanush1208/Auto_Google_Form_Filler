from email.header import Header
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
        self.smtp_user = (smtp_user or os.getenv("SMTP_USER") or db_user or "").strip()
        self.smtp_password = (smtp_password or os.getenv("SMTP_PASSWORD") or db_pass or "").strip()
        self.recipient_email = (recipient_email or os.getenv("ALERT_RECIPIENT_EMAIL", self.smtp_user) or "").strip()
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
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = f"Form Filler Alerts <{self.smtp_user}>"
        msg["To"] = self.recipient_email
        msg["Reply-To"] = self.smtp_user

        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        try:
            if self.smtp_port == 465:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15) as server:
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg, from_addr=self.smtp_user, to_addrs=[self.recipient_email])
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg, from_addr=self.smtp_user, to_addrs=[self.recipient_email])
            logger.info(f"Notification email sent successfully to {self.recipient_email}")
            return True
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Failed to send email notification to {self.recipient_email}: {e}")
            return False

    def notify_success(self, form_url: str, submitted_fields: Dict[str, Any], timestamp: str) -> bool:
        """Send a success alert email."""
        subject = "Form Submission Succeeded"
        
        field_rows = ""
        for k, v in (submitted_fields or {}).items():
            val_str = ", ".join(str(i) for i in v) if isinstance(v, list) else str(v)
            field_rows += (
                f"<tr><td style='padding:8px 12px;border:1px solid #e2e8f0;font-family:monospace;font-size:12px;color:#4a5568;'>{k}</td>"
                f"<td style='padding:8px 12px;border:1px solid #e2e8f0;font-weight:500;color:#1a202c;'>{val_str}</td></tr>"
            )

        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; padding: 24px; color: #1e293b;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
                <div style="background-color: #16a34a; color: white; padding: 18px 24px;">
                    <h2 style="margin: 0; font-size: 18px; font-weight: 700;">Google Form Submission Succeeded</h2>
                </div>
                <div style="padding: 24px;">
                    <p style="margin-top: 0; color: #475569; font-size: 14px;">Your scheduled autonomous form submission was recorded successfully.</p>
                    <div style="background-color: #f1f5f9; padding: 12px 16px; border-radius: 8px; font-size: 13px; margin-bottom: 20px;">
                        <p style="margin: 0 0 6px 0;"><strong>Timestamp:</strong> {timestamp}</p>
                        <p style="margin: 0;"><strong>Form URL:</strong> <a href="{form_url}" style="color: #4f46e5; text-decoration: underline;">{form_url}</a></p>
                    </div>
                    
                    <h3 style="margin: 20px 0 10px 0; color: #0f172a; font-size: 14px; font-weight: 600;">Submitted Field Values:</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="background-color: #f8fafc; text-align: left;">
                                <th style="padding: 8px 12px; border: 1px solid #e2e8f0; font-size: 12px; color: #64748b;">Field ID</th>
                                <th style="padding: 8px 12px; border: 1px solid #e2e8f0; font-size: 12px; color: #64748b;">Selected / Entered Value</th>
                            </tr>
                        </thead>
                        <tbody>
                            {field_rows}
                        </tbody>
                    </table>
                </div>
                <div style="background-color: #f8fafc; padding: 14px 24px; font-size: 12px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0;">
                    Auto Google Form Filler &bull; Autonomous Cloud Automation
                </div>
            </div>
        </body>
        </html>
        """

        plain = f"Google Form submitted successfully at {timestamp}.\nForm: {form_url}\n\nSubmitted Values:\n"
        for k, v in (submitted_fields or {}).items():
            val_str = ", ".join(str(i) for i in v) if isinstance(v, list) else str(v)
            plain += f"  {k}: {val_str}\n"

        return self.send_email(subject, plain, html)

    def notify_failure(self, form_url: str, error_message: str, timestamp: str) -> bool:
        """Send a failure alert email."""
        subject = "Google Form Submission Failed"

        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; padding: 24px; color: #1e293b;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; border: 1px solid #fed7d7; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
                <div style="background-color: #dc2626; color: white; padding: 18px 24px;">
                    <h2 style="margin: 0; font-size: 18px; font-weight: 700;">Google Form Submission Failed</h2>
                </div>
                <div style="padding: 24px;">
                    <p style="margin-top: 0; color: #475569; font-size: 14px;">An error occurred during scheduled autonomous form submission.</p>
                    <div style="background-color: #f1f5f9; padding: 12px 16px; border-radius: 8px; font-size: 13px; margin-bottom: 16px;">
                        <p style="margin: 0 0 6px 0;"><strong>Timestamp:</strong> {timestamp}</p>
                        <p style="margin: 0;"><strong>Target Form:</strong> <a href="{form_url}" style="color: #4f46e5; text-decoration: underline;">{form_url}</a></p>
                    </div>
                    
                    <h3 style="margin: 16px 0 8px 0; color: #0f172a; font-size: 14px; font-weight: 600;">Error Details:</h3>
                    <div style="background-color: #fef2f2; border: 1px solid #fecaca; padding: 14px; border-radius: 8px; font-family: monospace; font-size: 13px; color: #991b1b; white-space: pre-wrap;">{error_message}</div>
                </div>
                <div style="background-color: #f8fafc; padding: 14px 24px; font-size: 12px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0;">
                    Auto Google Form Filler &bull; Autonomous Cloud Automation
                </div>
            </div>
        </body>
        </html>
        """

        plain = f"Google Form submission failed at {timestamp}.\nForm: {form_url}\nError: {error_message}\n"
        return self.send_email(subject, plain, html)

