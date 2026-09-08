"""Date and dynamic variable resolution utilities for form filling."""
import re
from datetime import datetime, timedelta
from typing import Any, Union
import pytz


DEFAULT_TIMEZONE = "Asia/Kolkata"


def get_current_time(tz_name: str = DEFAULT_TIMEZONE) -> datetime:
    """Return timezone-aware current datetime."""
    try:
        tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        tz = pytz.timezone(DEFAULT_TIMEZONE)
    return datetime.now(tz)


def resolve_string(template: str, now: datetime = None, tz_name: str = DEFAULT_TIMEZONE) -> str:
    """Resolve dynamic placeholders inside a single string.
    
    Supported placeholders:
    - {{TODAY}} -> YYYY-MM-DD
    - {{NOW}} -> HH:MM:SS
    - {{TIMESTAMP}} -> YYYY-MM-DD HH:MM:SS
    - {{YESTERDAY}} -> YYYY-MM-DD
    - {{TOMORROW}} -> YYYY-MM-DD
    - {{DAY_NAME}} -> Full weekday name (e.g. Monday)
    - {{SHORT_DAY}} -> Short weekday name (e.g. Mon)
    - {{MONTH_NAME}} -> Full month name (e.g. September)
    - {{YEAR}} -> 4-digit year (e.g. 2026)
    - {{TODAY_FORMAT:<format>}} or {{DATE_FORMAT:<format>}} -> Custom strftime
    """
    if not isinstance(template, str) or "{{" not in template:
        return template

    if now is None:
        now = get_current_time(tz_name)

    result = template
    yesterday = now - timedelta(days=1)
    tomorrow = now + timedelta(days=1)

    # Standard static substitutions
    subs = {
        "{{TODAY}}": now.strftime("%Y-%m-%d"),
        "{{NOW}}": now.strftime("%H:%M:%S"),
        "{{TIMESTAMP}}": now.strftime("%Y-%m-%d %H:%M:%S"),
        "{{YESTERDAY}}": yesterday.strftime("%Y-%m-%d"),
        "{{TOMORROW}}": tomorrow.strftime("%Y-%m-%d"),
        "{{DAY_NAME}}": now.strftime("%A"),
        "{{SHORT_DAY}}": now.strftime("%a"),
        "{{MONTH_NAME}}": now.strftime("%B"),
        "{{YEAR}}": now.strftime("%Y"),
    }

    for placeholder, val in subs.items():
        result = result.replace(placeholder, val)

    # Custom format substitutions: {{TODAY_FORMAT:%d/%m/%Y}} or {{DATE_FORMAT:%d-%m-%Y}}
    custom_format_pattern = re.compile(r"\{\{(?:TODAY_FORMAT|DATE_FORMAT):([^}]+)\}\}")
    matches = custom_format_pattern.findall(result)
    for fmt in matches:
        try:
            formatted = now.strftime(fmt)
            result = result.replace(f"{{{{TODAY_FORMAT:{fmt}}}}}", formatted)
            result = result.replace(f"{{{{DATE_FORMAT:{fmt}}}}}", formatted)
        except Exception:
            pass

    return result


def resolve_variables(data: Any, tz_name: str = DEFAULT_TIMEZONE, now: datetime = None) -> Any:
    """Recursively resolve variables in strings, lists, or dictionaries."""
    if now is None:
        now = get_current_time(tz_name)

    if isinstance(data, str):
        return resolve_string(data, now=now, tz_name=tz_name)
    elif isinstance(data, list):
        return [resolve_variables(item, tz_name=tz_name, now=now) for item in data]
    elif isinstance(data, dict):
        return {k: resolve_variables(v, tz_name=tz_name, now=now) for k, v in data.items()}
    return data
