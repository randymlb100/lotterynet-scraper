-- Purpose:
-- Notify Render to drop in-memory results caches whenever Supabase snapshots change.
-- This keeps Android clients on snapshot-first paths without forcing repeated cache polls.
--
-- Before running:
-- 1. Replace __RENDER_URL__ with your Render base URL (no trailing slash).
-- 2. Ensure the pg_net extension is enabled.

create extension if not exists pg_net;

drop trigger if exists lotterynet_render_cache_invalidate_results on public.lotterynet_kv;

create trigger lotterynet_render_cache_invalidate_results
after insert or update or delete
on public.lotterynet_kv
for each row
when (
  coalesce(new.key, old.key) like 'lot_results_cache_by_day:%'
  or coalesce(new.key, old.key) like 'pick_results_cache_by_day:%'
  or coalesce(new.key, old.key) like 'manual_results_overrides_by_day:%'
)
execute function supabase_functions.http_request(
  '__RENDER_URL__/internal/supabase-cache-invalidate',
  'POST',
  '{"Content-Type":"application/json"}',
  '{}',
  '5000'
);

-- Optional check: see recent webhook requests after changes happen.
-- select * from net._http_response order by id desc limit 20;
