-- Run this complete file in the Supabase SQL editor before publishing StockAI 0.19.0.
alter table public.screening_results
add column if not exists individual_trade_count integer not null default 0;

alter table public.screening_results
add column if not exists individual_out_of_sample_trade_count integer not null default 0;

alter table public.screening_results
add column if not exists individual_out_of_sample_average_return_percent double precision;

alter table public.screening_results
add column if not exists individual_out_of_sample_win_rate_percent double precision;

alter table public.screening_results
add column if not exists sector_name text;

alter table public.screening_results
add column if not exists sector_backtest jsonb not null default '{}'::jsonb;

alter table public.screening_results
add column if not exists market_backtest jsonb not null default '{}'::jsonb;

alter table public.screening_results
add column if not exists backtest_coverage_ratio double precision;

alter table public.screening_results
add column if not exists backtest_confidence text;

grant select on table public.screening_results to authenticated;
grant select, insert, update, delete on table public.screening_results to service_role;
