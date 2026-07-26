-- StockAI 0.17.0: historical conditional price estimates.
-- This migration preserves all existing screening results and is safe to rerun.

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

grant select, insert, update, delete
on table public.screening_results
to service_role;
