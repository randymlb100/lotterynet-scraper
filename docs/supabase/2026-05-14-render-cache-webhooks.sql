-- Purpose:
-- Notify Render to drop in-memory results caches whenever Supabase snapshots change.
-- This keeps Android clients on snapshot-first paths without forcing repeated cache polls.
--
-- Before running:
-- 1. Replace __RENDER_URL__ with your Render base URL (no trailing slash).
-- 2. Replace __WEBHOOK_SECRET__ with LOTTERYNET_ADMIN_SHARED_SECRET from Render.
-- 3. Ensure the pg_net extension is enabled.

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

-- Optional check: see recent webhook requests after changes happen.
-- select * from net._http_response order by id desc limit 20;
