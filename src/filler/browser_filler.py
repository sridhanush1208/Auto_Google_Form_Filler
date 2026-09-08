"""Headless browser (Playwright) Google Form submission engine for forms requiring authentication."""
from typing import Dict, Any, Optional
import time

from .base import BaseFormFiller, SubmissionResult
from ..utils.date_resolver import resolve_variables


class BrowserFormFiller(BaseFormFiller):
    """Submits Google Forms using a headless Chromium browser via Playwright."""

    def __init__(self, form_url: str, headless: bool = True, timeout_ms: int = 30000):
        super().__init__(form_url)
        self.headless = headless
        self.timeout_ms = timeout_ms

    def submit(
        self,
        fields: Dict[str, Any],
        email: Optional[str] = None,
        dry_run: bool = False,
        tz_name: str = "Asia/Kolkata"
    ) -> SubmissionResult:
        """Submit form using Playwright headless browser."""
        resolved = resolve_variables(fields, tz_name=tz_name)
        payload_summary = dict(resolved)
        if email:
            payload_summary["emailAddress"] = email

        if dry_run:
            return SubmissionResult(
                success=True,
                status_code=200,
                message="[DRY-RUN] Browser filler validated payload successfully.",
                submitted_payload=payload_summary,
                dry_run=True
            )

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return SubmissionResult(
                success=False,
                status_code=None,
                message="Playwright is not installed.",
                submitted_payload=payload_summary,
                error=(
                    "To use browser mode, please install Playwright:\n"
                    "pip install -r requirements-browser.txt\n"
                    "playwright install chromium"
                ),
                dry_run=False
            )

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800}
                )
                page = context.new_page()
                page.goto(self.form_url, timeout=self.timeout_ms)
                page.wait_for_load_state("domcontentloaded")

                # Fill Email if present
                if email:
                    email_input = page.locator("input[type='email'], input[name='emailAddress']")
                    if email_input.count() > 0:
                        email_input.first.fill(email)

                # Fill question fields
                for key, val in resolved.items():
                    k = str(key).strip()
                    if not k.startswith("entry.") and k.isdigit():
                        k = f"entry.{k}"

                    # Try matching input by name="entry.XXXX"
                    input_locator = page.locator(f"input[name='{k}'], textarea[name='{k}']")
                    if input_locator.count() > 0:
                        if isinstance(val, list):
                            for v in val:
                                checkbox = page.locator(f"//div[@role='checkbox'][.//span[text()='{v}']]")
                                if checkbox.count() > 0:
                                    checkbox.first.click()
                        else:
                            input_type = input_locator.first.get_attribute("type")
                            if input_type in ("radio", "checkbox"):
                                input_locator.first.check()
                            else:
                                input_locator.first.fill(str(val))
                    else:
                        # Radio/Checkbox choice by label text
                        val_str = str(val)
                        choice_locator = page.locator(f"//div[@role='radio' or @role='checkbox'][.//span[contains(text(), '{val_str}')]]")
                        if choice_locator.count() > 0:
                            choice_locator.first.click()

                time.sleep(1)

                # Click Submit button
                submit_button = page.locator("//span[text()='Submit' or text()='Send']/ancestor::div[@role='button']")
                if submit_button.count() == 0:
                    submit_button = page.locator("button[type='submit'], div[role='button']:has-text('Submit')")

                if submit_button.count() > 0:
                    submit_button.first.click()
                else:
                    browser.close()
                    return SubmissionResult(
                        success=False,
                        status_code=None,
                        message="Could not find the Submit button on the form.",
                        submitted_payload=payload_summary,
                        error="Submit button not found",
                        dry_run=False
                    )

                # Wait for confirmation
                page.wait_for_load_state("networkidle")
                time.sleep(2)
                content = page.content()
                browser.close()

                if "Your response has been recorded" in content or "has been recorded" in content:
                    return SubmissionResult(
                        success=True,
                        status_code=200,
                        message="Form submitted successfully via browser.",
                        submitted_payload=payload_summary,
                        response_body_snippet=content[:200],
                        dry_run=False
                    )
                else:
                    return SubmissionResult(
                        success=False,
                        status_code=None,
                        message="Submission completed but confirmation message was not detected.",
                        submitted_payload=payload_summary,
                        response_body_snippet=content[:200],
                        error="Confirmation marker not found after submit",
                        dry_run=False
                    )

        except Exception as e:
            return SubmissionResult(
                success=False,
                status_code=None,
                message=f"Browser automation error: {e}",
                submitted_payload=payload_summary,
                error=str(e),
                dry_run=False
            )
