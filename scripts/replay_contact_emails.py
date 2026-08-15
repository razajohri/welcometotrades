"""Resend contact form emails that were stored without delivery."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from contact_handler import send_email  # noqa: E402
from data_store import get_service_client, is_supabase_database_configured  # noqa: E402


def main() -> int:
    if not is_supabase_database_configured():
        print("Supabase is not configured.")
        return 1

    rows = (
        get_service_client()
        .table("contact_messages")
        .select("id,email,subject,message,delivery_status")
        .eq("delivery_status", "stored_only")
        .order("created_at")
        .execute()
        .data
        or []
    )
    if not rows:
        print("No stored-only contact messages to replay.")
        return 0

    contact_to = os.getenv("CONTACT_EMAIL", "roman@welcometotrades.com")
    sent = 0
    for row in rows:
        ok = send_email(
            recipient_emails=contact_to,
            subject=row["subject"],
            message=row["message"],
            sender_email=row["email"],
        )
        if ok:
            get_service_client().table("contact_messages").update(
                {"delivery_status": "emailed"}
            ).eq("id", row["id"]).execute()
            sent += 1
            print(f"Sent: {row['email']} — {row['subject']}")
        else:
            print(f"Failed: {row['email']} — {row['subject']}")

    print(f"Replay complete. Sent {sent}/{len(rows)} messages.")
    return 0 if sent == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
