"""
LotteryNet RD — Scraper → Supabase
Scrapea loteriasdominicanas.com y guarda en lotterynet_kv
key: lot_results_cache_by_day
"""
import os, json, datetime, urllib.parse, re, asyncio, logging
from zoneinfo import ZoneInfo
import httpx
from bs4 import BeautifulSoup

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://unhoulkujbtsypccpirc.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TRACKED_REMOTE_RESULT_IDS = {"23", "24", "27", "28"}
US_PICK_NORMAL_CATALOG_STATE_CODES = set()
US_PICK_URLS = {
    "pick3": "https://pick-3.com/winning-numbers",
    "pick4": "https://pick-4.com/winning-numbers",
}
US_PICK_NJ_HOME_URLS = {
    "pick3": "https://nj.pick-3.com/",
    "pick4": "https://nj.pick-4.com/",
}
US_PICK_HISTORY_PATHS = {
    "pick3": ["numbers", "winning-numbers", "results", ""],
    "pick4": ["winning-numbers", "numbers", "results", ""],
}
US_PICK_SOURCE_NAMES = {
    "pick3": "pick-3.com",
    "pick4": "pick-4.com",
}
US_PICK_SINGLE_DRAW_LABELS = {
    ("pick3", "LA"): "Day Draw",
    ("pick3", "MN"): "Day Draw",
    ("pick3", "NE"): "Day Draw",
    ("pick3", "OK"): "Day Draw",
    ("pick3", "WA"): "Day Draw",
    ("pick3", "WV"): "09:00 PM Draw",
}

US_PICK_SUNDAY_NO_DRAW_ROWS = [
    {"id": "US-P3-AR-CASH-3-MIDDAY", "state": "Arkansas", "stateCode": "AR", "game": "pick3", "gameName": "Cash 3", "draw": "Midday Draw"},
    {"id": "US-P3-SC-PICK-3-MIDDAY", "state": "South Carolina", "stateCode": "SC", "game": "pick3", "gameName": "Pick 3", "draw": "Midday Draw"},
    {"id": "US-P3-TX-PICK-3-DAY", "state": "Texas", "stateCode": "TX", "game": "pick3", "gameName": "Pick 3", "draw": "Day Draw"},
    {"id": "US-P3-TX-PICK-3-EVENING", "state": "Texas", "stateCode": "TX", "game": "pick3", "gameName": "Pick 3", "draw": "Evening Draw"},
    {"id": "US-P3-TX-PICK-3-MORNING", "state": "Texas", "stateCode": "TX", "game": "pick3", "gameName": "Pick 3", "draw": "Morning Draw"},
    {"id": "US-P3-TX-PICK-3-NIGHT", "state": "Texas", "stateCode": "TX", "game": "pick3", "gameName": "Pick 3", "draw": "Night Draw"},
    {"id": "US-P4-AR-CASH-4-MIDDAY", "state": "Arkansas", "stateCode": "AR", "game": "pick4", "gameName": "Cash 4", "draw": "Midday Draw"},
    {"id": "US-P4-SC-PICK-4-MIDDAY", "state": "South Carolina", "stateCode": "SC", "game": "pick4", "gameName": "Pick 4", "draw": "Midday Draw"},
    {"id": "US-P4-TN-CASH-4-DAY", "state": "Tennessee", "stateCode": "TN", "game": "pick4", "gameName": "Cash 4", "draw": "Day Draw"},
    {"id": "US-P4-TX-DAILY-4-DAY", "state": "Texas", "stateCode": "TX", "game": "pick4", "gameName": "Daily 4", "draw": "Day Draw"},
    {"id": "US-P4-TX-DAILY-4-EVENING", "state": "Texas", "stateCode": "TX", "game": "pick4", "gameName": "Daily 4", "draw": "Evening Draw"},
    {"id": "US-P4-TX-DAILY-4-MORNING", "state": "Texas", "stateCode": "TX", "game": "pick4", "gameName": "Daily 4", "draw": "Morning Draw"},
    {"id": "US-P4-TX-DAILY-4-NIGHT", "state": "Texas", "stateCode": "TX", "game": "pick4", "gameName": "Daily 4", "draw": "Night Draw"},
]

US_STATE_CODES = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "Florida": "FL",
    "Georgia": "GA",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington DC": "DC",
    "Washington": "WA",
    "DC": "DC",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}

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
    "king lottery 12:30":    {"id": "23", "name": "King Lottery D\u00eda"},
    "king lottery 7:30":     {"id": "24", "name": "King Lottery Noche"},
}

MILOTERIA_NJ_MAP = {
    "new jersey am": {"id": "25", "name": "New Jersey AM"},
    "new jersey pm": {"id": "26", "name": "New Jersey PM"},
}

AUTHORITATIVE_NJ_IDS = {"19", "20", "21", "22", "25", "26"}

KING_LOTTERY_STATUS_ROWS = [
    {"id": "23", "name": "King Lottery D\u00eda"},
    {"id": "24", "name": "King Lottery Noche"},
]

ENLOTERIA_RESULT_SOURCES = [
    {"url": "https://enloteria.com/resultados-anguilla-8am", "id": "29", "name": "Anguilla 8AM"},
    {"url": "https://enloteria.com/resultados-anguilla-9am", "id": "30", "name": "Anguilla 9AM"},
    {"url": "https://enloteria.com/resultados-anguilla-10am", "id": "2", "name": "Anguila Mañana", "source_name": "Anguilla 10AM"},
    {"url": "https://enloteria.com/resultados-anguilla-11am", "id": "31", "name": "Anguilla 11AM"},
    {"url": "https://enloteria.com/resultados-anguilla-12pm", "id": "32", "name": "Anguilla 12PM"},
    {"url": "https://enloteria.com/resultados-anguilla-1pm", "id": "4", "name": "Anguila Mediodía", "source_name": "Anguilla 1PM"},
    {"url": "https://enloteria.com/resultados-anguilla-2pm", "id": "33", "name": "Anguilla 2PM"},
    {"url": "https://enloteria.com/resultados-anguilla-3pm", "id": "34", "name": "Anguilla 3PM"},
    {"url": "https://enloteria.com/resultados-anguilla-4pm", "id": "35", "name": "Anguilla 4PM"},
    {"url": "https://enloteria.com/resultados-anguilla-5pm", "id": "36", "name": "Anguilla 5PM"},
    {"url": "https://enloteria.com/resultados-anguilla-6pm", "id": "11", "name": "Anguila Tarde", "source_name": "Anguilla 6PM"},
    {"url": "https://enloteria.com/resultados-anguilla-7pm", "id": "37", "name": "Anguilla 7PM"},
    {"url": "https://enloteria.com/resultados-anguilla-8pm", "id": "38", "name": "Anguilla 8PM"},
    {"url": "https://enloteria.com/resultados-anguilla-9pm", "id": "14", "name": "Anguila Noche", "source_name": "Anguilla 9PM"},
    {"url": "https://enloteria.com/resultados-anguilla-10pm", "id": "39", "name": "Anguilla 10PM"},
    {"url": "https://enloteria.com/resultados-haiti-bolet-9-30-am", "id": "40", "name": "Haiti Bolet 9:30 AM"},
    {"url": "https://enloteria.com/resultados-haiti-bolet-10-30-am", "id": "41", "name": "Haiti Bolet 10:30 AM"},
    {
        "url": "https://enloteria.com/resultados-haiti-bolet-11-30-am",
        "id": "27",
        "name": "Haiti Bolet 11:30 AM",
    },
    {
        "url": "https://enloteria.com/resultados-haiti-bolet-6-30-pm",
        "id": "28",
        "name": "Haiti Bolet 6:30 PM",
    },
    {"url": "https://enloteria.com/resultados-haiti-bolet-5-30-pm", "id": "42", "name": "Haiti Bolet 5:30 PM"},
    {"url": "https://enloteria.com/resultados-haiti-bolet-7-30-pm", "id": "43", "name": "Haiti Bolet 7:30 PM"},
    {"url": "https://enloteria.com/resultados-georgia-dia", "id": "44", "name": "Georgia Día"},
    {"url": "https://enloteria.com/resultados-georgia-tarde", "id": "45", "name": "Georgia Tarde"},
    {"url": "https://enloteria.com/resultados-georgia-noche", "id": "46", "name": "Georgia Noche"},
    {"url": "https://enloteria.com/resultados-new-jersey-tarde", "id": "25", "name": "New Jersey Tarde"},
    {"url": "https://enloteria.com/resultados-new-jersey-noche", "id": "26", "name": "New Jersey Noche"},
]

