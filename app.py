import datetime
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, Response, copy_current_request_context, g, jsonify, request
from flask_cors import CORS

from scraper.scrape_and_save import (
    SUPABASE_KEY,
    SUPABASE_URL,
    fetch_existing_from_supabase,
    get_dr_date_str,
    pick_results_cache_key,
    save_to_supabase,
    save_us_picks_to_supabase,
    scrape,
    scrape_us_picks,
)

app = Flask(__name__)
CORS(app)
port = int(os.environ.get("PORT", 5000))
SCRAPE_CACHE_TTL_SECONDS = int(os.environ.get("SCRAPE_CACHE_TTL_SECONDS", "120"))
LIVE_RESPONSE_CACHE_TTL_SECONDS = int(os.environ.get("LIVE_RESPONSE_CACHE_TTL_SECONDS", "5"))
PICK_BACKGROUND_REFRESH_MIN_INTERVAL_SECONDS = int(os.environ.get("PICK_BACKGROUND_REFRESH_MIN_INTERVAL_SECONDS", "30"))

_scrape_cache = {}
_pick_scrape_cache = {}
_live_system_results_cache = {}
_manual_override_cache = {}
_lottery_refresh_lock = threading.Lock()
_lottery_refresh_inflight = set()
_pick_refresh_lock = threading.Lock()
_pick_refresh_inflight = set()
_pick_refresh_last_started = {}
ADMIN_ROLES = {"admin", "master"}
USERS_STATE_KEY = "sys_users_v4"
_supabase_cache = {}
_CACHE_TTL_SECONDS = 300
INTERNAL_SHARED_SECRET = os.environ.get("LOTTERYNET_ADMIN_SHARED_SECRET", "").strip()
PUBLIC_CACHE_INVALIDATION_PREFIXES = (
    "lot_results_cache_by_day:",
    "pick_results_cache_by_day:",
    "manual_results_overrides_by_day:",
)


def json_utf8(data, status=200):
    return Response(
        json.dumps(data, ensure_ascii=False),
        status=status,
        content_type="application/json; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*",
        },
    )


def normalize_result_row(row):
    number = str(row.get("number", "")).strip()
    name = str(row.get("name", "")).strip()
    game = str(row.get("game", "")).lower().replace("-", "")
    out = {
        "id": str(row.get("id", "")).strip(),
        "name": name,
        "date": str(row.get("date", "")).strip(),
        "number": number,
    }
    normalized_name = name.lower()
    if game == "pick3" or "pick 3" in normalized_name:
        out["pick3"] = number
    if game == "pick4" or "pick 4" in normalized_name:
        out["pick4"] = number
    for key in (
        "status", "source", "firstSeenAt", "lastSeenAt",
        "state", "stateCode", "game", "gameName", "draw", "playTypes",
        "backfilled", "noDrawReason", "isManualOverride",
        "manualEditedBy", "manualEditedAt",
    ):
        value = row.get(key)
        if value is not None and value != "":
            out[key] = value
    if "backfilled" in out:
        out["isBackfilled"] = bool(out["backfilled"])
    return out


def normalize_pick_row(row):
    normalized = normalize_result_row(row)
    game = str(row.get("game", "")).lower().replace("-", "")
    game_name = str(row.get("gameName", "")).strip()
    if not game_name and game:
        game_name = "Pick 4" if game == "pick4" else "Pick 3"
    draw = str(row.get("draw", "")).strip()
    state = str(row.get("state", "")).strip()
    if state or game_name or draw:
        normalized["name"] = " ".join(part for part in [state, game_name, draw] if part)
    return normalized


def unique_sorted_results(rows):
    by_id = {}
    for row in rows:
        normalized = normalize_result_row(row)
        if not normalized["id"]:
            continue
        by_id[normalized["id"]] = normalized
    return sorted(by_id.values(), key=lambda item: (0, int(item["id"])) if item["id"].isdigit() else (1, item["id"]))


def unique_sorted_pick_results(rows):
    by_id = {}
    for row in rows:
        normalized = normalize_pick_row(row)
        if normalized["id"]:
            by_id[normalized["id"]] = normalized
    return sorted(by_id.values(), key=lambda item: item["id"])


def is_pick_result_row(row):
    row_id = str(row.get("id", "")).upper()
    name = str(row.get("name", "")).lower()
    game = str(row.get("game", "")).lower().replace("-", "")
    return (
        row_id.startswith("US-P3-") or
        row_id.startswith("US-P4-") or
        bool(row.get("pick3")) or
        bool(row.get("pick4")) or
        game in {"pick3", "pick4"} or
        "pick 3" in name or
        "pick 4" in name
    )


def utc_now_iso():
    return datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")


def fetch_supabase_results_cache(cache_key):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    params = urllib.parse.urlencode({"key": f"eq.{cache_key}", "select": "value"})
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/lotterynet_kv?{params}",
        headers={
            "Accept": "application/json",
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        },
    )
    try:
        raw = urllib.request.urlopen(req, timeout=5).read().decode("utf-8")
        rows = json.loads(raw)
        value = rows[0].get("value") if rows else []
        if isinstance(value, str):
            value = json.loads(value)
        if isinstance(value, dict):
            value = value.get("results") or value.get("rows") or []
        return value if isinstance(value, list) else []
    except Exception:
        return []


def fetch_supabase_results_cache_cached(cache_key):
    now = time.monotonic()
    entry = _supabase_cache.get(cache_key)
    if entry is not None:
        value, ts = entry
        if now - ts < _CACHE_TTL_SECONDS:
            return value
    result = fetch_supabase_results_cache(cache_key)
    _supabase_cache[cache_key] = (result, now)
    return result


def cache_results_snapshot(cache_key, rows):
    _supabase_cache[cache_key] = (rows if isinstance(rows, list) else [], time.monotonic())


def invalidate_results_cache_key(cache_key):
    if not cache_key:
        return
    _supabase_cache.pop(cache_key, None)
    if ":" in cache_key:
        date_key = cache_key.split(":", 1)[1]
        if is_public_cache_invalidation_key(cache_key):
            _manual_override_cache.pop(date_key, None)
        keys_to_delete = [
            key for key in _live_system_results_cache
            if (
                isinstance(key, tuple) and key and key[0] == date_key
            ) or (
                isinstance(key, str) and key.startswith(f"{date_key}:")
            )
        ]
        for live_key in keys_to_delete:
            _live_system_results_cache.pop(live_key, None)


