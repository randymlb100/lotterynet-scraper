"""
LotteryNet RD — Scraper → Supabase
Scrapea loteriasdominicanas.com y guarda en lotterynet_kv
key: lot_results_cache_by_day
"""
import os, json, datetime, urllib.request
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
    if not date_str:
        date_str = datetime.datetime.now().strftime("%d-%m-%Y")

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

    # Ordenar por id numérico
    results.sort(key=lambda x: int(x["id"]))
    return results

def save_to_supabase(date_str, results):
    import urllib.parse
    key = f"lot_results_cache_by_day:{date_str}"
    value = json.dumps(results, ensure_ascii=False)

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
        print(f"Saved {len(results)} results for {date_str} → HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Supabase error {e.code}: {body}")

if __name__ == "__main__":
    today = datetime.datetime.now().strftime("%d-%m-%Y")
    print(f"Scraping {today}...")
    results = scrape(today)
    print(f"Found {len(results)} lotteries")
    for r in results:
        print(f"  [{r['id']}] {r['name']}: {r['number']}")

    if not SUPABASE_KEY:
        print("No SUPABASE_KEY — skipping save")
    else:
        save_to_supabase(today, results)
