"""Tests for date and dynamic variable resolution."""
from datetime import datetime
import pytz
from src.utils.date_resolver import resolve_string, resolve_variables


def test_resolve_standard_placeholders():
    fixed_dt = datetime(2026, 9, 8, 14, 30, 0)
    
    assert resolve_string("{{TODAY}}", now=fixed_dt) == "2026-09-08"
    assert resolve_string("{{NOW}}", now=fixed_dt) == "14:30:00"
    assert resolve_string("{{TIMESTAMP}}", now=fixed_dt) == "2026-09-08 14:30:00"
    assert resolve_string("{{YESTERDAY}}", now=fixed_dt) == "2026-09-07"
    assert resolve_string("{{TOMORROW}}", now=fixed_dt) == "2026-09-09"
    assert resolve_string("{{DAY_NAME}}", now=fixed_dt) == "Tuesday"
    assert resolve_string("{{YEAR}}", now=fixed_dt) == "2026"


def test_resolve_custom_format():
    fixed_dt = datetime(2026, 9, 8, 14, 30, 0)
    assert resolve_string("{{TODAY_FORMAT:%d/%m/%Y}}", now=fixed_dt) == "08/09/2026"
    assert resolve_string("Prefix {{TODAY_FORMAT:%Y-%m-%d}} Suffix", now=fixed_dt) == "Prefix 2026-09-08 Suffix"


def test_resolve_nested_data():
    fixed_dt = datetime(2026, 9, 8, 14, 30, 0)
    data = {
        "name": "Static Name",
        "date": "{{TODAY}}",
        "list_items": ["Item 1", "{{NOW}}", "Static Item"],
        "nested": {
            "time": "{{TIMESTAMP}}"
        }
    }

    resolved = resolve_variables(data, now=fixed_dt)
    assert resolved["name"] == "Static Name"
    assert resolved["date"] == "2026-09-08"
    assert resolved["list_items"] == ["Item 1", "14:30:00", "Static Item"]
    assert resolved["nested"]["time"] == "2026-09-08 14:30:00"
