create table if not exists public.screening_results (
  user_id uuid not null references auth.users(id) on delete cascade,
  screening_date date not null,
  profile_name text not null,
  position integer not null check (position > 0),
  code text not null,
  company_name text,
  expectation_score double precision,
  reason text,
  comment text,
  chart_url text,
  holding_days integer check (holding_days between 1 and 1000),
  condition_summary text,
  expectation_condition_summary text,
  trade_direction text not null default 'long' check (trade_direction in ('long', 'short')),
  expectation_evaluation_mode text not null default 'condition_exit',
  target_return_percent double precision not null default 5.0,
  outcome_probability_percent double precision,
  average_return_percent double precision,
  win_rate_percent double precision,
  max_drawdown_percent double precision,
  reference_price double precision,
  estimated_price_median double precision,
  estimated_price_low double precision,
  estimated_price_high double precision,
  estimate_sample_count integer not null default 0,
  median_days_to_outcome double precision,
  updated_at timestamptz not null default now(),
  primary key (user_id, screening_date, profile_name, code)
);

alter table public.screening_results
add column if not exists holding_days integer;
alter table public.screening_results
add column if not exists condition_summary text;
alter table public.screening_results
add column if not exists expectation_condition_summary text;
alter table public.screening_results
add column if not exists trade_direction text not null default 'long';
alter table public.screening_results
add column if not exists expectation_evaluation_mode text not null default 'condition_exit';
alter table public.screening_results
add column if not exists target_return_percent double precision not null default 5.0;
alter table public.screening_results
add column if not exists outcome_probability_percent double precision;
alter table public.screening_results
add column if not exists average_return_percent double precision;
alter table public.screening_results
add column if not exists win_rate_percent double precision;
alter table public.screening_results
add column if not exists max_drawdown_percent double precision;
alter table public.screening_results
add column if not exists reference_price double precision;
alter table public.screening_results
add column if not exists estimated_price_median double precision;
alter table public.screening_results
add column if not exists estimated_price_low double precision;
alter table public.screening_results
add column if not exists estimated_price_high double precision;
alter table public.screening_results
add column if not exists estimate_sample_count integer not null default 0;
alter table public.screening_results
add column if not exists median_days_to_outcome double precision;

create index if not exists screening_results_user_date_idx
on public.screening_results (user_id, screening_date desc, position);

alter table public.screening_results enable row level security;

grant select
on table public.screening_results
to authenticated;

grant select, insert, update, delete
on table public.screening_results
to service_role;

drop policy if exists "read own screening results" on public.screening_results;
create policy "read own screening results"
on public.screening_results for select
to authenticated
using ((select auth.uid()) = user_id);

create table if not exists public.screening_runs (
  user_id uuid primary key references auth.users(id) on delete cascade,
  screening_date date not null,
  profile_name text not null,
  holding_days integer not null check (holding_days between 1 and 1000),
  condition_summary text,
  expectation_condition_summary text,
  trade_direction text not null default 'long' check (trade_direction in ('long', 'short')),
  expectation_evaluation_mode text not null default 'condition_exit',
  target_return_percent double precision not null default 5.0,
  relaxation_label text,
  relaxation_counts jsonb not null default '[]'::jsonb,
  hit_count integer not null check (hit_count >= 0),
  updated_at timestamptz not null default now()
);

alter table public.screening_runs
add column if not exists expectation_condition_summary text;
alter table public.screening_runs
add column if not exists trade_direction text not null default 'long';
alter table public.screening_runs
add column if not exists expectation_evaluation_mode text not null default 'condition_exit';
alter table public.screening_runs
add column if not exists target_return_percent double precision not null default 5.0;
alter table public.screening_runs
add column if not exists relaxation_label text;
alter table public.screening_runs
add column if not exists relaxation_counts jsonb not null default '[]'::jsonb;

alter table public.screening_runs enable row level security;

grant select on table public.screening_runs to authenticated;
grant select, insert, update on table public.screening_runs to service_role;

drop policy if exists "read own screening run" on public.screening_runs;
create policy "read own screening run"
on public.screening_runs for select
to authenticated
using ((select auth.uid()) = user_id);