ENLOTERIA_HAITI_BOLET_SOURCES = [
    source for source in ENLOTERIA_RESULT_SOURCES
    if str(source["name"]).startswith("Haiti Bolet")
]

# ---------------------------------------------------------------------------
# Async infrastructure
# ---------------------------------------------------------------------------
logger = logging.getLogger("scraper")
_http_client = None
_RETRY_MAX = 3
_RETRY_BASE_DELAY = 1.0

def get_http_client():
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(25.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
        )
    return _http_client


async def close_http_client():
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def async_http_get(url, client=None, accept_json=False):
    c = client or get_http_client()
    headers = {"Accept": "application/json"} if accept_json else {}
    for attempt in range(1, _RETRY_MAX + 1):
        try:
            resp = await c.get(url, headers=headers)
            if resp.is_error:
                if 400 <= resp.status_code < 500:
                    resp.raise_for_status()
                resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if 400 <= status < 500:
                logger.debug("Client error %d fetching %s — not retrying", status, url)
                raise
            logger.warning("HTTP error fetching %s (attempt %d/%d): %s", url, attempt, _RETRY_MAX, exc)
            if attempt < _RETRY_MAX:
                await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** (attempt - 1)))
            else:
                raise
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            logger.warning("HTTP error fetching %s (attempt %d/%d): %s", url, attempt, _RETRY_MAX, exc)
            if attempt < _RETRY_MAX:
                await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** (attempt - 1)))
            else:
                raise


async def async_http_post(url, data_bytes, content_type="application/x-www-form-urlencoded; charset=UTF-8", client=None):
    c = client or get_http_client()
    headers = {"Content-Type": content_type}
    for attempt in range(1, _RETRY_MAX + 1):
        try:
            resp = await c.post(url, content=data_bytes, headers=headers)
            if resp.is_error:
                if 400 <= resp.status_code < 500:
                    resp.raise_for_status()
                resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if 400 <= status < 500:
                logger.debug("Client error %d POST %s — not retrying", status, url)
                raise
            logger.warning("HTTP POST error fetching %s (attempt %d/%d): %s", url, attempt, _RETRY_MAX, exc)
            if attempt < _RETRY_MAX:
                await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** (attempt - 1)))
            else:
                raise
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            logger.warning("HTTP POST error fetching %s (attempt %d/%d): %s", url, attempt, _RETRY_MAX, exc)
            if attempt < _RETRY_MAX:
                await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** (attempt - 1)))
            else:
                raise


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


def sync_run(coro):
    """Run an async coroutine synchronously. Safe for CLI scripts, Flask threads, and WSGI."""
    global _http_client
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _renew_http_client()
        return asyncio.run(coro)
    # Already in an event loop -- create a new one in a separate thread
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_run_with_fresh_client, coro).result()


def _renew_http_client():
    global _http_client
    if _http_client is not None:
        try:
            # Best-effort close — may fail if bound to a closed loop
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    _http_client = None
                    return
            except RuntimeError:
                _http_client = None
                return
        except Exception:
            pass
        _http_client = None


def _run_with_fresh_client(coro):
    _renew_http_client()
    return asyncio.run(coro)


def should_fail_without_supabase_key(supabase_key, env=None):
    """GitHub Actions must fail instead of reporting success without saving."""
    source_env = env if env is not None else os.environ
    return not bool(str(supabase_key or "").strip()) and source_env.get("GITHUB_ACTIONS") == "true"

def get_dr_now():
    """Current Dominican Republic time (AST / UTC-4)."""
    return datetime.datetime.utcnow() - datetime.timedelta(hours=4)

def get_et_date_str():
    """Today's date in US/Eastern timezone (proper DST handling)."""
    return datetime.datetime.now(ZoneInfo("America/New_York")).strftime("%d-%m-%Y")

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
    text = re.sub(r"^[A-Za-z]+,\s*", "", text)
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%m/%d/%Y %I:%M:%S %p"):
        try:
            parsed = datetime.datetime.strptime(text, fmt)
            return parsed.strftime("%d-%m-%Y")
        except ValueError:
            continue
    return ""

def parse_lotteryusa_date(raw):
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.datetime.strptime(text, "%b %d, %Y")
    except ValueError:
        return ""
    return parsed.strftime("%d-%m-%Y")


def slug_token(raw):
    text = str(raw or "").upper()
    text = re.sub(r"[^A-Z0-9]+", "-", text)
    return text.strip("-")


def normalize_us_pick_game(game):
    value = str(game or "").lower().replace("-", "")
    if value in ("pick3", "p3"):
        return "pick3"
    if value in ("pick4", "p4"):
        return "pick4"
    return ""


def build_us_pick_result_id(game, state_code, game_name, draw_label):
    normalized_game = normalize_us_pick_game(game)
    prefix = "P3" if normalized_game == "pick3" else "P4"
    draw = str(draw_label or "").replace(" Draw", "")
    return "-".join([
        "US",
        prefix,
        slug_token(state_code),
        slug_token(game_name),
        slug_token(draw),
    ])


# ── Extra pick sources (states not covered by pick-3.com / pick-4.com) ──

async def _async_fetch_wa_match4(target_date, client=None):
    """Washington Match 4 — single daily draw at 8PM PDT, sourced from lotteryusa.com."""
    url = "https://www.lotteryusa.com/washington/match-4/"
    c = client or get_http_client()
    try:
        resp = await async_http_get(url, client=c)
        html = resp.content
    except Exception as e:
        logger.warning("WA Match 4 error: %s", e)
        return []
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
        if len(balls) < 4:
            logger.warning("WA Match 4: incomplete row for %s", target_date)
            return []
        number = "-".join(balls[:4])
        result_id = "US-P4-WA-MATCH-4-EVENING"
        row_data = {
            "id": result_id,
            "state": "Washington",
            "stateCode": "WA",
            "game": "pick4",
            "gameName": "Match 4",
            "draw": "Evening Draw",
            "date": target_date,
            "number": number,
            "playTypes": ["straight"],
            "source": "lotteryusa.com",
        }
        logger.info("WA Match 4 [%s] %s: %s", result_id, target_date, number)
        return [row_data]
    logger.info("WA Match 4: no result for %s", target_date)
    return []


def parse_us_pick_draw_date(raw):
    text = str(raw or "").strip()
    match = re.search(r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{2})\s+(.+?Draw)", text)
    if not match:
        return "", ""
    try:
        parsed = datetime.datetime.strptime(match.group(1), "%d %b %y")
    except ValueError:
        return "", ""
    return parsed.strftime("%d-%m-%Y"), match.group(2).strip()


def parse_us_pick_date_only(raw):
    text = str(raw or "").strip()
    try:
        parsed = datetime.datetime.strptime(text, "%d %b %y")
    except ValueError:
        return ""
    return parsed.strftime("%d-%m-%Y")


def parse_us_pick_long_date(raw):
    text = str(raw or "").strip()
    text = re.sub(r"^[A-Za-z]+,\s*", "", text)
    try:
        parsed = datetime.datetime.strptime(text, "%B %d, %Y")
    except ValueError:
        return ""
    return parsed.strftime("%d-%m-%Y")


