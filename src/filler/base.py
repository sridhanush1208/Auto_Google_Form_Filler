"""Base classes for Google Form filler engines."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


@dataclass
class SubmissionResult:
    """Represents the result of a form submission."""
    success: bool
    status_code: Optional[int] = None
    message: str = ""
    submitted_payload: Dict[str, Any] = field(default_factory=dict)
    response_body_snippet: str = ""
    error: Optional[str] = None
    dry_run: bool = False


class BaseFormFiller(ABC):
    """Abstract base class for all form filler implementations."""

    def __init__(self, form_url: str):
        self.form_url = form_url.strip()
        self.response_url = self._resolve_response_url(self.form_url)

    def _resolve_response_url(self, url: str) -> str:
        """Convert viewform or edit URL to formResponse endpoint."""
        clean = url.split("?")[0]
        if "/viewform" in clean:
            return clean.replace("/viewform", "/formResponse")
        if not clean.endswith("/formResponse"):
            clean = clean.rstrip("/") + "/formResponse"
        return clean

    @abstractmethod
    def submit(
        self,
        fields: Dict[str, Any],
        email: Optional[str] = None,
        dry_run: bool = False
    ) -> SubmissionResult:
        """Submit the form with given fields and email."""
        pass
