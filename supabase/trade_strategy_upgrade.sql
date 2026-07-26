-- StockAI 0.14.0: entry/exit conditions and long/short strategy metadata.
-- This script is rerunnable and preserves existing settings and results.

alter table public.screening_preferences
add column if not exists trade_direction text not null default 'long';
alter table public.screening_preferences
drop constraint if exists screening_preferences_trade_direction_check;
alter table public.screening_preferences
add constraint screening_preferences_trade_direction_check
check (trade_direction in ('long', 'short'));

alter table public.screening_results
add column if not exists expectation_condition_summary text;
alter table public.screening_results
add column if not exists trade_direction text not null default 'long';
alter table public.screening_results
drop constraint if exists screening_results_trade_direction_check;
alter table public.screening_results
add constraint screening_results_trade_direction_check
check (trade_direction in ('long', 'short'));

alter table public.screening_runs
add column if not exists expectation_condition_summary text;
alter table public.screening_runs
add column if not exists trade_direction text not null default 'long';
alter table public.screening_runs
add column if not exists relaxation_label text;
alter table public.screening_runs
add column if not exists relaxation_counts jsonb not null default '[]'::jsonb;
alter table public.screening_runs
drop constraint if exists screening_runs_trade_direction_check;
alter table public.screening_runs
add constraint screening_runs_trade_direction_check
check (trade_direction in ('long', 'short'));

grant select on table public.screening_preferences to service_role;
grant select, insert, update, delete on table public.screening_results to service_role;
grant select, insert, update on table public.screening_runs to service_role;
