-- StockAI: bounded condition exits and favorable-price milestone probabilities.
-- Safe to rerun; existing screening result rows are preserved.

alter table public.screening_results
add column if not exists profit_10_probability_percent double precision;

alter table public.screening_results
add column if not exists profit_20_probability_percent double precision;

grant select, insert, update, delete
on table public.screening_results
to service_role;