def parse_us_pick_history_date(raw, target_date):
    parsed = parse_us_pick_long_date(raw)
    if parsed:
        return parsed
    text = str(raw or "").strip()
    match = re.search(r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+([A-Za-z]+)\s+(\d{1,2})(?:,|\b)", text)
    if not match:
        return ""
    try:
        target_year = datetime.datetime.strptime(str(target_date), "%d-%m-%Y").year
        parsed = datetime.datetime.strptime(f"{match.group(1)} {match.group(2)} {target_year}", "%B %d %Y")
    except ValueError:
        return ""
    return parsed.strftime("%d-%m-%Y")


def find_us_pick_long_date(html_text):
    text = BeautifulSoup(str(html_text or ""), "html.parser").get_text(" ", strip=True)
    match = re.search(r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}\b", text)
    return parse_us_pick_long_date(match.group(0)) if match else ""


def split_us_pick_title(title):
    cleaned = re.sub(r"\s+Latest\s+Draws!?\s*$", "", str(title or "").strip(), flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    for state_name in sorted(US_STATE_CODES.keys(), key=len, reverse=True):
        if cleaned.lower().startswith(state_name.lower() + " "):
            return state_name, US_STATE_CODES[state_name], cleaned[len(state_name):].strip()
    return "", "", cleaned


def candidate_text_parts(node):
    return [part.strip() for part in node.get_text("|", strip=True).split("|") if part.strip()]


def find_pick_candidate_block(image):
    current = image
    for _ in range(0, 6):
        current = current.parent
        if not current:
            break
        parts = candidate_text_parts(current)
        if any("Check Numbers" in part for part in parts):
            return current
        if len([part for part in parts if re.fullmatch(r"\d{1,2}", part)]) >= 3:
            return current
    return image.parent


def parse_us_pick_overview(html_text, game):
    normalized_game = normalize_us_pick_game(game)
    digits = 3 if normalized_game == "pick3" else 4 if normalized_game == "pick4" else 0
    if not digits:
        return []
    soup = BeautifulSoup(str(html_text or ""), "html.parser")
    results = []
    seen_ids = set()
    for image in soup.find_all("img"):
        alt = image.get("alt") or ""
        if "Latest Draws" not in alt:
            continue
        state_name, state_code, game_name = split_us_pick_title(alt)
        if not state_code or state_code in US_PICK_NORMAL_CATALOG_STATE_CODES:
            continue
        block = find_pick_candidate_block(image)
        parts = candidate_text_parts(block)
        date_key = ""
        draw_label = ""
        for index, part in enumerate(parts):
            parsed_key, parsed_draw = parse_us_pick_draw_date(part)
            if parsed_key:
                date_key = parsed_key
                draw_label = parsed_draw
                break
            parsed_date = parse_us_pick_date_only(part)
            if parsed_date and index + 1 < len(parts) and "Draw" in parts[index + 1]:
                date_key = parsed_date
                draw_label = parts[index + 1]
                break
            if not draw_label and "Draw" in part:
                draw_label = part
        numbers = [part for part in parts if re.fullmatch(r"\d{1,2}", part)]
        if not draw_label or len(numbers) < digits:
            continue
        result_id = build_us_pick_result_id(normalized_game, state_code, game_name, draw_label)
        if result_id in seen_ids:
            continue
        seen_ids.add(result_id)
        results.append({
            "id": result_id,
            "state": "Washington DC" if state_code == "DC" and state_name == "DC" else state_name,
            "stateCode": state_code,
            "game": normalized_game,
            "gameName": game_name,
            "draw": draw_label,
            "date": date_key,
            "number": "-".join(numbers[:digits]),
            "playTypes": ["straight", "box"],
            "source": US_PICK_SOURCE_NAMES[normalized_game],
        })
    return sorted(results, key=lambda row: (row["state"], row["game"], row["draw"], row["gameName"]))


def parse_new_jersey_pick_home(html_text, game):
    normalized_game = normalize_us_pick_game(game)
    digits = 3 if normalized_game == "pick3" else 4 if normalized_game == "pick4" else 0
    if not digits:
        return []
    soup = BeautifulSoup(str(html_text or ""), "html.parser")
    date_node = soup.select_one(".resultsHome .date")
    date_key = parse_us_pick_long_date(date_node.get_text(" ", strip=True) if date_node else "")
    if not date_key:
        date_key = find_us_pick_long_date(html_text)
    game_name = "Pick 3" if normalized_game == "pick3" else "Pick 4"
    rows = []
    for box in soup.select(".resultsHome .result-box .box"):
        label_text = box.get_text(" ", strip=True)
        if re.search(r"\bMidday\b", label_text, re.I):
            draw_label = "Midday Draw"
        elif re.search(r"\bEvening\b", label_text, re.I):
            draw_label = "Evening Draw"
        else:
            continue
        numbers = []
        for ball in box.select(".resultBall"):
            classes = set(ball.get("class") or [])
            if "fireball" in classes:
                continue
            value = extract_pick_ball_value(ball)
            if re.fullmatch(r"\d{1,2}", value):
                numbers.append(value)
        if len(numbers) < digits:
            continue
        rows.append({
            "id": build_us_pick_result_id(normalized_game, "NJ", game_name, draw_label),
            "state": "New Jersey",
            "stateCode": "NJ",
            "game": normalized_game,
            "gameName": game_name,
            "draw": draw_label,
            "date": date_key,
            "number": "-".join(numbers[:digits]),
            "playTypes": ["straight", "box"],
            "source": US_PICK_SOURCE_NAMES[normalized_game],
        })
    if not rows:
        rows = parse_new_jersey_pick_marker_balls(soup, normalized_game, digits, date_key, game_name)
    return sorted(rows, key=lambda row: (row["state"], row["game"], row["draw"], row["gameName"]))


def extract_pick_ball_value(ball):
    text = ball.get_text("", strip=True)
    classes = set(ball.get("class") or [])
    if any(str(item).startswith("number-part-") for item in classes):
        match = re.search(r"\d", text)
        return match.group(0) if match else ""
    return text


def parse_new_jersey_pick_marker_balls(soup, normalized_game, digits, date_key, game_name):
    rows = []
    active_draw = ""
    active_numbers = []
    for ball in soup.select(".resultBall"):
        classes = set(ball.get("class") or [])
        if "middayDraw" in classes or "eveningDraw" in classes:
            if active_draw and len(active_numbers) >= digits:
                rows.append(build_new_jersey_pick_row(normalized_game, game_name, active_draw, date_key, active_numbers[:digits]))
            active_draw = "Midday Draw" if "middayDraw" in classes else "Evening Draw"
            active_numbers = []
            continue
        if not active_draw:
            continue
        value = extract_pick_ball_value(ball)
        if re.fullmatch(r"\d{1,2}", value):
            active_numbers.append(value)
    if active_draw and len(active_numbers) >= digits:
        rows.append(build_new_jersey_pick_row(normalized_game, game_name, active_draw, date_key, active_numbers[:digits]))
    return rows


def build_new_jersey_pick_row(normalized_game, game_name, draw_label, date_key, numbers):
    return {
        "id": build_us_pick_result_id(normalized_game, "NJ", game_name, draw_label),
        "state": "New Jersey",
        "stateCode": "NJ",
        "game": normalized_game,
        "gameName": game_name,
        "draw": draw_label,
        "date": date_key,
        "number": "-".join(numbers),
        "playTypes": ["straight", "box"],
        "source": US_PICK_SOURCE_NAMES[normalized_game],
    }


def normalize_pick_history_draw_label(raw):
    text = str(raw or "").strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return ""
    if re.fullmatch(r"(Midday|Morning|Day|Evening|Night)(?:\s+Draw)?", text, re.I):
        base = text.split()[0].capitalize()
        return f"{base} Draw"
    if re.fullmatch(r"\d{1,2}:\d{2}\s*(?:AM|PM)(?:\s+Draw)?", text, re.I):
        return re.sub(r"\s+Draw$", "", text, flags=re.I).upper().replace(" AM", " AM").replace(" PM", " PM") + " Draw"
    if text.lower() == "draw":
        return "Draw"
    return ""


def catalog_us_pick_draw_label(normalized_game, state_code, game_name, draw_label):
    code = str(state_code or "").upper()
    game = normalize_us_pick_game(normalized_game)
    label = str(draw_label or "").strip()
    if game == "pick3" and code == "DC" and label == "Day Draw":
        return "Midday Draw"
    if game == "pick3" and code == "TN" and label == "Evening Draw":
        return "06:28 PM Draw"
    return label


def build_us_pick_history_row(normalized_game, state_code, state_name, game_name, draw_label, date_key, numbers):
    draw_label = catalog_us_pick_draw_label(normalized_game, state_code, game_name, draw_label)
    return {
        "id": build_us_pick_result_id(normalized_game, state_code, game_name, draw_label),
        "state": "Washington DC" if state_code == "DC" and state_name == "DC" else state_name,
        "stateCode": state_code,
        "game": normalized_game,
        "gameName": game_name,
        "draw": draw_label,
        "date": date_key,
        "number": "-".join(numbers),
        "playTypes": ["straight", "box"],
        "source": US_PICK_SOURCE_NAMES[normalized_game],
    }


def parse_pick_history_marker_rows(container, normalized_game, state_code, state_name, game_name, date_key, digits):
    rows = []
    active_draw = ""
    active_numbers = []
    for ball in container.select(".resultBall"):
        classes = set(ball.get("class") or [])
        if "middayDraw" in classes or "morningDraw" in classes or "dayDraw" in classes or "eveningDraw" in classes or "nightDraw" in classes:
            if active_draw and len(active_numbers) >= digits:
                rows.append(build_us_pick_history_row(
                    normalized_game, state_code, state_name, game_name, active_draw, date_key, active_numbers[:digits],
                ))
            if "eveningDraw" in classes:
                active_draw = "Evening Draw"
            elif "nightDraw" in classes:
                active_draw = "Night Draw"
            elif "morningDraw" in classes:
                active_draw = "Morning Draw"
            elif "dayDraw" in classes:
                active_draw = "Day Draw"
            else:
                active_draw = "Midday Draw"
            active_numbers = []
            continue
        if not active_draw or "fireball" in classes:
            continue
        value = extract_pick_ball_value(ball)
        if re.fullmatch(r"\d{1,2}", value):
            active_numbers.append(value)
    if active_draw and len(active_numbers) >= digits:
        rows.append(build_us_pick_history_row(
            normalized_game, state_code, state_name, game_name, active_draw, date_key, active_numbers[:digits],
        ))
    return rows


def parse_pick_history_text_rows(container, normalized_game, state_code, state_name, game_name, date_key, digits):
    parts = candidate_text_parts(container)
    rows = []
    draw_label = ""
    numbers = []
    for part in parts:
        if parse_us_pick_long_date(part):
            continue
        normalized_draw = normalize_pick_history_draw_label(part)
        if normalized_draw:
            if draw_label and len(numbers) >= digits:
                rows.append(build_us_pick_history_row(
                    normalized_game, state_code, state_name, game_name, draw_label, date_key, numbers[:digits],
                ))
            draw_label = normalized_draw
            numbers = []
            continue
        if draw_label and re.fullmatch(r"\d{1,2}", part):
            numbers.append(part)
    if draw_label and len(numbers) >= digits:
        rows.append(build_us_pick_history_row(
            normalized_game, state_code, state_name, game_name, draw_label, date_key, numbers[:digits],
        ))
    return rows


def parse_pick_history_box_rows(container, normalized_game, state_code, state_name, game_name, date_key, digits):
    rows = []
    for box in container.select(".box"):
        draw_label = ""
        label_text = box.get_text(" ", strip=True)
        for candidate in ("Midday Draw", "Evening Draw", "Morning Draw", "Day Draw", "Night Draw", "Midday", "Evening"):
            if re.search(rf"\b{re.escape(candidate)}\b", label_text, re.I):
                draw_label = normalize_pick_history_draw_label(candidate)
                break
        if not draw_label:
            continue
        numbers = []
        for ball in box.select(".resultBall"):
            classes = set(ball.get("class") or [])
            if "fireball" in classes:
                continue
            value = extract_pick_ball_value(ball)
            if re.fullmatch(r"\d{1,2}", value):
                numbers.append(value)
        if len(numbers) >= digits:
            rows.append(build_us_pick_history_row(
                normalized_game, state_code, state_name, game_name, draw_label, date_key, numbers[:digits],
            ))
    return rows


def parse_pick_history_single_draw_rows(container, normalized_game, state_code, state_name, game_name, date_key, digits):
    draw_label = US_PICK_SINGLE_DRAW_LABELS.get((normalized_game, str(state_code or "").upper()))
    if not draw_label:
        return []
    numbers = []
    for ball in container.select(".resultBall"):
        classes = set(ball.get("class") or [])
        if "fireball" in classes:
            continue
        value = extract_pick_ball_value(ball)
        if re.fullmatch(r"\d{1,2}", value):
            numbers.append(value)
    if len(numbers) < digits:
        return []
    return [
        build_us_pick_history_row(
            normalized_game, state_code, state_name, game_name, draw_label, date_key, numbers[:digits],
        )
    ]


def parse_us_pick_history_page(html_text, game, state_code, state_name, game_name, target_date):
    normalized_game = normalize_us_pick_game(game)
    digits = 3 if normalized_game == "pick3" else 4 if normalized_game == "pick4" else 0
    if not digits:
        return []
    soup = BeautifulSoup(str(html_text or ""), "html.parser")
    containers = soup.select(".drawContainer, .resultsBox")
    rows_by_id = {}
    for container in containers:
        date_key = ""
        for part in candidate_text_parts(container):
            date_key = parse_us_pick_history_date(part, target_date)
            if date_key:
                break
        if date_key != target_date:
            continue
        rows = []
        rows.extend(parse_pick_history_marker_rows(
            container, normalized_game, state_code, state_name, game_name, date_key, digits,
        ))
        rows.extend(parse_pick_history_box_rows(
            container, normalized_game, state_code, state_name, game_name, date_key, digits,
        ))
        rows.extend(parse_pick_history_text_rows(
            container, normalized_game, state_code, state_name, game_name, date_key, digits,
        ))
        if not rows:
            rows = parse_pick_history_single_draw_rows(
                container, normalized_game, state_code, state_name, game_name, date_key, digits,
            )
        for row in rows:
            rows_by_id[row["id"]] = row
    return sorted(rows_by_id.values(), key=lambda row: (row["state"], row["game"], row["draw"], row["gameName"]))


async def _async_fetch_new_jersey_pick_home(game, client=None):
    normalized_game = normalize_us_pick_game(game)
    url = US_PICK_NJ_HOME_URLS.get(normalized_game)
    if not url:
        return []
    c = client or get_http_client()
    try:
        resp = await async_http_get(url, client=c)
        html = resp.text
    except Exception as e:
        logger.warning("NJ Pick error for %s: %s", normalized_game, e)
        return []
    return parse_new_jersey_pick_home(html, normalized_game)


def fetch_new_jersey_pick_home(game):
    return sync_run(_async_fetch_new_jersey_pick_home(game))


def us_pick_history_url_candidates(game, state_code):
    normalized_game = normalize_us_pick_game(game)
    domain = "pick-3.com" if normalized_game == "pick3" else "pick-4.com"
    code = str(state_code or "").lower()
    urls = []
    for path in US_PICK_HISTORY_PATHS.get(normalized_game, []):
        suffix = f"/{path}" if path else "/"
        urls.append(f"https://{code}.{domain}{suffix}")
    return urls


async def _async_fetch_us_pick_state_history(game, state_code, state_name, game_name, target_date, client=None):
    normalized_game = normalize_us_pick_game(game)
    c = client or get_http_client()
    for url in us_pick_history_url_candidates(normalized_game, state_code):
        try:
            resp = await async_http_get(url, client=c)
            html = resp.text
        except Exception:
            continue
        rows = parse_us_pick_history_page(
            html,
            game=normalized_game,
            state_code=state_code,
            state_name=state_name,
            game_name=game_name,
            target_date=target_date,
        )
        if rows:
            return rows
    return []


async def _async_fetch_us_pick_overview(game, client=None):
    normalized_game = normalize_us_pick_game(game)
    url = US_PICK_URLS.get(normalized_game)
    if not url:
        return []
    c = client or get_http_client()
    try:
        resp = await async_http_get(url, client=c)
        html = resp.text
    except Exception as e:
        logger.warning("US Pick error for %s: %s", normalized_game, e)
        return []
    return parse_us_pick_overview(html, normalized_game)


def fetch_us_pick_state_history(game, state_code, state_name, game_name, target_date):
    return sync_run(_async_fetch_us_pick_state_history(game, state_code, state_name, game_name, target_date))


def fetch_us_pick_overview(game):
    return sync_run(_async_fetch_us_pick_overview(game))


async def _async_scrape_us_picks(date_str=None, games=None, existing_rows=None, client=None):
    _ = existing_rows  # kept for API compat; scraper always fetches fresh
    target_date = date_str or get_dr_date_str()
    c = client or get_http_client()
    rows_by_id = {}
    game_list = games or ("pick3", "pick4")

    async def _process_game(game):
        game_rows_by_id = {}
        overview_rows = await _async_fetch_us_pick_overview(game, client=c)
        if target_date:
            history_keys = set()
            state_rows = {}
            overview_rows_by_id = {}
            for row in overview_rows:
                state_key = (row.get("stateCode"), row.get("gameName"))
                state_rows[state_key] = row
                if row.get("id"):
                    overview_rows_by_id[row["id"]] = row

            # Fetch all state history pages in parallel
            history_tasks = []
            for row in state_rows.values():
                history_tasks.append(
                    _async_fetch_us_pick_state_history(
                        game,
                        row.get("stateCode"),
                        row.get("state"),
                        row.get("gameName"),
                        target_date,
                        client=c,
                    )
                )
            nj_home_task = _async_fetch_new_jersey_pick_home(game, client=c)
            nj_lotteryusa_task = _async_fetch_nj_picks_lotteryusa(target_date, client=c)
            state_history_results, nj_rows, nj_lotteryusa_rows = await asyncio.gather(
                asyncio.gather(*history_tasks),
                nj_home_task,
                nj_lotteryusa_task,
            )

            for row in state_rows.values():
                state_key = (row.get("stateCode"), row.get("gameName"))

            for history_rows in state_history_results:
                for history_row in history_rows:
                    game_rows_by_id[history_row["id"]] = history_row
                    # Only mark key when history row matches target date;
                    # otherwise overview fallback will fill in
                    if history_row.get("date") == target_date:
                        key = (history_row.get("stateCode"), history_row.get("gameName"))
                        if history_row.get("stateCode"):
                            history_keys.add(key)

            for nj_row in nj_rows:
                if nj_row.get("date") == target_date:
                    history_keys.add((nj_row.get("stateCode"), nj_row.get("gameName")))
                    game_rows_by_id[nj_row["id"]] = nj_row

            for nj_row in nj_lotteryusa_rows:
                if nj_row.get("date") != target_date:
                    continue
                previous = game_rows_by_id.get(nj_row["id"]) or overview_rows_by_id.get(nj_row["id"]) or {}
                state_code = str(previous.get("stateCode", "")).strip()
                game_name = str(previous.get("gameName", "")).strip()
                if state_code:
                    history_keys.add((state_code, game_name))
                merged = dict(previous)
                merged.update(nj_row)
                game_rows_by_id[nj_row["id"]] = enrich_us_pick_result_row(merged)

            for row in overview_rows:
                state_key = (row.get("stateCode"), row.get("gameName"))
                if state_key not in history_keys:
                    row["date"] = target_date
                    game_rows_by_id[row["id"]] = row

            # Extra states not listed in overview but with working subdomains
            extra_states = {"pick3": {"NH"}, "pick4": set()}
            norm_game = normalize_us_pick_game(game)
            for extra_sc in extra_states.get(norm_game, set()):
                extra_rows = await _async_fetch_us_pick_state_history(
                    norm_game, extra_sc, "", "", target_date, client=c,
                )
                for er in extra_rows:
                    if er.get("date") == target_date:
                        game_rows_by_id[er["id"]] = er

            # WA Match 4 — single evening draw sourced from lotteryusa.com
            if norm_game == "pick4":
                for wr in await _async_fetch_wa_match4(target_date, client=c):
                    game_rows_by_id[wr["id"]] = wr

            missing_ids = sorted(
                result_id
                for result_id, row in game_rows_by_id.items()
                if not str(row.get("number", "")).strip()
            )
            if missing_ids:
                for fallback_row in await _async_fetch_lotteryusa_pick_fallbacks(
                    target_date,
                    ids=missing_ids,
                    client=c,
                ):
                    previous = game_rows_by_id.get(fallback_row["id"]) or {}
                    merged = dict(previous)
                    merged.update(fallback_row)
                    merged["source"] = "lotteryusa.com"
                    game_rows_by_id[fallback_row["id"]] = enrich_us_pick_result_row(merged)
        else:
            for row in overview_rows:
                game_rows_by_id[row["id"]] = row
            for row in await _async_fetch_new_jersey_pick_home(game, client=c):
                game_rows_by_id[row["id"]] = row

        return game_rows_by_id

    # Process both games in parallel
    game_results = await asyncio.gather(*[_process_game(g) for g in game_list])
    for gr in game_results:
        rows_by_id.update(gr)

    rows = list(rows_by_id.values())
    if target_date:
        rows = [row for row in rows if row.get("date") == target_date]
        append_us_pick_calendar_no_draw_rows(rows, target_date)
    return sorted(rows, key=lambda row: (row["state"], row["game"], row["draw"], row["gameName"]))


def scrape_us_picks(date_str=None, games=None, existing_rows=None):
    return sync_run(_async_scrape_us_picks(date_str, games=games, existing_rows=existing_rows))


def append_us_pick_calendar_no_draw_rows(rows, target_date):
    try:
        selected_day = datetime.datetime.strptime(str(target_date), "%d-%m-%Y").date()
    except ValueError:
        return
    if selected_day.weekday() != 6:
        return
    existing_ids = {str(row.get("id", "")) for row in rows}
    for source in US_PICK_SUNDAY_NO_DRAW_ROWS:
        if source["id"] in existing_ids:
            continue
        row = dict(source)
        row["date"] = target_date
        row["number"] = ""
        row["status"] = "no_draw"
        row["source"] = "calendar"
        row["playTypes"] = ["straight", "box"]
        rows.append(row)
        existing_ids.add(row["id"])


def iso_date_to_dr_date(raw):
    text = str(raw or "").strip()
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        return ""
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"


def recent_dr_dates(date_str, days_back=2):
    try:
        start = datetime.datetime.strptime(str(date_str), "%d-%m-%Y")
    except ValueError:
        return [date_str]
    return [
        (start - datetime.timedelta(days=offset)).strftime("%d-%m-%Y")
        for offset in range(0, int(days_back) + 1)
    ]


def parse_dr_date_key(date_str):
    try:
        return datetime.datetime.strptime(str(date_str), "%d-%m-%Y").date()
    except ValueError:
        return None


def build_king_no_draw_rows(date_str, seen_ids, now_dr=None):
    """Mark past King dates as no_draw when the source never published that date.

    loteriasdominicanas sometimes serves stale King blocks from a prior date.
    We prefer an explicit no_draw status over saving stale numbers under a new day.
    """
    requested = parse_dr_date_key(date_str)
    current = (now_dr or get_dr_now()).date()
    if not requested or requested >= current:
        return []
    rows = []
    for lottery in KING_LOTTERY_STATUS_ROWS:
        if lottery["id"] in seen_ids:
            continue
        rows.append({
            "id": lottery["id"],
            "name": lottery["name"],
            "date": date_str,
            "number": "",
            "status": "no_draw",
            "source": "no_draw",
        })
    return rows


def parse_winning_numbers_from_text(raw):
    text = str(raw or "")
    match = re.search(r"N[uú]meros ganadores:\s*([0-9]{1,2})\s*,\s*([0-9]{1,2})\s*,\s*([0-9]{1,2})", text, re.I)
    if not match:
        return []
    return [part.zfill(2) for part in match.groups()]


SPANISH_MONTHS = {
    "enero": "01",
    "febrero": "02",
    "marzo": "03",
    "abril": "04",
    "mayo": "05",
    "junio": "06",
    "julio": "07",
    "agosto": "08",
    "septiembre": "09",
    "setiembre": "09",
    "octubre": "10",
    "noviembre": "11",
    "diciembre": "12",
}


def parse_enloteria_spanish_date(raw):
    text = str(raw or "").strip().lower()
    match = re.search(r"(\d{1,2})\s+de\s+([a-záéíóúñ]+),\s*(\d{4})", text, re.I)
    if not match:
        return ""
    month = SPANISH_MONTHS.get(match.group(2))
    if not month:
        return ""
    return f"{int(match.group(1)):02d}-{month}-{match.group(3)}"


def parse_enloteria_result_dom_for_dates(html_text, lottery_id, lottery_name, target_dates, source_name=None):
    allowed_dates = [str(date) for date in target_dates if str(date or "").strip()]
    expected_name = str(source_name or lottery_name).lower()
    soup = BeautifulSoup(str(html_text or ""), "html.parser")
    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    for heading in headings:
        if heading.get_text(" ", strip=True).lower() != expected_name:
            continue
        parent = heading.parent
        if not parent:
            continue
        parts = [part.strip() for part in parent.get_text("|", strip=True).split("|") if part.strip()]
        result_date = ""
        for part in parts:
            parsed = parse_enloteria_spanish_date(part)
            if parsed:
                result_date = parsed
                break
        if result_date not in allowed_dates:
            continue
        numbers = [
            part.zfill(2)
            for part in parts
            if re.fullmatch(r"\d{1,2}", part)
        ]
        if len(numbers) < 3:
            continue
        return {
            "id": lottery_id,
            "name": lottery_name,
            "date": result_date,
            "number": "-".join(numbers[:3]),
        }
    return None


def parse_enloteria_haiti_bolet_dom_for_dates(html_text, lottery_id, lottery_name, target_dates):
    return parse_enloteria_result_dom_for_dates(html_text, lottery_id, lottery_name, target_dates)


def iter_enloteria_jsonld_objects(html_text):
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        str(html_text or ""),
        re.I | re.S,
    ):
        raw_json = match.group(1).strip()
        if not raw_json:
            continue
        try:
            yield json.loads(raw_json)
        except Exception:
            continue


def parse_enloteria_haiti_bolet_jsonld(html_text, lottery_id, lottery_name, target_date):
    return parse_enloteria_haiti_bolet_jsonld_for_dates(
        html_text,
        lottery_id=lottery_id,
        lottery_name=lottery_name,
        target_dates=[target_date],
    )


def parse_enloteria_result_jsonld_for_dates(html_text, lottery_id, lottery_name, target_dates, source_name=None):
    allowed_dates = [str(date) for date in target_dates if str(date or "").strip()]
    expected_name = str(source_name or lottery_name).lower()
    for data in iter_enloteria_jsonld_objects(html_text):
        graph = data.get("@graph") if isinstance(data, dict) else None
        nodes = graph if isinstance(graph, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("@type") != "Event":
                continue
            if str(node.get("name", "")).strip().lower() != expected_name:
                continue
            result_date = iso_date_to_dr_date(node.get("startDate"))
            if result_date not in allowed_dates:
                continue
            numbers = parse_winning_numbers_from_text(node.get("description"))
            if len(numbers) != 3:
                continue
            return {
                "id": lottery_id,
                "name": lottery_name,
                "date": result_date,
                "number": "-".join(numbers),
            }
    return parse_enloteria_result_dom_for_dates(
        html_text,
        lottery_id=lottery_id,
        lottery_name=lottery_name,
        target_dates=target_dates,
        source_name=source_name,
    )


def parse_enloteria_haiti_bolet_jsonld_for_dates(html_text, lottery_id, lottery_name, target_dates):
    return parse_enloteria_result_jsonld_for_dates(
        html_text,
        lottery_id=lottery_id,
        lottery_name=lottery_name,
        target_dates=target_dates,
    )


async def _async_fetch_enloteria_results(date_str=None, fallback_days=0, sources=None, client=None):
    target_date = date_str or get_dr_date_str()
    target_dates = recent_dr_dates(target_date, days_back=fallback_days)
    c = client or get_http_client()
    source_list = sources or ENLOTERIA_RESULT_SOURCES

    async def _fetch_one(source):
        try:
            resp = await async_http_get(source["url"], client=c)
            html = resp.text
        except Exception as e:
            logger.warning("EnLoteria error for %s: %s", source["name"], e)
            return None
        row = parse_enloteria_result_jsonld_for_dates(
            html,
            lottery_id=source["id"],
            lottery_name=source["name"],
            target_dates=target_dates,
            source_name=source.get("source_name"),
        )
        if row:
            logger.info("EnLoteria [%s] %s (%s): %s", row['id'], row['name'], row['date'], row['number'])
        else:
            logger.info("EnLoteria: no recent result for %s on %s", source["name"], ", ".join(target_dates))
        return row

    all_results = await asyncio.gather(*[_fetch_one(s) for s in source_list])
    return [r for r in all_results if r is not None]


async def _async_fetch_lotteryusa_results(url, lottery_id, lottery_name, digits, target_date, client=None):
    c = client or get_http_client()
    try:
        resp = await async_http_get(url, client=c)
        html = resp.content
    except Exception as e:
        logger.warning("Lottery USA error for %s: %s", lottery_name, e)
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
            logger.warning("Lottery USA: incomplete row for %s on %s", lottery_name, target_date)
            return None

        number = "-".join(balls[:digits])
        logger.info("Lottery USA [%s] %s: %s", lottery_id, lottery_name, number)
        return {
            "id": lottery_id,
            "name": lottery_name,
            "date": target_date,
            "number": number,
        }

    logger.info("Lottery USA: no result for %s on %s", lottery_name, target_date)
    return None


async def _async_fetch_nj_picks_lotteryusa(date_str=None, client=None):
    target_date = date_str or get_et_date_str()
    c = client or get_http_client()
    sources = [
        ("https://www.lotteryusa.com/new-jersey/midday-pick-3/", "19", "NJ Pick 3 Día", 3),
        ("https://www.lotteryusa.com/new-jersey/pick-3/", "20", "NJ Pick 3 Noche", 3),
        ("https://www.lotteryusa.com/new-jersey/midday-pick-4/", "21", "NJ Pick 4 Día", 4),
        ("https://www.lotteryusa.com/new-jersey/pick-4/", "22", "NJ Pick 4 Noche", 4),
    ]
    all_results = await asyncio.gather(*[
        _async_fetch_lotteryusa_results(url, lid, lname, digits, target_date, client=c)
        for url, lid, lname, digits in sources
    ])
    return [r for r in all_results if r is not None]


LOTTERYUSA_PICK_FALLBACK_SOURCES = {
    "US-P3-AZ-PICK-3-DRAW": {
        "url": "https://www.lotteryusa.com/arizona/pick-3/",
        "name": "Arizona Pick 3",
        "digits": 3,
        "state": "Arizona",
        "stateCode": "AZ",
        "game": "pick3",
        "gameName": "Pick 3",
        "draw": "Draw",
    },
    "US-P3-OK-PICK-3-DAY": {
        "url": "https://www.lotteryusa.com/oklahoma/pick-3/",
        "name": "Oklahoma Pick 3",
        "digits": 3,
        "state": "Oklahoma",
        "stateCode": "OK",
        "game": "pick3",
        "gameName": "Pick 3",
        "draw": "Day Draw",
    },
    "US-P3-NE-PICK-3-DAY": {
        "url": "https://www.lotteryusa.com/nebraska/pick-3/",
        "name": "Nebraska Pick 3",
        "digits": 3,
        "state": "Nebraska",
        "stateCode": "NE",
        "game": "pick3",
        "gameName": "Pick 3",
        "draw": "Day Draw",
    },
    "US-P4-CT-PLAY-4-EVENING": {
        "url": "https://www.lotteryusa.com/connecticut/play-4/",
        "name": "Connecticut Play 4 Evening",
        "digits": 4,
        "state": "Connecticut",
        "stateCode": "CT",
        "game": "pick4",
        "gameName": "Play 4",
        "draw": "Evening Draw",
    },
    "US-P4-FL-PICK-4-EVENING": {
        "url": "https://www.lotteryusa.com/florida/pick-4/",
        "name": "Florida Pick 4 Evening",
        "digits": 4,
        "state": "Florida",
        "stateCode": "FL",
        "game": "pick4",
        "gameName": "Pick 4",
        "draw": "Evening Draw",
    },
    "US-P4-IL-PICK-4-EVENING": {
        "url": "https://www.lotteryusa.com/illinois/daily-4/",
        "name": "Illinois Pick 4 Evening",
        "digits": 4,
        "state": "Illinois",
        "stateCode": "IL",
        "game": "pick4",
        "gameName": "Pick 4",
        "draw": "Evening Draw",
    },
    "US-P4-IN-DAILY-4-EVENING": {
        "url": "https://www.lotteryusa.com/indiana/daily-4/",
        "name": "Indiana Daily 4 Evening",
        "digits": 4,
        "state": "Indiana",
        "stateCode": "IN",
        "game": "pick4",
        "gameName": "Daily 4",
        "draw": "Evening Draw",
    },
    "US-P4-MS-CASH-4-EVENING": {
        "url": "https://www.lotteryusa.com/mississippi/cash-4/",
        "name": "Mississippi Cash 4 Evening",
        "digits": 4,
        "state": "Mississippi",
        "stateCode": "MS",
        "game": "pick4",
        "gameName": "Cash 4",
        "draw": "Evening Draw",
    },
    "US-P4-MO-PICK-4-EVENING": {
        "url": "https://www.lotteryusa.com/missouri/pick-4/",
        "name": "Missouri Pick 4 Evening",
        "digits": 4,
        "state": "Missouri",
        "stateCode": "MO",
        "game": "pick4",
        "gameName": "Pick 4",
        "draw": "Evening Draw",
    },
    "US-P4-NC-PICK-4-EVENING": {
        "url": "https://www.lotteryusa.com/north-carolina/pick-4/",
        "name": "North Carolina Pick 4 Evening",
        "digits": 4,
        "state": "North Carolina",
        "stateCode": "NC",
        "game": "pick4",
        "gameName": "Pick 4",
        "draw": "Evening Draw",
    },
    "US-P4-NE-PICK-4-DAY": {
        "url": "https://www.lotteryusa.com/nebraska/pick-4/",
        "name": "Nebraska Pick 4",
        "digits": 4,
        "state": "Nebraska",
        "stateCode": "NE",
        "game": "pick4",
        "gameName": "Pick 4",
        "draw": "Day Draw",
    },
    "US-P4-TX-DAILY-4-NIGHT": {
        "url": "https://www.lotteryusa.com/texas/daily-4/",
        "name": "Texas Daily 4 Night",
        "digits": 4,
        "state": "Texas",
        "stateCode": "TX",
        "game": "pick4",
        "gameName": "Daily 4",
        "draw": "Night Draw",
    },
    "US-P4-VA-PICK-4-EVENING": {
        "url": "https://www.lotteryusa.com/virginia/pick-4/",
        "name": "Virginia Pick 4 Evening",
        "digits": 4,
        "state": "Virginia",
        "stateCode": "VA",
        "game": "pick4",
        "gameName": "Pick 4",
        "draw": "Evening Draw",
    },
}

US_PICK_STATIC_RESULT_METADATA = {
    "19": {"state": "New Jersey", "stateCode": "NJ", "game": "pick3", "gameName": "Pick 3", "draw": "Midday Draw"},
    "20": {"state": "New Jersey", "stateCode": "NJ", "game": "pick3", "gameName": "Pick 3", "draw": "Evening Draw"},
    "21": {"state": "New Jersey", "stateCode": "NJ", "game": "pick4", "gameName": "Pick 4", "draw": "Midday Draw"},
    "22": {"state": "New Jersey", "stateCode": "NJ", "game": "pick4", "gameName": "Pick 4", "draw": "Evening Draw"},
}


def enrich_us_pick_result_row(row):
    result_id = str(row.get("id", "")).strip()
    if not result_id:
        return row
    metadata = dict(US_PICK_STATIC_RESULT_METADATA.get(result_id) or {})
    fallback = LOTTERYUSA_PICK_FALLBACK_SOURCES.get(result_id) or {}
    for field in ("state", "stateCode", "game", "gameName", "draw", "name"):
        if field in fallback:
            metadata[field] = fallback[field]
    enriched = dict(metadata)
    enriched.update(row)
    enriched.setdefault("playTypes", ["straight", "box"])
    return enriched


async def _async_fetch_lotteryusa_pick_fallbacks(date_str=None, ids=None, client=None):
    target_date = date_str or get_et_date_str()
    selected_ids = {str(item).strip() for item in (ids or []) if str(item).strip()}
    sources = []
    for result_id, source in LOTTERYUSA_PICK_FALLBACK_SOURCES.items():
        if selected_ids and result_id not in selected_ids:
            continue
        sources.append(
            _async_fetch_lotteryusa_results(
                source["url"],
                result_id,
                source["name"],
                source["digits"],
                target_date,
                client=client,
            )
        )
    if not sources:
        return []
    rows = await asyncio.gather(*sources)
    return [row for row in rows if row is not None]


async def _async_fetch_miloteria_new_jersey(date_str=None, client=None):
    target_date = date_str or get_dr_date_str()
    c = client or get_http_client()
    payload = urllib.parse.urlencode({"zonaHorariaUsuario": "America/Santo_Domingo"}).encode("utf-8")
    try:
        resp = await async_http_post("https://www.miloteria.net/api/v1/draws.php", payload, client=c)
        data = resp.json()
    except Exception as e:
        logger.warning("MiLoteria NJ error: %s", e)
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
        logger.info("MiLoteria [%s] %s: %s", row['id'], row['name'], row['number'])
    return results


def fetch_enloteria_results(date_str=None, fallback_days=0, sources=None):
    return sync_run(_async_fetch_enloteria_results(date_str, fallback_days, sources))


def fetch_enloteria_haiti_bolet(date_str=None, fallback_days=2):
    return sync_run(_async_fetch_enloteria_results(
        date_str=date_str,
        fallback_days=fallback_days,
        sources=ENLOTERIA_HAITI_BOLET_SOURCES,
    ))


def fetch_nj_picks_lotteryusa(date_str=None):
    return sync_run(_async_fetch_nj_picks_lotteryusa(date_str))


def fetch_miloteria_new_jersey(date_str=None):
    return sync_run(_async_fetch_miloteria_new_jersey(date_str))


async def _async_fetch_blocks(url, client):
    try:
        resp = await async_http_get(url, client=client)
        soup = BeautifulSoup(resp.text, "html.parser")
        return soup.find_all("div", class_="game-block")
    except Exception as e:
        logger.warning("Error fetching %s: %s", url, e)
        return []


async def _async_scrape(date_str=None, client=None):
    if not date_str:
        date_str = get_dr_date_str()
    c = client or get_http_client()

    base = "https://loteriasdominicanas.com"
    urls = [
        f"{base}/?date={date_str}",
        f"{base}/anguila?date={date_str}",
        f"{base}/king-lottery?date={date_str}",
    ]

    block_results = await asyncio.gather(*[_async_fetch_blocks(u, c) for u in urls])
    all_blocks = [b for blocks in block_results for b in blocks]

    results = []
    seen_ids = set()
    expected_ddmm = date_str[:5]

    for block in all_blocks:
        try:
            date_el = block.find("div", class_="session-date")
            if date_el:
                block_ddmm = date_el.get_text(strip=True)
                if block_ddmm != expected_ddmm:
                    continue

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
                "id": match["id"],
                "name": match["name"],
                "date": date_str,
                "number": "-".join(numbers),
            })
            seen_ids.add(match["id"])
        except Exception as e:
            logger.warning("Parse error: %s", e)
            continue

    for row in build_king_no_draw_rows(date_str, seen_ids):
        results.append(row)
        seen_ids.add(row["id"])
        logger.info("King [%s] %s: no_draw for %s", row['id'], row['name'], date_str)

    nj_nj = await _async_fetch_nj_picks_lotteryusa(date_str, client=c)
    for row in nj_nj:
        if row["id"] not in seen_ids:
            results.append(row)
            seen_ids.add(row["id"])

    miloteria_nj = await _async_fetch_miloteria_new_jersey(date_str, client=c)
    for row in miloteria_nj:
        if row["id"] not in seen_ids:
            results.append(row)
            seen_ids.add(row["id"])

    enloteria_rows = await _async_fetch_enloteria_results(date_str, fallback_days=0, client=c)
    for row in enloteria_rows:
        if row["id"] not in seen_ids:
            results.append(row)
            seen_ids.add(row["id"])

    results.sort(key=lambda x: int(x["id"]))
    return results


