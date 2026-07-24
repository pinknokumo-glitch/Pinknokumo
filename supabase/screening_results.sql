create table if not exists public.screening_results (
  user_id uuid not null references auth.users(id) on delete cascade,
  screening_date date not null,
  profile_name text not null,
  position integer not null check (position > 0),
  code text not null,
  company_name text,
  expectation_score double precision,
  reason text,
  comment text,
  chart_url text,
  updated_at timestamptz not null default now(),
  primary key (user_id, screening_date, profile_name, code)
);

create index if not exists screening_results_user_date_idx
on public.screening_results (user_id, screening_date desc, position);

alter table public.screening_results enable row level security;

drop policy if exists "read own screening results" on public.screening_results;
create policy "read own screening results"
on public.screening_results for select
to authenticated
using ((select auth.uid()) = user_id);