def is_internal_secret_valid(request_obj):
    if not INTERNAL_SHARED_SECRET:
        return False
    provided = (request_obj.headers.get("x-lotterynet-admin-secret") or "").strip()
    return provided == INTERNAL_SHARED_SECRET


def is_public_cache_invalidation_key(cache_key):
    return any(cache_key.startswith(prefix) for prefix in PUBLIC_CACHE_INVALIDATION_PREFIXES)


def load_cached_sections(target_date):
    lottery_cache = fetch_supabase_results_cache_cached(f"lot_results_cache_by_day:{target_date}")
    pick_cache = fetch_supabase_results_cache_cached(f"pick_results_cache_by_day:{target_date}")
    legacy_lottery_rows, legacy_pick_rows = split_lottery_and_pick_rows(lottery_cache)
    pick_rows = pick_cache or legacy_pick_rows
    return unique_sorted_results(legacy_lottery_rows), unique_sorted_pick_results(pick_rows)


def load_pick_only_cached(target_date):
    pick_cache = fetch_supabase_results_cache_cached(f"pick_results_cache_by_day:{target_date}")
    if pick_cache:
        return unique_sorted_pick_results(pick_cache)
    lottery_cache = fetch_supabase_results_cache_cached(f"lot_results_cache_by_day:{target_date}")
    _, legacy_pick_rows = split_lottery_and_pick_rows(lottery_cache)
    return unique_sorted_pick_results(legacy_pick_rows)


def load_lottery_only_cached(target_date):
    lottery_cache = fetch_supabase_results_cache_cached(f"lot_results_cache_by_day:{target_date}")
    legacy_lottery_rows, _ = split_lottery_and_pick_rows(lottery_cache)
    return unique_sorted_results(legacy_lottery_rows)


def split_lottery_and_pick_rows(rows):
    lottery_rows = []
    pick_rows = []
    for row in rows or []:
        if is_pick_result_row(row):
            pick_rows.append(row)
        else:
            lottery_rows.append(row)
    return lottery_rows, pick_rows


def should_use_live_scrape():
    return request.args.get("live") == "1"


def scrape_cached(date_key):
    now = time.time()
    cached = _scrape_cache.get(date_key)
    if cached and now - cached["stored_at"] < SCRAPE_CACHE_TTL_SECONDS:
        return cached["rows"]
    rows = scrape(date_key)
    _scrape_cache[date_key] = {"stored_at": now, "rows": rows}
    return rows


def set_lottery_scrape_cache(date_key, rows):
    _scrape_cache[date_key] = {"stored_at": time.time(), "rows": rows}


def refresh_lottery_cache_async(date_key):
    try:
        rows = unique_sorted_results(scrape(date_key))
        set_lottery_scrape_cache(date_key, rows)
        if rows and SUPABASE_KEY.strip():
            save_to_supabase(date_key, rows)
    except Exception as error:
        print(f"Warning: background lottery refresh failed for {date_key}: {error}")
    finally:
        with _lottery_refresh_lock:
            _lottery_refresh_inflight.discard(date_key)


def schedule_background_lottery_refresh(date_key):
    with _lottery_refresh_lock:
        if date_key in _lottery_refresh_inflight:
            return False
        _lottery_refresh_inflight.add(date_key)
    thread = threading.Thread(
        target=refresh_lottery_cache_async,
        args=(date_key,),
        daemon=True,
        name=f"lottery-refresh-{date_key}",
    )
    thread.start()
    return True


def set_live_served_from_flag(section, value):
    try:
        setattr(g, f"{section}_live_served_from", value)
    except RuntimeError:
        return


def get_live_served_from_flag(section):
    try:
        return getattr(g, f"{section}_live_served_from", "")
    except RuntimeError:
        return ""


def get_fresh_live_system_results_cache(date_key, mode):
    cache_key = f"{date_key}:{mode}"
    cached = _live_system_results_cache.get(cache_key)
    if not cached:
        return None
    if time.time() - cached["stored_at"] >= LIVE_RESPONSE_CACHE_TTL_SECONDS:
        return None
    return cached["payload"]


def set_live_system_results_cache(date_key, mode, payload):
    _live_system_results_cache[f"{date_key}:{mode}"] = {
        "stored_at": time.time(),
        "payload": payload,
    }
    if mode == "both":
        if "lotteries" in payload:
            _live_system_results_cache[f"{date_key}:lottery"] = {
                "stored_at": time.time(),
                "payload": {
                    "date": payload["date"],
                    "mode": "lottery",
                    "source": payload.get("source", "live-scraper"),
                    "generatedAt": payload.get("generatedAt"),
                    "lotteries": payload["lotteries"],
                },
            }
        if "picks" in payload:
            _live_system_results_cache[f"{date_key}:pick"] = {
                "stored_at": time.time(),
                "payload": {
                    "date": payload["date"],
                    "mode": "pick",
                    "source": payload.get("source", "live-scraper"),
                    "generatedAt": payload.get("generatedAt"),
                    "picks": payload["picks"],
                },
            }


def get_composed_live_system_results_cache(date_key, mode):
    cached_payload = get_fresh_live_system_results_cache(date_key, mode)
    if cached_payload is not None:
        cached_copy = dict(cached_payload)
        cached_copy["servedFrom"] = "response-cache"
        return cached_copy
    if mode != "both":
        return None
    cached_lottery = get_fresh_live_system_results_cache(date_key, "lottery")
    cached_pick = get_fresh_live_system_results_cache(date_key, "pick")
    if cached_lottery is None or cached_pick is None:
        return None
    return {
        "date": date_key,
        "mode": "both",
        "source": "live-scraper",
        "servedFrom": "section-cache",
        "generatedAt": max(
            str(cached_lottery.get("generatedAt") or ""),
            str(cached_pick.get("generatedAt") or ""),
        ),
        "lotteries": cached_lottery["lotteries"],
        "picks": cached_pick["picks"],
    }


