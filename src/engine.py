"""Autonomous Background Scheduler Engine using APScheduler."""
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from src.db import get_all_jobs, get_job, update_job_last_run, log_execution, toggle_job
from src.filler.http_filler import HttpFormFiller
from src.filler.browser_filler import BrowserFormFiller
from src.utils.notifier import EmailNotifier
from src.utils.date_resolver import get_current_time

logger = logging.getLogger("AutonomousEngine")

# Global background scheduler instance
scheduler = BackgroundScheduler(daemon=True)

# Map human day names to APScheduler day_of_week format (mon, tue, wed, etc.)
DAY_ABBR = {
    "monday": "mon", "mon": "mon", "1": "mon",
    "tuesday": "tue", "tue": "tue", "2": "tue",
    "wednesday": "wed", "wed": "wed", "3": "wed",
    "thursday": "thu", "thu": "thu", "4": "thu",
    "friday": "fri", "fri": "fri", "5": "fri",
    "saturday": "sat", "sat": "sat", "6": "sat",
    "sunday": "sun", "sun": "sun", "0": "sun", "7": "sun",
}


def run_scheduled_job(job_id: str):
    """Callback function executed by APScheduler when a job trigger fires."""
    logger.info(f"⏰ Triggering scheduled autonomous job [{job_id}]")
    job = get_job(job_id)
    if not job:
        logger.warning(f"Job [{job_id}] not found in database. Skipping.")
        return

    if not job.get("is_active"):
        logger.info(f"Job [{job_id}] is paused. Skipping.")
        return

    tz_name = job.get("timezone", "Asia/Kolkata")
    now_dt = get_current_time(tz_name)
    timestamp_str = now_dt.strftime("%Y-%m-%d %H:%M:%S %Z")

    form_url = job.get("form_url")
    form_email = job.get("form_email", "")
    alert_email = job.get("alert_email", "")
    fields = job.get("fields", {})
    mode = job.get("mode", "http").lower()

    if mode == "browser":
        filler = BrowserFormFiller(form_url=form_url)
    else:
        filler = HttpFormFiller(form_url=form_url)

    result = filler.submit(fields=fields, email=form_email, dry_run=False, tz_name=tz_name)

    status_str = "SUCCESS" if result.success else "FAILED"
    is_one_time = (job.get("schedule_type") == "once")
    exec_msg = result.message if result.success else (result.error or result.message or "Submission failed")

    # Dispatch email notification to the user-entered alert email
    email_note = ""
    if alert_email:
        try:
            notifier = EmailNotifier(recipient_email=alert_email)
            if result.success:
                sent = notifier.notify_success(
                    form_url=form_url,
                    submitted_fields=result.submitted_payload,
                    timestamp=timestamp_str
                )
            else:
                sent = notifier.notify_failure(
                    form_url=form_url,
                    error_message=result.error or result.message,
                    timestamp=timestamp_str
                )
            if sent:
                email_note = f"Email sent to {alert_email}"
                logger.info(f"Notification email dispatched successfully to {alert_email} for job [{job_id}]")
            else:
                email_note = f"Email failed: {notifier.last_error or 'SMTP dispatch error'}"
                logger.warning(f"Notification email failed to send to {alert_email} for job [{job_id}]: {notifier.last_error}")
        except Exception as ex:
            email_note = f"Email error: {ex}"
            logger.exception(f"Unexpected exception while sending alert email for job [{job_id}]: {ex}")
    else:
        logger.info(f"No alert_email set for job [{job_id}]. Skipping email dispatch.")

    final_msg = f"{exec_msg} | {email_note}" if email_note else exec_msg

    if is_one_time:
        comp_status = "COMPLETED" if result.success else "FAILED"
        update_job_last_run(job_id, comp_status, message=final_msg)
        toggle_job(job_id, False)
        unschedule_job_in_memory(job_id)
    else:
        update_job_last_run(job_id, status_str, message=final_msg)

    log_execution(
        job_id=job_id,
        status="COMPLETED" if (is_one_time and result.success) else status_str,
        message=final_msg,
        alert_recipient=alert_email,
        payload=result.submitted_payload
    )


def schedule_job_in_memory(job: Dict[str, Any]):
    """Add or update a single job in the APScheduler instance."""
    job_id = job["id"]
    unschedule_job_in_memory(job_id)

    if not job.get("is_active"):
        return

    tz_name = job.get("timezone", "Asia/Kolkata")
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.timezone("Asia/Kolkata")

    schedule_type = job.get("schedule_type", "recurring")

    # Specific One-time Date Execution
    if schedule_type == "once":
        target_date = job.get("target_date")
        time_str = job.get("time", "09:30").strip()
        if not target_date:
            return
        try:
            dt_str = f"{target_date} {time_str}"
            naive_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            localized_dt = tz.localize(naive_dt)
            now_dt = datetime.now(tz)

            # If the scheduled time has arrived or passed and the job hasn't executed yet:
            if localized_dt <= now_dt:
                if not job.get("last_run_status"):
                    logger.info(f"⚡ Scheduled time {localized_dt} reached for active job [{job_id}]. Triggering execution now!")
                    scheduler.add_job(
                        run_scheduled_job,
                        trigger=DateTrigger(run_date=now_dt, timezone=tz),
                        args=[job_id],
                        id=job_id,
                        name=job.get("name", job_id),
                        replace_existing=True,
                        misfire_grace_time=None
                    )
                return

            # Future scheduled execution
            trigger = DateTrigger(run_date=localized_dt, timezone=tz)
            scheduler.add_job(
                run_scheduled_job,
                trigger=trigger,
                args=[job_id],
                id=job_id,
                name=job.get("name", job_id),
                replace_existing=True,
                misfire_grace_time=None
            )
            logger.info(f"✅ Registered one-time job [{job_id}] for {localized_dt}")
        except Exception as e:
            logger.error(f"Failed to schedule one-time job [{job_id}]: {e}")
        return

    # Recurring Schedule Execution
    days_list = job.get("days", [])
    if not days_list:
        return

    # Convert days to APScheduler format: "mon,wed,fri"
    norm_days = []
    for d in days_list:
        clean = str(d).strip().lower()
        if clean in DAY_ABBR:
            norm_days.append(DAY_ABBR[clean])

    if not norm_days:
        return

    days_str = ",".join(sorted(set(norm_days)))

    # Parse time "HH:MM"
    time_str = job.get("time", "09:30").strip()
    try:
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        hour = 9
        minute = 30

    trigger = CronTrigger(
        day_of_week=days_str,
        hour=hour,
        minute=minute,
        timezone=tz
    )

    scheduler.add_job(
        run_scheduled_job,
        trigger=trigger,
        args=[job_id],
        id=job_id,
        name=job.get("name", job_id),
        replace_existing=True,
        misfire_grace_time=None
    )
    logger.info(f"✅ Successfully registered job [{job_id}] ('{job.get('name')}') for {days_str} at {hour:02d}:{minute:02d} {tz_name}")


def unschedule_job_in_memory(job_id: str):
    """Remove a job from APScheduler if it exists."""
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"Removed job [{job_id}] from scheduler.")


def init_scheduler():
    """Start APScheduler and load all active jobs from the database."""
    if not scheduler.running:
        scheduler.start()
        logger.info("🚀 Background Autonomous Scheduler started successfully.")

    jobs = get_all_jobs()
    for job in jobs:
        schedule_job_in_memory(job)
    logger.info(f"Loaded and scheduled {len(jobs)} jobs from database.")