def fetch_blocks(url):
    try:
        return sync_run(_async_fetch_single_block(url))
    except Exception as e:
        logger.warning("Error fetching %s: %s", url, e)
        return []


async def _async_fetch_single_block(url):
    c = get_http_client()
    try:
        resp = await async_http_get(url, client=c)
        soup = BeautifulSoup(resp.text, "html.parser")
        return soup.find_all("div", class_="game-block")
    except Exception:
        return []


def scrape(date_str=None):
    return sync_run(_async_scrape(date_str))

async def _async_fetch_kv_list(key, client=None):
    params = urllib.parse.urlencode({"key": f"eq.{key}", "select": "value"})
    url = f"{SUPABASE_URL}/rest/v1/lotterynet_kv?{params}"
    c = client or get_http_client()
    if not SUPABASE_KEY.strip():
        return []
    try:
        resp = await c.get(url, headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        })
        resp.raise_for_status()
        rows = resp.json()
        if rows and rows[0].get("value"):
            existing = rows[0]["value"]
            if isinstance(existing, str):
                existing = json.loads(existing)
            if isinstance(existing, list):
                return existing
    except Exception as e:
        logger.warning("Could not fetch existing cache for %s: %s", key, e)
    return []


async def _async_fetch_existing_from_supabase(date_str, client=None):
    key = f"lot_results_cache_by_day:{date_str}"
    return await _async_fetch_kv_list(key, client=client)


