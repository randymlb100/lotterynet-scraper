"""
LotteryNet RD - Scraper -> Supabase
Scrapea loteriasdominicanas.com y guarda en lotterynet_kv.
key: lot_results_cache_by_day
"""

import datetime
import json
import os
import re
import urllib.error
import urllib.request

from bs4 import BeautifulSoup


SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://unhoulkujbtsypccpirc.supabase.co"
)
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")

LOTTERY_MAP = {
    "la primera día": {"id": "1", "name": "La Primera Día"},
    "anguila mañana": {"id": "2", "name": "Anguila Mañana"},
    "la suerte 12:30": {"id": "3", "name": "La Suerte 12:30"},
    "anguila medio día": {"id": "4", "name": "Anguila Mediodía"},
    "quiniela real": {"id": "5", "name": "Quiniela Real"},
    "florida día": {"id": "6", "name": "Florida Día"},
    "quiniela lotedom": {"id": "7", "name": "Quiniela LoteDom"},
    "new york tarde": {"id": "8", "name": "New York Tarde"},
    "gana más": {"id": "9", "name": "Gana Más"},
    "la suerte 18:00": {"id": "10", "name": "La Suerte Tarde"},
    "anguila tarde": {"id": "11", "name": "Anguila Tarde"},
    "quiniela loteka": {"id": "12", "name": "Quiniela Loteka"},
    "lotería nacional": {"id": "13", "name": "Lotería Nacional"},
    "anguila noche": {"id": "14", "name": "Anguila Noche"},
    "quiniela leidsa": {"id": "15", "name": "Quiniela Leidsa"},
    "primera noche": {"id": "16", "name": "Primera Noche"},
    "florida noche": {"id": "17", "name": "Florida Noche"},
    "new york noche": {"id": "18", "name": "New York Noche"},
}

NJ_PICK_MAP = {
    "PICK-3": [
        {"draw_time": "midday", "id": "19", "name": "NJ Pick 3 Dia", "digits": 3},
        {"draw_time": "evening", "id": "20", "name": "NJ Pick 3 Noche", "digits": 3},
    ],
    "PICK-4": [
        {"draw_time": "midday", "id": "21", "name": "NJ Pick 4 Dia", "digits": 4},
        {"draw_time": "evening", "id": "22", "name": "NJ Pick 4 Noche", "digits": 4},
    ],
}

LP_GAME_MAP = {
    "pick 3 midday": {"id": "19", "name": "NJ Pick 3 Dia", "digits": 3},
    "pick-3 midday": {"id": "19", "name": "NJ Pick 3 Dia", "digits": 3},
    "pick 3 evening": {"id": "20", "name": "NJ Pick 3 Noche", "digits": 3},
    "pick-3 evening": {"id": "20", "name": "NJ Pick 3 Noche", "digits": 3},
    "pick 4 midday": {"id": "21", "name": "NJ Pick 4 Dia", "digits": 4},
    "pick-4 midday": {"id": "21", "name": "NJ Pick 4 Dia", "digits": 4},
    "pick 4 evening": {"id": "22", "name": "NJ Pick 4 Noche", "digits": 4},
    "pick-4 evening": {"id": "22", "name": "NJ Pick 4 Noche", "digits": 4},
}


def get_et_date_str():
    et = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    return et.strftime("%d-%m-%Y")


def get_dr_date_str():
    dr = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    return dr.strftime("%d-%m-%Y")


def fetch_url(url, headers=None, timeout=15):
    req = urllib.request.Request(
        url,
        headers=headers or {"User-Agent": "Mozilla/5.0"},
    )
    return urllib.request.urlopen(req, timeout=timeout)


def scrape_nj_lotterypost(date_str=None):
    et_date_str = date_str or get_et_date_str()
    url = "https://www.lotterypost.com/results/nj"
    try:
        html = fetch_url(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
            },
        ).read()
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        print(f"  lotterypost.com error: {exc}")
        return []

    results = []
    seen = set()
    single_digit_re = re.compile(r"^(\d)$")
    for tr in soup.find_all("tr"):
        tr_text = tr.get_text(" ", strip=True).lower()
        matched = None
        for key, cfg in LP_GAME_MAP.items():
            if key in tr_text and cfg["id"] not in seen:
                matched = cfg
                break
        if not matched:
            continue
        balls = [
            el.get_text(strip=True)
            for el in tr.find_all(["td", "li", "span"])
            if single_digit_re.match(el.get_text(strip=True))
        ]
        if len(balls) >= matched["digits"]:
            parsed = "-".join(balls[: matched["digits"]])
            results.append(
                {
                    "id": matched["id"],
                    "name": matched["name"],
                    "date": et_date_str,
                    "number": parsed,
                }
            )
            seen.add(matched["id"])
            print(f"  lotterypost [{matched['id']}] {matched['name']}: {parsed}")
    return results


