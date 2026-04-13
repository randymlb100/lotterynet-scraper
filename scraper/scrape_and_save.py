"""
LotteryNet RD — Scraper → Supabase
Scrapea loteriasdominicanas.com y guarda en lotterynet_kv
key: lot_results_cache_by_day
"""
import os, json, datetime, urllib.request, urllib.parse, re
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
    "king lottery 12:30":    {"id": "23", "name": "King Lottery Día"},
    "king lottery 7:30":     {"id": "24", "name": "King Lottery Noche"},
}

MILOTERIA_NJ_MAP = {
    "new jersey am": {"id": "25", "name": "New Jersey AM"},
    "new jersey pm": {"id": "26", "name": "New Jersey PM"},
}

AUTHORITATIVE_NJ_IDS = {"19", "20", "21", "22", "25", "26"}

def get_dr_now():
    """Current Dominican Republic time (AST / UTC-4)."""
    return datetime.datetime.utcnow() - datetime.timedelta(hours=4)

def get_et_date_str():
    """Today's date in Eastern Time (UTC-4, approximation valid for ET)."""
    et = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    return et.strftime("%d-%m-%Y")

def get_dr_date_str():
    """Today's date in Dominican Republic / Atlantic Standard Time (UTC-4)."""
    return get_dr_now().strftime("%d-%m-%Y")

def get_dr_date_str_for_offset(days_ago):
    """Date string in DR time for today/ayer/antes de ayer style backfills."""
    return (get_dr_now() - datetime.timedelta(days=int(days_ago))).strftime("%d-%m-%Y")


def parse_miloteria_date(raw):
    text = str(raw or "").strip()
    if not text:
        return ""
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    match = re.search(r"\b([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})\b", text)
    if not match:
        return ""
    month = months.get(match.group(1).lower())
    if not month:
        return ""
    day = int(match.group(2))
    year = int(match.group(3))
    return f"{day:02d}-{month:02d}-{year}"

def parse_lotteryusa_date(raw):
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.datetime.strptime(text, "%b %d, %Y")
    except ValueError:
        return ""
    return parsed.strftime("%d-%m-%Y")


def fetch_lotteryusa_results(url, lottery_id, lottery_name, digits, target_date):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        html = urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:
        print(f"  Lottery USA error for {lottery_name}: {e}")
        return None

    soup = BeautifulSoup(html, "html.parser")
    for row in soup.select("tbody#js-state-results-table tr.c-draw-card"):
        date_el = row.select_one(".c-draw-card__draw-date-sub")
        draw_date = parse_lotteryusa_date(date_el.get_text(" ", strip=True) if date_el else "")
        if draw_date != target_date:
            continue

        balls = []
        for ball in row.select("li.c-ball"):
            classes = ball.get("class") or []
            if "c-ball--fire" in classes:
                continue
            value = ball.get_text(strip=True)
            if value:
                balls.append(value)

        if len(balls) < digits:
            print(f"  Lottery USA: incomplete row for {lottery_name} on {target_date}")
            return None

        number = "-".join(balls[:digits])
        print(f"  Lottery USA [{lottery_id}] {lottery_name}: {number}")
        return {
            "id": lottery_id,
            "name": lottery_name,
            "date": target_date,
            "number": number,
        }

    print(f"  Lottery USA: no result for {lottery_name} on {target_date}")
    return None


def fetch_nj_picks_lotteryusa(date_str=None):
    """Fetch NJ Pick 3/4 Dia y Noche from Lottery USA pages."""
    target_date = date_str or get_et_date_str()
    sources = [
        ("https://www.lotteryusa.com/new-jersey/midday-pick-3/", "19", "NJ Pick 3 Día", 3),
        ("https://www.lotteryusa.com/new-jersey/pick-3/", "20", "NJ Pick 3 Noche", 3),
        ("https://www.lotteryusa.com/new-jersey/midday-pick-4/", "21", "NJ Pick 4 Día", 4),
        ("https://www.lotteryusa.com/new-jersey/pick-4/", "22", "NJ Pick 4 Noche", 4),
    ]
    results = []
    for url, lottery_id, lottery_name, digits in sources:
        row = fetch_lotteryusa_results(url, lottery_id, lottery_name, digits, target_date)
        if row:
            results.append(row)
    return results


