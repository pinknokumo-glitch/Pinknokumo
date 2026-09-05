-- Apply after specified_stock_analysis_upgrade.sql. Secrets are configured in Vault UI.
begin;
create extension if not exists pg_net with schema extensions;
alter table public.stock_search_catalog add column if not exists dataset_run_id text;
alter table public.stock_search_catalog add column if not exists available boolean not null default false;
alter table public.backtest_requests add column if not exists input_snapshot jsonb;
alter table public.backtest_requests add column if not exists dataset_run_id text;
alter table public.backtest_requests add column if not exists dispatch_id bigint;

create or replace function public.publish_evening_catalog(p_run_id text, p_stocks jsonb)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if p_run_id !~ '^[0-9]+$' or jsonb_array_length(p_stocks) = 0 then
    raise exception 'Invalid evening snapshot';
  end if;
  update public.stock_search_catalog set available=false;
  insert into public.stock_search_catalog(code, company_name, dataset_run_id, available, updated_at)
  select x.code, x.company_name, p_run_id, true, now()
  from jsonb_to_recordset(p_stocks) as x(code text, company_name text)
  on conflict(code) do update set company_name=excluded.company_name,
    dataset_run_id=excluded.dataset_run_id, available=true, updated_at=now();
end $$;
revoke all on function public.publish_evening_catalog(text,jsonb) from public, anon, authenticated;
grant execute on function public.publish_evening_catalog(text,jsonb) to service_role;

-- Only this RPC can create on-demand requests; legacy pending requests remain supported.
revoke insert on public.backtest_requests from authenticated;
grant insert(user_id,code,up_target_percent,down_target_percent,status) on public.backtest_requests to authenticated;

create or replace function public.start_stock_analysis(p_code text, p_up double precision default null, p_down double precision default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  uid uuid := auth.uid();
  pref jsonb;
  dataset text;
  token text;
  rid bigint;
  http_id bigint;
begin
  if uid is null then raise exception 'Login required'; end if;
  -- Serialize submissions globally: personal-use rate cap and double-tap protection.
  perform pg_advisory_xact_lock(73194261);
  select id into rid from public.backtest_requests
    where user_id=uid and input_snapshot is not null and status in ('pending','processing')
      and created_at > now()-interval '2 hours' order by id desc limit 1;
  if rid is not null then
    if exists(select 1 from public.backtest_requests where id=rid and code=upper(trim(p_code))) then
      return jsonb_build_object('id',rid);
    end if;
    raise exception '別の銘柄を分析中です。完了後にお試しください';
  end if;
  if (select count(*) from public.backtest_requests where input_snapshot is not null
      and created_at > now()-interval '1 hour') >= 12 then
    raise exception '分析依頼が混み合っています。時間をおいて再度お試しください';
  end if;
  select dataset_run_id into dataset from public.stock_search_catalog
    where code=upper(trim(p_code)) and available=true;
  if dataset is null then raise exception '夕方の取得データがありません'; end if;
  select to_jsonb(p) into pref from public.screening_preferences p where user_id=uid;
  if pref is null then raise exception '先に分析条件を保存してください'; end if;
  select decrypted_secret into token from vault.decrypted_secrets where name='stockai_actions_token' limit 1;
  if token is null or token='' then raise exception '分析起動用の設定が未完了です'; end if;
  insert into public.backtest_requests(user_id,code,up_target_percent,down_target_percent,input_snapshot,dataset_run_id)
    values(uid,upper(trim(p_code)),p_up,p_down,pref,dataset) returning id into rid;
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
revoke all on function public.start_stock_analysis(text,double precision,double precision) from public, anon;
grant execute on function public.start_stock_analysis(text,double precision,double precision) to authenticated;

-- Polling records dispatch failures without returning GitHub response bodies or secrets.
create or replace function public.refresh_stock_analysis(p_id bigint)
returns void language plpgsql security definer set search_path = '' as $$
declare r public.backtest_requests; http_status integer; request_timed_out boolean; network_error text;
begin
  select * into r from public.backtest_requests where id=p_id and user_id=auth.uid() for update;
  if r.id is null or r.status not in ('pending','processing') or r.input_snapshot is null then return; end if;
  select h.status_code, h.timed_out, h.error_msg into http_status, request_timed_out, network_error
    from net._http_response h where h.id=r.dispatch_id;
  if coalesce(request_timed_out,false) or network_error is not null
      or (http_status is not null and http_status not between 200 and 299) then
    update public.backtest_requests set status='failed', updated_at=now(),
      error_message='分析の起動に失敗しました。起動設定を確認して再依頼してください。' where id=p_id;
  elsif r.created_at < now()-interval '2 hours' then
    update public.backtest_requests set status='failed', updated_at=now(),
      error_message='分析の待機時間を超えました。再依頼してください。' where id=p_id;
  end if;
end $$;
revoke all on function public.refresh_stock_analysis(bigint) from public, anon;
grant execute on function public.refresh_stock_analysis(bigint) to authenticated;
commit;
