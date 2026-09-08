"""Tests for FastAPI Web Dashboard endpoints."""
from fastapi.testclient import TestClient
from src.web.app import app

client = TestClient(app)


def test_index_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "Auto Google Form Filler" in response.text
    assert "Form Inspector" in response.text


def test_api_schedule_endpoint():
    payload = {
        "days": ["Mon", "Wed", "Fri"],
        "time": "09:30",
        "timezone": "Asia/Kolkata"
    }
    response = client.post("/api/schedule", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["cron"] == "0 4 * * 1,3,5"


def test_api_test_submit_dry_run():
    payload = {
        "dry_run": True,
        "form_url": "https://docs.google.com/forms/d/e/1FAIpQLSeXXXX/viewform",
        "email": "test@example.com",
        "fields": {
            "entry.123": "Sample",
            "entry.456": "{{TODAY}}"
        }
    }
    response = client.post("/api/test-submit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["dry_run"] is True
    assert data["submitted_payload"]["emailAddress"] == "test@example.com"
    assert data["submitted_payload"]["entry.123"] == "Sample"
    assert "{{" not in data["submitted_payload"]["entry.456"]


def test_api_download_endpoints():
    res_cfg = client.get("/api/config/download")
    assert res_cfg.status_code == 200
    assert "form_url" in res_cfg.text

    res_wf = client.get("/api/workflow/download")
    assert res_wf.status_code == 200
    assert "Autonomous Google Form Submission" in res_wf.text


def test_api_jobs_crud_flow():
    # 1. Create a job
    job_payload = {
        "name": "Friend Attendance Job",
        "form_url": "https://docs.google.com/forms/d/e/1FAIpQLSeTEST3/viewform",
        "fields": {"entry.111": "Present"},
        "days": ["Mon", "Fri"],
        "time": "08:45",
        "timezone": "Asia/Kolkata",
        "alert_email": "myfriend@gmail.com",
        "form_email": "friend_in_form@gmail.com",
        "mode": "http"
    }
    create_res = client.post("/api/jobs", json=job_payload)
    assert create_res.status_code == 200
    create_data = create_res.json()
    assert create_data["success"] is True
    job_id = create_data["job_id"]
    assert job_id is not None

    # 2. List jobs
    list_res = client.get("/api/jobs")
    assert list_res.status_code == 200
    jobs = list_res.json()
    assert any(j["id"] == job_id for j in jobs)

    # 3. Toggle job
    toggle_res = client.post(f"/api/jobs/{job_id}/toggle", json={"is_active": False})
    assert toggle_res.status_code == 200
    assert toggle_res.json()["is_active"] is False

    # 4. Delete job
    del_res = client.delete(f"/api/jobs/{job_id}")
    assert del_res.status_code == 200


def test_api_logs_endpoint():
    res = client.get("/api/logs")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


