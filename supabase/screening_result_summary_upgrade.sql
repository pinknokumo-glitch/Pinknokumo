-- Add the compact backtest metrics used by the Android delivery-result list.
-- Safe to run repeatedly. Existing rows are preserved.

alter table public.screening_results
add column if not exists average_return_percent double precision;

alter table public.screening_results
add column if not exists win_rate_percent double precision;

alter table public.screening_results
add column if not exists max_drawdown_percent double precision;

grant select
on table public.screening_results
to authenticated;

grant select, insert, update, delete
on table public.screening_results
to service_role;
