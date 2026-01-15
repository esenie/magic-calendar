from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
import calendar
import pytz
import os
import requests
import subprocess
from icalendar import Calendar

# =========================
# Canvas
# =========================
W, H = 680, 960

# =========================
# Colors (E-Ink friendly)
# =========================
TEXT = (0, 0, 0)
FADE = TEXT
RED  = (200, 0, 0)

DOW = ["S", "M", "T", "W", "T", "F", "S"]
ICON_DIR = "assets/weather"

# =========================
# Weather helpers
# =========================
def code_to_kind(wid: int) -> str:
    if 200 <= wid <= 232: return "thunder"
    if 300 <= wid <= 531: return "rain"
    if 600 <= wid <= 622: return "snow"
    if 701 <= wid <= 781: return "fog"
    if wid == 800:        return "sun"
    if 801 <= wid <= 804: return "cloud"
    return "cloud"

def get_today_tmro_kind(lat: float, lon: float):
    api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if not api_key:
        return ("", "")

    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()

    tz = pytz.timezone("Asia/Seoul")
    today = datetime.now(tz).date()
    tmro = today + timedelta(days=1)

    picked = {}
    for item in data.get("list", []):
        d = datetime.fromtimestamp(item["dt"], tz).date()
        if d not in picked and item.get("weather"):
            picked[d] = code_to_kind(int(item["weather"][0]["id"]))
        if today in picked and tmro in picked:
            break

    return picked.get(today, ""), picked.get(tmro, "")

def ensure_icons():
    need = ["sun","cloud","rain","snow","thunder","fog"]
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
# ICS helpers
# =========================
def fetch_events_by_date(tzname="Asia/Seoul", max_per_day=2):
    url = os.getenv("ICAL_URL", "").strip()
    if not url:
        return {}

    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]

    r = requests.get(url, timeout=20)
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
        dtstart = dtstart.dt

        summary = str(comp.get("summary", "")).strip()
        if not summary:
            continue

        if isinstance(dtstart, datetime):
            if dtstart.tzinfo is None:
                dtstart = tz.localize(dtstart)
            day = dtstart.astimezone(tz).date()
        else:
            day = dtstart

        events.setdefault(day, []).append(summary)

    for d in list(events.keys()):
        events[d] = events[d][:max_per_day]

    return events

def truncate(draw, text, font, max_w):
    if draw.textlength(text, font=font) <= max_w:
        return text
    ell = "…"
    while text and draw.textlength(text + ell, font=font) > max_w:
        text = text[:-1]
    return text + ell

# =========================
# Main
# =========================
def main():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.now(tz)
    today = now.date()
    year, month = now.year, now.month

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    # =========================
    # Fonts
    # =========================
    font_month = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 200)
    font_date  = ImageFont.truetype("assets/Inter_28pt-ExtraLight.ttf", 40)
    font_dow   = ImageFont.truetype("assets/NanumGothicBold.ttf", 30)
    font_event = ImageFont.truetype("assets/NanumSquareR.ttf", 13)
    font_label = ImageFont.truetype("assets/Inter_28pt-ExtraLight.ttf", 12)

    side_margin = 60
    top_margin  = 70

    # ===== Weather =====
    wx, wy = side_margin, 22
    widget_w, gap = 150, 6
    col_w = (widget_w - gap) / 2

    def label(x_left, t):
        tw = draw.textlength(t, font=font_label)
        draw.text((x_left + (col_w - tw)/2, wy), t, fill=TEXT, font=font_label)

    label(wx, "TODAY")
    label(wx + col_w + gap, "TMRO")

    ensure_icons()
    lat = float(os.getenv("OPENWEATHER_LAT", "37.5665"))
    lon = float(os.getenv("OPENWEATHER_LON", "126.9780"))
    k_today, k_tmro = get_today_tmro_kind(lat, lon)

    icon_size = 44
    icon_y = wy + 14

    def paste_icon(kind, x_left):
        icon = load_icon(kind)
        if not icon:
            return
        icon = icon.resize((icon_size, icon_size))
        x = int(x_left + (col_w - icon_size)/2)
        img.paste(icon, (x, int(icon_y)), icon)

    paste_icon(k_today, wx)
    paste_icon(k_tmro, wx + col_w + gap)

    # ===== Month =====
    mstr = str(month)
    mw = draw.textlength(mstr, font=font_month)
    draw.text(((W - mw)/2, top_margin), mstr, fill=TEXT, font=font_month)

    month_bottom = top_margin + font_month.size
    month_to_dow_gap = 30

    # ===== Update time =====
    updated = now.strftime("%m-%d %H:%M")
    uw = draw.textlength(updated, font=font_label)
    draw.text((W - side_margin - uw, 22), updated, fill=TEXT, font=font_label)

    # ===== Grid layout =====
    dow_y = month_bottom + month_to_dow_gap
    grid_top = dow_y + 45
    grid_bottom = 950

    grid_w = W - side_margin*2
    grid_h = grid_bottom - grid_top
    cols, rows = 7, 6
    cell_w = grid_w / cols
    cell_h = grid_h / rows
    grid_left = side_margin

    # ===== DOW =====
    for c, dch in enumerate(DOW):
        x = grid_left + c*cell_w + cell_w/2
        color = RED if c == 0 else TEXT
        dw = draw.textlength(dch, font=font_dow)
        draw.text((x - dw/2, dow_y), dch, fill=color, font=font_dow)

    # ===== Dates + Events =====
    cal = calendar.Calendar(firstweekday=6)
    days = list(cal.itermonthdates(year, month))[:42]
    events_by_date = fetch_events_by_date(max_per_day=2)

    for i, day in enumerate(days):
        r, c = divmod(i, cols)
        x0 = grid_left + c*cell_w
        y0 = grid_top  + r*cell_h

        is_sunday = (c == 0)
        date_color = RED if is_sunday else TEXT

        # Date number
        s = str(day.day)
        sw = draw.textlength(s, font=font_date)
        sx = x0 + (cell_w - sw)/2
        sy = y0 + int(cell_h * 0.30)
        draw.text((sx, sy), s, fill=date_color, font=font_date)

        # Today underline
        if day == today:
            uy = sy + 42
            draw.line(
                [(x0 + cell_w*0.28, uy), (x0 + cell_w*0.72, uy)],
                fill=RED,
                width=3
            )

        # Events
        evs = events_by_date.get(day, [])
        if evs:
            base_y = y0 + int(cell_h * 0.66)
            left_pad = x0 + 10
            text_x = left_pad + 10
            max_text_w = (x0 + cell_w) - text_x - 6

            for idx, t in enumerate(evs[:2]):
                t = truncate(draw, t.strip(), font_event, max_text_w)
                ty = base_y + idx * 18

                # red dot
                draw.ellipse(
                    [left_pad, ty + 5, left_pad + 6, ty + 11],
                    fill=RED
                )
                draw.text((text_x, ty), t, fill=TEXT, font=font_event)

    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")
    img.save("docs/latest.bmp")

if __name__ == "__main__":
    main()
