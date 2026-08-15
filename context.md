# Welcome to Trades — Full Handoff Context

**Last updated:** 2026-08-07  
**Domain:** https://welcometotrades.com (Namecheap)  
**GitHub:** https://github.com/razajohri/welcometotrades.git  
**TikTok promo:** https://www.tiktok.com/@rigtimmins  
**Reference production app (DO NOT break):** https://github.com/razajohri/remotejobscanda.ca  

This file is the complete context dump for the next Cursor agent / laptop push. Read this first.

---

## 1) What we decided (locked product decisions)

| # | Decision | Answer |
|---|----------|--------|
| 1 | Site / domain | Already owned: **welcometotrades.com** (Namecheap) |
| 2 | Geography | **USA + Canada**, with **city filters** |
| 3 | Work type | **On-site** mining / trades (NOT remote desk jobs) |
| 4 | Monetization | **Later** — first make the app; `/search` is free at launch |
| 5 | Repo name | **welcometotrades** |
| 6 | Clone of | Remote Jobs Canada UI + structure + backend patterns |
| 7 | Safety rule | **New repo + new infra only.** Never deploy this from the Canada production Railway/Supabase |

### Target job roles (exactly these kinds)

1. Haul Truck Operator  
2. Mine Equipment Operator  
3. Dozer Operator  
4. Grader Operator  
5. Excavator Operator  
6. Loader Operator  
7. Underground Operator  
8. Underground Miner  
9. Mine Operator  
10. Mill Operator  
11. Process Plant Operator  
12. Crusher Operator  
13. Conveyor Operator  
14. Driller  
15. Jumbo Operator  
16. Blast Operator  
17. Blaster  
18. General Mine Laborer  
19. Utility Worker  
20. Construction Miner  
21. Construction Helper  
22. Mechanic  
23. Heavy Duty Mechanic  
24. Millwright  
25. Electrician  
26. Underground Maintenance Electrician  
27. Welder  
28. Assayer  
29. Safety Technician  
30. Mine Geologist  

Promote via TikTok **@rigtimmins**.

---

## 2) Conversation history (what we talked about)

### A. OpenSEO evaluation (earlier)
- User asked about a repo named **OpenSEO** for SEO and whether to use it for Remote Jobs Canada.
- Correct project identified: **`every-app/open-seo`** → https://openseo.so (Semrush/Ahrefs-style tool).
- How it works: separate SEO research platform; DataForSEO data; keyword research, rank tracking, backlinks, site audits, AI visibility, MCP for agents.
- Verdict: useful **beside** the job site for keyword/competitor research — **not** something to wire into Flask. Canada already has on-page SEO in `seo.py`.
- Status: evaluation only; not integrated.

### B. Pakistan jobs app handoff (haunsla-pk)
- User wanted scrape/storage playbook to copy into another Cursor agent for a Pakistan remote jobs app.
- Created playbook documenting Canada pipeline: scrape → `jobs_cache.pkl` → Supabase upsert.
- File (on Canada repo PR branch): `docs/JOB_SCRAPE_AND_STORAGE_PLAYBOOK.md`
- Pakistan note: use looser “worldwide remote” rules; consider JobSpy `bayt` / `naukri`.

### C. Welcome to Trades (this product)
- User wants an **exact clone** of Remote Jobs Canada (UI/structure/pages/backend) for mining/trades.
- Strong requirement: **do not affect Canada production**.
- Decision: **new GitHub repo**, new Supabase, new Railway, new domain wiring.
- This Canada Cloud Agent **cannot push** to `welcometotrades` (token scoped / 403). Code was built in an isolated artifact package for the user to push, or for a new agent on that repo to continue.

---

## 3) Tech stack

Same stack as Remote Jobs Canada:

