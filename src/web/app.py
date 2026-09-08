"""FastAPI application for the Auto Google Form Filler Web Dashboard."""
import os
import re
from typing import Dict, Any, List, Optional
from pathlib import Path
from contextlib import asynccontextmanager
import yaml
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.inspector import inspect_google_form
from src.scheduler import local_to_utc_cron, save_workflow_file
from src.filler.http_filler import HttpFormFiller
from src.filler.browser_filler import BrowserFormFiller
from src.utils.notifier import EmailNotifier
from src.utils.date_resolver import get_current_time
from src.db import (
    init_db, create_job, get_all_jobs, get_job, delete_job,
    toggle_job, get_logs, log_execution, get_setting, set_setting
)
from src.engine import (
    init_scheduler, schedule_job_in_memory,
    unschedule_job_in_memory, run_scheduled_job, scheduler
)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

CONFIG_PATH = Path("config/form_config.yaml")
EXAMPLE_CONFIG_PATH = Path("config/form_config.example.yaml")
WORKFLOW_PATH = Path(".github/workflows/scheduled_submission.yml")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events: initialize database and background scheduler."""
    init_db()
    init_scheduler()
    yield
    if scheduler.running:
        scheduler.shutdown()


app = FastAPI(title="Auto Google Form Filler", version="2.0.0", lifespan=lifespan)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class InspectRequest(BaseModel):
    url: str


class ScheduleRequest(BaseModel):
    days: List[str]
    time: str
    timezone: str = "Asia/Kolkata"


class SaveConfigRequest(BaseModel):
    form_url: str
    mode: str = "http"
    email: Optional[str] = ""
    alert_email: Optional[str] = ""
    fields: Dict[str, Any]
    notifications: Optional[Dict[str, Any]] = None


ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


class AdminLoginRequest(BaseModel):
    password: str


class JobRequest(BaseModel):
    id: Optional[str] = None
    name: str = "My Scheduled Form"
    form_title: Optional[str] = ""
    form_url: str
    mode: str = "http"
    form_email: Optional[str] = ""
    alert_email: Optional[str] = ""
    fields: Dict[str, Any]
    schedule_type: str = "recurring"
    target_date: Optional[str] = ""
    days: Optional[List[str]] = []
    time: str = "09:30"
    timezone: str = "Asia/Kolkata"


class TestSubmitRequest(BaseModel):
    dry_run: bool = True
    mode: Optional[str] = None
    email: Optional[str] = None
    alert_email: Optional[str] = None
    fields: Optional[Dict[str, Any]] = None
    form_url: Optional[str] = None
    timezone: str = "Asia/Kolkata"


class TestEmailRequest(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    recipient_email: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/api/inspect")
async def api_inspect(req: InspectRequest):
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="Form URL is required.")
    
    result = inspect_google_form(req.url.strip())
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to inspect form."))
    return result


@app.get("/api/config")
async def api_get_config():
    target = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
    if not target.exists():
        return {"form_url": "", "mode": "http", "email": "", "alert_email": "", "fields": {}, "notifications": {"enabled": True}}
    
    with open(target, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


@app.post("/api/config")
async def api_save_config(req: SaveConfigRequest):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "form_url": req.form_url.strip(),
        "mode": req.mode.strip().lower(),
        "email": req.email.strip() if req.email else "",
        "alert_email": req.alert_email.strip() if req.alert_email else "",
        "fields": req.fields,
        "notifications": req.notifications or {"enabled": True, "on_success": True, "on_failure": True}
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(payload, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return {"success": True, "message": "Configuration saved successfully to config/form_config.yaml"}


@app.get("/api/config/download")
async def api_download_config():
    target = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
    if not target.exists():
        raise HTTPException(status_code=404, detail="No configuration found to download.")
    content = target.read_text(encoding="utf-8")
    return PlainTextResponse(
        content=content,
        media_type="text/yaml",
        headers={"Content-Disposition": "attachment; filename=form_config.yaml"}
    )


@app.get("/api/workflow/download")
async def api_download_workflow():
    if not WORKFLOW_PATH.exists():
        raise HTTPException(status_code=404, detail="Workflow file does not exist.")
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    return PlainTextResponse(
        content=content,
        media_type="text/yaml",
        headers={"Content-Disposition": "attachment; filename=scheduled_submission.yml"}
    )


@app.get("/api/schedule")
async def api_get_schedule():
    if not WORKFLOW_PATH.exists():
        return {"cron": "0 4 * * 1,3,5", "raw": ""}
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    match = re.search(r"cron:\s*['\"]([^'\"]+)['\"]", content)
    cron_str = match.group(1) if match else "0 4 * * 1,3,5"
    return {"cron": cron_str, "file_exists": True}


@app.post("/api/schedule")
async def api_save_schedule(req: ScheduleRequest):
    try:
        cron_expr, details = local_to_utc_cron(req.days, req.time, tz_name=req.timezone)
        saved_path = save_workflow_file(cron_expr)
        return {
            "success": True,
            "cron": cron_expr,
            "details": details,
            "saved_file": saved_path,
            "message": f"Schedule successfully saved to {saved_path}!"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/admin/login")
async def api_admin_login(req: AdminLoginRequest):
    """Authenticate administrator with secret code."""
    admin_pw = os.getenv("ADMIN_PASSWORD", ADMIN_PASSWORD).strip()
    if not admin_pw:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_PASSWORD is not configured on the server. Please add it to your Environment Variables."
        )
    if req.password.strip() == admin_pw:
        return {"success": True, "token": "admin-authenticated"}
    raise HTTPException(status_code=401, detail="Invalid secret code. Please check your password and try again.")


# Multi-User Autonomous Jobs API
@app.get("/api/jobs")
async def api_get_jobs():
    """Retrieve all autonomous scheduled jobs."""
    return get_all_jobs()


@app.post("/api/jobs")
async def api_save_job(req: JobRequest):
    """Create or update a scheduled autonomous job in the database and register in background scheduler."""
    if not req.form_url or not req.form_url.strip():
        raise HTTPException(status_code=400, detail="Form URL is required.")

    schedule_type = (req.schedule_type or "recurring").lower()

    if schedule_type == "once":
        if not req.target_date or not req.target_date.strip():
            raise HTTPException(status_code=400, detail="Please select a specific date for submission.")
        cron_expr = f"once@{req.target_date}_{req.time}"
        days = []
    else:
        if not req.days:
            raise HTTPException(status_code=400, detail="At least one day of the week must be selected for recurring schedule.")
        cron_expr, _ = local_to_utc_cron(req.days, req.time, tz_name=req.timezone)
        days = req.days

    job_id = create_job(
        name=req.name,
        form_url=req.form_url,
        fields=req.fields,
        days=days,
        time=req.time,
        timezone=req.timezone,
        cron=cron_expr,
        alert_email=req.alert_email or "",
        form_email=req.form_email or "",
        mode=req.mode,
        schedule_type=schedule_type,
        target_date=req.target_date or "",
        form_title=req.form_title or "",
        job_id=req.id
    )

    job_data = get_job(job_id)
    if job_data:
        schedule_job_in_memory(job_data)

    return {
        "success": True,
        "job_id": job_id,
        "message": f"Form '{req.name}' successfully scheduled and active!",
        "job": job_data
    }


@app.delete("/api/jobs/{job_id}")
async def api_delete_job(job_id: str):
    """Delete a scheduled job."""
    unschedule_job_in_memory(job_id)
    deleted = delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"success": True, "message": f"Job [{job_id}] deleted successfully."}


@app.post("/api/jobs/{job_id}/toggle")
async def api_toggle_job(job_id: str, payload: Dict[str, bool]):
    """Pause or resume a scheduled job."""
    is_active = payload.get("is_active", True)
    toggle_job(job_id, is_active)
    job_data = get_job(job_id)
    if job_data:
        if is_active:
            schedule_job_in_memory(job_data)
        else:
            unschedule_job_in_memory(job_id)
    return {"success": True, "is_active": is_active, "message": f"Job is now {'active' if is_active else 'paused'}."}


@app.post("/api/jobs/{job_id}/run-now")
async def api_run_job_now(job_id: str):
    """Trigger an immediate execution of a scheduled job."""
    job_data = get_job(job_id)
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found.")
    
    run_scheduled_job(job_id)
    return {"success": True, "message": f"Triggered immediate submission for '{job_data.get('name')}'."}


@app.get("/api/logs")
async def api_get_logs():
    """Retrieve recent autonomous execution history."""
    return get_logs(limit=50)


@app.post("/api/test-submit")
async def api_test_submit(req: TestSubmitRequest):
    config = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    form_url = req.form_url or config.get("form_url")
    if not form_url or "YOUR_FORM_ID_HERE" in form_url:
        raise HTTPException(status_code=400, detail="Valid form URL must be provided or configured.")

    mode = (req.mode or config.get("mode", "http")).lower()
    email = req.email if req.email is not None else config.get("email")
    alert_email = req.alert_email or config.get("alert_email")
    fields = req.fields if req.fields is not None else config.get("fields", {})

    if mode == "browser":
        filler = BrowserFormFiller(form_url=form_url)
    else:
        filler = HttpFormFiller(form_url=form_url)

    res = filler.submit(fields=fields, email=email, dry_run=req.dry_run, tz_name=req.timezone)

    # If live submission and user provided an alert email, dispatch alert!
    if not req.dry_run and alert_email:
        notifier = EmailNotifier(recipient_email=alert_email)
        now_str = get_current_time(req.timezone).strftime("%Y-%m-%d %H:%M:%S %Z")
        if res.success:
            notifier.notify_success(
                form_url=form_url,
                submitted_fields=res.submitted_payload,
                timestamp=now_str
            )
        else:
            notifier.notify_failure(
                form_url=form_url,
                error_message=res.error or res.message,
                timestamp=now_str
            )

    return {
        "success": res.success,
        "status_code": res.status_code,
        "message": res.message,
        "submitted_payload": res.submitted_payload,
        "error": res.error,
        "dry_run": res.dry_run,
        "alert_sent_to": alert_email if not req.dry_run and alert_email else None
    }


@app.post("/api/test-email")
async def api_test_email(req: TestEmailRequest):
    notifier = EmailNotifier(
        smtp_host=req.smtp_host,
        smtp_port=req.smtp_port,
        smtp_user=req.smtp_user,
        smtp_password=req.smtp_password,
        recipient_email=req.recipient_email
    )
    if not notifier.is_configured:
        raise HTTPException(status_code=400, detail="Incomplete SMTP settings provided.")

    now = get_current_time().strftime("%Y-%m-%d %H:%M:%S")
    ok = notifier.send_email(
        subject="🧪 Test Notification - Auto Google Form Filler",
        body_text=f"Test alert dispatched successfully from Web Dashboard to {notifier.recipient_email} at {now}.",
        body_html=f"<div style='font-family:sans-serif;padding:16px;'><h3>🧪 Test Notification</h3><p>Your SMTP email configuration is working properly!</p><p>Recipient: {notifier.recipient_email}</p><p>Timestamp: {now}</p></div>"
    )

    if ok:
        return {"success": True, "message": f"Test email sent successfully to {notifier.recipient_email}!"}
    else:
        err = notifier.last_error or "Check your SMTP host, port, or App Password."
        raise HTTPException(status_code=500, detail=f"Failed to send test email: {err}")


class SmtpConfigRequest(BaseModel):
    smtp_host: Optional[str] = "smtp.gmail.com"
    smtp_port: Optional[int] = 587
    smtp_user: str
    smtp_password: Optional[str] = ""
    recipient_email: Optional[str] = ""


@app.get("/api/admin/smtp")
async def api_get_admin_smtp():
    """Retrieve current SMTP status and sender email without exposing password."""
    user = os.getenv("SMTP_USER") or get_setting("smtp_user", "")
    host = os.getenv("SMTP_HOST") or get_setting("smtp_host", "smtp.gmail.com")
    port = os.getenv("SMTP_PORT") or get_setting("smtp_port", "587")
    has_pass = bool(os.getenv("SMTP_PASSWORD") or get_setting("smtp_password", ""))
    return {
        "configured": bool(user and has_pass),
        "smtp_user": user,
        "smtp_host": host,
        "smtp_port": int(port)
    }


@app.post("/api/admin/smtp")
async def api_save_admin_smtp(req: SmtpConfigRequest):
    """Save SMTP sender credentials into persistent settings."""
    if not req.smtp_user or not req.smtp_user.strip():
        raise HTTPException(status_code=400, detail="Sender email address is required.")
    
    set_setting("smtp_user", req.smtp_user.strip())
    set_setting("smtp_host", (req.smtp_host or "smtp.gmail.com").strip())
    set_setting("smtp_port", str(req.smtp_port or 587).strip())
    if req.smtp_password and req.smtp_password.strip():
        set_setting("smtp_password", req.smtp_password.strip())
    
    return {"success": True, "message": "Email settings saved successfully!"}


@app.post("/api/admin/smtp/test")
async def api_admin_test_email(req: SmtpConfigRequest):
    """Save and test email delivery live."""
    user = req.smtp_user.strip() if req.smtp_user else (os.getenv("SMTP_USER") or get_setting("smtp_user", ""))
    password = req.smtp_password.strip() if req.smtp_password else (os.getenv("SMTP_PASSWORD") or get_setting("smtp_password", ""))
    recipient = (req.recipient_email or user).strip()

    if not user or not password:
        raise HTTPException(status_code=400, detail="Both Gmail address and 16-character App Password are required.")
    
    # Persist settings
    set_setting("smtp_user", user)
    if req.smtp_password and req.smtp_password.strip():
        set_setting("smtp_password", req.smtp_password.strip())
    if req.smtp_host:
        set_setting("smtp_host", req.smtp_host.strip())
    if req.smtp_port:
        set_setting("smtp_port", str(req.smtp_port))

    notifier = EmailNotifier(
        smtp_host=req.smtp_host or "smtp.gmail.com",
        smtp_port=req.smtp_port or 587,
        smtp_user=user,
        smtp_password=password,
        recipient_email=recipient
    )

    now = get_current_time().strftime("%Y-%m-%d %H:%M:%S")
    ok = notifier.send_email(
        subject="✅ Auto Google Form Filler - SMTP Test Verification",
        body_text=f"Success! Your Google Form email notifications are configured and working properly. Dispatched to {recipient} at {now}.",
        body_html=f"""
        <div style="font-family:sans-serif;padding:20px;max-width:500px;border:1px solid #e2e8f0;border-radius:10px;">
          <h2 style="color:#16a34a;margin-top:0;">✅ Email Alerts Are Active!</h2>
          <p>Your SMTP credentials are valid and can send automated Google Form submission receipts.</p>
          <hr style="border:none;border-top:1px solid #e2e8f0;margin:16px 0;" />
          <p style="font-size:13px;color:#64748b;"><strong>Sender:</strong> {user}<br/><strong>Recipient:</strong> {recipient}<br/><strong>Timestamp:</strong> {now}</p>
        </div>
        """
    )

    if ok:
        return {
            "success": True,
            "message": f"Test email sent successfully to {recipient}! Please check your inbox (and Spam folder)."
        }
    else:
        err = notifier.last_error or "Unknown SMTP authentication error. Please verify your App Password."
        raise HTTPException(status_code=500, detail=f"Failed to send email: {err}")
