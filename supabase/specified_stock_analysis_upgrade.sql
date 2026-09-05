-- StockAI specified-stock analysis: target bands and a read-only search catalog.
alter table public.backtest_requests
add column if not exists up_target_percent double precision;
alter table public.backtest_requests
add column if not exists down_target_percent double precision;
alter table public.backtest_requests
drop constraint if exists backtest_requests_up_target_percent_check;
alter table public.backtest_requests
add constraint backtest_requests_up_target_percent_check
check (up_target_percent is null or up_target_percent > 0 and up_target_percent <= 100);
alter table public.backtest_requests
drop constraint if exists backtest_requests_down_target_percent_check;
alter table public.backtest_requests
add constraint backtest_requests_down_target_percent_check
check (down_target_percent is null or down_target_percent > 0 and down_target_percent <= 100);

create table if not exists public.stock_search_catalog (
  code text primary key,
  company_name text not null default '',
  updated_at timestamptz not null default now()
);
create index if not exists stock_search_catalog_company_name_idx
on public.stock_search_catalog (company_name);
alter table public.stock_search_catalog enable row level security;
grant select on table public.stock_search_catalog to authenticated;
grant select, insert, update on table public.stock_search_catalog to service_role;
drop policy if exists "authenticated users search stock catalog"
on public.stock_search_catalog;
create policy "authenticated users search stock catalog"
on public.stock_search_catalog for select to authenticated using (true);

