create table if not exists public.screening_preferences (
  user_id uuid primary key references auth.users(id) on delete cascade,
  mode text not null check (mode in ('auto', 'manual')) default 'auto',
  genre_id text,
  manual_logic text check (manual_logic in ('all', 'any')) default 'all',
  manual_conditions jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now(),
  constraint auto_requires_genre check (mode <> 'auto' or genre_id is not null),
  constraint manual_condition_limit check (jsonb_array_length(manual_conditions) <= 8)
);

alter table public.screening_preferences enable row level security;

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
