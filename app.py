import json
import os
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote
import urllib.request

from scraper.scrape_and_save import get_dr_date_str, save_to_supabase, save_us_picks_to_supabase, scrape, scrape_us_picks

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://unhoulkujbtsypccpirc.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


def normalize_result_row(row):
    number = str(row.get("number", "")).strip()
    name = str(row.get("name", "")).strip()
    out = {
        "id": str(row.get("id", "")).strip(),
        "name": name,
        "date": str(row.get("date", "")).strip(),
        "number": number,
        **({"status": row.get("status")} if row.get("status") else {}),
        **({"source": row.get("source")} if row.get("source") else {}),
        **({"firstSeenAt": row.get("firstSeenAt")} if row.get("firstSeenAt") else {}),
        **({"lastSeenAt": row.get("lastSeenAt")} if row.get("lastSeenAt") else {}),
    }
    normalized_name = name.lower()
    game = str(row.get("game", "")).lower().replace("-", "")
    if game == "pick3" or "pick 3" in normalized_name:
        out["pick3"] = number
    if game == "pick4" or "pick 4" in normalized_name:
        out["pick4"] = number
    for key in ("state", "stateCode", "game", "gameName", "draw", "playTypes"):
        if row.get(key):
            out[key] = row.get(key)
    return out


def unique_sorted_results(rows):
    by_id = {}
    for row in rows:
        normalized = normalize_result_row(row)
        if not normalized["id"]:
            continue
        by_id[normalized["id"]] = normalized
    return sorted(by_id.values(), key=lambda item: (0, int(item["id"])) if item["id"].isdigit() else (1, item["id"]))


def normalize_pick_row(row):
    normalized = normalize_result_row(row)
    game = str(row.get("game", "")).lower().replace("-", "")
    game_name = str(row.get("gameName", "")).strip() or ("Pick 4" if game == "pick4" else "Pick 3")
    draw = str(row.get("draw", "")).strip()
    state = str(row.get("state", "")).strip()
    normalized["name"] = " ".join(part for part in [state, game_name, draw] if part)
    return normalized


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


def split_lottery_and_pick_rows(rows):
    lottery_rows = []
    pick_rows = []
    for row in rows or []:
        if is_pick_result_row(row):
            pick_rows.append(row)
        else:
            lottery_rows.append(row)
    return lottery_rows, pick_rows


def fetch_supabase_results_cache(cache_key):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    url = (
        f"{SUPABASE_URL.rstrip('/')}/rest/v1/lotterynet_kv"
        f"?key=eq.{quote(cache_key, safe='')}&select=value"
    )
    req = urllib.request.Request(
        url,
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


def load_cached_sections(target_date):
    lottery_cache = fetch_supabase_results_cache(f"lot_results_cache_by_day:{target_date}")
    pick_cache = fetch_supabase_results_cache(f"pick_results_cache_by_day:{target_date}")
    legacy_lottery_rows, legacy_pick_rows = split_lottery_and_pick_rows(lottery_cache)
    pick_rows = pick_cache or legacy_pick_rows
    return unique_sorted_results(legacy_lottery_rows), unique_sorted_pick_results(pick_rows)


def build_results_response(date_key=None, save=False):
    target_date = date_key or get_dr_date_str()
    lottery_results, pick_results = ([], []) if save else load_cached_sections(target_date)
    source = "supabase-cache" if lottery_results or pick_results else "cache-miss"
    if save:
        source = "scraper"
        lottery_results = unique_sorted_results(scrape(target_date))
        pick_results = unique_sorted_pick_results(scrape_us_picks(target_date))
    results = unique_sorted_results(lottery_results + pick_results)
    saved = False
    save_error = None
    if save:
        if os.environ.get("SUPABASE_KEY", "").strip():
            try:
                save_to_supabase(target_date, lottery_results)
                save_us_picks_to_supabase(target_date, pick_results)
                saved = True
            except Exception as error:
                save_error = str(error)
        else:
            save_error = "SUPABASE_KEY is not configured"
    return {
        "date": target_date,
        "count": len(results),
        "saved": saved,
        "saveError": save_error,
        "source": source,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "lotteryCount": len(lottery_results),
        "pickCount": len(pick_results),
        "results": results,
    }


def build_pick_results_response(date_key=None, save=False):
    target_date = date_key or get_dr_date_str()
    results = [] if save else load_cached_sections(target_date)[1]
    source = "supabase-cache" if results else "cache-miss"
    if save:
        source = "scraper"
        results = unique_sorted_pick_results(scrape_us_picks(target_date))
    saved = False
    save_error = None
    if save:
        if os.environ.get("SUPABASE_KEY", "").strip():
            try:
                save_us_picks_to_supabase(target_date, results)
                saved = True
            except Exception as error:
                save_error = str(error)
        else:
            save_error = "SUPABASE_KEY is not configured"
    return {
        "date": target_date,
        "section": "picks",
        "count": len(results),
        "saved": saved,
        "saveError": save_error,
        "source": source,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "results": results,
    }


def build_system_results_response(date_key=None, mode="lottery"):
    target_date = date_key or get_dr_date_str()
    normalized_mode = str(mode or "lottery").strip().lower()
    if normalized_mode not in {"lottery", "pick", "both"}:
        normalized_mode = "lottery"
    payload = {
        "date": target_date,
        "mode": normalized_mode,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    cached_lotteries, cached_picks = load_cached_sections(target_date)
    used_cache = bool(cached_lotteries or cached_picks)
    if normalized_mode in {"lottery", "both"}:
        payload["lotteries"] = {
            "section": "lotteries",
            "count": len(cached_lotteries),
            "results": cached_lotteries,
        }
    if normalized_mode in {"pick", "both"}:
        payload["picks"] = {
            "section": "picks",
            "count": len(cached_picks),
            "results": cached_picks,
        }
    payload["source"] = "supabase-cache" if used_cache else "cache-miss"
    return payload


def json_response(start_response, payload, status="200 OK"):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(status, [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Access-Control-Allow-Origin", "*"),
        ("Cache-Control", "no-store"),
        ("Content-Length", str(len(body))),
    ])
    return [body]


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    params = parse_qs(environ.get("QUERY_STRING", ""))
    date_key = params.get("date", [None])[0]

    if path == "/health":
        return json_response(start_response, {"ok": True, "service": "lotterynet-results"})

    if path == "/" and not date_key:
        return json_response(start_response, {"ok": True, "service": "lotterynet-results"})

    if path in {"/", "/results"}:
        payload = build_results_response(date_key=date_key, save=False)
        return json_response(start_response, payload["results"] if path == "/" else payload)

    if path == "/pick-results":
        payload = build_pick_results_response(date_key=date_key, save=False)
        return json_response(start_response, payload)

    if path == "/system-results":
        mode = params.get("mode", ["lottery"])[0]
        payload = build_system_results_response(date_key=date_key, mode=mode)
        return json_response(start_response, payload)

    if path == "/run-scraper":
        payload = build_results_response(date_key=date_key, save=True)
        status = "200 OK" if payload["saved"] else "503 Service Unavailable"
        return json_response(start_response, payload, status=status)

    if path == "/run-pick-scraper":
        payload = build_pick_results_response(date_key=date_key, save=True)
        status = "200 OK" if payload["saved"] else "503 Service Unavailable"
        return json_response(start_response, payload, status=status)

    return json_response(start_response, {"error": "Not found"}, status="404 Not Found")