def live_served_from(date_key, mode, lottery_rows, pick_rows):
    if mode == "lottery":
        return get_live_served_from_flag("lottery") or "inline-scrape"
    if mode == "pick":
        return get_live_served_from_flag("pick") or "inline-scrape"
    if mode == "both":
        lottery_served_from = get_live_served_from_flag("lottery") or "inline-scrape"
        pick_served_from = get_live_served_from_flag("pick") or "inline-scrape"
        if lottery_served_from == "supabase-snapshot" and pick_served_from == "supabase-snapshot":
            return "supabase-snapshot"
        if "section-cache" in (lottery_served_from, pick_served_from):
            return "section-cache"
        return "inline-scrape"
    return "inline-scrape"


def log_live_request(date_key, mode, served_from, started_at):
    duration_ms = round((time.perf_counter() - started_at) * 1000, 1)
    print(
        f"Results live request date={date_key} mode={mode} servedFrom={served_from} durationMs={duration_ms}"
    )


def set_pick_scrape_cache(date_key, rows):
    normalized = unique_sorted_pick_results(rows)
    _pick_scrape_cache[date_key] = {"stored_at": time.time(), "rows": normalized}
    for game_filter in ("pick3", "pick4"):
        filtered = [row for row in normalized if row.get("game") == game_filter]
        _pick_scrape_cache[f"{date_key}:{game_filter}"] = {"stored_at": time.time(), "rows": filtered}


def refresh_pick_cache_async(date_key):
    try:
        existing_rows = fetch_pick_rows_from_supabase(date_key)
        rows = unique_sorted_pick_results(scrape_us_picks(date_key, existing_rows=existing_rows))
        set_pick_scrape_cache(date_key, rows)
        if rows and SUPABASE_KEY.strip():
            save_us_picks_to_supabase(date_key, rows)
    except Exception as error:
        print(f"Warning: background pick refresh failed for {date_key}: {error}")
    finally:
        with _pick_refresh_lock:
            _pick_refresh_inflight.discard(date_key)


def schedule_background_pick_refresh(date_key):
    with _pick_refresh_lock:
        now = time.time()
        if date_key in _pick_refresh_inflight:
            return False
        last_started = _pick_refresh_last_started.get(date_key, 0)
        if now - last_started < PICK_BACKGROUND_REFRESH_MIN_INTERVAL_SECONDS:
            return False
        _pick_refresh_inflight.add(date_key)
        _pick_refresh_last_started[date_key] = now
    thread = threading.Thread(
        target=refresh_pick_cache_async,
        args=(date_key,),
        daemon=True,
        name=f"pick-refresh-{date_key}",
    )
    thread.start()
    return True


def pick_scrape_cached(date_key, existing_rows=None):
    now = time.time()
    cached = _pick_scrape_cache.get(date_key)
    if cached and now - cached["stored_at"] < SCRAPE_CACHE_TTL_SECONDS:
        return cached["rows"]
    rows = scrape_us_picks(date_key, existing_rows=existing_rows)
    _pick_scrape_cache[date_key] = {"stored_at": now, "rows": rows}
    return rows


def pick_scrape_cached_for_game(date_key, game_filter, existing_rows=None):
    if game_filter not in ("pick3", "pick4"):
        return pick_scrape_cached(date_key, existing_rows=existing_rows)
    cache_key = f"{date_key}:{game_filter}"
    now = time.time()
    cached = _pick_scrape_cache.get(cache_key)
    if cached and now - cached["stored_at"] < SCRAPE_CACHE_TTL_SECONDS:
        return cached["rows"]
    rows = scrape_us_picks(date_key, games=(game_filter,), existing_rows=existing_rows)
    _pick_scrape_cache[cache_key] = {"stored_at": now, "rows": rows}
    return rows


def get_fresh_pick_cache(date_key, game_filter=""):
    cache_key = f"{date_key}:{game_filter}" if game_filter in ("pick3", "pick4") else date_key
    cached = _pick_scrape_cache.get(cache_key)
    if not cached:
        return []
    if time.time() - cached["stored_at"] >= SCRAPE_CACHE_TTL_SECONDS:
        return []
    return cached["rows"]


def lottery_rows_for_request_date(date_key):
    if should_use_live_scrape():
        cached_lottery_rows, _ = split_lottery_and_pick_rows(fetch_existing_from_supabase(date_key))
        cached_lottery_rows = unique_sorted_results(cached_lottery_rows)
        if cached_lottery_rows and date_key == get_dr_date_str():
            set_live_served_from_flag("lottery", "supabase-snapshot")
            schedule_background_lottery_refresh(date_key)
            return cached_lottery_rows
        set_live_served_from_flag("lottery", "inline-scrape")
        return unique_sorted_results(scrape_cached(date_key))
    lottery_rows, _ = split_lottery_and_pick_rows(fetch_existing_from_supabase(date_key))
    return apply_manual_overrides(date_key, unique_sorted_results(lottery_rows), include_pick=False)


def fetch_pick_rows_from_supabase(date_key):
    if not SUPABASE_KEY.strip():
        return []
    params = urllib.parse.urlencode({"key": f"eq.{pick_results_cache_key(date_key)}", "select": "value"})
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/lotterynet_kv?{params}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        rows = json.loads(resp.read().decode("utf-8"))
        if rows and rows[0].get("value"):
            value = rows[0]["value"]
            if isinstance(value, str):
                value = json.loads(value)
            if isinstance(value, list):
                return value
    except Exception as error:
        print(f"Warning: could not fetch pick cache: {error}")
    return []


