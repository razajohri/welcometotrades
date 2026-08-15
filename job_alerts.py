"""Daily job alert emails via Resend."""

from __future__ import annotations

import html
import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import resend

from data_store import (
    fetch_recent_jobs_for_alerts,
    finish_job_alert_run,
    list_active_subscribers_for_alerts,
    start_job_alert_run,
    touch_job_alert_sent,
)

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
RESEND_FROM_EMAIL = os.getenv(
    "RESEND_FROM_EMAIL",
    "Welcome to Trades <jobs@welcometotrades.com>",
).strip()
SITE_URL = os.getenv("CANONICAL_HOST", "https://www.welcometotrades.com").strip()
if SITE_URL and not SITE_URL.startswith("http"):
    SITE_URL = f"https://{SITE_URL}"

JOB_ALERTS_LOOKBACK_HOURS = int(os.getenv("JOB_ALERTS_LOOKBACK_HOURS", "24"))
JOB_ALERTS_MAX_JOBS = int(os.getenv("JOB_ALERTS_MAX_JOBS", "15"))
JOB_ALERTS_DRY_RUN = os.getenv("JOB_ALERTS_DRY_RUN", "false").lower() in {"1", "true", "yes"}


def _job_apply_url(job: dict[str, Any]) -> str:
    direct = (job.get("job_url_direct") or "").strip()
    fallback = (job.get("job_url") or "").strip()
    return direct or fallback or urljoin(SITE_URL, "/search")


def _format_posted(date_value: Any) -> str:
    if not date_value:
        return ""
    try:
        text = str(date_value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%b %d")
    except Exception:
        return ""


def build_alert_email_html(*, jobs: list[dict[str, Any]], recipient_email: str) -> str:
    account_url = urljoin(SITE_URL, "/account")
    search_url = urljoin(SITE_URL, "/search")
    job_rows = []
    for job in jobs:
        title = html.escape(str(job.get("title") or "Remote role"))
        company = html.escape(str(job.get("company") or "Company"))
        posted = html.escape(_format_posted(job.get("date_posted")))
        apply_url = html.escape(_job_apply_url(job))
        meta_parts = [part for part in (company, posted) if part]
        meta = " · ".join(meta_parts)
        job_rows.append(
            f"""
            <tr>
              <td style="padding:14px 0;border-bottom:1px solid #ececec;">
                <a href="{apply_url}" style="color:#1a1a1a;font-size:16px;font-weight:700;text-decoration:none;">{title}</a>
                <div style="color:#666;font-size:14px;margin-top:4px;">{meta}</div>
              </td>
            </tr>
            """
        )

    jobs_html = "".join(job_rows)
    count = len(jobs)
    heading = f"{count} new remote job{'s' if count != 1 else ''} for Canadians"

    return f"""
    <div style="font-family:Inter,Arial,sans-serif;background:#f7f7f8;padding:24px;">
      <div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:16px;padding:28px;border:1px solid #ececec;">
        <div style="font-size:22px;font-weight:800;color:#1a1a1a;margin-bottom:8px;">{heading}</div>
        <div style="font-size:15px;color:#555;line-height:1.6;margin-bottom:20px;">
          Fresh roles posted directly on company sites — picked for Canadian remote job seekers.
        </div>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
          {jobs_html}
        </table>
        <div style="margin-top:24px;text-align:center;">
          <a href="{html.escape(search_url)}" style="display:inline-block;background:#e53935;color:#ffffff;text-decoration:none;font-weight:700;padding:14px 22px;border-radius:999px;">Search all jobs</a>
        </div>
        <p style="font-size:12px;color:#888;line-height:1.6;margin-top:24px;text-align:center;">
          Sent to {html.escape(recipient_email)} ·
          <a href="{html.escape(account_url)}" style="color:#888;">Manage alerts</a>
        </p>
      </div>
    </div>
    """


def send_alert_email(*, recipient_email: str, jobs: list[dict[str, Any]]) -> None:
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is not configured.")

    resend.api_key = RESEND_API_KEY
    subject = f"{len(jobs)} new remote jobs on Welcome to Trades"
    html_body = build_alert_email_html(jobs=jobs, recipient_email=recipient_email)

    if JOB_ALERTS_DRY_RUN:
        logger.info("DRY RUN: would send alert to %s (%s jobs)", recipient_email, len(jobs))
        return

    resend.Emails.send(
        {
            "from": RESEND_FROM_EMAIL,
            "to": [recipient_email],
            "subject": subject,
            "html": html_body,
        }
    )


def run_daily_job_alerts() -> bool:
    """Send daily digest to active subscribers. Returns True on success."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

    if not RESEND_API_KEY and not JOB_ALERTS_DRY_RUN:
        logger.error("RESEND_API_KEY is missing. Set it on Railway for the cron service.")
        return False

    run_id = start_job_alert_run()
    if run_id is None:
        logger.error("Job alert tables are missing. Apply db/migrations/add_job_alerts.sql in Supabase.")
        return False
    emails_sent = 0
    emails_skipped = 0

    try:
        jobs = fetch_recent_jobs_for_alerts(
            lookback_hours=JOB_ALERTS_LOOKBACK_HOURS,
            limit=JOB_ALERTS_MAX_JOBS,
        )
        if not jobs:
            logger.info("No new jobs in the last %s hours — skipping sends.", JOB_ALERTS_LOOKBACK_HOURS)
            finish_job_alert_run(
                run_id,
                jobs_count=0,
                emails_sent=0,
                emails_skipped=0,
                status="completed",
            )
            return True

        recipients = list_active_subscribers_for_alerts()
        logger.info("Found %s new jobs and %s alert recipients.", len(jobs), len(recipients))

        for recipient in recipients:
            email = recipient["email"]
            user_id = recipient["user_id"]
            try:
                send_alert_email(recipient_email=email, jobs=jobs)
                touch_job_alert_sent(user_id)
                emails_sent += 1
            except Exception as exc:
                emails_skipped += 1
                logger.exception("Failed to send alert to %s: %s", email, exc)

        finish_job_alert_run(
            run_id,
            jobs_count=len(jobs),
            emails_sent=emails_sent,
            emails_skipped=emails_skipped,
            status="completed",
        )
        logger.info("Job alerts finished. sent=%s skipped=%s", emails_sent, emails_skipped)
        return True
    except Exception as exc:
        logger.exception("Job alert run failed")
        finish_job_alert_run(
            run_id,
            jobs_count=0,
            emails_sent=emails_sent,
            emails_skipped=emails_skipped,
            status="failed",
            error_message=str(exc),
        )
        return False