def fetch_existing_from_supabase(date_str):
    return sync_run(_async_fetch_existing_from_supabase(date_str))


def pick_results_cache_key(date_str):
    return f"pick_results_cache_by_day:{date_str}"


async def _async_fetch_existing_pick_results_from_supabase(date_str, client=None):
    return await _async_fetch_kv_list(pick_results_cache_key(date_str), client=client)


def _pick_result_quality(row):
    number = str(row.get("number", "")).strip()
    status = str(row.get("status", "")).strip().lower()
    if number:
        return (3, len(number))
    if status and status != "pending":
        return (2, 0)
    if status == "pending":
        return (1, 0)
    return (0, 0)


def merge_us_pick_results_by_id(existing, results, observed_at=None):
    observed = observed_at or utc_now_iso()
    merged = {str(r["id"]): dict(r) for r in existing if str(r.get("id", "")).strip()}
    for r in results:
        key = str(r.get("id", "")).strip()
        if not key:
            continue
        previous = merged.get(key) or {}
        candidate = dict(r)
        if previous and _pick_result_quality(previous) > _pick_result_quality(candidate):
            preserved = dict(previous)
            preserved["lastSeenAt"] = observed
            merged[key] = preserved
            continue
        same_result = (
            str(previous.get("number", "")) == str(candidate.get("number", "")) and
            str(previous.get("status", "")) == str(candidate.get("status", ""))
        )
        if same_result and previous.get("firstSeenAt"):
            candidate["firstSeenAt"] = previous["firstSeenAt"]
        else:
            candidate["firstSeenAt"] = observed
        candidate["lastSeenAt"] = observed
        merged[key] = candidate
    return sorted(merged.values(), key=lambda row: row.get("id", ""))