def pick_rows_for_request_date(date_key, game_filter="", allow_combined_fallback=False):
    if should_use_live_scrape():
        if date_key == get_dr_date_str():
            fresh_cached_rows = get_fresh_pick_cache(date_key, game_filter)
            if fresh_cached_rows:
                set_live_served_from_flag("pick", "section-cache")
                return unique_sorted_pick_results(fresh_cached_rows)
        existing_rows = fetch_pick_rows_from_supabase(date_key)
        if existing_rows and date_key == get_dr_date_str():
            set_pick_scrape_cache(date_key, existing_rows)
            set_live_served_from_flag("pick", "supabase-snapshot")
            schedule_background_pick_refresh(date_key)
            rows = existing_rows
        else:
            set_live_served_from_flag("pick", "inline-scrape")
            rows = pick_scrape_cached_for_game(date_key, game_filter, existing_rows=existing_rows)
            if rows and SUPABASE_KEY.strip():
                try:
                    save_us_picks_to_supabase(date_key, unique_sorted_pick_results(rows))
                except Exception as error:
                    print(f"Warning: could not save live pick refresh: {error}")
    else:
        rows = fetch_pick_rows_from_supabase(date_key)
        if not rows and allow_combined_fallback:
            _, rows = split_lottery_and_pick_rows(fetch_existing_from_supabase(date_key))
    if game_filter in ("pick3", "pick4"):
        rows = [row for row in rows if row.get("game") == game_filter]
    return apply_manual_overrides(date_key, unique_sorted_pick_results(rows), include_pick=True)


def results_for_request():
    date_key = request.args.get("date") or get_dr_date_str()
    name_filter = (request.args.get("name") or request.args.get("lottery") or "").strip().lower()
    if should_use_live_scrape():
        lottery_rows, pick_rows = live_results_sections_for_date(date_key)
    else:
        lottery_rows = lottery_rows_for_request_date(date_key)
        pick_rows = pick_rows_for_request_date(date_key, allow_combined_fallback=True)
    rows = unique_sorted_results(lottery_rows + pick_rows)
    if name_filter:
        rows = [row for row in rows if name_filter in row["name"].lower()]
    return date_key, rows


def pick_results_for_request():
    date_key = request.args.get("date") or get_dr_date_str()
    state_filter = (request.args.get("state") or "").strip().lower()
    game_filter = (request.args.get("game") or "").strip().lower().replace("-", "")
    rows = pick_rows_for_request_date(date_key, game_filter)
    if state_filter:
        rows = [
            row for row in rows
            if state_filter in str(row.get("state", "")).lower()
            or state_filter == str(row.get("stateCode", "")).lower()
        ]
    if game_filter in ("pick3", "pick4"):
        rows = [row for row in rows if row.get("game") == game_filter]
    return date_key, rows


def live_results_sections_for_date(date_key, include_lottery=True, include_pick=True, game_filter=""):
    tasks = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        if include_lottery:
            lottery_fetch = copy_current_request_context(lambda: lottery_rows_for_request_date(date_key))
            tasks["lottery"] = executor.submit(lottery_fetch)
        if include_pick:
            pick_fetch = copy_current_request_context(lambda: pick_rows_for_request_date(date_key, game_filter))
            tasks["pick"] = executor.submit(pick_fetch)
    lottery_rows = tasks["lottery"].result() if "lottery" in tasks else []
    pick_rows = tasks["pick"].result() if "pick" in tasks else []
    return lottery_rows, pick_rows


# --- Manual overrides ---

def manual_results_override_cache_key(date_key):
    return f"manual_results_overrides_by_day:{date_key}"


def get_cached_manual_overrides(date_key):
    cached = _manual_override_cache.get(date_key)
    if not cached:
        return None
    if time.time() - cached["stored_at"] >= SCRAPE_CACHE_TTL_SECONDS:
        return None
    return cached["rows"]


def set_cached_manual_overrides(date_key, rows):
    _manual_override_cache[date_key] = {
        "stored_at": time.time(),
        "rows": rows,
    }


def fetch_manual_overrides_from_supabase(date_key):
    cached = get_cached_manual_overrides(date_key)
    if cached is not None:
        return cached
    if not SUPABASE_KEY.strip():
        return []
    params = urllib.parse.urlencode({"key": f"eq.{manual_results_override_cache_key(date_key)}", "select": "value"})
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/lotterynet_kv?{params}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        rows = json.loads(resp.read().decode("utf-8"))
        if rows and rows[0].get("value"):
            value = rows[0]["value"]
            if isinstance(value, str):
                value = json.loads(value)
            if isinstance(value, list):
                normalized = [normalize_manual_override_row(row, date_key) for row in value if row]
                set_cached_manual_overrides(date_key, normalized)
                return normalized
    except Exception as error:
        print(f"Warning: could not fetch manual overrides: {error}")
    return []


