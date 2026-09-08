"""Unified CLI runner for Autonomous Google Form Filler."""
import os
import sys
import argparse
import logging
from datetime import datetime
import yaml
from dotenv import load_dotenv

# Load local .env if present
load_dotenv()

from src.filler.http_filler import HttpFormFiller
from src.filler.browser_filler import BrowserFormFiller
from src.utils.notifier import EmailNotifier
from src.utils.date_resolver import resolve_variables, get_current_time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("FormFillerMain")


def load_config(config_path: str = "config/form_config.yaml") -> dict:
    """Load configuration from YAML file or environment overrides."""
    if not os.path.exists(config_path):
        # Fallback to example if available
        example_path = "config/form_config.example.yaml"
        if os.path.exists(example_path):
            logger.warning(f"Config file '{config_path}' not found. Loading '{example_path}' as fallback.")
            config_path = example_path
        else:
            raise FileNotFoundError(f"Configuration file not found at: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    # Allow environment variable overrides
    env_email = os.getenv("FORM_SUBMISSION_EMAIL")
    if env_email:
        config["email"] = env_email

    return config


def run(
    config_path: str = "config/form_config.yaml",
    dry_run: bool = False,
    override_mode: str = None,
    override_email: str = None,
    no_notify: bool = False,
    tz_name: str = "Asia/Kolkata"
) -> bool:
    """Execute the form submission workflow."""
    now_dt = get_current_time(tz_name)
    timestamp_str = now_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    logger.info(f"Starting form submission workflow at {timestamp_str}")

    try:
        config = load_config(config_path)
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        return False

    form_url = config.get("form_url")
    if not form_url or "YOUR_FORM_ID_HERE" in form_url:
        logger.error(f"Invalid or placeholder form_url configured in {config_path}")
        return False

    mode = (override_mode or config.get("mode", "http")).lower()
    email = override_email or config.get("email")
    fields = config.get("fields", {})
    notification_cfg = config.get("notifications", {})

    logger.info(f"Target Form URL: {form_url}")
    logger.info(f"Submission Mode: {mode.upper()}")
    logger.info(f"Submission Email: {email or 'None'}")
    logger.info(f"Configured Fields Count: {len(fields)}")
    if dry_run:
        logger.info("=== DRY-RUN MODE ENABLED (No actual HTTP requests will be sent) ===")

    # Select engine
    if mode == "browser":
        filler = BrowserFormFiller(form_url=form_url)
    else:
        filler = HttpFormFiller(form_url=form_url)

    # Submit
    result = filler.submit(fields=fields, email=email, dry_run=dry_run, tz_name=tz_name)

    # Handle notifications
    notifier = EmailNotifier()
    should_notify = notification_cfg.get("enabled", True) and not no_notify and not dry_run

    if result.success:
        logger.info(f"🎉 SUCCESS: {result.message}")
        logger.info(f"Submitted Payload: {result.submitted_payload}")
        if should_notify and notification_cfg.get("on_success", True):
            notifier.notify_success(
                form_url=form_url,
                submitted_fields=result.submitted_payload,
                timestamp=timestamp_str
            )
        return True
    else:
        logger.error(f"❌ FAILURE: {result.message}")
        if result.error:
            logger.error(f"Error details: {result.error}")
        if should_notify and notification_cfg.get("on_failure", True):
            notifier.notify_failure(
                form_url=form_url,
                error_message=result.error or result.message,
                timestamp=timestamp_str
            )
        return False


def main():
    parser = argparse.ArgumentParser(description="Autonomous Google Form Filler CLI")
    parser.add_argument("--config", default="config/form_config.yaml", help="Path to config YAML file")
    parser.add_argument("--dry-run", action="store_true", help="Simulate submission without making network calls")
    parser.add_argument("--mode", choices=["http", "browser"], help="Override submission engine mode")
    parser.add_argument("--email", help="Override submission email address")
    parser.add_argument("--no-notify", action="store_true", help="Disable email notifications")
    parser.add_argument("--tz", default="Asia/Kolkata", help="Timezone for dynamic date values (default: Asia/Kolkata)")

    args = parser.parse_args()
    success = run(
        config_path=args.config,
        dry_run=args.dry_run,
        override_mode=args.mode,
        override_email=args.email,
        no_notify=args.no_notify,
        tz_name=args.tz
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
