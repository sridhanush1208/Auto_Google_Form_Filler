"""Tests for SQLite database operations and background scheduler engine."""
import os
import pytest
from src.db import (
    init_db, create_job, get_all_jobs, get_job,
    delete_job, toggle_job, log_execution, get_logs
)
from src.engine import schedule_job_in_memory, unschedule_job_in_memory, scheduler


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    yield


def test_create_and_get_job():
    job_id = create_job(
        name="Team Standup Form",
        form_url="https://docs.google.com/forms/d/e/1FAIpQLSeTEST/viewform",
        fields={"entry.123": "Attending", "entry.456": "{{TODAY}}"},
        days=["Mon", "Wed", "Fri"],
        time="10:00",
        timezone="Asia/Kolkata",
        cron="0 4 * * 1,3,5",
        alert_email="friend@example.com",
        form_email="submitter@example.com",
        mode="http"
    )

    assert job_id is not None
    job = get_job(job_id)
    assert job is not None
    assert job["name"] == "Team Standup Form"
    assert job["alert_email"] == "friend@example.com"
    assert job["form_email"] == "submitter@example.com"
    assert "Mon" in job["days"]
    assert job["is_active"] is True

    # Test toggling
    toggle_job(job_id, False)
    job_updated = get_job(job_id)
    assert job_updated["is_active"] is False

    # Clean up
    assert delete_job(job_id) is True
    assert get_job(job_id) is None


def test_scheduler_in_memory_registration():
    job_id = create_job(
        name="Scheduled Test Job",
        form_url="https://docs.google.com/forms/d/e/1FAIpQLSeTEST2/viewform",
        fields={"entry.999": "Value"},
        days=["Tue", "Thu"],
        time="14:30",
        timezone="Asia/Kolkata",
        cron="0 9 * * 2,4",
        alert_email="friend2@example.com"
    )
    job = get_job(job_id)

    schedule_job_in_memory(job)
    aps_job = scheduler.get_job(job_id)
    assert aps_job is not None
    assert aps_job.name == "Scheduled Test Job"

    # Unschedule
    unschedule_job_in_memory(job_id)
    assert scheduler.get_job(job_id) is None
    delete_job(job_id)


def test_log_execution_and_retrieval():
    log_execution(
        job_id="test-job-id",
        status="SUCCESS",
        message="Form submitted successfully",
        alert_recipient="alert@example.com",
        payload={"entry.1": "Test"}
    )

    logs = get_logs(limit=5)
    assert len(logs) > 0
    assert logs[0]["status"] == "SUCCESS"
    assert logs[0]["alert_recipient"] == "alert@example.com"


def test_past_one_time_job_expires():
    from src.db import check_and_expire_past_jobs

    # Create a job with target_date in the past
    past_job_id = create_job(
        name="Expired Event Form",
        form_url="https://docs.google.com/forms/d/e/1FAIpQLSeTESTPAST/viewform",
        fields={"entry.1": "Yes"},
        days=[],
        time="00:01",
        timezone="Asia/Kolkata",
        schedule_type="once",
        target_date="2020-01-01",
        form_title="Old Event Form"
    )

    # Trigger expiration check
    check_and_expire_past_jobs()

    job = get_job(past_job_id)
    assert job is not None
    assert job["last_run_status"] == "EXPIRED"
    assert job["is_active"] is False

    delete_job(past_job_id)

