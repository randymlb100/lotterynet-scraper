"""
LotteryNet RD — Scraper → Supabase
Scrapea loteriasdominicanas.com y guarda en lotterynet_kv
key: lot_results_cache_by_day
"""
import os, json, datetime, urllib.request, urllib.parse, re
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
    {"id": "US-P3-AR-CASH-3-EVENING", "state": "Arkansas", "stateCode": "AR", "game": "pick3", "gameName": "Cash 3", "draw": "Evening Draw"},
    {"id": "US-P3-AR-CASH-3-MIDDAY", "state": "Arkansas", "stateCode": "AR", "game": "pick3", "gameName": "Cash 3", "draw": "Midday Draw"},
    {"id": "US-P3-SC-PICK-3-MIDDAY", "state": "South Carolina", "stateCode": "SC", "game": "pick3", "gameName": "Pick 3", "draw": "Midday Draw"},
    {"id": "US-P3-TX-PICK-3-DAY", "state": "Texas", "stateCode": "TX", "game": "pick3", "gameName": "Pick 3", "draw": "Day Draw"},
    {"id": "US-P3-TX-PICK-3-EVENING", "state": "Texas", "stateCode": "TX", "game": "pick3", "gameName": "Pick 3", "draw": "Evening Draw"},
    {"id": "US-P3-TX-PICK-3-MORNING", "state": "Texas", "stateCode": "TX", "game": "pick3", "gameName": "Pick 3", "draw": "Morning Draw"},
    {"id": "US-P3-TX-PICK-3-NIGHT", "state": "Texas", "stateCode": "TX", "game": "pick3", "gameName": "Pick 3", "draw": "Night Draw"},
    {"id": "US-P4-AR-CASH-4-MIDDAY", "state": "Arkansas", "stateCode": "AR", "game": "pick4", "gameName": "Cash 4", "draw": "Midday Draw"},
    {"id": "US-P4-SC-PICK-4-EVENING", "state": "South Carolina", "stateCode": "SC", "game": "pick4", "gameName": "Pick 4", "draw": "Evening Draw"},
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

def should_fail_without_supabase_key(supabase_key, env=None):
    """GitHub Actions must fail instead of reporting success without saving."""
    source_env = env if env is not None else os.environ
    return not bool(str(supabase_key or "").strip()) and source_env.get("GITHUB_ACTIONS") == "true"

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


def fetch_new_jersey_pick_home(game):
    normalized_game = normalize_us_pick_game(game)
    url = US_PICK_NJ_HOME_URLS.get(normalized_game)
    if not url:
        return []
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        html = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"  NJ Pick error for {normalized_game}: {e}")
        return []
    return parse_new_jersey_pick_home(html, normalized_game)


def us_pick_history_url_candidates(game, state_code):
    normalized_game = normalize_us_pick_game(game)
    domain = "pick-3.com" if normalized_game == "pick3" else "pick-4.com"
    code = str(state_code or "").lower()
    urls = []
    for path in US_PICK_HISTORY_PATHS.get(normalized_game, []):
        suffix = f"/{path}" if path else "/"
        urls.append(f"https://{code}.{domain}{suffix}")
    return urls


def fetch_us_pick_state_history(game, state_code, state_name, game_name, target_date):
    normalized_game = normalize_us_pick_game(game)
    for url in us_pick_history_url_candidates(normalized_game, state_code):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        try:
            html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
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


def fetch_us_pick_overview(game):
    normalized_game = normalize_us_pick_game(game)
    url = US_PICK_URLS.get(normalized_game)
    if not url:
        return []
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        html = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"  US Pick error for {normalized_game}: {e}")
        return []
    return parse_us_pick_overview(html, normalized_game)


def scrape_us_picks(date_str=None):
    target_date = date_str or get_dr_date_str()
    rows_by_id = {}
    for game in ("pick3", "pick4"):
        overview_rows = fetch_us_pick_overview(game)
        if target_date:
            history_keys = set()
            state_rows = {}
            for row in overview_rows:
                state_key = (row.get("stateCode"), row.get("gameName"))
                state_rows[state_key] = row
            for row in state_rows.values():
                history_rows = fetch_us_pick_state_history(
                    game,
                    row.get("stateCode"),
                    row.get("state"),
                    row.get("gameName"),
                    target_date,
                )
                if history_rows:
                    history_keys.add((row.get("stateCode"), row.get("gameName")))
                for history_row in history_rows:
                    rows_by_id[history_row["id"]] = history_row
            for row in fetch_new_jersey_pick_home(game):
                if row.get("date") == target_date:
                    history_keys.add((row.get("stateCode"), row.get("gameName")))
                    rows_by_id[row["id"]] = row
            for row in overview_rows:
                state_key = (row.get("stateCode"), row.get("gameName"))
                if state_key not in history_keys:
                    rows_by_id[row["id"]] = row
        else:
            for row in overview_rows:
                rows_by_id[row["id"]] = row
            for row in fetch_new_jersey_pick_home(game):
                rows_by_id[row["id"]] = row
    rows = list(rows_by_id.values())
    if target_date:
        rows = [row for row in rows if row.get("date") == target_date]
        append_us_pick_calendar_no_draw_rows(rows, target_date)
    return sorted(rows, key=lambda row: (row["state"], row["game"], row["draw"], row["gameName"]))


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


