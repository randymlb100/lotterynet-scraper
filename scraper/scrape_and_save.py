"""
LotteryNet RD — Scraper → Supabase
Scrapea loteriasdominicanas.com y guarda en lotterynet_kv
key: lot_results_cache_by_day
"""
import os, json, datetime, urllib.request, re
from bs4 import BeautifulSoup

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://unhoulkujbtsypccpirc.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# Mapa: nombre en loteriasdominicanas.com → id de lotería en la app
LOTTERY_MAP = {
    "la primera día":        {"id": "1",  "name": "La Primera Día"},
    "anguila mañana":        {"id": "2",  "name": "Anguila Mañana"},
    "la suerte 12:30":       {"id": "3",  "name": "La Suerte 12:30"},
    "anguila medio día":     {"id": "4",  "name": "Anguila Mediodía"},
    "quiniela real":         {"id": "5",  "name": "Quiniela Real"},
    "florida día":           {"id": "6",  "name": "Florida Día"},
    "quiniela lotedom":      {"id": "7",  "name": "Quiniela LoteDom"},
    "new york tarde":        {"id": "8",  "name": "New York Tarde"},
    "gana más":              {"id": "9",  "name": "Gana Más"},
    "la suerte 18:00":       {"id": "10", "name": "La Suerte Tarde"},
    "anguila tarde":         {"id": "11", "name": "Anguila Tarde"},
    "quiniela loteka":       {"id": "12", "name": "Quiniela Loteka"},
    "lotería nacional":      {"id": "13", "name": "Lotería Nacional"},
    "anguila noche":         {"id": "14", "name": "Anguila Noche"},
    "quiniela leidsa":       {"id": "15", "name": "Quiniela Leidsa"},
    "primera noche":         {"id": "16", "name": "Primera Noche"},
    "florida noche":         {"id": "17", "name": "Florida Noche"},
    "new york noche":        {"id": "18", "name": "New York Noche"},
}

# ── NJ Pick 3 / Pick 4 ────────────────────────────────────────────────────────
NJ_PICK_MAP = {
    "PICK-3": [
        {"draw_time": "midday",  "id": "19", "name": "NJ Pick 3 Dia",   "digits": 3},
        {"draw_time": "evening", "id": "20", "name": "NJ Pick 3 Noche", "digits": 3},
    ],
    "PICK-4": [
        {"draw_time": "midday",  "id": "21", "name": "NJ Pick 4 Dia",   "digits": 4},
        {"draw_time": "evening", "id": "22", "name": "NJ Pick 4 Noche", "digits": 4},
    ],
}

LP_GAME_MAP = {
    "pick 3 midday":  {"id": "19", "name": "NJ Pick 3 Dia",   "digits": 3},
    "pick-3 midday":  {"id": "19", "name": "NJ Pick 3 Dia",   "digits": 3},
    "pick 3 evening": {"id": "20", "name": "NJ Pick 3 Noche", "digits": 3},
    "pick-3 evening": {"id": "20", "name": "NJ Pick 3 Noche", "digits": 3},
    "pick 4 midday":  {"id": "21", "name": "NJ Pick 4 Dia",   "digits": 4},
    "pick-4 midday":  {"id": "21", "name": "NJ Pick 4 Dia",   "digits": 4},
    "pick 4 evening": {"id": "22", "name": "NJ Pick 4 Noche", "digits": 4},
    "pick-4 evening": {"id": "22", "name": "NJ Pick 4 Noche", "digits": 4},
}

def get_et_date_str():
    """Today's date in Eastern Time (UTC-4, approximation valid for ET)."""
    et = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    return et.strftime("%d-%m-%Y")

def get_dr_date_str():
    """Today's date in Dominican Republic / Atlantic Standard Time (UTC-4)."""
    dr = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    return dr.strftime("%d-%m-%Y")

def get_et_iso_date():
    et = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    return et.strftime("%Y-%m-%d")

