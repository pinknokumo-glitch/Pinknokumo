create table if not exists public.screening_preferences (
  user_id uuid primary key references auth.users(id) on delete cascade,
  mode text not null check (mode in ('auto', 'manual')) default 'auto',
  genre_id text,
  manual_logic text check (manual_logic in ('all', 'any')) default 'all',
  manual_conditions jsonb not null default '[]'::jsonb,
  holding_days integer not null default 60 check (holding_days between 1 and 250),
  expectation_mode text not null default 'auto' check (expectation_mode in ('auto', 'manual')),
  expectation_genre_id text,
  expectation_manual_logic text not null default 'all' check (expectation_manual_logic in ('all', 'any')),
  expectation_manual_conditions jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now(),
  constraint auto_requires_genre check (mode <> 'auto' or genre_id is not null),
  constraint manual_condition_limit check (jsonb_array_length(manual_conditions) <= 32)
);

alter table public.screening_preferences
add column if not exists holding_days integer not null default 60;
alter table public.screening_preferences
add column if not exists expectation_mode text not null default 'auto';
alter table public.screening_preferences
add column if not exists expectation_genre_id text;
alter table public.screening_preferences
add column if not exists expectation_manual_logic text not null default 'all';
alter table public.screening_preferences
add column if not exists expectation_manual_conditions jsonb not null default '[]'::jsonb;
alter table public.screening_preferences
drop constraint if exists manual_condition_limit;
alter table public.screening_preferences
add constraint manual_condition_limit
check (jsonb_array_length(manual_conditions) <= 32);

alter table public.screening_preferences
drop constraint if exists screening_preferences_holding_days_check;
alter table public.screening_preferences
add constraint screening_preferences_holding_days_check
check (holding_days between 1 and 250);

alter table public.screening_preferences enable row level security;

grant select, insert, update
on table public.screening_preferences
to authenticated;

drop policy if exists "read own screening preference" on public.screening_preferences;
create policy "read own screening preference"
on public.screening_preferences for select
to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "insert own screening preference" on public.screening_preferences;
create policy "insert own screening preference"
on public.screening_preferences for insert
to authenticated
with check ((select auth.uid()) = user_id);

drop policy if exists "update own screening preference" on public.screening_preferences;
create policy "update own screening preference"
on public.screening_preferences for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);
