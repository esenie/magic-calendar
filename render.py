from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
import calendar
import pytz
import os
import requests
import subprocess
from icalendar import Calendar

# =========================
# Canvas (final output)
# =========================
W, H = 680, 960

# =========================
# Supersampling (anti-aliasing)
# =========================
SCALE = 2  # 2x render -> downscale
W2, H2 = W * SCALE, H * SCALE

# =========================
# Colors (E-Ink friendly)
# =========================
TEXT = (0, 0, 0)
RED  = (200, 0, 0)
WHITE = (255, 255, 255)

DOW = ["S", "M", "T", "W", "T", "F", "S"]
ICON_DIR = "assets/weather"

# -------------------------
# Weather helpers
# -------------------------
def code_to_kind(wid: int) -> str:
    if 200 <= wid <= 232: return "thunder"
    if 300 <= wid <= 531: return "rain"
    if 600 <= wid <= 622: return "snow"
    if 701 <= wid <= 781: return "fog"
    if wid == 800:        return "sun"
    if 801 <= wid <= 804: return "cloud"
    return "cloud"

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

def get_5day_forecast(lat: float, lon: float, tzname="Asia/Seoul"):
    """
    Returns a list of up to 5 dicts:
    [
      { 'date': date_obj, 'kind': 'sun', 'min': 10, 'max': 20 },
      ...
    ]
    """
    api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if not api_key:
        return []

    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"}
    
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []

    tz = pytz.timezone(tzname)
    now_date = datetime.now(tz).date()
    
    # Organize by date
    daily_data = {} # date -> { 'temps': [], 'codes': [] }

    for item in data.get("list", []):
        dt = datetime.fromtimestamp(item["dt"], tz)
        d = dt.date()
        
        # Skip past (though usually API gives future)
        if d < now_date:
            continue
            
        if d not in daily_data:
            daily_data[d] = {'temps': [], 'codes': []}
        
        main = item.get("main", {})
        temp = main.get("temp")
        if isinstance(temp, (int, float)):
            daily_data[d]['temps'].append(temp)
            
        if item.get("weather"):
            daily_data[d]['codes'].append(int(item["weather"][0]["id"]))

    # Convert to result list (take first 5 days found)
    results = []
    sorted_dates = sorted(daily_data.keys())[:5]

    for d in sorted_dates:
        temps = daily_data[d]['temps']
        codes = daily_data[d]['codes']
        
        if not temps: 
            continue
            
        tmin = min(temps)
        tmax = max(temps)
        
        # For icon: simple logic, pick most frequent or just the first valid one
        # Here we prefer rain/snow icons if they exist in the day to warn the user
        # Priorities: Snow(6xx) > Rain(5xx,3xx) > Thunder(2xx) > Fog > Cloud > Sun
        # But for simplicity, let's just pick the code that appears most or the "worst" one.
        # Let's pick the one that occurs in the middle of the list (midday) usually represents the day well.
        if codes:
            mid_idx = len(codes) // 2
            rep_code = codes[mid_idx]
            kind = code_to_kind(rep_code)
        else:
            kind = "cloud"

        results.append({
            'date': d,
            'kind': kind,
            'min': tmin,
            'max': tmax
        })
        
    return results

