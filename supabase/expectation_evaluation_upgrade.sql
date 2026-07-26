-- StockAI 0.15.0: selectable expectation outcomes.
-- Rerunnable. Existing preferences and results are preserved.

alter table public.screening_preferences
add column if not exists expectation_evaluation_mode text not null default 'condition_exit';
alter table public.screening_preferences
add column if not exists target_return_percent double precision not null default 5.0;
alter table public.screening_preferences
drop constraint if exists screening_preferences_expectation_evaluation_mode_check;
alter table public.screening_preferences
add constraint screening_preferences_expectation_evaluation_mode_check
check (expectation_evaluation_mode in (
  'condition_exit', 'period_end', 'within_period_up', 'target_return'
));
alter table public.screening_preferences
drop constraint if exists screening_preferences_target_return_percent_check;
alter table public.screening_preferences
add constraint screening_preferences_target_return_percent_check
check (target_return_percent > 0 and target_return_percent <= 100);

alter table public.screening_results
add column if not exists expectation_evaluation_mode text not null default 'condition_exit';
alter table public.screening_results
add column if not exists target_return_percent double precision not null default 5.0;
alter table public.screening_results
add column if not exists outcome_probability_percent double precision;

alter table public.screening_runs
add column if not exists expectation_evaluation_mode text not null default 'condition_exit';
alter table public.screening_runs
add column if not exists target_return_percent double precision not null default 5.0;

grant select on table public.screening_preferences to service_role;
grant select, insert, delete on table public.screening_results to service_role;
grant select, insert, update on table public.screening_runs to service_role;