async def _async_save_us_picks_to_supabase(date_str, rows, client=None):
    key = pick_results_cache_key(date_str)
    c = client or get_http_client()
    existing = await _async_fetch_existing_pick_results_from_supabase(date_str, client=c)
    merged_rows = merge_us_pick_results_by_id(existing, rows, observed_at=utc_now_iso())
    value = json.dumps(merged_rows, ensure_ascii=False)
    payload = json.dumps({"key": key, "value": value, "upd": utc_now_iso()}).encode("utf-8")
    url = f"{SUPABASE_URL}/rest/v1/lotterynet_kv"
    try:
        resp = await c.post(url, content=payload, headers={
            "Content-Type": "application/json",
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Prefer": "resolution=merge-duplicates",
        })
        logger.info("Saved %d US pick results for %s -> HTTP %s", len(merged_rows), date_str, resp.status_code)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error("Supabase pick error %s: %s", e.response.status_code, e.response.text)
        raise


def save_us_picks_to_supabase(date_str, rows):
    sync_run(_async_save_us_picks_to_supabase(date_str, rows))


def unique_us_pick_results(rows):
    by_id = {}
    for row in rows:
        result_id = str(row.get("id", "")).strip()
        if result_id:
            by_id[result_id] = row
    return sorted(by_id.values(), key=lambda row: row.get("id", ""))


