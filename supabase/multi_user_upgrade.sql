-- Safe upgrade for existing StockAI Supabase projects.
alter table public.screening_preferences
add column if not exists holding_days integer not null default 60;

alter table public.screening_preferences
drop constraint if exists screening_preferences_holding_days_check;
alter table public.screening_preferences
add constraint screening_preferences_holding_days_check
check (holding_days between 1 and 250);

alter table public.screening_results
add column if not exists holding_days integer;
alter table public.screening_results
add column if not exists condition_summary text;

grant select, insert, update
on table public.screening_preferences
to authenticated;

grant select
on table public.screening_results
to authenticated;
