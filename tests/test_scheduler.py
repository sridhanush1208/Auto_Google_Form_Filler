"""Tests for scheduler and cron conversion."""
from src.scheduler import local_to_utc_cron, generate_workflow_yaml


def test_local_to_utc_cron_ist():
    # 09:30 AM IST on Mon, Wed, Fri -> 04:00 UTC on Mon, Wed, Fri
    cron, info = local_to_utc_cron(["Mon", "Wed", "Fri"], "09:30", tz_name="Asia/Kolkata")
    assert cron == "0 4 * * 1,3,5"
    assert info["utc_time"] == "04:00 UTC"


def test_local_to_utc_cron_day_shift():
    # 02:00 AM IST on Monday -> 20:30 UTC on Sunday (previous day)
    cron, info = local_to_utc_cron(["Mon"], "02:00", tz_name="Asia/Kolkata")
    # Sunday is 0 in POSIX cron
    assert cron == "30 20 * * 0"


def test_generate_workflow_yaml():
    yaml_str = generate_workflow_yaml("0 4 * * 1,3,5")
    assert "cron: '0 4 * * 1,3,5'" in yaml_str
    assert "workflow_dispatch:" in yaml_str
    assert "python src/main.py" in yaml_str