def fetch_enloteria_results(date_str=None, fallback_days=0, sources=None):
    target_date = date_str or get_dr_date_str()
    target_dates = recent_dr_dates(target_date, days_back=fallback_days)
    results = []
    for source in sources or ENLOTERIA_RESULT_SOURCES:
        req = urllib.request.Request(
            source["url"],
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        try:
            html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
        except Exception as e:
            print(f"  EnLoteria error for {source['name']}: {e}")
            continue
        row = parse_enloteria_result_jsonld_for_dates(
            html,
            lottery_id=source["id"],
            lottery_name=source["name"],
            target_dates=target_dates,
            source_name=source.get("source_name"),
        )
        if row:
            results.append(row)
            print(f"  EnLoteria [{row['id']}] {row['name']} ({row['date']}): {row['number']}")
        else:
            print(f"  EnLoteria: no recent result for {source['name']} on {', '.join(target_dates)}")
    return results


def fetch_enloteria_haiti_bolet(date_str=None, fallback_days=2):
    return fetch_enloteria_results(
        date_str=date_str,
        fallback_days=fallback_days,
        sources=ENLOTERIA_HAITI_BOLET_SOURCES,
    )


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

    for row in build_king_no_draw_rows(date_str, seen_ids):
        results.append(row)
        seen_ids.add(row["id"])
        print(f"  King [{row['id']}] {row['name']}: no_draw for {date_str}")

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

    enloteria_rows = fetch_enloteria_results(date_str, fallback_days=0)
    for row in enloteria_rows:
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


def pick_results_cache_key(date_str):
    return f"pick_results_cache_by_day:{date_str}"


def save_us_picks_to_supabase(date_str, rows):
    key = pick_results_cache_key(date_str)
    value = json.dumps(rows, ensure_ascii=False)
    payload = json.dumps({"key": key, "value": value, "upd": utc_now_iso()}).encode("utf-8")
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
        print(f"Saved {len(rows)} US pick results for {date_str} -> HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Supabase pick error {e.code}: {body}")
        raise


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


def save_native_results_table(date_str, merged_list):
    payload = json.dumps([{
        "result_date": date_str,
        "payload": merged_list,
        "updated_at": utc_now_iso(),
    }], ensure_ascii=False).encode("utf-8")
    url = f"{SUPABASE_URL}/rest/v1/lotterynet_results_by_day"
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
    resp = urllib.request.urlopen(req, timeout=15)
    print(f"Saved native results table for {date_str} -> HTTP {resp.status}")


def save_to_supabase(date_str, results, prune_missing_ids=None):
    import urllib.parse
    key = f"lot_results_cache_by_day:{date_str}"

    # Merge: preserve existing rows by default, override with fresh ones by id.
    # For today's authoritatives we can optionally prune IDs that were not freshly found,
    # which lets us clear stale same-day rows without damaging historical backfills.
    existing = fetch_existing_from_supabase(date_str)
    merged_list = merge_results_by_id(existing, results, prune_missing_ids, observed_at=utc_now_iso())
    missing_tracked = missing_tracked_result_ids(merged_list)
    if missing_tracked:
        print(f"Warning: missing tracked remote result ids for {date_str}: {', '.join(missing_tracked)}")

    value = json.dumps(merged_list, ensure_ascii=False)

    payload = json.dumps({"key": key, "value": value, "upd": utc_now_iso()}).encode("utf-8")
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
        try:
            save_native_results_table(date_str, merged_list)
        except Exception as e:
            print(f"Warning: native results table save failed for {date_str}: {e}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Supabase error {e.code}: {body}")
        raise

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
            printable = r.get("number") or r.get("status") or ""
            print(f"  [{r['id']}] {r['name']}: {printable}")

        if not SUPABASE_KEY:
            if should_fail_without_supabase_key(SUPABASE_KEY):
                raise RuntimeError("SUPABASE_KEY is required in GitHub Actions")
            print("No SUPABASE_KEY — skipping save")
            continue
        if results:
            prune_missing_ids = AUTHORITATIVE_NJ_IDS if idx == 0 and target_date == get_dr_date_str() else None
            save_to_supabase(target_date, results, prune_missing_ids=prune_missing_ids)
        else:
            print(f"No results found for {target_date} — skipping RD save")

        print(f"\n[US Pick] Scraping {target_date}...")
        pick_results = unique_us_pick_results(scrape_us_picks(target_date))
        print(f"Found {len(pick_results)} US Pick results")
        if pick_results:
            pick3_count = sum(1 for row in pick_results if row.get("game") == "pick3")
            pick4_count = sum(1 for row in pick_results if row.get("game") == "pick4")
            print(f"  Pick 3: {pick3_count}")
            print(f"  Pick 4: {pick4_count}")
            save_us_picks_to_supabase(target_date, pick_results)
        else:
            print(f"No US Pick results found for {target_date} — skipping pick save")
