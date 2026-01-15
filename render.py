import os
import io
import math
import textwrap
import calendar as pycal
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont

# Optional: ical parsing
try:
    from icalendar import Calendar
except Exception:
    Calendar = None

# Optional: KR holidays
try:
    import holidays
    KR_HOLIDAYS = holidays.KR()
except Exception:
    KR_HOLIDAYS = None


# =========================
# CONFIG
# =========================
TZ = ZoneInfo("Asia/Seoul")
W, H = 680, 960  # (BMP header will show w=680 h=960)

ASSET_DIR = "assets"
DOCS_DIR = "docs"
OUT_PNG = os.path.join(DOCS_DIR, "latest.png")
OUT_BMP = os.path.join(DOCS_DIR, "latest.bmp")

# Fonts (NanumGothic.ttf exists; NanumGothicBold.ttf optional)
FONT_REG_PATH = os.path.join(ASSET_DIR, "NanumGothic.ttf")
FONT_BOLD_PATH = os.path.join(ASSET_DIR, "NanumGothicBold.ttf")  # optional


# =========================
# COLORS (FADE -> BLACK)
# =========================
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
FADE = BLACK          # ✅ 모든 회색 톤을 검정으로 통일
GRID = BLACK          # 라인도 검정
RED = (220, 0, 0)
BLUE = (0, 70, 255)   # 3색 패널일 경우 파란 표시용(ESP32에서 blue 지원 시 의미 있음)


# =========================
# HELPERS: fonts / bold text
# =========================
def load_font(path, size):
    return ImageFont.truetype(path, size)

def get_font(size, bold=False):
    """Try bold font file; fallback to regular."""
    if bold and os.path.exists(FONT_BOLD_PATH):
        return load_font(FONT_BOLD_PATH, size)
    return load_font(FONT_REG_PATH, size)

def draw_text_bold(draw: ImageDraw.ImageDraw, xy, text, font, fill, strength=1):
    """
    Faux-bold: draw text multiple times with tiny offsets.
    strength=1~2 recommended for readability.
    """
    x, y = xy
    # Offsets: (0,0) + neighbors
    offsets = [(0,0)]
    if strength >= 1:
        offsets += [(1,0), (0,1), (1,1)]
    if strength >= 2:
        offsets += [(-1,0), (0,-1), (-1,-1), (1,-1), (-1,1)]
    for dx, dy in offsets:
        draw.text((x+dx, y+dy), text, font=font, fill=fill)

def text_width(draw, text, font):
    bbox = draw.textbbox((0,0), text, font=font)
    return bbox[2] - bbox[0]

def ellipsize(draw, text, font, max_w):
    if text_width(draw, text, font) <= max_w:
        return text
    # Reserve for ellipsis
    ell = "…"
    if text_width(draw, ell, font) > max_w:
        return ""
    # Binary search cut
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        t = text[:mid].rstrip() + ell
        if text_width(draw, t, font) <= max_w:
            lo = mid + 1
        else:
            hi = mid
    cut = max(0, lo-1)
    return text[:cut].rstrip() + ell


# =========================
# WEATHER (simple icon)
# =========================
def fetch_openweather_icon():
    """
    Returns (today_icon, tmro_icon, today_temp, tmro_temp) or None.
    We keep it simple; your calendar already has layout.
    """
    key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    lat = os.getenv("OPENWEATHER_LAT", "").strip()
    lon = os.getenv("OPENWEATHER_LON", "").strip()
    if not (key and lat and lon):
        return None

    # 3-hour forecast endpoint
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": key, "units": "metric", "lang": "kr"}
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None

    now = datetime.now(TZ)
    today = now.date()
    tmro = today + timedelta(days=1)

    # Pick one representative forecast near 12:00 for each day
    def pick_icon_for(d: date):
        target = datetime(d.year, d.month, d.day, 12, 0, tzinfo=TZ)
        best = None
        best_dt = None
        for item in data.get("list", []):
            # dt_txt is UTC-ish; use timestamp
            dt = datetime.fromtimestamp(item["dt"], tz=TZ)
            if dt.date() != d:
                continue
            if best is None:
                best = item
                best_dt = dt
            else:
                if abs((dt - target).total_seconds()) < abs((best_dt - target).total_seconds()):
                    best = item
                    best_dt = dt
        if not best:
            return ("?", None)
        wid = best["weather"][0]["id"]
        temp = best.get("main", {}).get("temp")
        return (weather_id_to_emoji(wid), temp)

    (t_icon, t_temp) = pick_icon_for(today)
    (m_icon, m_temp) = pick_icon_for(tmro)
    return (t_icon, m_icon, t_temp, m_temp)

