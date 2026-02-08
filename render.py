from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
import calendar
import pytz
import os
import requests
import subprocess
from icalendar import Calendar
import holidays  # 대한민국 공휴일 라이브러리 추가

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

    if c == 0: return "sun"
    if c in (1, 2, 3): return "cloud"
    if c in (45, 48): return "fog"
    if 51 <= c <= 67: return "rain"
    if 71 <= c <= 77: return "snow"
    if 80 <= c <= 82: return "rain"
    if 85 <= c <= 86: return "snow"
    if c in (95, 96, 99): return "thunder"
    return "cloud"

def fetch_openmeteo_daily_5(lat: float, lon: float, tzname="Asia/Seoul", days=5):
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
    times = daily.get("time", []) or []
    tmins = daily.get("temperature_2m_min", []) or []
    tmaxs = daily.get("temperature_2m_max", []) or []
    wcodes = daily.get("weathercode", []) or []

    out = []
    for i in range(min(days, len(times), len(tmins), len(tmaxs), len(wcodes))):
        d = datetime.strptime(times[i], "%Y-%m-%d").date()
        out.append({
            "date": d,
            "kind": openmeteo_code_to_kind(wcodes[i]),
            "tmin": tmins[i],
            "tmax": tmaxs[i],
        })
    return out

# =========================
# ICS helpers
# =========================
def fetch_events_by_date(tzname="Asia/Seoul", max_per_day=2):
    url = os.getenv("ICAL_URL", "").strip()
    if not url: return {}
    if url.startswith("webcal://"): url = "https://" + url[len("webcal://"):]

    r = requests.get(url, timeout=25)
    r.raise_for_status()
    cal = Calendar.from_ical(r.text)
    tz = pytz.timezone(tzname)

    events = {}
    for comp in cal.walk():
        if comp.name != "VEVENT": continue
        dtstart = comp.get("dtstart")
        if not dtstart: continue
        dtstart = dtstart.dt
        summary = str(comp.get("summary", "")).strip()
        if not summary: continue

        if isinstance(dtstart, datetime):
            if dtstart.tzinfo is None: dtstart = tz.localize(dtstart)
            day = dtstart.astimezone(tz).date()
        else:
            day = dtstart
        events.setdefault(day, []).append(summary)
    
    for d in list(events.keys()):
        events[d] = events[d][:max_per_day]
    return events

def truncate(draw, text, font, max_w):
    text = (text or "").replace("\n", " ").strip()
    if not text: return ""
    if draw.textlength(text, font=font) <= max_w: return text
    ell = "…"
    while text and draw.textlength(text + ell, font=font) > max_w:
        text = text[:-1]
    return text + ell

