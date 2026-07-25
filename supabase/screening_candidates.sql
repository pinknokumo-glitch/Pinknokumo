create table if not exists public.screening_candidates (
  pool_date date not null,
  code text not null,
  updated_at timestamptz not null default now(),
  primary key (pool_date, code)
);

create index if not exists screening_candidates_date_idx
on public.screening_candidates (pool_date desc, code);

alter table public.screening_candidates enable row level security;

grant select on table public.screening_candidates to authenticated;

drop policy if exists "authenticated users read candidate pool"
on public.screening_candidates;
create policy "authenticated users read candidate pool"
on public.screening_candidates for select
to authenticated
using (true);
