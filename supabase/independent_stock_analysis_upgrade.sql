-- Apply after on_demand_analysis_upgrade.sql. Old clients/RPC remain supported.
begin;
create or replace function public.start_independent_stock_analysis(
  p_code text, p_days integer, p_up double precision, p_down double precision
)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
  dataset text;
  token text;
  rid bigint;
  http_id bigint;
  snapshot jsonb;
begin
  if uid is null then raise exception 'Login required'; end if;
  if p_days is null or p_days < 1 or p_days > 1000 then
    raise exception '検証期間は1～1000営業日です';
  end if;
  if p_code is null or upper(trim(p_code)) !~ '^[0-9A-Z]{4,5}$' then
    raise exception 'Invalid stock code';
  end if;
  if (p_up is not null and not (p_up > 0 and p_up <= 100)) or
     (p_down is not null and not (p_down > 0 and p_down <= 100)) then
    raise exception '目標率は0より大きく100以下です';
  end if;
  snapshot := jsonb_build_object('analysis_mode','independent','holding_days',p_days);
  perform pg_advisory_xact_lock(73194261);
  select id into rid from public.backtest_requests
    where user_id=uid and input_snapshot is not null and status in ('pending','processing')
      and created_at > now()-interval '2 hours' order by id desc limit 1;
  if rid is not null then
    if exists(select 1 from public.backtest_requests where id=rid and code=upper(trim(p_code))
      and input_snapshot=snapshot and up_target_percent is not distinct from p_up
      and down_target_percent is not distinct from p_down) then
      return jsonb_build_object('id',rid);
    end if;
    raise exception '別の条件を分析中です。完了後にお試しください';
  end if;
  if (select count(*) from public.backtest_requests where input_snapshot is not null
      and created_at > now()-interval '1 hour') >= 12 then
    raise exception '分析依頼が混み合っています。時間をおいて再度お試しください';
  end if;
  select dataset_run_id into dataset from public.stock_search_catalog
    where code=upper(trim(p_code)) and available=true;
  if dataset is null then raise exception '夕方の取得データがありません'; end if;
  select decrypted_secret into token from vault.decrypted_secrets where name='stockai_actions_token' limit 1;
  if token is null or token='' then raise exception '分析起動用の設定が未完了です'; end if;
  insert into public.backtest_requests(user_id,code,up_target_percent,down_target_percent,input_snapshot,dataset_run_id)
    values(uid,upper(trim(p_code)),p_up,p_down,snapshot,dataset) returning id into rid;
  select net.http_post(
    url := 'https://api.github.com/repos/pinknokumo-glitch/Pinknokumo/actions/workflows/stock-analysis.yml/dispatches',
    headers := jsonb_build_object('Authorization','Bearer '||token,'Accept','application/vnd.github+json',
      'Content-Type','application/json','User-Agent','StockAI'),
    body := jsonb_build_object('ref','main','inputs',jsonb_build_object('request_id',rid::text,'dataset_run_id',dataset)),
    timeout_milliseconds := 15000
  ) into http_id;
  update public.backtest_requests set dispatch_id=http_id where id=rid;
  return jsonb_build_object('id',rid);
end $$;
revoke all on function public.start_independent_stock_analysis(text,integer,double precision,double precision) from public, anon;
grant execute on function public.start_independent_stock_analysis(text,integer,double precision,double precision) to authenticated;
commit;
