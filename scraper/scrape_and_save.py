"""
LotteryNet RD — Scraper → Supabase
Scrapea loteriasdominicanas.com y guarda en lotterynet_kv
key: lot_results_cache_by_day
"""
import os, json, datetime, urllib.request
from bs4 import BeautifulSoup

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://unhoulkujbtsypccpirc.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")

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
    # King Lottery (Dominican — appears on loteriasdominicanas.com)
    "king lottery":          {"id": "23", "name": "King Lottery Día"},
    "king lottery día":      {"id": "23", "name": "King Lottery Día"},
    "king lottery 12:30":    {"id": "23", "name": "King Lottery Día"},
    "quiniela día king":     {"id": "23", "name": "King Lottery Día"},
    "king lottery noche":    {"id": "24", "name": "King Lottery Noche"},
    "king lottery 7:30":     {"id": "24", "name": "King Lottery Noche"},
    "quiniela noche king":   {"id": "24", "name": "King Lottery Noche"},
}

def fetch_blocks(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=15).read()
        soup = BeautifulSoup(html, "html.parser")
        return soup.find_all("div", class_="game-block")
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return []

def get_rd_date_str():
    """Fecha en hora RD (UTC-4) — igual que la app, independiente del timezone del servidor."""
    return (datetime.datetime.utcnow() - datetime.timedelta(hours=4)).strftime("%d-%m-%Y")

def scrape(date_str=None):
    if not date_str:
        date_str = get_rd_date_str()

    base = "https://loteriasdominicanas.com"
    urls = [
        f"{base}/?date={date_str}",
        f"{base}/anguila?date={date_str}",
        f"{base}/king-lottery?date={date_str}",
    ]

    all_blocks = []
    for url in urls:
        all_blocks.extend(fetch_blocks(url))

    results = []
    seen_ids = set()

    for block in all_blocks:
        try:
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

    # Fetch NJ Pick 3/4 Evening (Noche) from NJ Lottery API
    nj_results = fetch_nj_picks(date_str)
    for r in nj_results:
        if r["id"] not in seen_ids:
            results.append(r)
            seen_ids.add(r["id"])

    # Fetch NJ Pick 3/4 Midday (Día) from RapidAPI
    nj_midday = fetch_nj_picks_midday(date_str)
    for r in nj_midday:
        if r["id"] not in seen_ids:
            results.append(r)
            seen_ids.add(r["id"])

    # Ordenar por id numérico
    results.sort(key=lambda x: int(x["id"]))
    return results

def fetch_nj_picks(date_str):
    """Fetch NJ Pick 3/4 Evening (Noche) results from NJ Lottery API.
    The API returns ONE draw per game per day — the Evening draw.
    drawTime is stored as midnight EDT (04:00 UTC) of the draw date.
    Midday results are not available from this API.
    """
    results = []
    try:
        parts = date_str.split("-")
        target_date_iso = f"{parts[2]}-{parts[1]}-{parts[0]}"
    except Exception:
        target_date_iso = None

    # API returns only the Evening draw per game per day
    game_map = {
        "Pick 3": {"id": "20", "name": "NJ Pick 3 Noche", "digits": 3},
        "Pick 4": {"id": "22", "name": "NJ Pick 4 Noche", "digits": 4},
    }
    found_ids = set()

    try:
        url = "https://www.njlottery.com/api/v1/draw-games/draws.json?numDraws=20"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        draws = data.get("draws") or []

        for draw in draws:
            game_name = draw.get("gameName", "")
            if game_name not in game_map:
                continue
            draw_ts = draw.get("drawTime")
            if not draw_ts:
                continue
            # drawTime = midnight EDT (04:00 UTC) of the NJ local draw date
            draw_date_iso = datetime.datetime.fromtimestamp(
                draw_ts / 1000, tz=datetime.timezone.utc
            ).strftime("%Y-%m-%d")
            if target_date_iso and draw_date_iso != target_date_iso:
                continue
            game = game_map[game_name]
            if game["id"] in found_ids:
                continue

            digits = game["digits"]
            draw_results = draw.get("results") or []
            plain_num = None
            # Find the entry with exactly 1 pure-digit element of correct length
            for res in draw_results:
                p = res.get("primary") or []
                if len(p) == 1:
                    s = "".join(c for c in str(p[0]) if c.isdigit())
                    if len(s) == digits:
                        plain_num = s
                        break
            # Fallback: any pure-digit entry of correct length
            if not plain_num:
                for res in draw_results:
                    for entry in (res.get("primary") or []):
                        s = "".join(c for c in str(entry) if c.isdigit())
                        if len(s) == digits:
                            plain_num = s
                            break
                    if plain_num:
                        break
            if not plain_num or len(plain_num) < digits:
                continue
            plain_num = plain_num[:digits]
            number = "-".join(plain_num)
            results.append({
                "id":     game["id"],
                "name":   game["name"],
                "date":   date_str,
                "number": number,
            })
            print(f"  NJ API [{game['id']}] {game['name']}: {number}")
            found_ids.add(game["id"])

    except Exception as e:
        print(f"  NJ API error: {e}")

    return results