# -------------------------
# ICS helpers
# -------------------------
def fetch_events_by_date(tzname="Asia/Seoul", max_per_day=2):
    url = os.getenv("ICAL_URL", "").strip()
    if not url:
        return {}

    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]

    try:
        r = requests.get(url, timeout=25)
        r.raise_for_status()
        cal = Calendar.from_ical(r.text)
    except Exception:
        return {}

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
    text = (text or "").replace("\n", " ").strip()
    if not text:
        return ""
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

    # Canvas
    img2 = Image.new("RGB", (W2, H2), "white")
    draw2 = ImageDraw.Draw(img2)

    # -------------------------
    # Fonts
    # -------------------------
    # Sizes tuned for 2x scale
    font_month = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 60 * SCALE)
    font_update = ImageFont.truetype("assets/Inter_28pt-ExtraLight.ttf", 12 * SCALE)
    
    font_dow   = ImageFont.truetype("assets/NanumGothicBold.ttf", 20 * SCALE)
    font_date  = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 40 * SCALE)
    font_event = ImageFont.truetype("assets/NanumSquareR.ttf", 15 * SCALE)
    
    # Weather fonts
    font_wx_day = ImageFont.truetype("assets/NanumGothicBold.ttf", 16 * SCALE)
    font_wx_temp = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 16 * SCALE)

    # -------------------------
    # Layout Config
    # -------------------------
    # Margins (Minimalist)
    side_margin = 2 * SCALE  
    top_margin = 2 * SCALE
    bottom_margin = 2 * SCALE

    # Header Area (Month + Update Time)
    header_h = 80 * SCALE
    
    # Footer Area (Weather) - Bottom 15% roughly
    footer_h = 160 * SCALE 
    
    # Grid Area (Calendar)
    grid_top = top_margin + header_h
    grid_bottom = H2 - footer_h - bottom_margin
    grid_h = grid_bottom - grid_top
    
    grid_left = side_margin
    grid_right = W2 - side_margin
    grid_w = grid_right - grid_left

    # -------------------------
    # Draw Header
    # -------------------------
    # 1. Month (Top Left)
    mstr = str(month)
    draw2.text((grid_left + 10 * SCALE, top_margin), mstr, fill=TEXT, font=font_month)
    
    # 2. Update Time (Top Right)
    updated = now.strftime("%m-%d %H:%M")
    uw = draw2.textlength(updated, font=font_update)
    draw2.text((grid_right - uw - 10 * SCALE, top_margin + 20 * SCALE), updated, fill=TEXT, font=font_update)

    # 3. Year (Optional, small next to month or just skip to save space)
    # We skip year to keep it clean, as month is big.

    # -------------------------
    # Draw Calendar Grid
    # -------------------------
    cols, rows = 7, 6  # 6 rows to accommodate all months safely
    cell_w = grid_w / cols
    cell_h = grid_h / rows
    
    # Draw DOW Headers (Inside the top of grid area, or just above first row)
    # Let's put DOW at the very top of grid_top
    dow_h = 30 * SCALE
    
    for c, dch in enumerate(DOW):
        x = grid_left + c * cell_w + cell_w / 2
        y = grid_top
        color = RED if c == 0 else TEXT
        dw = draw2.textlength(dch, font=font_dow)
        draw2.text((x - dw / 2, y), dch, fill=color, font=font_dow)
        
    # Draw Days
    cal_obj = calendar.Calendar(firstweekday=6)
    days = list(cal_obj.itermonthdates(year, month))[:42]
    
    events_by_date = fetch_events_by_date(max_per_day=2)

    # Shift rows down by dow_h to make room for M/T/W...
    row_start_y = grid_top + dow_h
    actual_cell_h = (grid_bottom - row_start_y) / rows

    for i, day in enumerate(days):
        r, c = divmod(i, cols)
        x0 = grid_left + c * cell_w
        y0 = row_start_y + r * actual_cell_h

        # Date number
        s = str(day.day)
        is_sunday = (c == 0)
        
        # Grayscale for other month dates
        is_this_month = (day.month == month)
        if not is_this_month:
            date_color = (150, 150, 150) # Grey
        else:
            date_color = RED if is_sunday else TEXT

        sw = draw2.textlength(s, font=font_date)
        # Position date at top-center of cell
        sx = x0 + (cell_w - sw) / 2
        sy = y0 + (5 * SCALE)
        draw2.text((sx, sy), s, fill=date_color, font=font_date)

        # Today indicator (Circle or Underline)
        if day == today:
            # Underline
            line_y = sy + font_date.size + (2 * SCALE)
            draw2.line(
                [(sx, line_y), (sx + sw, line_y)], 
                fill=RED, width=int(3 * SCALE)
            )

        # Events
        evs = events_by_date.get(day, [])
        if evs:
            # Start events below the date
            event_y_start = sy + font_date.size + (6 * SCALE)
            line_height = 20 * SCALE
            
            for k, txt in enumerate(evs[:2]):
                ey = event_y_start + k * line_height
                if ey + line_height > y0 + actual_cell_h: 
                    break # Don't overflow cell
                
                # Small dot
                dot_r = 3 * SCALE
                dx = x0 + 6 * SCALE
                dy_center = ey + 8 * SCALE
                draw2.ellipse([dx-dot_r, dy_center-dot_r, dx+dot_r, dy_center+dot_r], fill=RED)
                
                # Text
                t_x = dx + 8 * SCALE
                max_tw = cell_w - (16 * SCALE)
                trunc_txt = truncate(draw2, txt, font_event, max_tw)
                draw2.text((t_x, ey), trunc_txt, fill=TEXT, font=font_event)

    # -------------------------
    # Draw Footer (5-Day Weather)
    # -------------------------
    # Separator line
    draw2.line([(0, grid_bottom), (W2, grid_bottom)], fill=TEXT, width=int(2*SCALE))

    lat = float(os.getenv("OPENWEATHER_LAT", "37.5665"))
    lon = float(os.getenv("OPENWEATHER_LON", "126.9780"))
    ensure_icons()
    
    forecasts = get_5day_forecast(lat, lon)
    
    # 5 columns
    wx_col_w = W2 / 5
    wx_y_start = grid_bottom + (10 * SCALE)
    
    icon_size = 50 * SCALE

    for i in range(5):
        cx = i * wx_col_w + (wx_col_w / 2)
        
        if i < len(forecasts):
            f = forecasts[i]
            d_obj = f['date']
            kind = f['kind']
            tmin, tmax = f['min'], f['max']
            
            # 1. Day Name (Mon, Tue...)
            day_str = d_obj.strftime("%a") # Mon, Tue
            dw = draw2.textlength(day_str, font=font_wx_day)
            draw2.text((cx - dw/2, wx_y_start), day_str, fill=TEXT, font=font_wx_day)
            
            # 2. Icon
            icon = load_icon(kind)
            if icon:
                icon = icon.resize((icon_size, icon_size))
                ix = int(cx - icon_size/2)
                iy = int(wx_y_start + 25 * SCALE)
                img2.paste(icon, (ix, iy), icon)
            
            # 3. Temp (Min/Max)
            t_str = f"{int(round(tmin))}°/{int(round(tmax))}°"
            tw = draw2.textlength(t_str, font=font_wx_temp)
            ty = wx_y_start + 85 * SCALE
            draw2.text((cx - tw/2, ty), t_str, fill=TEXT, font=font_wx_temp)

    # -------------------------
    # Save
    # -------------------------
    img = img2.resize((W, H), resample=Image.Resampling.LANCZOS)
    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")
    img.save("docs/latest.bmp")

if __name__ == "__main__":
    main()