def fetch_nj_picks_midday(date_str):
    """Fetch NJ Pick 3/4 midday results from RapidAPI AllState."""
    if not RAPIDAPI_KEY:
        print("  RapidAPI: no RAPIDAPI_KEY - skipping NJ midday")
        return []

    try:
        day, month, year = date_str.split("-")
        target_date_iso = f"{year}-{month}-{day}"
    except ValueError:
        return []

    headers = {
        "x-rapidapi-host": "usa-lottery-result-all-state-api.p.rapidapi.com",
        "x-rapidapi-key": RAPIDAPI_KEY,
        "User-Agent": "Mozilla/5.0",
    }
    game_map = {
        283: {"id": "19", "name": "NJ Pick 3 Dia", "digits": 3},
        285: {"id": "21", "name": "NJ Pick 4 Dia", "digits": 4},
    }
    results = []

    for game_id, game in game_map.items():
        try:
            draws_url = (
                "https://usa-lottery-result-all-state-api.p.rapidapi.com"
                f"/lottery-results/past-draws-dates?gameID={game_id}"
            )
            draws_req = urllib.request.Request(draws_url, headers=headers)
            draws_data = json.loads(urllib.request.urlopen(draws_req, timeout=10).read().decode())
            dates_list = (draws_data.get("data") or {}).get("date") or []

            draw_id = None
            for entry in dates_list:
                if entry.get("drawDate") == target_date_iso:
                    draw_id = entry.get("drawID")
                    break
            if not draw_id:
                print(f"  RapidAPI: no drawID for {game['name']} on {target_date_iso}")
                continue

            result_url = (
                "https://usa-lottery-result-all-state-api.p.rapidapi.com"
                f"/lottery-results/game-result?gameID={game_id}&drawID={draw_id}"
            )
            result_req = urllib.request.Request(result_url, headers=headers)
            result_data = json.loads(urllib.request.urlopen(result_req, timeout=10).read().decode())
            winning_numbers = (result_data.get("data") or {}).get("winningNumbers") or []
            digits = [str(n).zfill(1) for n in winning_numbers]
            if len(digits) != game["digits"]:
                print(f"  RapidAPI: unexpected numbers {winning_numbers} for {game['name']}")
                continue

            parsed = "-".join(digits)
            results.append(
                {
                    "id": game["id"],
                    "name": game["name"],
                    "date": date_str,
                    "number": parsed,
                }
            )
            print(f"  RapidAPI [{game['id']}] {game['name']}: {parsed}")
        except Exception as exc:
            print(f"  RapidAPI error for {game['name']}: {exc}")

    return results


def scrape_nj_picks(date_str=None):
    et_date_str = date_str or get_et_date_str()
    parts = et_date_str.split("-")
    iso_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
    results = []
    seen_ids = set()

    for game_id, draw_configs in NJ_PICK_MAP.items():
        url = (
            "https://www.njlottery.com/api/v1/draw-games/draws.json"
            f"?gameId={game_id}&numDraws=4"
        )
        try:
            resp = fetch_url(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible)",
                    "Accept": "application/json",
                },
            )
            data = json.loads(resp.read().decode())
            draws_list = (
                data.get("draws")
                or (data.get("drawGames") or {}).get("draws")
                or data.get("draw")
                or []
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
                            draw.get("numbers")
                            or draw.get("winningNumbers")
                            or draw.get("number")
                            or ""
                        )
                        digits = re.findall(r"\d", numbers_raw)
                        if len(digits) == cfg["digits"]:
                            parsed = "-".join(digits)
                            results.append(
                                {
                                    "id": cfg["id"],
                                    "name": cfg["name"],
                                    "date": et_date_str,
                                    "number": parsed,
                                }
                            )
                            seen_ids.add(cfg["id"])
                            print(f"  NJ API [{cfg['id']}] {cfg['name']}: {parsed}")
                            break
        except Exception as exc:
            print(f"  NJ API error for {game_id}: {exc}")

    missing = [
        cfg
        for configs in NJ_PICK_MAP.values()
        for cfg in configs
        if cfg["id"] not in seen_ids
    ]
    midday_ids = {"19", "21"}
    if any(cfg["id"] in midday_ids for cfg in missing):
        for row in fetch_nj_picks_midday(et_date_str):
            if row["id"] not in seen_ids:
                results.append(row)
                seen_ids.add(row["id"])

    missing = [
        cfg
        for configs in NJ_PICK_MAP.values()
        for cfg in configs
        if cfg["id"] not in seen_ids
    ]
    if missing:
        print(f"  NJ API missing {len(missing)} draws - trying lotterypost.com...")
        for row in scrape_nj_lotterypost(et_date_str):
            if row["id"] not in seen_ids:
                results.append(row)
                seen_ids.add(row["id"])

    return results


