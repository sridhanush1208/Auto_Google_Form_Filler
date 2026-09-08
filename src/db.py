"""SQLite database layer for multi-user job management and execution logs."""
import os
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import pytz

DB_DIR = Path("data")
DB_PATH = DB_DIR / "form_filler.db"


def get_connection() -> sqlite3.Connection:
    """Return SQLite connection with dictionary-like row factory."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables if they do not exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                form_url TEXT NOT NULL,
                mode TEXT DEFAULT 'http',
                form_email TEXT DEFAULT '',
                alert_email TEXT DEFAULT '',
                fields TEXT NOT NULL,
                days TEXT NOT NULL,
                time TEXT NOT NULL,
                timezone TEXT DEFAULT 'Asia/Kolkata',
                cron TEXT NOT NULL,
                schedule_type TEXT DEFAULT 'recurring',
                target_date TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                last_run_at TEXT DEFAULT NULL,
                last_run_status TEXT DEFAULT NULL,
                created_at TEXT NOT NULL
            )
        """)
        try:
            cursor.execute("ALTER TABLE jobs ADD COLUMN schedule_type TEXT DEFAULT 'recurring'")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE jobs ADD COLUMN target_date TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE jobs ADD COLUMN form_title TEXT DEFAULT ''")
        except Exception:
            pass
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id TEXT PRIMARY KEY,
                job_id TEXT,
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                alert_recipient TEXT DEFAULT '',
                submitted_payload TEXT DEFAULT '',
                FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE
            )
        """)
        conn.commit()


def create_job(
    name: str,
    form_url: str,
    fields: Dict[str, Any],
    days: List[str],
    time: str,
    timezone: str = "Asia/Kolkata",
    cron: str = "",
    alert_email: str = "",
    form_email: str = "",
    mode: str = "http",
    schedule_type: str = "recurring",
    target_date: str = "",
    form_title: str = "",
    job_id: Optional[str] = None
) -> str:
    """Create or update a scheduled autonomous job."""
    init_db()
    jid = job_id or str(uuid.uuid4())[:8]
    now_str = datetime.now(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO jobs (
                id, name, form_url, form_title, mode, form_email, alert_email, fields, days, time, timezone, cron, schedule_type, target_date, is_active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (
            jid,
            name.strip() or "Untitled Submitter",
            form_url.strip(),
            form_title.strip() or "Google Form",
            mode.strip().lower(),
            form_email.strip(),
            alert_email.strip(),
            json.dumps(fields),
            json.dumps(days or []),
            time.strip(),
            timezone.strip(),
            cron.strip(),
            schedule_type.strip().lower(),
            target_date.strip(),
            now_str
        ))
        conn.commit()
    return jid


def check_and_expire_past_jobs() -> None:
    """Detect any one-time jobs whose scheduled date has passed without executing and mark them EXPIRED."""
    now_utc = datetime.now(pytz.UTC)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, schedule_type, target_date, time, timezone, is_active, last_run_status
            FROM jobs
            WHERE schedule_type = 'once' AND (last_run_status IS NULL OR (last_run_status != 'COMPLETED' AND last_run_status != 'EXPIRED'))
        """)
        rows = cursor.fetchall()
        for r in rows:
            target_date = r["target_date"]
            time_str = r["time"] or "09:30"
            tz_name = r["timezone"] or "Asia/Kolkata"
            if target_date:
                try:
                    tz = pytz.timezone(tz_name)
                    naive_dt = datetime.strptime(f"{target_date} {time_str}", "%Y-%m-%d %H:%M")
                    scheduled_dt = tz.localize(naive_dt)
                    if scheduled_dt < now_utc:
                        cursor.execute("""
                            UPDATE jobs
                            SET last_run_status = 'EXPIRED', is_active = 0, last_run_at = ?
                            WHERE id = ?
                        """, (now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"), r["id"]))
                except Exception:
                    pass
        conn.commit()


def get_all_jobs() -> List[Dict[str, Any]]:
    """Retrieve all scheduled jobs, automatically marking expired one-time runs."""
    init_db()
    check_and_expire_past_jobs()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC")
        rows = cursor.fetchall()
        jobs = []
        for r in rows:
            job = dict(r)
            job["fields"] = json.loads(job["fields"])
            job["days"] = json.loads(job["days"])
            job["is_active"] = bool(job["is_active"])
            jobs.append(job)
        return jobs


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single job by ID."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        if not row:
            return None
        job = dict(row)
        job["fields"] = json.loads(job["fields"])
        job["days"] = json.loads(job["days"])
        job["is_active"] = bool(job["is_active"])
        return job


def delete_job(job_id: str) -> bool:
    """Delete a scheduled job and associated logs."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        deleted = cursor.rowcount > 0
        cursor.execute("DELETE FROM logs WHERE job_id = ?", (job_id,))
        conn.commit()
        return deleted


def toggle_job(job_id: str, is_active: bool) -> bool:
    """Toggle a job active or paused."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET is_active = ? WHERE id = ?", (1 if is_active else 0, job_id))
        conn.commit()
        return cursor.rowcount > 0


def update_job_last_run(job_id: str, status: str):
    """Update last run time and status for a job."""
    init_db()
    now_str = datetime.now(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET last_run_at = ?, last_run_status = ? WHERE id = ?", (now_str, status, job_id))
        conn.commit()


def log_execution(job_id: Optional[str], status: str, message: str, alert_recipient: str = "", payload: Dict[str, Any] = None):
    """Save an execution record in logs."""
    init_db()
    log_id = str(uuid.uuid4())[:8]
    now_str = datetime.now(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    payload_str = json.dumps(payload or {})

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO logs (id, job_id, timestamp, status, message, alert_recipient, submitted_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (log_id, job_id, now_str, status, message, alert_recipient, payload_str))
        conn.commit()


def get_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve recent execution logs."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        logs = []
        for r in rows:
            l = dict(r)
            try:
                l["submitted_payload"] = json.loads(l["submitted_payload"])
            except Exception:
                pass
            logs.append(l)
        return logs


def get_setting(key: str, default: str = "") -> str:
    """Retrieve a persistent setting value."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    """Save a persistent setting value."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value).strip()))
        conn.commit()


def get_all_settings() -> Dict[str, str]:
    """Retrieve all persistent settings."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        rows = cursor.fetchall()
        return {r["key"]: r["value"] for r in rows}

