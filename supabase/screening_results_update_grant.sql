-- StockAI: allow service-role upserts into per-user screening results.
-- Rerunnable. No rows are changed or deleted.

grant select, insert, update, delete
on table public.screening_results
to service_role;