def needed_week_rows(days42, month: int) -> int:
    last_idx = 0
    for i, d in enumerate(days42):
        if d.month == month: last_idx = i
    return (last_idx // 7) + 1

# =========================
# Main
# =========================
def main():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.now(tz)
    today = now.date()
    year, month = now.year, now.month

    # 대한민국 공휴일 정보 로드
    kr_holidays = holidays.KR(years=[year, year + 1])

    img2 = Image.new("RGB", (W2, H2), "white")
    draw2 = ImageDraw.Draw(img2)

    # Fonts (Paths must exist in your assets folder)
    font_month = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 235 * SCALE)
    font_date  = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 44 * SCALE)
    font_dow   = ImageFont.truetype("assets/NanumGothicBold.ttf", 32 * SCALE)
    font_event = ImageFont.truetype("assets/NanumSquareEB.ttf", 12 * SCALE)
    font_label = ImageFont.truetype("assets/Inter_28pt-ExtraLight.ttf", 12 * SCALE)
    font_wday  = ImageFont.truetype("assets/NanumGothicBold.ttf", 14 * SCALE)
    font_temp  = ImageFont.truetype("assets/Inter_28pt-ExtraLight.ttf", 12 * SCALE)

    side_margin = 6 * SCALE
    top_margin  = 4 * SCALE
    bottom_margin = 4 * SCALE
    GRID_TO_FORECAST_GAP = 2 * SCALE
    FORECAST_H = 110 * SCALE

    # Updated time
    updated = now.strftime("%m-%d %H:%M")
    uw = draw2.textlength(updated, font=font_label)
    draw2.text((W2 - side_margin - uw, 6 * SCALE), updated, fill=TEXT, font=font_label)

    # Month
    mstr = str(month)
    mw = draw2.textlength(mstr, font=font_month)
    month_y = top_margin
    draw2.text(((W2 - mw) / 2, month_y), mstr, fill=TEXT, font=font_month)
    month_bottom = month_y + font_month.size

    # DOW & Grid
    dow_y = month_bottom + 24 * SCALE
    grid_top = dow_y + (30 * SCALE)
    grid_bottom = H2 - bottom_margin - FORECAST_H - GRID_TO_FORECAST_GAP
    grid_left, grid_right = side_margin, W2 - side_margin
    grid_w = grid_right - grid_left

    cal_obj = calendar.Calendar(firstweekday=6)
    days42 = list(cal_obj.itermonthdates(year, month))[:42]
    rows = needed_week_rows(days42, month)
    days = days42[:rows * 7]
    cell_w, cell_h = grid_w / 7, (grid_bottom - grid_top) / rows

    # Draw DOW
    for c, dch in enumerate(DOW):
        x = grid_left + c * cell_w + cell_w / 2
        draw2.text((x - draw2.textlength(dch, font=font_dow)/2, dow_y), dch, fill=RED if c==0 else TEXT, font=font_dow)

    # Fetch ICS events
    try:
        events_by_date = fetch_events_by_date(max_per_day=2)
    except Exception:
        events_by_date = {}

    # Draw Days
    for i, day in enumerate(days):
        r, c = divmod(i, cols=7)
        x0, y0 = grid_left + c * cell_w, grid_top + r * cell_h

        # 공휴일 체크 및 색상 결정
        is_holiday = day in kr_holidays
        date_color = RED if (c == 0 or is_holiday) else TEXT

        # 날짜 텍스트
        s = str(day.day)
        sw = draw2.textlength(s, font=font_date)
        sx, sy = x0 + (cell_w - sw) / 2, y0 + int(cell_h * 0.08)
        draw2.text((sx, sy), s, fill=date_color, font=font_date)
        bx1, by1, bx2, by2 = draw2.textbbox((sx, sy), s, font=font_date)

        # 오늘 표시
        today_box_bottom = None
        if day == today:
            pad_x, pad_y = 10 * SCALE, 8 * SCALE
            draw2.rounded_rectangle([bx1-pad_x, by1-pad_y, bx2+pad_x, by2+pad_y], radius=10*SCALE, outline=RED, width=3*SCALE)
            today_box_bottom = by2 + pad_y

        # 이벤트 및 공휴일 이름 표시
        evs = events_by_date.get(day, []).copy()
        if is_holiday:
            h_name = kr_holidays.get(day)
            if h_name not in evs: evs.insert(0, h_name) # 공휴일 이름을 맨 처음에 추가

        if evs:
            base_y = max(y0 + int(cell_h * 0.56), (today_box_bottom or 0) + 6*SCALE)
            dot_r = int(3 * SCALE)
            _, e_y1, _, e_y2 = draw2.textbbox((0, 0), "가A", font=font_event)
            line_h = e_y2 - e_y1
            
            for idx, t in enumerate(evs[:2]):
                max_w = cell_w - (25 * SCALE)
                t2 = truncate(draw2, t, font_event, max_w)
                ty = base_y + idx * (line_h + 6*SCALE)
                if ty + line_h > (y0 + cell_h - 4*SCALE): break
                
                cx = x0 + 14*SCALE + dot_r
                draw2.ellipse([cx-dot_r, ty+line_h*0.55-dot_r, cx+dot_r, ty+line_h*0.55+dot_r], fill=RED if is_holiday and idx==0 else RED)
                draw2.text((x0 + 28*SCALE, ty), t2, fill=TEXT, font=font_event)

    # Forecast (Open-Meteo)
    ensure_icons()
    lat = float(os.getenv("FORECAST_LAT", "37.5665"))
    lon = float(os.getenv("FORECAST_LON", "126.9780"))
    try: fc = fetch_openmeteo_daily_5(lat, lon)
    except Exception: fc = []

    sep_y = H2 - bottom_margin - FORECAST_H + 2*SCALE
    draw2.line([(side_margin, sep_y), (W2-side_margin, sep_y)], fill=TEXT, width=1)

    f_cell_w = (W2 - 2*side_margin) / 5
    for idx in range(min(5, len(fc))):
        cx = side_margin + idx * f_cell_w + f_cell_w/2
        d, kind, tmin, tmax = fc[idx]["date"], fc[idx]["kind"], fc[idx]["tmin"], fc[idx]["tmax"]
        
        # Label
        lbl = f"{d.month}/{d.day}"
        draw2.text((cx - draw2.textlength(lbl, font=font_wday)/2, H2 - FORECAST_H + 10*SCALE), lbl, fill=TEXT, font=font_wday)
        # Icon
        icon = load_icon(kind)
        if icon:
            icon = icon.resize((40*SCALE, 40*SCALE))
            img2.paste(icon, (int(cx - 20*SCALE), int(H2 - FORECAST_H + 32*SCALE)), icon)
        # Temp
        tstr = f"{int(round(tmin))}°/{int(round(tmax))}°" if tmin is not None else ""
        draw2.text((cx - draw2.textlength(tstr, font=font_temp)/2, H2 - FORECAST_H + 78*SCALE), tstr, fill=TEXT, font=font_temp)

    # Save
    img = img2.resize((W, H), resample=Image.Resampling.LANCZOS)
    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")
    img.save("docs/latest.bmp")

if __name__ == "__main__":
    main()
