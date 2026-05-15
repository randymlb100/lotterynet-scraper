-- LotteryNet Supabase cutover
-- Run this in Supabase SQL Editor after replacing the placeholders below.
--
-- Required replacements:
--   __RENDER_URL__ -> your Render base URL without trailing slash
--   __WEBHOOK_SECRET__ -> LOTTERYNET_ADMIN_SHARED_SECRET from Render
--
-- This script does two things:
-- 1. enables narrow Realtime replication for the tables the app listens to
-- 2. installs a database webhook that tells Render to drop stale in-memory results caches

do $$
begin
  if exists (
    select 1
    from pg_publication
    where pubname = 'supabase_realtime'
  ) then
    if exists (
      select 1
      from information_schema.tables
      where table_schema = 'public' and table_name = 'lotterynet_users_state'
    ) and not exists (
      select 1
      from pg_publication_tables
      where pubname = 'supabase_realtime'
        and schemaname = 'public'
        and tablename = 'lotterynet_users_state'
    ) then
      alter publication supabase_realtime add table public.lotterynet_users_state;
    end if;

    if exists (
      select 1
      from information_schema.tables
      where table_schema = 'public' and table_name = 'lotterynet_master_state'
    ) and not exists (
      select 1
      from pg_publication_tables
      where pubname = 'supabase_realtime'
        and schemaname = 'public'
        and tablename = 'lotterynet_master_state'
    ) then
      alter publication supabase_realtime add table public.lotterynet_master_state;
    end if;

    if exists (
      select 1
      from information_schema.tables
      where table_schema = 'public' and table_name = 'lotterynet_tickets_by_owner'
    ) and not exists (
      select 1
      from pg_publication_tables
      where pubname = 'supabase_realtime'
        and schemaname = 'public'
        and tablename = 'lotterynet_tickets_by_owner'
    ) then
      alter publication supabase_realtime add table public.lotterynet_tickets_by_owner;
    end if;

    if exists (
      select 1
      from information_schema.tables
      where table_schema = 'public' and table_name = 'lotterynet_kv'
    ) and not exists (
      select 1
      from pg_publication_tables
      where pubname = 'supabase_realtime'
        and schemaname = 'public'
        and tablename = 'lotterynet_kv'
    ) then
      alter publication supabase_realtime add table public.lotterynet_kv;
    end if;
  else
    raise exception 'Publication supabase_realtime does not exist in this project';
  end if;
end $$;

create extension if not exists pg_net;

drop trigger if exists lotterynet_render_cache_invalidate_results on public.lotterynet_kv;
drop trigger if exists lotterynet_render_cache_invalidate_results_write on public.lotterynet_kv;
drop trigger if exists lotterynet_render_cache_invalidate_results_delete on public.lotterynet_kv;

create trigger lotterynet_render_cache_invalidate_results_write
after insert or update
on public.lotterynet_kv
for each row
when (
  new.key like 'lot_results_cache_by_day:%'
  or new.key like 'pick_results_cache_by_day:%'
  or new.key like 'manual_results_overrides_by_day:%'
)
execute function supabase_functions.http_request(
  '__RENDER_URL__/internal/supabase-cache-invalidate',
  'POST',
  '{"Content-Type":"application/json","x-lotterynet-admin-secret":"__WEBHOOK_SECRET__"}',
  '{}',
  '5000'
);

create trigger lotterynet_render_cache_invalidate_results_delete
after delete
on public.lotterynet_kv
for each row
when (
  old.key like 'lot_results_cache_by_day:%'
  or old.key like 'pick_results_cache_by_day:%'
  or old.key like 'manual_results_overrides_by_day:%'
)
execute function supabase_functions.http_request(
  '__RENDER_URL__/internal/supabase-cache-invalidate',
  'POST',
  '{"Content-Type":"application/json","x-lotterynet-admin-secret":"__WEBHOOK_SECRET__"}',
  '{}',
  '5000'
);

select schemaname, tablename
from pg_publication_tables
where pubname = 'supabase_realtime'
  and schemaname = 'public'
  and tablename in (
    'lotterynet_users_state',
    'lotterynet_master_state',
    'lotterynet_tickets_by_owner',
    'lotterynet_kv'
  )
order by tablename;

-- Optional:
-- select * from net._http_response order by id desc limit 20;
