-- Adds what the admin panel needs: an email on staff_profiles (so the
-- staff list doesn't need a separate admin-API call to auth.users), and
-- backfills it for any staff created before this migration.

alter table public.staff_profiles add column if not exists email text;

update public.staff_profiles sp
set email = u.email
from auth.users u
where sp.id = u.id and sp.email is null;

-- Keep handle_new_user() in sync so future signups populate email too.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.staff_profiles (id, full_name, email)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)),
    new.email
  )
  on conflict (id) do update set email = excluded.email;
  return new;
end;
$$;
