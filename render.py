from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
import calendar
import pytz
import os
import requests
import subprocess
from icalendar import Calendar
import holidays

# =========================
# Canvas (final output)
# =========================
W, H = 680, 960

# =========================
# Supersampling (anti-aliasing)
# =========================
SCALE = 2
W2, H2 = W * SCALE, H * SCALE

# =========================
# Colors (E-Ink friendly)
# =========================
TEXT = (0, 0, 0)
RED  = (200, 0, 0)

DOW = ["S", "M", "T", "W", "T", "F", "S"]
ICON_DIR = "assets/weather"

# =========================
# Icons helpers
# =========================
def ensure_icons():
    need = ["sun", "cloud", "rain", "snow", "thunder", "fog"]
    if all(os.path.exists(os.path.join(ICON_DIR, f"{k}.png")) for k in need):
        return
    if os.path.exists("make_icons.py"):
        subprocess.run(["python", "make_icons.py"], check=False)

def load_icon(kind: str):
    if not kind:
        return None
    p = os.path.join(ICON_DIR, f"{kind}.png")
    if not os.path.exists(p):
        return None
    return Image.open(p).convert("RGBA")

# =========================
# Open-Meteo helpers
# =========================
def openmeteo_code_to_kind(code: int) -> str:
    try:
        c = int(code)
    except Exception:
        return "cloud"

    if c == 0:
        return "sun"
    if c in (1, 2, 3):
        return "cloud"
    if c in (45, 48):
        return "fog"
    if 51 <= c <= 67:
        return "rain"
    if 71 <= c <= 77:
        return "snow"
    if 80 <= c <= 82:
        return "rain"
    if 85 <= c <= 86:
        return "snow"
    if c in (95, 96, 99):
        return "thunder"
    return "cloud"

def fetch_openmeteo_daily_5(lat, lon, tzname="Asia/Seoul", days=5):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": tzname,
        "forecast_days": days,
        "daily": "temperature_2m_min,temperature_2m_max,weathercode",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    daily = data.get("daily", {})
    out = []
    for i in range(days):
        d = datetime.strptime(daily["time"][i], "%Y-%m-%d").date()
        out.append({
            "date": d,
            "kind": openmeteo_code_to_kind(daily["weathercode"][i]),
            "tmin": daily["temperature_2m_min"][i],
            "tmax": daily["temperature_2m_max"][i],
        })
    return out

# =========================
# ICS helpers
# =========================
def fetch_events_by_date(tzname="Asia/Seoul", max_per_day=2):
    url = os.getenv("ICAL_URL", "").strip()
    if not url:
        return {}

    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]

    r = requests.get(url, timeout=25)
    r.raise_for_status()

    cal = Calendar.from_ical(r.text)
    tz = pytz.timezone(tzname)

    events = {}
    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue

        dtstart = comp.get("dtstart")
        if not dtstart:
            continue

        summary = str(comp.get("summary", "")).strip()
        if not summary:
            continue

        dt = dtstart.dt
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = tz.localize(dt)
            day = dt.astimezone(tz).date()
        else:
            day = dt

        events.setdefault(day, []).append(summary)

    for d in events:
        events[d] = events[d][:max_per_day]

    return events

# =========================
# Text helpers
# =========================
def truncate(draw, text, font, max_w):
    if draw.textlength(text, font=font) <= max_w:
        return text
    ell = "…"
    while text and draw.textlength(text + ell, font=font) > max_w:
        text = text[:-1]
    return text + ell if text else ell

def shorten_holiday_name(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return ""

    if n.startswith("대체공휴일"):
        if "(" in n and ")" in n:
            inside = n[n.find("(")+1:n.rfind(")")]
            return f"대체({inside})"
        return "대체"

    if n.startswith("임시공휴일"):
        return "임시"

    replace = {
        "기독탄신일": "성탄절",
        "삼일절": "3·1절",
    }
    return replace.get(n, n)

def needed_week_rows(days42, month):
    last = max(i for i, d in enumerate(days42) if d.month == month)
    return (last // 7) + 1

# =========================
# Main
# =========================
def main():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.now(tz)
    today = now.date()
    year, month = now.year, now.month

    try:
        kr_holidays = holidays.KR(years=[year-1, year, year+1], language="ko")
    except TypeError:
        kr_holidays = holidays.KR(years=[year-1, year, year+1])

    img2 = Image.new("RGB", (W2, H2), "white")
    draw2 = ImageDraw.Draw(img2)

    font_month = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 235 * SCALE)
    font_date  = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 44 * SCALE)
    font_dow   = ImageFont.truetype("assets/NanumGothicBold.ttf", 32 * SCALE)
    font_event = ImageFont.truetype("assets/NanumSquareEB.ttf", 12 * SCALE)
    font_holiday = ImageFont.truetype("assets/NanumGothicBold.ttf", 11 * SCALE)

    side = 6 * SCALE
    top = 4 * SCALE

    cal = calendar.Calendar(firstweekday=6)
    days42 = list(cal.itermonthdates(year, month))[:42]
    rows = needed_week_rows(days42, month)
    days = days42[:rows * 7]

    grid_top = 280 * SCALE
    grid_bottom = 700 * SCALE
    grid_left = side
    grid_right = W2 - side

    cell_w = (grid_right - grid_left) / 7
    cell_h = (grid_bottom - grid_top) / rows

    # DOW
    for c, d in enumerate(DOW):
        color = RED if c == 0 else TEXT
        w = draw2.textlength(d, font=font_dow)
        draw2.text((grid_left + c * cell_w + cell_w/2 - w/2, 220*SCALE),
                   d, fill=color, font=font_dow)

    events = fetch_events_by_date()

    for i, day in enumerate(days):
        r, c = divmod(i, 7)
        x0 = grid_left + c * cell_w
        y0 = grid_top + r * cell_h

        is_holiday = day in kr_holidays
        is_sunday = (c == 0)
        date_color = RED if (is_holiday or is_sunday) else TEXT

        s = str(day.day)
        sw = draw2.textlength(s, font=font_date)
        sx = x0 + (cell_w - sw)/2
        sy = y0 + int(cell_h * 0.08)
        draw2.text((sx, sy), s, fill=date_color, font=font_date)

        bx1, by1, bx2, by2 = draw2.textbbox((sx, sy), s, font=font_date)

        if is_holiday and day.month == month:
            hname = shorten_holiday_name(str(kr_holidays.get(day)))
            max_w = cell_w - (10 * SCALE)
            htxt = truncate(draw2, hname, font_holiday, max_w)
            hw = draw2.textlength(htxt, font=font_holiday)
            draw2.text((x0 + (cell_w - hw)/2, by2 + 4*SCALE),
                       htxt, fill=RED, font=font_holiday)

    img = img2.resize((W, H), Image.Resampling.LANCZOS)
    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")
    img.save("docs/latest.bmp")

if __name__ == "__main__":
    main()