def save_manual_overrides_to_supabase(date_key, rows):
    normalized_rows = [normalize_manual_override_row(row, date_key) for row in rows if row]
    set_cached_manual_overrides(date_key, normalized_rows)
    if not SUPABASE_KEY.strip():
        return
    value = json.dumps(normalized_rows, ensure_ascii=False)
    payload = json.dumps({
        "key": manual_results_override_cache_key(date_key),
        "value": value,
        "upd": utc_now_iso(),
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/lotterynet_kv",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Prefer": "resolution=merge-duplicates",
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=15)


def normalize_manual_override_row(row, date_key):
    normalized = dict(row)
    normalized["id"] = str(row.get("id") or row.get("resultId") or "").strip()
    normalized["name"] = str(row.get("name") or "").strip()
    normalized["date"] = str(row.get("date") or date_key).strip() or date_key
    normalized["number"] = str(row.get("number") or "").strip()
    normalized["game"] = str(row.get("game") or "").strip().lower().replace("-", "")
    normalized["source"] = "manual-override"
    normalized["status"] = "published"
    normalized["isManualOverride"] = True
    normalized["backfilled"] = False
    edited_by = str(row.get("editedBy") or row.get("manualEditedBy") or "").strip()
    edited_at = str(row.get("editedAt") or row.get("manualEditedAt") or utc_now_iso()).strip()
    if edited_by:
        normalized["editedBy"] = edited_by
        normalized["manualEditedBy"] = edited_by
    normalized["editedAt"] = edited_at
    normalized["manualEditedAt"] = edited_at
    if normalized["game"] == "pick3":
        normalized["pick3"] = normalized["number"]
        normalized.pop("pick4", None)
    elif normalized["game"] == "pick4":
        normalized["pick4"] = normalized["number"]
        normalized.pop("pick3", None)
    return normalized


def manual_override_is_pick(row):
    game = str(row.get("game", "")).lower().replace("-", "")
    row_id = str(row.get("id", "")).upper()
    name = str(row.get("name", "")).lower()
    return game in {"pick3", "pick4"} or row_id.startswith("US-P3-") or row_id.startswith("US-P4-") or row_id in {"19", "20", "21", "22"} or "pick 3" in name or "pick 4" in name


def normalize_override_number(raw_number):
    digits = [part for part in str(raw_number or "").split("-") if part != ""]
    return "-".join(digits)


def resolved_row_number(row):
    if row.get("pick4"):
        return normalize_override_number(row.get("pick4"))
    if row.get("pick3"):
        return normalize_override_number(row.get("pick3"))
    if row.get("number"):
        return normalize_override_number(row.get("number"))
    classic = [str(row.get("first", "")).strip(), str(row.get("second", "")).strip(), str(row.get("third", "")).strip()]
    classic = [value for value in classic if value]
    if classic:
        return "-".join(classic)
    return ""


def row_has_published_number(row):
    if str(row.get("status", "")).strip().lower() == "no_draw":
        return False
    return bool(resolved_row_number(row))


def validate_override_number(number, game):
    if game == "pick3":
        return bool(re.match(r"^\d-\d-\d$", number))
    if game == "pick4":
        return bool(re.match(r"^\d-\d-\d-\d$", number))
    return bool(re.match(r"^\d{2}-\d{2}-\d{2}$", number))


def apply_manual_overrides(date_key, rows, include_pick):
    overrides = fetch_manual_overrides_from_supabase(date_key)
    if not overrides:
        return rows
    filtered_overrides = [row for row in overrides if manual_override_is_pick(row) == include_pick]
    if not filtered_overrides:
        return rows
    by_id = {str(row.get("id", "")).strip(): dict(row) for row in rows if str(row.get("id", "")).strip()}
    override_map = {str(row.get("id", "")).strip(): normalize_manual_override_row(row, date_key) for row in filtered_overrides}
    remaining_overrides = {str(row.get("id", "")).strip(): normalize_manual_override_row(row, date_key) for row in overrides}
    changed = False
    for result_id, override in override_map.items():
        current = by_id.get(result_id)
        if current and row_has_published_number(current):
            current_number = resolved_row_number(current)
            if current_number == normalize_override_number(override.get("number")):
                remaining_overrides.pop(result_id, None)
                changed = True
            else:
                remaining_overrides.pop(result_id, None)
                changed = True
            continue
        by_id[result_id] = normalize_pick_row(override) if include_pick else normalize_result_row(override)
    if changed:
        save_manual_overrides_to_supabase(date_key, list(remaining_overrides.values()))
    return unique_sorted_pick_results(by_id.values()) if include_pick else unique_sorted_results(by_id.values())


def request_json_body():
    return request.get_json(silent=True) or {}


def is_admin_role(value):
    return str(value or "").strip().lower() in ADMIN_ROLES


# --- Users state ---

def fetch_users_state_from_supabase():
    if not SUPABASE_KEY.strip():
        return None
    params = urllib.parse.urlencode({"scope": "eq.global", "select": "payload"})
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/lotterynet_users_state?{params}",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        },
    )
    resp = urllib.request.urlopen(req, timeout=8)
    rows = json.loads(resp.read().decode("utf-8"))
    value = rows[0].get("payload") if rows else None
    if isinstance(value, str):
        value = json.loads(value)
    return value if isinstance(value, dict) else None