def fetch_miloteria_new_jersey(date_str=None):
    """Fetch New Jersey AM/PM quiniela-style results from MiLoteria."""
    target_date = date_str or get_dr_date_str()
    payload = urllib.parse.urlencode({
        "zonaHorariaUsuario": "America/Santo_Domingo"
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://www.miloteria.net/api/v1/draws.php",
        data=payload,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        },
        method="POST",
    )
    try:
        raw = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
        data = json.loads(raw)
    except Exception as e:
        print(f"  MiLoteria NJ error: {e}")
        return []

    results = []
    for draw in data if isinstance(data, list) else []:
        nombre = str(draw.get("nombre", "")).strip().lower()
        match = MILOTERIA_NJ_MAP.get(nombre)
        if not match:
            continue
        result = draw.get("result") or {}
        result_date = parse_miloteria_date(result.get("date"))
        if result_date != target_date:
            continue
        numbers = [
            str(result.get("first", "")).strip(),
            str(result.get("second", "")).strip(),
            str(result.get("third", "")).strip(),
        ]
        numbers = [n for n in numbers if n]
        if len(numbers) < 3:
            continue
        row = {
            "id": match["id"],
            "name": match["name"],
            "date": target_date,
            "number": "-".join(numbers[:3]),
        }
        results.append(row)
        print(f"  MiLoteria [{row['id']}] {row['name']}: {row['number']}")
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
        f"{base}/king-lottery?date={date_str}",
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

    nj_rows = fetch_nj_picks_lotteryusa(date_str)
    for row in nj_rows:
        if row["id"] not in seen_ids:
            results.append(row)
            seen_ids.add(row["id"])

    miloteria_nj = fetch_miloteria_new_jersey(date_str)
    for row in miloteria_nj:
        if row["id"] not in seen_ids:
            results.append(row)
            seen_ids.add(row["id"])

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

def save_to_supabase(date_str, results, prune_missing_ids=None):
    import urllib.parse
    key = f"lot_results_cache_by_day:{date_str}"

    # Merge: preserve existing rows by default, override with fresh ones by id.
    # For today's authoritatives we can optionally prune IDs that were not freshly found,
    # which lets us clear stale same-day rows without damaging historical backfills.
    existing = fetch_existing_from_supabase(date_str)
    merged = {str(r["id"]): r for r in existing}
    for stale_id in (prune_missing_ids or []):
        merged.pop(str(stale_id), None)
    for r in results:
        merged[str(r["id"])] = r
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
        print(f"Saved {len(merged_list)} results (merged) for {date_str} -> HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Supabase error {e.code}: {body}")

if __name__ == "__main__":
    import sys

    # No args: refresh today + yesterday + day before.
    # Args: treat each arg as an explicit DD-MM-YYYY date to scrape and save.
    if len(sys.argv) > 1:
        target_dates = sys.argv[1:]
    else:
        target_dates = [get_dr_date_str_for_offset(off) for off in range(0, 3)]

    print(f"\n[RD] Syncing dates: {', '.join(target_dates)} (UTC now={datetime.datetime.utcnow().strftime('%H:%M')})")

    for idx, target_date in enumerate(target_dates):
        print(f"\n[RD] Scraping {target_date}...")
        results = scrape(target_date)
        print(f"Found {len(results)} lotteries")
        for r in results:
            print(f"  [{r['id']}] {r['name']}: {r['number']}")

        if not SUPABASE_KEY:
            print("No SUPABASE_KEY — skipping save")
            continue
        if not results:
            print(f"No results found for {target_date} — skipping save")
            continue

        prune_missing_ids = AUTHORITATIVE_NJ_IDS if idx == 0 and target_date == get_dr_date_str() else None
        save_to_supabase(target_date, results, prune_missing_ids=prune_missing_ids)