def utc_now_iso():
    return datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")


def merge_results_by_id(existing, results, prune_missing_ids=None, observed_at=None):
    observed = observed_at or utc_now_iso()
    merged = {str(r["id"]): r for r in existing if str(r.get("id", "")).strip()}
    for stale_id in (prune_missing_ids or []):
        merged.pop(str(stale_id), None)
    for r in results:
        key = str(r["id"])
        previous = merged.get(key) or {}
        row = dict(r)
        same_result = (
            str(previous.get("number", "")) == str(row.get("number", "")) and
            str(previous.get("status", "")) == str(row.get("status", ""))
        )
        if same_result and previous.get("firstSeenAt"):
            row["firstSeenAt"] = previous["firstSeenAt"]
        else:
            row["firstSeenAt"] = observed
        row["lastSeenAt"] = observed
        merged[key] = row
    return sorted(merged.values(), key=result_sort_key)


def result_sort_key(row):
    raw_id = str(row.get("id", ""))
    try:
        return (0, int(raw_id), "")
    except ValueError:
        return (1, 999999, raw_id)


def missing_tracked_result_ids(results):
    available = {str(row.get("id", "")) for row in results}
    return sorted(TRACKED_REMOTE_RESULT_IDS - available, key=int)


async def _async_save_native_results_table(date_str, merged_list, client=None):
    payload = json.dumps([{
        "result_date": date_str,
        "payload": merged_list,
        "updated_at": utc_now_iso(),
    }], ensure_ascii=False).encode("utf-8")
    url = f"{SUPABASE_URL}/rest/v1/lotterynet_results_by_day"
    c = client or get_http_client()
    resp = await c.post(url, content=payload, headers={
        "Content-Type": "application/json",
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Prefer": "resolution=merge-duplicates",
    })
    resp.raise_for_status()
    logger.info("Saved native results table for %s -> HTTP %s", date_str, resp.status_code)


