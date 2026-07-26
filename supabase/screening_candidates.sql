create table if not exists public.screening_candidates (
  pool_date date not null,
  code text not null,
  updated_at timestamptz not null default now(),
  primary key (pool_date, code)
);

create index if not exists screening_candidates_date_idx
on public.screening_candidates (pool_date desc, code);

alter table public.screening_candidates enable row level security;

grant select on table public.screening_candidates to authenticated;

drop policy if exists "authenticated users read candidate pool"
on public.screening_candidates;
create policy "authenticated users read candidate pool"
on public.screening_candidates for select
to authenticated
using (true);

create table if not exists public.screening_candidate_runs (
  pool_date date primary key,
  universe_count integer not null default 0 check (universe_count >= 0),
  evaluated_count integer not null default 0 check (evaluated_count >= 0),
  candidate_count integer not null default 0 check (candidate_count >= 0),
  failed_count integer not null default 0 check (failed_count >= 0),
  coverage_ratio double precision not null default 0
    check (coverage_ratio >= 0 and coverage_ratio <= 1),
  status text not null default 'pending',
  usable boolean not null default false,
  updated_at timestamptz not null default now()
);

-- CREATE TABLE IF NOT EXISTS does not add columns to an existing older table.
-- Keep this migration rerunnable so upgrades work without dropping user data.
alter table public.screening_candidate_runs
  add column if not exists universe_count integer not null default 0,
  add column if not exists evaluated_count integer not null default 0,
  add column if not exists candidate_count integer not null default 0,
  add column if not exists failed_count integer not null default 0,
  add column if not exists coverage_ratio double precision not null default 0,
  add column if not exists status text not null default 'pending',
  add column if not exists usable boolean not null default false,
  add column if not exists updated_at timestamptz not null default now();

create unique index if not exists screening_candidate_runs_pool_date_idx
on public.screening_candidate_runs (pool_date);

alter table public.screening_candidate_runs enable row level security;

grant select on table public.screening_candidate_runs to authenticated;

drop policy if exists "authenticated users read candidate run"
on public.screening_candidate_runs;
create policy "authenticated users read candidate run"
on public.screening_candidate_runs for select
to authenticated
using (true);