def weather_id_to_emoji(wid: int) -> str:
    # Very simple mapping (works well on e-ink)
    if 200 <= wid < 300:
        return "⛈️"
    if 300 <= wid < 400:
        return "🌦️"
    if 500 <= wid < 600:
        return "🌧️"
    if 600 <= wid < 700:
        return "❄️"
    if 700 <= wid < 800:
        return "🌫️"
    if wid == 800:
        return "☀️"
    if 801 <= wid <= 804:
        return "☁️"
    return "?"


# =========================
# ICAL EVENTS
# =========================
def fetch_ical_events():
    """
    Returns dict[date] = list[str] (event titles), limited later in render.
    """
    ical_url = os.getenv("ICAL_URL", "").strip()
    if not (ical_url and Calendar):
        return {}

    # Support webcal:// -> https://
    if ical_url.startswith("webcal://"):
        ical_url = "https://" + ical_url[len("webcal://"):]

    try:
        r = requests.get(ical_url, timeout=25)
        r.raise_for_status()
        cal = Calendar.from_ical(r.content)
    except Exception:
        return {}

    now = datetime.now(TZ)
    start = datetime(now.year, now.month, 1, tzinfo=TZ)
    # show full 6-week grid range
    end = start + timedelta(days=45)

    out = {}
    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue
        try:
            summary = str(comp.get("summary", "")).strip()
            if not summary:
                continue
            dtstart = comp.decoded("dtstart")
            # dtstart can be date or datetime
            if isinstance(dtstart, datetime):
                dt = dtstart.astimezone(TZ)
                d = dt.date()
            else:
                d = dtstart
            if start.date() <= d <= end.date():
                out.setdefault(d, []).append(summary)
        except Exception:
            continue

    # Sort for stability
    for d in list(out.keys()):
        out[d] = out[d][:20]
    return out


# =========================
# HOLIDAYS
# =========================
def is_kr_holiday(d: date) -> bool:
    if KR_HOLIDAYS is None:
        return False
    return d in KR_HOLIDAYS


