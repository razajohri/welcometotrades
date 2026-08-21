# Welcome to Trades

Mining and skilled-trades job board for **on-site roles in the USA and Canada**.

- Domain: [welcometotrades.com](https://welcometotrades.com)
- TikTok: [@rigtimmins](https://www.tiktok.com/@rigtimmins)
- Stack: Flask + JobSpy + Supabase (same architecture as Remote Jobs Canada)

## Setup

```bash
git submodule update --init --recursive
pip install -r requirements.txt
cp .env.example .env
python scripts/apply_schema.py
python app.py
```

## Refresh jobs

```bash
python scripts/update_jobs_cache.py
```

On Railway, deploy a second service from `railway.job-scrape.toml` (weekly cron) with the same Supabase env vars as the web app. That runs the expanded Indeed + Google mining/trades sweep and upserts into `public.jobs`.

## Deploy

Use a **new** Railway project, **new** Supabase, and point Namecheap DNS for `welcometotrades.com` here.
Do **not** reuse Remote Jobs Canada infrastructure.
