-- Job alert preferences + send log (run once in Supabase SQL editor).

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

create table if not exists public.job_alert_preferences (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  enabled boolean not null default true,
  frequency text not null default 'daily' check (frequency in ('daily', 'weekly')),
  last_sent_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create trigger job_alert_preferences_set_updated_at
before update on public.job_alert_preferences
for each row execute function public.set_updated_at();

create table if not exists public.job_alert_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default timezone('utc', now()),
  completed_at timestamptz,
  jobs_count integer not null default 0,
  emails_sent integer not null default 0,
  emails_skipped integer not null default 0,
  status text not null default 'running',
  error_message text
);

alter table public.job_alert_preferences enable row level security;
alter table public.job_alert_runs enable row level security;

drop policy if exists "Users can view their job alert preferences" on public.job_alert_preferences;
create policy "Users can view their job alert preferences"
on public.job_alert_preferences
for select
using (auth.uid() = user_id);

drop policy if exists "Users can update their job alert preferences" on public.job_alert_preferences;
create policy "Users can update their job alert preferences"
on public.job_alert_preferences
for update
using (auth.uid() = user_id);