def fetch_nj_picks_midday(date_str):
    """Fetch NJ Pick 3/4 Midday (Día) from RapidAPI USA Lottery.
    Two-step: (1) past-draws-dates to get drawID, (2) game-result for numbers.
    gameID 283 = Pick-3 Midday (id 19), gameID 285 = Pick-4 Midday (id 21).
    """
    if not RAPIDAPI_KEY:
        print("  RapidAPI: no RAPIDAPI_KEY — skipping NJ midday")
        return []

    results = []
    try:
        parts = date_str.split("-")
        target_date_iso = f"{parts[2]}-{parts[1]}-{parts[0]}"
    except Exception:
        return []

    game_map = {
        283: {"id": "19", "name": "NJ Pick 3 Día", "digits": 3},
        285: {"id": "21", "name": "NJ Pick 4 Día", "digits": 4},
    }
    headers = {
        "x-rapidapi-host": "usa-lottery-result-all-state-api.p.rapidapi.com",
        "x-rapidapi-key":  RAPIDAPI_KEY,
        "User-Agent": "Mozilla/5.0",
    }

    for game_id, game in game_map.items():
        try:
            # Step 1: get drawID for target date
            url1 = (
                "https://usa-lottery-result-all-state-api.p.rapidapi.com"
                f"/lottery-results/past-draws-dates?gameID={game_id}"
            )
            req1 = urllib.request.Request(url1, headers=headers)
            data1 = json.loads(urllib.request.urlopen(req1, timeout=10).read().decode())
            dates_list = (data1.get("data") or {}).get("date") or []
            draw_id = None
            for entry in dates_list:
                if entry.get("drawDate") == target_date_iso:
                    draw_id = entry.get("drawID")
                    break
            if not draw_id:
                print(f"  RapidAPI: no drawID for {game['name']} on {target_date_iso}")
                continue

            # Step 2: get the actual winning numbers
            url2 = (
                "https://usa-lottery-result-all-state-api.p.rapidapi.com"
                f"/lottery-results/game-result?gameID={game_id}&drawID={draw_id}"
            )
            req2 = urllib.request.Request(url2, headers=headers)
            data2 = json.loads(urllib.request.urlopen(req2, timeout=10).read().decode())
            nums = (data2.get("data") or {}).get("winningNumbers") or []
            if len(nums) != game["digits"]:
                print(f"  RapidAPI: unexpected numbers {nums} for {game['name']}")
                continue

            number = "-".join(str(n) for n in nums)
            results.append({
                "id":     game["id"],
                "name":   game["name"],
                "date":   date_str,
                "number": number,
            })
            print(f"  RapidAPI [{game['id']}] {game['name']}: {number}")
        except Exception as e:
            print(f"  RapidAPI error for {game['name']}: {e}")

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
    import sys
    today = sys.argv[1] if len(sys.argv) > 1 else get_rd_date_str()
    print(f"Scraping {today}...")
    results = scrape(today)
    print(f"Found {len(results)} lotteries")
    for r in results:
        print(f"  [{r['id']}] {r['name']}: {r['number']}")

    if not SUPABASE_KEY:
        print("No SUPABASE_KEY — skipping save")
    else:
        save_to_supabase(today, results)