async def _async_save_to_supabase(date_str, results, prune_missing_ids=None, client=None):
    key = f"lot_results_cache_by_day:{date_str}"
    c = client or get_http_client()

    existing = await _async_fetch_existing_from_supabase(date_str, client=c)
    merged_list = merge_results_by_id(existing, results, prune_missing_ids, observed_at=utc_now_iso())
    missing_tracked = missing_tracked_result_ids(merged_list)
    if missing_tracked:
        logger.warning("Missing tracked remote result ids for %s: %s", date_str, ", ".join(missing_tracked))

    value = json.dumps(merged_list, ensure_ascii=False)
    payload = json.dumps({"key": key, "value": value, "upd": utc_now_iso()}).encode("utf-8")
    url = f"{SUPABASE_URL}/rest/v1/lotterynet_kv"

    try:
        resp = await c.post(url, content=payload, headers={
            "Content-Type": "application/json",
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Prefer": "resolution=merge-duplicates",
        })
        resp.raise_for_status()
        logger.info("Saved %d results (merged) for %s -> HTTP %s", len(merged_list), date_str, resp.status_code)
        try:
            await _async_save_native_results_table(date_str, merged_list, client=c)
        except Exception as e:
            logger.warning("Native results table save failed for %s: %s", date_str, e)
    except httpx.HTTPStatusError as e:
        logger.error("Supabase error %s: %s", e.response.status_code, e.response.text)
        raise


def save_to_supabase(date_str, results, prune_missing_ids=None):
    sync_run(_async_save_to_supabase(date_str, results, prune_missing_ids))

async def _async_main():
    import sys

    if len(sys.argv) > 1:
        target_dates = sys.argv[1:]
    else:
        target_dates = [get_dr_date_str()]

    logger.info("Syncing dates: %s (UTC now=%s)", ", ".join(target_dates), datetime.datetime.utcnow().strftime("%H:%M"))
    client = get_http_client()

    for idx, target_date in enumerate(target_dates):
        logger.info("Scraping %s...", target_date)

        results, pick_results = await asyncio.gather(
            _async_scrape(target_date, client=client),
            _async_scrape_us_picks(target_date, client=client),
        )

        logger.info("Found %d lotteries and %d US Pick results", len(results), len(pick_results))
        for r in results:
            printable = r.get("number") or r.get("status") or ""
            logger.info("  [%s] %s: %s", r['id'], r['name'], printable)

        if not SUPABASE_KEY:
            if should_fail_without_supabase_key(SUPABASE_KEY):
                raise RuntimeError("SUPABASE_KEY is required in GitHub Actions")
            logger.info("No SUPABASE_KEY — skipping save")
            continue

        if results:
            prune_missing_ids = AUTHORITATIVE_NJ_IDS if idx == 0 and target_date == get_dr_date_str() else None
            await _async_save_to_supabase(target_date, results, prune_missing_ids=prune_missing_ids, client=client)
        else:
            logger.info("No results found for %s — skipping RD save", target_date)

        pick_results = unique_us_pick_results(pick_results)
        if pick_results:
            pick3_count = sum(1 for row in pick_results if row.get("game") == "pick3")
            pick4_count = sum(1 for row in pick_results if row.get("game") == "pick4")
            logger.info("  Pick 3: %d  Pick 4: %d", pick3_count, pick4_count)
            await _async_save_us_picks_to_supabase(target_date, pick_results, client=client)
        else:
            logger.info("No US Pick results found for %s — skipping pick save", target_date)

    await close_http_client()


if __name__ == "__main__":
    asyncio.run(_async_main())