def save_users_state_to_supabase(payload):
    if not SUPABASE_KEY.strip():
        raise RuntimeError("SUPABASE_KEY is not configured")
    body = json.dumps({
        "scope": "global",
        "payload": payload,
        "updated_at": utc_now_iso(),
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/lotterynet_users_state?on_conflict=scope",
        data=body,
        headers={
            "Content-Type": "application/json",
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Prefer": "resolution=merge-duplicates",
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=15)


# --- Routes: API v1 ---

@app.route("/api/v1/health", methods=["GET"])
@app.route("/api/v1/", methods=["GET"])
def api_v1_root():
    return jsonify({"ok": True, "service": "lotterynet-results", "version": "v1"})


@app.route("/api/v1/results", methods=["GET"])
def api_v1_results():
    date_key, rows = results_for_request()
    return json_utf8({
        "date": date_key,
        "count": len(rows),
        "source": "live-scraper" if should_use_live_scrape() else ("supabase-cache" if rows else "cache-miss"),
        "generatedAt": utc_now_iso(),
        "results": rows,
    })


@app.route("/api/v1/results/lottery", methods=["GET"])
def api_v1_results_lottery():
    date_key = request.args.get("date") or get_dr_date_str()
    lottery_rows = lottery_rows_for_request_date(date_key)
    return json_utf8({
        "date": date_key,
        "section": "lotteries",
        "count": len(lottery_rows),
        "source": "live-scraper" if should_use_live_scrape() else ("supabase-cache" if lottery_rows else "cache-miss"),
        "generatedAt": utc_now_iso(),
        "results": lottery_rows,
    })


@app.route("/api/v1/results/picks", methods=["GET"])
def api_v1_results_picks():
    date_key, rows = pick_results_for_request()
    return json_utf8({
        "date": date_key,
        "section": "picks",
        "count": len(rows),
        "source": "live-scraper" if should_use_live_scrape() else ("supabase-cache" if rows else "cache-miss"),
        "generatedAt": utc_now_iso(),
        "results": rows,
    })


@app.route("/api/v1/scrape", methods=["GET", "POST"])
def api_v1_scrape():
    date_key = request.args.get("date") or get_dr_date_str()
    lottery_rows = unique_sorted_results(scrape_cached(date_key))
    pick_rows = unique_sorted_pick_results(pick_scrape_cached(date_key))
    rows = unique_sorted_results(lottery_rows + pick_rows)
    if not SUPABASE_KEY.strip():
        return json_utf8({
            "date": date_key,
            "count": len(rows),
            "saved": False,
            "error": "SUPABASE_KEY is not configured",
            "results": rows,
        }, status=503)
    try:
        save_to_supabase(date_key, lottery_rows)
        save_us_picks_to_supabase(date_key, pick_rows)
        cache_results_snapshot(f"lot_results_cache_by_day:{date_key}", lottery_rows)
        cache_results_snapshot(f"pick_results_cache_by_day:{date_key}", pick_rows)
    except Exception as error:
        return json_utf8({
            "date": date_key,
            "count": len(rows),
            "saved": False,
            "error": str(error),
            "results": rows,
        }, status=500)
    return json_utf8({
        "date": date_key,
        "count": len(rows),
        "saved": True,
        "results": rows,
    })


@app.route("/api/v1/scrape/picks", methods=["GET", "POST"])
def api_v1_scrape_picks():
    date_key = request.args.get("date") or get_dr_date_str()
    pick_rows = unique_sorted_pick_results(pick_scrape_cached(date_key))
    if not SUPABASE_KEY.strip():
        return json_utf8({
            "date": date_key,
            "section": "picks",
            "count": len(pick_rows),
            "saved": False,
            "error": "SUPABASE_KEY is not configured",
            "results": pick_rows,
        }, status=503)
    try:
        save_us_picks_to_supabase(date_key, pick_rows)
        cache_results_snapshot(f"pick_results_cache_by_day:{date_key}", pick_rows)
    except Exception as error:
        return json_utf8({
            "date": date_key,
            "count": len(pick_rows),
            "saved": False,
            "error": str(error),
            "results": pick_rows,
        }, status=500)
    return json_utf8({
        "date": date_key,
        "section": "picks",
        "count": len(pick_rows),
        "saved": True,
        "results": pick_rows,
    })


# --- Routes: Legacy / existing ---

@app.route("/", methods=["GET"])
def all_results():
    if not request.args.get("date") and not request.args.get("live"):
        return jsonify({"ok": True, "service": "lotterynet-results"})
    _, rows = results_for_request()
    return json_utf8(rows)


@app.route("/results", methods=["GET"])
def results_with_metadata():
    date_key, rows = results_for_request()
    return json_utf8({
        "date": date_key,
        "count": len(rows),
        "source": "live-scraper" if should_use_live_scrape() else ("supabase-cache" if rows else "cache-miss"),
        "generatedAt": utc_now_iso(),
        "results": rows,
    })


@app.route("/pick-results", methods=["GET"])
def pick_results_with_metadata():
    date_key, rows = pick_results_for_request()
    return json_utf8({
        "date": date_key,
        "section": "picks",
        "count": len(rows),
        "source": "live-scraper" if should_use_live_scrape() else ("supabase-cache" if rows else "cache-miss"),
        "generatedAt": utc_now_iso(),
        "results": rows,
    })


@app.route("/system-results", methods=["GET"])
def system_results():
    started_at = time.perf_counter()
    mode = (request.args.get("mode") or "lottery").strip().lower()
    if mode not in ("lottery", "pick", "both"):
        mode = "lottery"
    date_key = request.args.get("date") or get_dr_date_str()
    if should_use_live_scrape() and date_key == get_dr_date_str():
        cached_payload = get_composed_live_system_results_cache(date_key, mode)
        if cached_payload is not None:
            log_live_request(date_key, mode, cached_payload.get("servedFrom", "response-cache"), started_at)
            return json_utf8(cached_payload)
    payload = {
        "date": date_key,
        "mode": mode,
        "source": "live-scraper" if should_use_live_scrape() else "supabase-cache",
        "generatedAt": utc_now_iso(),
    }
    lottery_rows = []
    pick_rows = []
    if should_use_live_scrape():
        if mode == "lottery":
            lottery_rows = lottery_rows_for_request_date(date_key)
        elif mode == "pick":
            pick_rows = pick_rows_for_request_date(date_key)
        else:
            lottery_rows, pick_rows = live_results_sections_for_date(
                date_key,
                include_lottery=True,
                include_pick=True,
            )
    if mode in ("lottery", "both"):
        if not should_use_live_scrape():
            lottery_rows = lottery_rows_for_request_date(date_key)
        payload["lotteries"] = {
            "section": "lotteries",
            "count": len(lottery_rows),
            "results": lottery_rows,
        }
    if mode in ("pick", "both"):
        if not should_use_live_scrape():
            pick_rows = pick_rows_for_request_date(date_key, allow_combined_fallback=True)
        payload["picks"] = {
            "section": "picks",
            "count": len(pick_rows),
            "results": pick_rows,
        }
    if not any(payload.get(section, {}).get("count", 0) for section in ("lotteries", "picks")):
        payload["source"] = "live-scraper" if should_use_live_scrape() else "cache-miss"
    if should_use_live_scrape() and date_key == get_dr_date_str():
        payload["servedFrom"] = live_served_from(date_key, mode, lottery_rows, pick_rows)
    if should_use_live_scrape() and date_key == get_dr_date_str():
        set_live_system_results_cache(date_key, mode, payload)
        log_live_request(date_key, mode, payload.get("servedFrom", "inline-scrape"), started_at)
    return json_utf8(payload)


@app.route("/run-scraper", methods=["GET", "POST"])
def run_scraper():
    date_key = request.args.get("date") or get_dr_date_str()
    lottery_rows = unique_sorted_results(scrape_cached(date_key))
    pick_rows = unique_sorted_pick_results(pick_scrape_cached(date_key))
    rows = unique_sorted_results(lottery_rows + pick_rows)
    if not SUPABASE_KEY.strip():
        return json_utf8({
            "date": date_key,
            "count": len(rows),
            "saved": False,
            "error": "SUPABASE_KEY is not configured in Render",
            "results": rows,
        }, status=503)
    try:
        save_to_supabase(date_key, lottery_rows)
        save_us_picks_to_supabase(date_key, pick_rows)
        cache_results_snapshot(f"lot_results_cache_by_day:{date_key}", lottery_rows)
        cache_results_snapshot(f"pick_results_cache_by_day:{date_key}", pick_rows)
    except Exception as error:
        return json_utf8({
            "date": date_key,
            "count": len(rows),
            "saved": False,
            "error": str(error),
            "results": rows,
        }, status=500)
    return json_utf8({
        "date": date_key,
        "count": len(rows),
        "saved": True,
        "results": rows,
    })


@app.route("/run-system-scraper", methods=["GET", "POST"])
def run_system_scraper():
    mode = (request.args.get("mode") or "lottery").strip().lower()
    if mode not in ("lottery", "pick", "both"):
        mode = "lottery"
    date_key = request.args.get("date") or get_dr_date_str()
    if not SUPABASE_KEY.strip():
        return json_utf8({
            "date": date_key,
            "mode": mode,
            "saved": False,
            "error": "SUPABASE_KEY is not configured in Render",
        }, status=503)
    payload = {
        "date": date_key,
        "mode": mode,
        "saved": True,
        "generatedAt": utc_now_iso(),
    }
    try:
        if mode in ("lottery", "both"):
            lottery_rows = unique_sorted_results(scrape_cached(date_key))
            save_to_supabase(date_key, lottery_rows)
            payload["lotteries"] = {
                "count": len(lottery_rows),
                "results": lottery_rows,
            }
        if mode in ("pick", "both"):
            existing_pick_rows = fetch_pick_rows_from_supabase(date_key)
            pick_rows = unique_sorted_pick_results(pick_scrape_cached(date_key, existing_rows=existing_pick_rows))
            save_us_picks_to_supabase(date_key, pick_rows)
            payload["picks"] = {
                "count": len(pick_rows),
                "results": pick_rows,
            }
    except Exception as error:
        payload["saved"] = False
        payload["error"] = str(error)
        return json_utf8(payload, status=500)
    return json_utf8(payload)


@app.route("/run-pick-scraper", methods=["GET", "POST"])
def run_pick_scraper():
    date_key = request.args.get("date") or get_dr_date_str()
    pick_rows = unique_sorted_pick_results(pick_scrape_cached(date_key))
    if not SUPABASE_KEY.strip():
        return json_utf8({
            "date": date_key,
            "section": "picks",
            "count": len(pick_rows),
            "saved": False,
            "error": "SUPABASE_KEY is not configured",
            "results": pick_rows,
        }, status=503)
    try:
        save_us_picks_to_supabase(date_key, pick_rows)
        cache_results_snapshot(f"pick_results_cache_by_day:{date_key}", pick_rows)
    except Exception as error:
        return json_utf8({
            "date": date_key,
            "count": len(pick_rows),
            "saved": False,
            "error": str(error),
            "results": pick_rows,
        }, status=500)
    return json_utf8({
        "date": date_key,
        "section": "picks",
        "count": len(pick_rows),
        "saved": True,
        "results": pick_rows,
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "lotterynet-results"})


@app.route("/config-check", methods=["GET"])
def config_check():
    return jsonify({
        "ok": True,
        "service": "lotterynet-results",
        "supabaseUrlConfigured": bool(SUPABASE_URL.strip()),
        "supabaseKeyConfigured": bool(SUPABASE_KEY.strip()),
        "supabaseKeyPrefix": SUPABASE_KEY[:14] if SUPABASE_KEY else "",
    })


@app.route("/search", methods=["GET"])
def search_lottery_by_name():
    _, rows = results_for_request()
    if not request.args.get("name"):
        return jsonify({"error": "Missing 'name' parameter"}), 400
    return json_utf8(rows)


@app.route("/admin/results/manual-override", methods=["POST"])
def upsert_manual_result_override():
    payload = request_json_body()
    if not is_admin_role(payload.get("role")):
        return json_utf8({"saved": False, "error": "Admin role required"}, status=403)
    date_key = str(payload.get("date") or get_dr_date_str()).strip()
    result_id = str(payload.get("resultId") or payload.get("id") or "").strip()
    name = str(payload.get("name") or "").strip()
    number = str(payload.get("number") or "").strip()
    game = str(payload.get("game") or "").strip().lower().replace("-", "")
    edited_by = str(payload.get("editedBy") or payload.get("username") or "").strip()
    if not result_id or not name or not number:
        return json_utf8({"saved": False, "error": "date, resultId, name and number are required"}, status=400)
    if not validate_override_number(number, game):
        return json_utf8({"saved": False, "error": "Invalid number format for result type"}, status=400)
    overrides = fetch_manual_overrides_from_supabase(date_key)
    remaining = [row for row in overrides if str(row.get("id", "")).strip() != result_id]
    override_row = normalize_manual_override_row({
        "id": result_id,
        "name": name,
        "date": date_key,
        "number": number,
        "game": game,
        "editedBy": edited_by,
        "editedAt": utc_now_iso(),
    }, date_key)
    remaining.append(override_row)
    save_manual_overrides_to_supabase(date_key, remaining)
    return json_utf8({
        "saved": True,
        "date": date_key,
        "resultId": result_id,
        "override": override_row,
    })


@app.route("/admin/results/manual-override", methods=["DELETE"])
def delete_manual_result_override():
    payload = request_json_body()
    if not is_admin_role(payload.get("role")):
        return json_utf8({"saved": False, "error": "Admin role required"}, status=403)
    date_key = str(payload.get("date") or get_dr_date_str()).strip()
    result_id = str(payload.get("resultId") or payload.get("id") or "").strip()
    if not result_id:
        return json_utf8({"saved": False, "error": "resultId is required"}, status=400)
    overrides = fetch_manual_overrides_from_supabase(date_key)
    remaining = [row for row in overrides if str(row.get("id", "")).strip() != result_id]
    save_manual_overrides_to_supabase(date_key, remaining)
    return json_utf8({
        "saved": True,
        "date": date_key,
        "resultId": result_id,
        "deleted": True,
    })


@app.route("/users-state", methods=["GET"])
def users_state():
    payload = fetch_users_state_from_supabase()
    if payload is None:
        return json_utf8({"ok": False, "payload": None, "source": "supabase-kv"}, status=404)
    admins = payload.get("admins") if isinstance(payload, dict) else []
    cashiers = payload.get("cajeros") if isinstance(payload, dict) else []
    supervisors = payload.get("supervisores") if isinstance(payload, dict) else payload.get("supervisors", [])
    return json_utf8({
        "ok": True,
        "source": "supabase-kv",
        "adminCount": len(admins or []),
        "supervisorCount": len(supervisors or []),
        "cashierCount": len(cashiers or []),
        "payload": payload,
    })


@app.route("/users-state", methods=["POST"])
def update_users_state():
    body = request.get_json(silent=True) or {}
    payload = body.get("payload") if isinstance(body, dict) and "payload" in body else body
    if not isinstance(payload, dict):
        return json_utf8({"ok": False, "message": "Payload invalido."}, status=400)
    if "admins" not in payload or "cajeros" not in payload:
        return json_utf8({"ok": False, "message": "Payload de usuarios incompleto."}, status=400)
    save_users_state_to_supabase(payload)
    return json_utf8({"ok": True, "source": "supabase-kv"})


@app.route("/internal/supabase-cache-invalidate", methods=["POST"])
def internal_supabase_cache_invalidate():
    payload = request_json_body()
    keys = []
    direct_key = str(payload.get("key") or "").strip()
    if direct_key:
        keys.append(direct_key)
    record = payload.get("record") if isinstance(payload.get("record"), dict) else {}
    old_record = payload.get("old_record") if isinstance(payload.get("old_record"), dict) else {}
    for candidate in (record.get("key"), old_record.get("key")):
        candidate_key = str(candidate or "").strip()
        if candidate_key:
            keys.append(candidate_key)
    normalized_keys = []
    rejected_keys = []
    for cache_key in keys:
        if cache_key and cache_key not in normalized_keys:
            if is_public_cache_invalidation_key(cache_key):
                normalized_keys.append(cache_key)
                invalidate_results_cache_key(cache_key)
            else:
                rejected_keys.append(cache_key)
    if rejected_keys:
        return json_utf8({
            "ok": False,
            "message": "Invalid cache key for public invalidation.",
            "rejectedKeys": rejected_keys,
        }, status=403)
    if not normalized_keys:
        if not is_internal_secret_valid(request):
            return json_utf8({"ok": False, "message": "Shared secret is invalid."}, status=403)
    return json_utf8({
        "ok": True,
        "invalidatedKeys": normalized_keys,
        "count": len(normalized_keys),
    })


LEGACY_ROUTE_FILTERS = {
    "/loteria-gana-mas": "Gana Más",
    "/loteria-primera": "Primera",
    "/loteria-primera-12am": "La Primera Día",
    "/loteria-primera-noche": "Primera Noche",
    "/loteria-la-suerte": "La Suerte",
    "/loteria-la-suerte-12am": "La Suerte 12:30",
    "/loteria-la-suerte-tarde": "La Suerte Tarde",
    "/loteria-lotedom": "Quiniela LoteDom",
    "/loteria-anguila": "Anguila",
    "/loteria-anguila-10am": "Anguila Mañana",
    "/loteria-anguila-12am": "Anguila Mediodía",
    "/loteria-anguila-6pm": "Anguila Tarde",
    "/loteria-anguila-9pm": "Anguila Noche",
    "/loterias-nacionales": "",
    "/loteria-nacional": "Lotería Nacional",
    "/loteria-leidsa": "Quiniela Leidsa",
    "/loteria-real": "Quiniela Real",
    "/loteria-loteka": "Quiniela Loteka",
    "/loteria-americana": "",
    "/loteria-florida-tarde": "Florida Día",
    "/loteria-florida-noche": "Florida Noche",
    "/loteria-new-york-12am": "New York Tarde",
    "/loteria-new-york-noche": "New York Noche",
    "/loteria-king": "King Lottery",
    "/loteria-king-dia": "King Lottery Día",
    "/loteria-king-noche": "King Lottery Noche",
    "/loteria-haiti": "Haiti Bolet",
    "/loteria-haiti-1130": "Haiti Bolet 11:30 AM",
    "/loteria-haiti-630": "Haiti Bolet 6:30 PM",
    "/loteria-new-jersey": "New Jersey",
    "/loteria-pick3": "Pick 3",
    "/loteria-pick4": "Pick 4",
}


@app.route("/loteria-gana-mas", methods=["GET"])
@app.route("/loteria-primera", methods=["GET"])
@app.route("/loteria-primera-12am", methods=["GET"])
@app.route("/loteria-primera-noche", methods=["GET"])
@app.route("/loteria-la-suerte", methods=["GET"])
@app.route("/loteria-la-suerte-12am", methods=["GET"])
@app.route("/loteria-la-suerte-tarde", methods=["GET"])
@app.route("/loteria-lotedom", methods=["GET"])
@app.route("/loteria-anguila", methods=["GET"])
@app.route("/loteria-anguila-10am", methods=["GET"])
@app.route("/loteria-anguila-12am", methods=["GET"])
@app.route("/loteria-anguila-6pm", methods=["GET"])
@app.route("/loteria-anguila-9pm", methods=["GET"])
@app.route("/loterias-nacionales", methods=["GET"])
@app.route("/loteria-nacional", methods=["GET"])
@app.route("/loteria-leidsa", methods=["GET"])
@app.route("/loteria-real", methods=["GET"])
@app.route("/loteria-loteka", methods=["GET"])
@app.route("/loteria-americana", methods=["GET"])
@app.route("/loteria-florida-tarde", methods=["GET"])
@app.route("/loteria-florida-noche", methods=["GET"])
@app.route("/loteria-new-york-12am", methods=["GET"])
@app.route("/loteria-new-york-noche", methods=["GET"])
@app.route("/loteria-king", methods=["GET"])
@app.route("/loteria-king-dia", methods=["GET"])
@app.route("/loteria-king-noche", methods=["GET"])
@app.route("/loteria-haiti", methods=["GET"])
@app.route("/loteria-haiti-1130", methods=["GET"])
@app.route("/loteria-haiti-630", methods=["GET"])
@app.route("/loteria-new-jersey", methods=["GET"])
@app.route("/loteria-pick3", methods=["GET"])
@app.route("/loteria-pick4", methods=["GET"])
def legacy_filtered_route():
    date_key = request.args.get("date") or get_dr_date_str()
    route_filter = LEGACY_ROUTE_FILTERS.get(request.path, "")
    request_filter = request.args.get("name")
    query = (request_filter or route_filter or "").lower()
    if request.args.get("live") == "1":
        rows = unique_sorted_results(scrape_cached(date_key))
    else:
        lottery_rows = lottery_rows_for_request_date(date_key)
        pick_rows = pick_rows_for_request_date(date_key, allow_combined_fallback=True)
        rows = unique_sorted_results(lottery_rows + pick_rows)
    if query:
        rows = [row for row in rows if query in row["name"].lower()]
    return json_utf8(rows)


# WSGI backward compatibility
application = app


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
