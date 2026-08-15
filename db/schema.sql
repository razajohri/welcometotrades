create extension if not exists pgcrypto;
create extension if not exists pg_trgm;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null unique,
  is_admin boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create or replace function public.handle_auth_user_change()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, metadata)
  values (
    new.id,
    coalesce(new.email, ''),
    coalesce(new.raw_user_meta_data, '{}'::jsonb)
  )
  on conflict (id) do update
  set email = excluded.email,
      metadata = excluded.metadata,
      updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_auth_user_change();

drop trigger if exists on_auth_user_updated on auth.users;
create trigger on_auth_user_updated
after update on auth.users
for each row execute function public.handle_auth_user_change();

insert into public.profiles (id, email)
select id, email
from auth.users
where email is not null
on conflict (id) do update
set email = excluded.email,
    updated_at = timezone('utc', now());

create trigger profiles_set_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

create table if not exists public.subscriptions (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  email text,
  status text not null default 'inactive',
  stripe_customer_id text unique,
  stripe_subscription_id text unique,
  stripe_price_id text,
  stripe_checkout_session_id text,
  current_period_end timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint subscriptions_status_check check (
    status in (
      'inactive',
      'checkout_started',
      'active',
      'trialing',
      'past_due',
      'canceled',
      'lifetime'
    )
  )
);

create trigger subscriptions_set_updated_at
before update on public.subscriptions
for each row execute function public.set_updated_at();

create table if not exists public.jobs (
  id uuid primary key default gen_random_uuid(),
  source_key text not null unique,
  site text,
  title text not null,
  company text,
  location text,
  description text,
  compensation text,
  interval text,
  min_amount numeric,
  max_amount numeric,
  currency text,
  job_type text,
  job_url text,
  job_url_direct text,
  date_posted timestamptz,
  is_active boolean not null default true,
  is_remote boolean not null default true,
  raw_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists jobs_title_trgm_idx on public.jobs using gin (title gin_trgm_ops);
create index if not exists jobs_company_trgm_idx on public.jobs using gin (company gin_trgm_ops);
create index if not exists jobs_date_posted_idx on public.jobs (date_posted desc);
create index if not exists jobs_is_active_date_idx on public.jobs (is_active, date_posted desc);
create index if not exists jobs_site_idx on public.jobs (site);

create trigger jobs_set_updated_at
before update on public.jobs
for each row execute function public.set_updated_at();

create table if not exists public.contact_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles (id) on delete set null,
  email text not null,
  subject text not null,
  message text not null,
  ip_address text,
  recaptcha_score numeric,
  delivery_status text not null default 'received',
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.scrape_runs (
  id uuid primary key default gen_random_uuid(),
  status text not null,
  jobs_seen integer not null default 0,
  message text,
  created_at timestamptz not null default timezone('utc', now())
);

alter table public.profiles enable row level security;
alter table public.subscriptions enable row level security;
alter table public.jobs enable row level security;
alter table public.contact_messages enable row level security;
alter table public.scrape_runs enable row level security;

drop policy if exists "Users can view their profile" on public.profiles;
create policy "Users can view their profile"
on public.profiles
for select
using (auth.uid() = id);

drop policy if exists "Users can update their profile" on public.profiles;
create policy "Users can update their profile"
on public.profiles
for update
using (auth.uid() = id);

drop policy if exists "Users can view their subscription" on public.subscriptions;
create policy "Users can view their subscription"
on public.subscriptions
for select
using (auth.uid() = user_id);

drop policy if exists "Users can view their contact messages" on public.contact_messages;
create policy "Users can view their contact messages"
on public.contact_messages
for select
using (auth.uid() = user_id);