| Layer | Tech |
|-------|------|
| Web app | Python **Flask** |
| Templates | Jinja2 HTML (`templates/`) |
| CSS/JS | `static/app.css`, landing inline styles, small JS helpers |
| Job scraping | Vendored **JobSpy** (`JobSpy/`) — Indeed, Google, Ashby, Greenhouse, Lever |
| Local cache | `jobs_cache.pkl` (pandas DataFrame, atomic write) |
| Database | **Supabase / Postgres** — `public.jobs`, auth profiles, subscriptions, scrape_runs |
| Auth | Supabase Auth (magic link / OTP patterns from Canada) |
| Payments | Stripe (kept in code; **ungated for launch**) |
| Hosting target | Railway (new project) + Dockerfile / gunicorn patterns |
| DNS | Namecheap → `welcometotrades.com` / `www` |
| Email (optional later) | Resend / SMTP patterns from Canada `.env.example` |

---

## 4) How jobs are scraped (Welcome to Trades)

### Pipeline

```
scrape_all()                    [scraper.py]
  ├─ ATS: Ashby / Greenhouse / Lever  (trade search terms, USA + Canada, is_remote=False)
  ├─ Indeed: each of 30 roles × (Canada + USA)
  └─ Google Jobs: mining/trades queries
         ↓
  ats_location.is_trades_job_row()
    - title must match trade/mining role terms
    - reject pure remote/WFH desk jobs
    - require USA or Canada location
         ↓
  dedupe by job_url_direct / job_url
         ↓
  jobs_cache.pkl  (atomic .tmp → replace)
         ↓
  dataframe_to_job_records() → build_job_record()
         ↓
  upsert_jobs() → public.jobs  (unique source_key)
         ↓
  validate_job_links.py (soft-deactivate dead apply URLs)
         ↓
  Flask serves Supabase first; falls back to pickle
```

### Main command

```bash
python scripts/update_jobs_cache.py
```

Also:

```bash
python scripts/sync_jobs_to_supabase.py   # pickle → DB only
python scripts/validate_job_links.py
```

### Key files

| File | Role |
|------|------|
| `scraper.py` | Orchestrates Indeed/ATS/Google for the 30 roles |
| `ats_location.py` | On-site USA/Canada + trade-title filter + city helpers |
| `ats_companies.py` + `config/ats_companies.json` | ATS company slug lists (JobSpy boards) |
| `data_store.py` | Job records, upsert, search, city filter, categories |
| `scripts/update_jobs_cache.py` | Full refresh entrypoint |
| `db/schema.sql` | `public.jobs` schema |

### `source_key` (dedupe id)

```text
sha256(f"{site}|{job_url_direct or job_url}|{title}|{company}")
```

### Search filters (UI)

Categories:

- Operators  
- Underground  
- Mill & Plant  
- Trades  
- Labor  
- Safety & Geology  

City: dropdown built from cities extracted from current listings (`list_available_cities()`).

### Free launch gate

`/search` is **public** (no `@login_required`, no Stripe redirect). Stripe code remains for later.

---

## 5) Work DONE

### Product / code (in this package)

- [x] Isolated clone of Canada app architecture (not mixed into Canada deploy)
- [x] Rebrand strings → **Welcome to Trades** / **welcometotrades.com**
- [x] `seo.py` rewritten (titles, FAQ, sitemap, TikTok sameAs)
- [x] `scraper.py` rewritten for 30 trades roles, USA+Canada, on-site
- [x] `ats_location.py` rewritten (trade title + US/CA on-site + city extract/match)
- [x] `data_store.py` categories + city filter + eligibility rename
- [x] `app.py` free `/search`, city param, hosts → welcometotrades.com
- [x] Landing + search UI: new hero/copy, category chips, city field, TikTok `@rigtimmins`
- [x] Landing CTA points to `/search` (not paywall)
- [x] `README.md` + `LAUNCH.md`
- [x] `.env.example` updated for new domain
- [x] Packaged as `welcometotrades.zip` for laptop download

### Process / decisions documented

- [x] New-repo safety rule established
- [x] OpenSEO evaluated (optional later SEO research tool)
- [x] Pakistan scrape playbook created earlier on Canada side (separate product)

### Blocked / known limitation

- [ ] This Canada Cloud Agent **could not `git push`** to `razajohri/welcometotrades` (`cursor[bot]` 403)
- User must push from laptop **or** continue in a **new Cursor Cloud Agent opened on `welcometotrades`**

---

## 6) Work LEFT (launch checklist)

### A. Get code onto GitHub

