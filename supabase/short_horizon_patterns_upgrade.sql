-- Global, read-only short-horizon chart-pattern results.
-- This migration deliberately does not alter user preferences, deliveries, or requested analyses.
begin;

create table if not exists public.short_pattern_runs (
  run_id text primary key,
  signal_date date not null,
  source_run_id text not null,
  candidate_count integer not null default 0 check (candidate_count >= 0),
  updated_at timestamptz not null default now()
);

create table if not exists public.short_pattern_results (
  run_id text not null references public.short_pattern_runs(run_id) on delete cascade,
  position integer not null check (position > 0),
  code text not null,
  company_name text not null default '',
  pattern_id text not null,
  pattern_label text not null,
  direction text not null check (direction in ('long', 'short')),
  tier text not null check (tier in ('primary', 'watch')),
  pattern_summary text not null default '',
  signal_date date not null,
  signal_close double precision not null check (signal_close > 0),
  target_percent double precision not null check (target_percent > 0 and target_percent <= 100),
  target_price double precision not null check (target_price > 0),
  confirmation_trigger_price double precision,
  confirmation_window_sessions integer,
  resistance_price double precision,
  support_price double precision,
  holding_days integer not null check (holding_days between 1 and 30),
  target_probability_percent double precision not null check (target_probability_percent >= 0 and target_probability_percent <= 100),
  trade_count integer not null check (trade_count >= 0),
  average_return_percent double precision,
  median_return_percent double precision,
  max_adverse_percent double precision,
  out_of_sample_trade_count integer not null default 0 check (out_of_sample_trade_count >= 0),
  out_of_sample_target_probability_percent double precision,
  horizon_statistics jsonb not null default '{}'::jsonb,
  morning_price double precision,
  morning_price_at timestamptz,
  morning_target_price double precision,
  confirmation_status text not null default '',
  primary key (run_id, position)
);

create index if not exists short_pattern_runs_signal_date_idx
  on public.short_pattern_runs(signal_date desc, updated_at desc);
create index if not exists short_pattern_results_run_direction_idx
  on public.short_pattern_results(run_id, direction, position);

alter table public.short_pattern_runs enable row level security;
alter table public.short_pattern_results enable row level security;
grant select on table public.short_pattern_runs, public.short_pattern_results to authenticated;
grant select, insert, update, delete on table public.short_pattern_runs, public.short_pattern_results to service_role;

drop policy if exists "authenticated users read short pattern runs" on public.short_pattern_runs;
create policy "authenticated users read short pattern runs" on public.short_pattern_runs
  for select to authenticated using (true);
drop policy if exists "authenticated users read short pattern results" on public.short_pattern_results;
create policy "authenticated users read short pattern results" on public.short_pattern_results
  for select to authenticated using (true);

create or replace function public.publish_short_pattern_run(
  p_run_id text, p_signal_date date, p_source_run_id text, p_results jsonb
)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if p_run_id is null or btrim(p_run_id) = '' or p_source_run_id is null or btrim(p_source_run_id) = '' then
    raise exception 'run identifiers are required';
  end if;
  if p_signal_date is null or p_results is null or jsonb_typeof(p_results) <> 'array' then
    raise exception 'signal date and result array are required';
  end if;
  insert into public.short_pattern_runs(run_id, signal_date, source_run_id, candidate_count)
  values (p_run_id, p_signal_date, p_source_run_id, jsonb_array_length(p_results))
  on conflict (run_id) do update set
    signal_date=excluded.signal_date,
    source_run_id=excluded.source_run_id,
    candidate_count=excluded.candidate_count,
    updated_at=now();

  delete from public.short_pattern_results where run_id=p_run_id;
  insert into public.short_pattern_results(
    run_id, position, code, company_name, pattern_id, pattern_label, direction, tier, pattern_summary,
    signal_date, signal_close, target_percent, target_price, confirmation_trigger_price, confirmation_window_sessions,
    resistance_price, support_price, holding_days,
    target_probability_percent, trade_count, average_return_percent, median_return_percent, max_adverse_percent,
    out_of_sample_trade_count, out_of_sample_target_probability_percent, horizon_statistics,
    morning_price, morning_price_at, morning_target_price, confirmation_status
  )
  select p_run_id, r.position, r.code, coalesce(r.company_name,''), r.pattern_id, r.pattern_label,
    r.direction, r.tier, coalesce(r.pattern_summary,''), r.signal_date, r.signal_close, r.target_percent,
    r.target_price, r.confirmation_trigger_price, r.confirmation_window_sessions, r.resistance_price, r.support_price,
    r.holding_days, r.target_probability_percent,
    r.trade_count, r.average_return_percent, r.median_return_percent, r.max_adverse_percent,
    r.out_of_sample_trade_count, r.out_of_sample_target_probability_percent,
    coalesce(r.horizon_statistics, '{}'::jsonb), r.morning_price, r.morning_price_at,
    r.morning_target_price, coalesce(r.confirmation_status,'')
  from jsonb_to_recordset(p_results) as r(
    position integer, code text, company_name text, pattern_id text, pattern_label text, direction text, tier text,
    pattern_summary text, signal_date date, signal_close double precision, target_percent double precision,
    target_price double precision, confirmation_trigger_price double precision, confirmation_window_sessions integer,
    resistance_price double precision, support_price double precision,
    holding_days integer, target_probability_percent double precision, trade_count integer,
    average_return_percent double precision, median_return_percent double precision, max_adverse_percent double precision,
    out_of_sample_trade_count integer, out_of_sample_target_probability_percent double precision,
    horizon_statistics jsonb, morning_price double precision, morning_price_at timestamptz,
    morning_target_price double precision, confirmation_status text
  );
end $$;

revoke all on function public.publish_short_pattern_run(text,date,text,jsonb) from public, anon, authenticated;
grant execute on function public.publish_short_pattern_run(text,date,text,jsonb) to service_role;
commit;
