-- StockAI: selectable RSI calculation method.
alter table public.screening_preferences
add column if not exists rsi_method text not null default 'rakuten';

alter table public.screening_preferences
drop constraint if exists screening_preferences_rsi_method_check;
alter table public.screening_preferences
add constraint screening_preferences_rsi_method_check
check (rsi_method in ('auto', 'rakuten', 'wilder'));

alter table public.screening_runs
add column if not exists rsi_method text not null default 'rakuten';

alter table public.screening_runs
drop constraint if exists screening_runs_rsi_method_check;
alter table public.screening_runs
add constraint screening_runs_rsi_method_check
check (rsi_method in ('rakuten', 'wilder'));
