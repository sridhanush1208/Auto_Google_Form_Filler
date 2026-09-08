"""Tests for Form Filler engines."""
from src.filler.http_filler import HttpFormFiller


def test_http_filler_dry_run():
    filler = HttpFormFiller("https://docs.google.com/forms/d/e/1FAIpQLSeXXXX/viewform")
    assert filler.response_url == "https://docs.google.com/forms/d/e/1FAIpQLSeXXXX/formResponse"

    fields = {
        "entry.123456": "Static Value",
        "entry.654321": "{{TODAY}}",
        "entry.999888": ["Check 1", "Check 2"]
    }

    result = filler.submit(fields=fields, email="user@test.com", dry_run=True)
    assert result.success is True
    assert result.dry_run is True
    assert result.status_code == 200
    assert result.submitted_payload["entry.123456"] == "Static Value"
    assert result.submitted_payload["emailAddress"] == "user@test.com"
    assert isinstance(result.submitted_payload["entry.999888"], list)
    assert len(result.submitted_payload["entry.999888"]) == 2
    assert "{{" not in result.submitted_payload["entry.654321"]


def test_http_filler_payload_preparation():
    filler = HttpFormFiller("https://docs.google.com/forms/d/e/1FAIpQLSeXXXX/viewform")
    fields = {"123456": "Test"}
    payload = filler._prepare_payload(fields, email="abc@gmail.com")
    
    keys = [k for k, v in payload]
    assert "emailAddress" in keys
    assert "entry.123456" in keys
    assert "fvv" in keys
    assert "pageHistory" in keys
