"""FastAPI application for the Auto Google Form Filler Web Dashboard."""
import os
import re
from typing import Dict, Any, List, Optional
from pathlib import Path
import yaml
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.inspector import inspect_google_form
from src.scheduler import local_to_utc_cron, save_workflow_file
from src.filler.http_filler import HttpFormFiller
from src.filler.browser_filler import BrowserFormFiller
from src.utils.notifier import EmailNotifier
from src.utils.date_resolver import get_current_time

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Auto Google Form Filler", version="1.0.0")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

CONFIG_PATH = Path("config/form_config.yaml")
EXAMPLE_CONFIG_PATH = Path("config/form_config.example.yaml")
WORKFLOW_PATH = Path(".github/workflows/scheduled_submission.yml")


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
    fields: Dict[str, Any]
    notifications: Optional[Dict[str, Any]] = None


class TestSubmitRequest(BaseModel):
    dry_run: bool = True
    mode: Optional[str] = None
    email: Optional[str] = None
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
        return {"form_url": "", "mode": "http", "email": "", "fields": {}, "notifications": {"enabled": True}}
    
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
        "fields": req.fields,
        "notifications": req.notifications or {"enabled": True, "on_success": True, "on_failure": True}
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(payload, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return {"success": True, "message": "Configuration saved successfully to config/form_config.yaml"}


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


@app.post("/api/test-submit")
async def api_test_submit(req: TestSubmitRequest):
    # Load config fallback
    config = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    form_url = req.form_url or config.get("form_url")
    if not form_url or "YOUR_FORM_ID_HERE" in form_url:
        raise HTTPException(status_code=400, detail="Valid form URL must be provided or configured.")

    mode = (req.mode or config.get("mode", "http")).lower()
    email = req.email if req.email is not None else config.get("email")
    fields = req.fields if req.fields is not None else config.get("fields", {})

    if mode == "browser":
        filler = BrowserFormFiller(form_url=form_url)
    else:
        filler = HttpFormFiller(form_url=form_url)

    res = filler.submit(fields=fields, email=email, dry_run=req.dry_run, tz_name=req.timezone)

    return {
        "success": res.success,
        "status_code": res.status_code,
        "message": res.message,
        "submitted_payload": res.submitted_payload,
        "error": res.error,
        "dry_run": res.dry_run
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
        body_text=f"Test alert dispatched successfully from Web Dashboard at {now}.",
        body_html=f"<div style='font-family:sans-serif;padding:16px;'><h3>🧪 Test Notification</h3><p>Your SMTP email configuration is working properly!</p><p>Timestamp: {now}</p></div>"
    )

    if ok:
        return {"success": True, "message": f"Test email sent successfully to {notifier.recipient_email}!"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send test email. Check your SMTP host, port, or App Password.")