def scrape_nj_picks(date_str=None):
    """Scrape NJ Pick 3/4 from NJ Lottery API, fallback to lotterypost.com."""
    et_date_str = date_str or get_et_date_str()
    parts = et_date_str.split("-")
    iso_date = f"{parts[2]}-{parts[1]}-{parts[0]}"  # YYYY-MM-DD

    results = []
    seen_ids = set()

    # ── Primary: NJ Lottery official API ─────────────────────────────────────
    for game_id, draw_configs in NJ_PICK_MAP.items():
        url = f"https://www.njlottery.com/api/v1/draw-games/draws.json?gameId={game_id}&numDraws=4"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible)",
                "Accept": "application/json",
            })
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode())
            # API may nest draws under drawGames or directly
            draws_list = (
                data.get("draws") or
                (data.get("drawGames") or {}).get("draws") or
                data.get("draw") or []
            )
            if not isinstance(draws_list, list):
                draws_list = []

            for cfg in draw_configs:
                if cfg["id"] in seen_ids:
                    continue
                for draw in draws_list:
                    draw_date = str(draw.get("drawDate", "")).split("T")[0]
                    draw_time_raw = str(
                        draw.get("gameTimeType") or draw.get("drawTime") or ""
                    ).lower()
                    if draw_date == iso_date and cfg["draw_time"] in draw_time_raw:
                        numbers_raw = str(
                            draw.get("numbers") or
                            draw.get("winningNumbers") or
                            draw.get("number") or ""
                        )
                        digits = re.findall(r"\d", numbers_raw)
                        if len(digits) == cfg["digits"]:
                            results.append({
                                "id":     cfg["id"],
                                "name":   cfg["name"],
                                "date":   et_date_str,
                                "number": "-".join(digits),
                            })
                            seen_ids.add(cfg["id"])
                            print(f"  NJ API [{cfg['id']}] {cfg['name']}: {'-'.join(digits)}")
                            break
        except Exception as e:
            print(f"  NJ API error for {game_id}: {e}")

    # ── Fallback: lotterypost.com ─────────────────────────────────────────────
    missing = [cfg for configs in NJ_PICK_MAP.values() for cfg in configs
               if cfg["id"] not in seen_ids]
    if missing:
        print(f"  NJ API missing {len(missing)} draws — trying lotterypost.com...")
        lp = scrape_nj_lotterypost(et_date_str)
        for r in lp:
            if r["id"] not in seen_ids:
                results.append(r)
                seen_ids.add(r["id"])

    return results


def scrape_nj_lotterypost(date_str=None):
    """Fallback: parse NJ Pick 3/4 from lotterypost.com/results/nj."""
    et_date_str = date_str or get_et_date_str()
    url = "https://www.lotterypost.com/results/nj"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        })
        html = urllib.request.urlopen(req, timeout=15).read()
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        print(f"  lotterypost.com error: {e}")
        return []

    results = []
    seen = set()
    # Walk every <tr> looking for a Pick 3/4 game name cell
    for tr in soup.find_all("tr"):
        tr_text = tr.get_text(" ", strip=True).lower()
        matched = None
        for key, cfg in LP_GAME_MAP.items():
            if key in tr_text and cfg["id"] not in seen:
                matched = cfg
                break
        if not matched:
            continue
        # Collect digits from any single-child elements (balls)
        single_digit_re = re.compile(r"^(\d)$")
        balls = [
            el.get_text(strip=True)
            for el in tr.find_all(["td", "li", "span"])
            if single_digit_re.match(el.get_text(strip=True))
        ]
        if len(balls) >= matched["digits"]:
            digits = balls[:matched["digits"]]
            results.append({
                "id":     matched["id"],
                "name":   matched["name"],
                "date":   et_date_str,
                "number": "-".join(digits),
            })
            seen.add(matched["id"])
            print(f"  lotterypost [{matched['id']}] {matched['name']}: {'-'.join(digits)}")
    return results


def fetch_blocks(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=15).read()
        soup = BeautifulSoup(html, "html.parser")
        return soup.find_all("div", class_="game-block")
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return []

