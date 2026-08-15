"""Railway cron entrypoint: send daily job alert emails via Resend."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))

from job_alerts import run_daily_job_alerts


def main() -> int:
    ok = run_daily_job_alerts()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
