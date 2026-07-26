-- Safe upgrade for existing StockAI Supabase projects.
alter table public.screening_preferences
add column if not exists holding_days integer not null default 60;
alter table public.screening_preferences
add column if not exists expectation_mode text not null default 'auto';
alter table public.screening_preferences
add column if not exists expectation_genre_id text;
alter table public.screening_preferences
add column if not exists expectation_manual_logic text not null default 'all';
alter table public.screening_preferences
add column if not exists expectation_manual_conditions jsonb not null default '[]'::jsonb;
alter table public.screening_preferences
add column if not exists trade_direction text not null default 'long';
alter table public.screening_preferences
drop constraint if exists screening_preferences_trade_direction_check;
alter table public.screening_preferences
add constraint screening_preferences_trade_direction_check
check (trade_direction in ('long', 'short'));

alter table public.screening_preferences
drop constraint if exists screening_preferences_holding_days_check;
alter table public.screening_preferences
add constraint screening_preferences_holding_days_check
check (holding_days between 1 and 1000);

alter table public.screening_results
add column if not exists holding_days integer;
alter table public.screening_results
add column if not exists condition_summary text;
alter table public.screening_results
add column if not exists expectation_condition_summary text;
alter table public.screening_results
add column if not exists trade_direction text not null default 'long';

grant select, insert, update
on table public.screening_preferences
to authenticated;

grant select
on table public.screening_preferences
to service_role;

grant select
on table public.screening_results
to authenticated;

grant select, insert, update, delete
on table public.screening_results
to service_role;

create table if not exists public.screening_runs (
  user_id uuid primary key references auth.users(id) on delete cascade,
  screening_date date not null,
  profile_name text not null,
  holding_days integer not null check (holding_days between 1 and 1000),
  condition_summary text,
  expectation_condition_summary text,
  trade_direction text not null default 'long' check (trade_direction in ('long', 'short')),
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
