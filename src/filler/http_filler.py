"""Direct HTTP POST Google Form submission engine."""
import time
import re
from typing import Dict, Any, Optional, List, Tuple
import requests
from bs4 import BeautifulSoup

from .base import BaseFormFiller, SubmissionResult
from ..utils.date_resolver import resolve_variables


class HttpFormFiller(BaseFormFiller):
    """Submits Google Forms directly via HTTP POST to the formResponse endpoint."""

    def __init__(self, form_url: str, timeout: int = 15, max_retries: int = 3):
        super().__init__(form_url)
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": self.form_url,
            "Origin": "https://docs.google.com",
        })

    def _prepare_payload(
        self,
        fields: Dict[str, Any],
        email: Optional[str] = None,
        tz_name: str = "Asia/Kolkata"
    ) -> List[Tuple[str, str]]:
        """Resolve dynamic variables and construct list of key-value tuples for multipart/urlencoded form data."""
        resolved = resolve_variables(fields, tz_name=tz_name)
        payload: List[Tuple[str, str]] = []

        if email:
            payload.append(("emailAddress", str(email).strip()))

        for key, val in resolved.items():
            k = str(key).strip()
            # Ensure key starts with entry. if not already
            if not k.startswith("entry.") and k.isdigit():
                k = f"entry.{k}"

            if isinstance(val, list):
                for item in val:
                    payload.append((k, str(item)))
            else:
                payload.append((k, str(val)))

        # Standard Google Form control params
        payload.append(("fvv", "1"))
        payload.append(("pageHistory", "0"))

        return payload

    def _verify_response(self, response: requests.Response) -> Tuple[bool, str]:
        """Verify if response indicates successful recording of response."""
        if response.status_code != 200:
            return False, f"Server returned HTTP status {response.status_code}"

        html = response.text
        # Common Google Form success confirmation markers
        success_markers = [
            "Your response has been recorded",
            "freebirdFormviewerViewResponseConfirmationMessage",
            "v2CG7e", # modern Google form confirmation message CSS class
            "has been recorded",
            "response has been recorded",
            "Thanks for submitting",
        ]

        for marker in success_markers:
            if marker.lower() in html.lower():
                return True, "Response recorded successfully by Google Forms."

        # Check for Google Form validation errors
        soup = BeautifulSoup(html, "html.parser")
        error_elem = soup.find(class_=re.compile(r"(errorMessage|error-msg|freebirdFormviewerViewItemsItemErrorMessage)"))
        if error_elem:
            return False, f"Form validation error: {error_elem.get_text(strip=True)}"

        # If HTTP 200 and no explicit error, accept with warning
        return True, "Received HTTP 200 OK from formResponse."

    def submit(
        self,
        fields: Dict[str, Any],
        email: Optional[str] = None,
        dry_run: bool = False,
        tz_name: str = "Asia/Kolkata"
    ) -> SubmissionResult:
        """Submit the form via HTTP POST."""
        raw_payload = self._prepare_payload(fields, email=email, tz_name=tz_name)
        payload_dict = {}
        for k, v in raw_payload:
            if k in payload_dict:
                if isinstance(payload_dict[k], list):
                    payload_dict[k].append(v)
                else:
                    payload_dict[k] = [payload_dict[k], v]
            else:
                payload_dict[k] = v

        if dry_run:
            return SubmissionResult(
                success=True,
                status_code=200,
                message="[DRY-RUN] Form payload validated and dynamic variables resolved successfully.",
                submitted_payload=payload_dict,
                dry_run=True
            )

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.post(
                    self.response_url,
                    data=raw_payload,
                    timeout=self.timeout,
                    allow_redirects=True
                )
                success, msg = self._verify_response(response)
                snippet = response.text[:300]

                if success:
                    return SubmissionResult(
                        success=True,
                        status_code=response.status_code,
                        message=msg,
                        submitted_payload=payload_dict,
                        response_body_snippet=snippet,
                        dry_run=False
                    )
                else:
                    # Non-200 or validation error
                    if response.status_code >= 500 and attempt < self.max_retries:
                        time.sleep(2 * attempt)
                        continue
                    return SubmissionResult(
                        success=False,
                        status_code=response.status_code,
                        message=msg,
                        submitted_payload=payload_dict,
                        response_body_snippet=snippet,
                        error=msg,
                        dry_run=False
                    )

            except (requests.ConnectionError, requests.Timeout) as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    time.sleep(2 * attempt)
                    continue

        return SubmissionResult(
            success=False,
            status_code=None,
            message=f"Submission failed after {self.max_retries} attempts.",
            submitted_payload=payload_dict,
            error=last_error or "Network error / Connection timeout",
            dry_run=False
        )