def scrape(date_str=None):
    # Use Dominican Republic time (UTC-4) as default to avoid midnight UTC
    # causing evening lottery results to be discarded on the wrong date
    if not date_str:
        date_str = get_dr_date_str()

    base = "https://loteriasdominicanas.com"
    urls = [
        f"{base}/?date={date_str}",
        f"{base}/anguila?date={date_str}",
    ]

    all_blocks = []
    for url in urls:
        all_blocks.extend(fetch_blocks(url))

    results = []
    seen_ids = set()

    # Expected DD-MM from date_str (e.g. "10-04-2026" → "10-04")
    expected_ddmm = date_str[:5]  # "DD-MM"

    for block in all_blocks:
        try:
            # Validate block date against requested date — prevents storing
            # yesterday's results under today's key when today has no draws yet
            date_el = block.find("div", class_="session-date")
            if date_el:
                block_ddmm = date_el.get_text(strip=True)  # e.g. "10-04"
                if block_ddmm != expected_ddmm:
                    continue  # block belongs to a different day — skip

            title_el = block.find("a", "game-title")
            if not title_el:
                continue
            title = title_el.getText().strip().lower()
            match = LOTTERY_MAP.get(title)
            if not match or match["id"] in seen_ids:
                continue

            scores = block.find_all("span", "score")
            numbers = [s.text.strip() for s in scores if s.text.strip()]
            if not numbers:
                continue

            results.append({
                "id":     match["id"],
                "name":   match["name"],
                "date":   date_str,          # siempre DD-MM-YYYY del param, no del DOM
                "number": "-".join(numbers)  # "01-23-4" — formato que lee la app
            })
            seen_ids.add(match["id"])
        except Exception as e:
            print(f"Parse error: {e}")
            continue

    # Ordenar por id numérico
    results.sort(key=lambda x: int(x["id"]))
    return results

def fetch_existing_from_supabase(date_str):
    """Fetch previously saved results for the given date so we can merge."""
    key = f"lot_results_cache_by_day:{date_str}"
    import urllib.parse
    params = urllib.parse.urlencode({"key": f"eq.{key}", "select": "value"})
    url = f"{SUPABASE_URL}/rest/v1/lotterynet_kv?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        rows = json.loads(resp.read().decode())
        if rows and rows[0].get("value"):
            existing = rows[0]["value"]
            if isinstance(existing, str):
                existing = json.loads(existing)
            if isinstance(existing, list):
                return existing
    except Exception as e:
        print(f"Warning: could not fetch existing results: {e}")
    return []

def save_to_supabase(date_str, results):
    import urllib.parse
    key = f"lot_results_cache_by_day:{date_str}"

    # Merge: start from existing saved results, override with fresh ones by id
    existing = fetch_existing_from_supabase(date_str)
    merged = {r["id"]: r for r in existing}
    for r in results:
        merged[r["id"]] = r          # fresh data wins
    merged_list = sorted(merged.values(), key=lambda x: int(x["id"]))

    value = json.dumps(merged_list, ensure_ascii=False)

    payload = json.dumps({"key": key, "value": value, "upd": datetime.datetime.utcnow().isoformat() + "Z"}).encode("utf-8")
    url = f"{SUPABASE_URL}/rest/v1/lotterynet_kv"

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Prefer": "resolution=merge-duplicates",
        },
        method="POST"
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        print(f"Saved {len(merged_list)} results (merged) for {date_str} → HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Supabase error {e.code}: {body}")

if __name__ == "__main__":
    # Use DR time (UTC-4) — GitHub Actions runs in UTC, DR is UTC-4.
    # Without this, evening draws after 8 PM DR (= midnight UTC) get the
    # wrong date and are silently skipped by the date filter.
    today = get_dr_date_str()
    print(f"\n[RD] Scraping {today} (DR time, UTC now={datetime.datetime.utcnow().strftime('%H:%M')})...")
    results = scrape(today)
    print(f"Found {len(results)} RD lotteries")
    for r in results:
        print(f"  [{r['id']}] {r['name']}: {r['number']}")

    if not SUPABASE_KEY:
        print("No SUPABASE_KEY — skipping save")
    elif not results:
        print("No results found for today — skipping save (no draws yet or date mismatch)")
    else:
        save_to_supabase(today, results)

    # ── NJ Pick 3 / Pick 4 ───────────────────────────────────────────────────
    et_today = get_et_date_str()
    print(f"\n[NJ] Scraping Pick 3/4 for ET date {et_today}...")
    nj_results = scrape_nj_picks(et_today)
    print(f"Found {len(nj_results)} NJ picks")
    for r in nj_results:
        print(f"  [{r['id']}] {r['name']}: {r['number']}")

    if not SUPABASE_KEY:
        print("No SUPABASE_KEY — skipping NJ save")
    elif nj_results:
        save_to_supabase(et_today, nj_results)
    else:
        print("No NJ results yet — draws may not have occurred yet")
