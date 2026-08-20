-- Expand the bounded condition arrays for the larger technical indicator catalog.
alter table public.screening_preferences
drop constraint if exists manual_condition_limit;
alter table public.screening_preferences
add constraint manual_condition_limit
check (jsonb_array_length(manual_conditions) <= 128);

alter table public.screening_preferences
drop constraint if exists expectation_manual_condition_limit;
alter table public.screening_preferences
add constraint expectation_manual_condition_limit
check (jsonb_array_length(expectation_manual_conditions) <= 128);