1. Download `welcometotrades.zip` from this agent’s Artifacts, **or** rebuild in a new agent on the empty repo
2. On laptop:

```bash
mkdir welcometotrades && cd welcometotrades
unzip ~/Downloads/welcometotrades.zip
git init
git add .
git commit -m "Initial Welcome to Trades app"
git branch -M main
git remote add origin https://github.com/razajohri/welcometotrades.git
git push -u origin main
```

3. Confirm https://github.com/razajohri/welcometotrades is no longer empty

### B. Cursor / GitHub access hygiene

In https://cursor.com/dashboard/integrations → GitHub:

- Include **both** `remotejobscanda.ca` **and** `welcometotrades` (or All repositories)
- Open future Welcome to Trades work in an agent bound to **welcometotrades**

### C. New infrastructure (never share with Canada)

1. **New Supabase project**
   - Run `db/schema.sql` (+ migrations if needed)
   - Copy URL + anon + service role into `.env`
2. **New Railway project** from `welcometotrades` repo
   - Set env vars from `.env.example`
   - `CANONICAL_HOST=www.welcometotrades.com`
3. **Namecheap DNS** for `welcometotrades.com` / `www` → Railway
4. Optional later: Stripe products, Resend, GA4, Search Console

### D. First job scrape

```bash
python scripts/update_jobs_cache.py
```

First run can be slow (30 roles × 2 countries on Indeed).

### E. Smoke test before TikTok push

- [ ] `/` shows Welcome to Trades branding / mining copy
- [ ] `/search` works **without login**
- [ ] Category filters work
- [ ] City filter works
- [ ] Apply links open employer pages
- [ ] TikTok link → `@rigtimmins`
- [ ] Mobile layout OK (TikTok traffic)

### F. Polish later (not blocking launch)

- [ ] Replace Canada leftover assets (maple leaf imagery, old testimonial photos, guide page rewrite)
- [ ] Custom logo / OG image for Welcome to Trades
- [ ] Mining-specific ATS company lists (replace Canada SaaS-heavy boards)
- [ ] Legal pages lawyer-pass
- [ ] Monetization / Stripe re-enable when ready
- [ ] Job alerts for trades roles
- [ ] Optional OpenSEO for keyword research (separate tool)

---

## 7) Env vars to set (new project)

```env
FLASK_SECRET_KEY=...
TEST_MODE=true

SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...

# Stripe optional at launch
STRIPE_API_KEY=
STRIPE_WEBHOOK_SECRET=

CANONICAL_HOST=www.welcometotrades.com
CONTACT_EMAIL=hello@welcometotrades.com
```

---

## 8) Prompt to paste into a NEW Cursor agent on welcometotrades

```text
You are working in https://github.com/razajohri/welcometotrades

Read WELCOMETOTRADES_HANDOFF.md first (if present in zip/repo).

Goal: finish launching Welcome to Trades — a clone of remotejobscanda.ca architecture for on-site USA/Canada mining & trades jobs.

If repo is empty: scaffold from the handoff (Flask + JobSpy + Supabase), commit, push.
If code is already pushed: continue with Supabase schema, Railway deploy, DNS, first scrape, smoke test.

Rules:
- Do NOT modify remotejobscanda.ca production
- On-site jobs only (not remote desk)
- USA + Canada + city filters
- Free /search at launch
- TikTok https://www.tiktok.com/@rigtimmins
- 30 mining/trades roles listed in the handoff
```

---

## 9) Related repos / agents

| Repo | Purpose |
|------|---------|
| `razajohri/remotejobscanda.ca` | Live Canada remote jobs production — **do not break** |
| `razajohri/welcometotrades` | This new mining/trades product |
| `razajohri/haunsla-pk` | Separate Pakistan jobs app (remote/international) |
| `every-app/open-seo` | Optional SEO research platform (not required for launch) |

---

## 10) Bottom line

Welcome to Trades is a **same-stack clone** of Remote Jobs Canada, retargeted to **on-site mining/trades jobs in the USA & Canada**, with city filters and free search, promoted via **@rigtimmins**.

**Code is ready in the zip package.**  
**Left work is: push to GitHub → new Supabase → new Railway → DNS → scrape → smoke test → TikTok.**