def fetch_blocks(url):
    try:
        html = fetch_url(url).read()
        soup = BeautifulSoup(html, "html.parser")
        return soup.find_all("div", class_="game-block")
    except Exception as exc:
        print(f"Error fetching {url}: {exc}")
        return []


def scrape(date_str=None):
    if not date_str:
        date_str = get_dr_date_str()

    base = "https://loteriasdominicanas.com"
    urls = [f"{base}/?date={date_str}", f"{base}/anguila?date={date_str}"]
    all_blocks = []
    for url in urls:
        all_blocks.extend(fetch_blocks(url))

    results = []
    seen_ids = set()
    expected_ddmm = date_str[:5]

    for block in all_blocks:
        try:
            date_el = block.find("div", class_="session-date")
            if date_el and date_el.get_text(strip=True) != expected_ddmm:
                continue

            title_el = block.find("a", "game-title")
            if not title_el:
                continue

            title = title_el.get_text().strip().lower()
            match = LOTTERY_MAP.get(title)
            if not match or match["id"] in seen_ids:
                continue

            scores = block.find_all("span", "score")
            numbers = [score.text.strip() for score in scores if score.text.strip()]
            if not numbers:
                continue

            results.append(
                {
                    "id": match["id"],
                    "name": match["name"],
                    "date": date_str,
                    "number": "-".join(numbers),
                }
            )
            seen_ids.add(match["id"])
        except Exception as exc:
            print(f"Parse error: {exc}")

    results.sort(key=lambda row: int(row["id"]))
    return results


def fetch_existing_from_supabase(date_str):
    import urllib.parse

    key = f"lot_results_cache_by_day:{date_str}"
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
    except Exception as exc:
        print(f"Warning: could not fetch existing results: {exc}")
    return []


def save_to_supabase(date_str, results):
    key = f"lot_results_cache_by_day:{date_str}"
    existing = fetch_existing_from_supabase(date_str)
    merged = {row["id"]: row for row in existing}
    for row in results:
        merged[row["id"]] = row
    merged_list = sorted(merged.values(), key=lambda row: int(row["id"]))

    payload = json.dumps(
        {
            "key": key,
            "value": json.dumps(merged_list, ensure_ascii=False),
            "upd": datetime.datetime.utcnow().isoformat() + "Z",
        }
    ).encode("utf-8")
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
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        print(f"Saved {len(merged_list)} results (merged) for {date_str} -> HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        print(f"Supabase error {exc.code}: {body}")


if __name__ == "__main__":
    today = get_dr_date_str()
    print(
        f"\n[RD] Scraping {today} "
        f"(DR time, UTC now={datetime.datetime.utcnow().strftime('%H:%M')})..."
    )
    rd_results = scrape(today)
    print(f"Found {len(rd_results)} RD lotteries")
    for row in rd_results:
        print(f"  [{row['id']}] {row['name']}: {row['number']}")

    if not SUPABASE_KEY:
        print("No SUPABASE_KEY - skipping save")
    elif not rd_results:
        print("No results found for today - skipping save (no draws yet or date mismatch)")
    else:
        save_to_supabase(today, rd_results)

    et_today = get_et_date_str()
    print(f"\n[NJ] Scraping Pick 3/4 for ET date {et_today}...")
    nj_results = scrape_nj_picks(et_today)
    print(f"Found {len(nj_results)} NJ picks")
    for row in nj_results:
        print(f"  [{row['id']}] {row['name']}: {row['number']}")

    if not SUPABASE_KEY:
        print("No SUPABASE_KEY - skipping NJ save")
    elif nj_results:
        save_to_supabase(et_today, nj_results)
    else:
        print("No NJ results yet - draws may not have occurred yet")
