-- Run once on an existing Supabase project (SQL editor or scripts/apply_migration.py).
alter table public.jobs
  add column if not exists is_active boolean not null default true;

create index if not exists jobs_is_active_date_idx
  on public.jobs (is_active, date_posted desc);