# =========================
# RENDER
# =========================
def render():
    os.makedirs(DOCS_DIR, exist_ok=True)

    now = datetime.now(TZ)
    year, month = now.year, now.month
    today = now.date()

    # Pull data
    events_by_date = fetch_ical_events()
    wx = fetch_openweather_icon()  # may be None

    # Image canvas
    img = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)

    # Layout margins
    MARGIN_L = 28
    MARGIN_R = 28
    MARGIN_TOP = 18
    MARGIN_BOTTOM = 18  # ✅ 아래 여백 최소화 (하단 채우기)

    # Header / top blocks
    # Month label and weather area share the top
    month_font = get_font(70, bold=True)
    weekday_font = get_font(22, bold=True)
    date_font = get_font(26, bold=True)        # ✅ 일자 굵게
    event_font = get_font(18, bold=False)      # 일정은 작게(요청대로), 색은 BLACK 처리
    meta_font = get_font(18, bold=False)
    wx_label_font = get_font(16, bold=True)
    wx_icon_font = get_font(30, bold=False)

    # --- Month title (e.g., "12")
    month_text = str(month)
    # center near top
    month_y = MARGIN_TOP
    month_w = text_width(draw, month_text, month_font)
    month_x = (W - month_w) // 2
    # bold effect: stronger for month
    draw_text_bold(draw, (month_x, month_y), month_text, month_font, BLACK, strength=2)

    # --- Update time small, top-right
    updated_text = now.strftime("%m/%d %H:%M")
    upd_w = text_width(draw, updated_text, meta_font)
    upd_x = W - MARGIN_R - upd_w
    upd_y = MARGIN_TOP + 8
    draw.text((upd_x, upd_y), updated_text, font=meta_font, fill=BLACK)

    # --- Weather box: top-left
    wx_x = MARGIN_L
    wx_y = MARGIN_TOP + 6
    wx_w = 150
    wx_h = 70  # 좁게
    # Outline (minimal)
    draw.rectangle([wx_x, wx_y, wx_x + wx_w, wx_y + wx_h], outline=BLACK, width=1)

    # TODAY / TMRO labels + icons
    if wx:
        t_icon, m_icon, t_temp, m_temp = wx
    else:
        t_icon, m_icon, t_temp, m_temp = ("?", "?", None, None)

    # Left row: TODAY
    draw_text_bold(draw, (wx_x + 10, wx_y + 8), "TODAY", wx_label_font, BLACK, strength=1)
    draw.text((wx_x + 92, wx_y + 2), t_icon, font=wx_icon_font, fill=BLACK)

    # Right row: TMRO
    draw_text_bold(draw, (wx_x + 10, wx_y + 38), "TMRO", wx_label_font, BLACK, strength=1)
    draw.text((wx_x + 92, wx_y + 32), m_icon, font=wx_icon_font, fill=BLACK)

    # Header bottom (grid start)
    header_bottom = wx_y + wx_h + 22

    # =========================
    # GRID: fill to bottom
    # =========================
    grid_left = MARGIN_L
    grid_right = W - MARGIN_R
    grid_top = header_bottom
    grid_bottom = H - MARGIN_BOTTOM  # ✅ 하단까지 채움

    cols, rows = 7, 6
    grid_w = grid_right - grid_left
    grid_h = grid_bottom - grid_top
    cell_w = grid_w / cols
    cell_h = grid_h / rows

    # Weekday labels row above grid
    # Put it inside grid top area with small offset
    weekday_y = grid_top - 28
    weekday_names = ["S", "M", "T", "W", "T", "F", "S"]
    for i, wd in enumerate(weekday_names):
        x = grid_left + i * cell_w + (cell_w - text_width(draw, wd, weekday_font)) / 2
        # Sunday red, Saturday blue (if you want blue); otherwise keep black for weekday names
        fill = BLACK
        if i == 0:
            fill = RED
        elif i == 6:
            fill = BLUE
        draw_text_bold(draw, (x, weekday_y), wd, weekday_font, fill, strength=1)

    # Grid lines
    # Outer border
    draw.rectangle([grid_left, grid_top, grid_right, grid_bottom], outline=GRID, width=2)
    # Inner lines
    for c in range(1, cols):
        x = grid_left + c * cell_w
        draw.line([(x, grid_top), (x, grid_bottom)], fill=GRID, width=1)
    for r in range(1, rows):
        y = grid_top + r * cell_h
        draw.line([(grid_left, y), (grid_right, y)], fill=GRID, width=1)

    # Calendar matrix (start on Sunday)
    cal = pycal.Calendar(firstweekday=6)  # Sunday start
    month_days = list(cal.itermonthdates(year, month))  # includes prev/next month padding
    # Ensure 6 rows * 7 = 42
    month_days = month_days[:42]

    # Render each cell
    for idx, d in enumerate(month_days):
        r = idx // cols
        c = idx % cols
        cx0 = grid_left + c * cell_w
        cy0 = grid_top + r * cell_h
        cx1 = cx0 + cell_w
        cy1 = cy0 + cell_h

        in_month = (d.month == month)
        is_sun = (c == 0)
        is_sat = (c == 6)

        # Date color rules
        date_fill = BLACK
        if is_sun or is_kr_holiday(d):
            date_fill = RED
        elif is_sat:
            date_fill = BLUE

        # Dim out other-month dates slightly: since FADE=BLACK now, we instead use smaller text opacity via "lighter"?
        # On e-ink we only have black; so we just keep them black but you could make them smaller.
        # We'll just draw them as normal but optionally not bold.
        day_str = str(d.day)

        # Date position: top-left inside cell with padding
        pad_x = 10
        date_y = cy0 + int(cell_h * 0.10)
        date_x = cx0 + pad_x

        # ✅ 요일/일자 굵게: 날짜 숫자도 faux-bold
        if in_month:
            draw_text_bold(draw, (date_x, date_y), day_str, date_font, date_fill, strength=1)
        else:
            # other month: less bold
            draw.text((date_x, date_y), day_str, font=date_font, fill=date_fill)

        # Today underline (thin)
        if d == today:
            # underline just beneath number (thin)
            # Compute underline width roughly text width
            tw = text_width(draw, day_str, date_font)
            ux0 = date_x
            uy = date_y + 32  # approximate baseline for size 26; tweak if needed
            ux1 = date_x + tw
            draw.line([(ux0, uy), (ux1, uy)], fill=RED, width=1)

        # Events (max 2)
        evs = events_by_date.get(d, [])
        if evs:
            # Only show events for current month cells (optional). If you want show on padded days, remove this check.
            if in_month:
                show = evs[:2]
                # Event area: push down more (spacing request)
                ev_y1 = cy0 + int(cell_h * 0.55)
                ev_gap = int(cell_h * 0.18)
                # Max width inside cell (padding)
                max_text_w = int(cell_w - 2 * pad_x - 14)  # 14 for bullet+space
                for j, title in enumerate(show):
                    y = ev_y1 + j * ev_gap
                    # red bullet dot + black text
                    bullet_x = cx0 + pad_x
                    text_x = bullet_x + 12
                    # bullet
                    draw.ellipse([bullet_x, y + 6, bullet_x + 6, y + 12], fill=RED, outline=RED)
                    # text (BLACK)
                    t = ellipsize(draw, title, event_font, max_text_w)
                    draw.text((text_x, y), t, font=event_font, fill=BLACK)

    # Save PNG
    img.save(OUT_PNG, "PNG")

    # Save BMP (24-bit)
    # Pillow will write BMP; keep RGB
    img.save(OUT_BMP, "BMP")


if __name__ == "__main__":
    render()
    print(f"OK: wrote {OUT_PNG} and {OUT_BMP}")
