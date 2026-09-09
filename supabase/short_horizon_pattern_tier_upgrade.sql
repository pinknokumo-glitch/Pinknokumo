-- Add explicit primary/watch tiers to the independent short-pattern dataset.
-- Safe to run after short_horizon_patterns_upgrade.sql; does not touch user settings.
begin;

alter table public.short_pattern_results
  add column if not exists tier text not null default 'watch'
  check (tier in ('primary', 'watch'));

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
    signal_date, signal_close, target_percent, target_price, resistance_price, support_price, holding_days,
    target_probability_percent, trade_count, average_return_percent, median_return_percent, max_adverse_percent,
    out_of_sample_trade_count, out_of_sample_target_probability_percent, horizon_statistics,
    morning_price, morning_price_at, morning_target_price, confirmation_status
  )
  select p_run_id, r.position, r.code, coalesce(r.company_name,''), r.pattern_id, r.pattern_label,
    r.direction, coalesce(r.tier, 'watch'), coalesce(r.pattern_summary,''), r.signal_date, r.signal_close,
    r.target_percent, r.target_price, r.resistance_price, r.support_price, r.holding_days,
    r.target_probability_percent, r.trade_count, r.average_return_percent, r.median_return_percent,
    r.max_adverse_percent, r.out_of_sample_trade_count, r.out_of_sample_target_probability_percent,
    coalesce(r.horizon_statistics, '{}'::jsonb), r.morning_price, r.morning_price_at,
    r.morning_target_price, coalesce(r.confirmation_status,'')
  from jsonb_to_recordset(p_results) as r(
    position integer, code text, company_name text, pattern_id text, pattern_label text, direction text, tier text,
    pattern_summary text, signal_date date, signal_close double precision, target_percent double precision,
    target_price double precision, resistance_price double precision, support_price double precision,
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
