-- StockAI 0.16.0: allow long-horizon expectation analysis.
-- This migration preserves all existing rows and is safe to run repeatedly.

alter table public.screening_preferences
drop constraint if exists screening_preferences_holding_days_check;
alter table public.screening_preferences
add constraint screening_preferences_holding_days_check
check (holding_days between 1 and 1000);

alter table public.screening_results
drop constraint if exists screening_results_holding_days_check;
alter table public.screening_results
add constraint screening_results_holding_days_check
check (holding_days is null or holding_days between 1 and 1000);

alter table public.screening_runs
drop constraint if exists screening_runs_holding_days_check;
alter table public.screening_runs
add constraint screening_runs_holding_days_check
check (holding_days between 1 and 1000);
