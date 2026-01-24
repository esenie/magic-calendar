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
SCALE = 2  # 2x render -> downscale to reduce jaggies on e-ink
W2, H2 = W * SCALE, H * SCALE

# =========================
# Colors (E-Ink friendly)
# =========================
TEXT = (0, 0, 0)
FADE = TEXT  # keep all text black (e-ink)
RED  = (200, 0, 0)

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

def fetch_5day_forecast(lat: float, lon: float, tzname="Asia/Seoul", days=5):
    """
    OpenWeather 3-hour forecast -> group by local date
    return list of dict:
      [{"date": date, "kind": "sun", "tmin": 1.2, "tmax": 7.8}, ...] length=days
    Rules:
      - kind: pick entry closest to 12:00 local time (fallback first entry of that day)
      - tmin/tmax: use main.temp_min / main.temp_max across the day
    """
    api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if not api_key:
        return []

    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    tz = pytz.timezone(tzname)
    today = datetime.now(tz).date()

    # group items by date
    by_day = {}
    for item in data.get("list", []):
        dt = datetime.fromtimestamp(item["dt"], tz)
        d = dt.date()
        if d < today:
            continue
        by_day.setdefault(d, []).append((dt, item))

    out = []
    for d in sorted(by_day.keys()):
        if len(out) >= days:
            break
        items = by_day[d]

        # icon/kind: closest to 12:00
        target = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=tz)
        best = None
        best_dist = None
        for dt, item in items:
            dist = abs((dt - target).total_seconds())
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best = item

        # fallback: first item
        if best is None:
            best = items[0][1]

        kind = ""
        if best.get("weather"):
            wid = int(best["weather"][0]["id"])
            kind = code_to_kind(wid)

        # min/max using temp_min/temp_max
        tmin = None
        tmax = None
        for _, item in items:
            main = item.get("main", {})
            lo = main.get("temp_min", main.get("temp"))
            hi = main.get("temp_max", main.get("temp"))

            if isinstance(lo, (int, float)):
                tmin = lo if tmin is None else min(tmin, lo)
            if isinstance(hi, (int, float)):
                tmax = hi if tmax is None else max(tmax, hi)

        out.append({"date": d, "kind": kind, "tmin": tmin, "tmax": tmax})

    return out

# -------------------------
# ICS helpers
# -------------------------
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
        dtstart = dtstart.dt

        summary = str(comp.get("summary", "")).strip()
        if not summary:
            continue

        if isinstance(dtstart, datetime):
            if dtstart.tzinfo is None:
                dtstart = tz.localize(dtstart)
            day = dtstart.astimezone(tz).date()
        else:
            day = dtstart  # date

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
    if draw.textlength(ell, font=font) >= max_w:
        return ell
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

    # Supersampled canvas
    img2 = Image.new("RGB", (W2, H2), "white")
    draw2 = ImageDraw.Draw(img2)

    # -------------------------
    # Fonts (scaled)
    # -------------------------
    font_month = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 235 * SCALE)
    font_date  = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 44 * SCALE)
    font_dow   = ImageFont.truetype("assets/NanumGothicBold.ttf", 32 * SCALE)
    font_event = ImageFont.truetype("assets/NanumSquareEB.ttf", 14 * SCALE)

    font_label = ImageFont.truetype("assets/Inter_28pt-ExtraLight.ttf", 12 * SCALE)
    font_wday  = ImageFont.truetype("assets/NanumGothicBold.ttf", 14 * SCALE)  # forecast day label
    font_temp  = ImageFont.truetype("assets/Inter_28pt-ExtraLight.ttf", 12 * SCALE)

    # -------------------------
    # Layout: minimize margins
    # -------------------------
    side_margin = 6 * SCALE
    top_margin  = 4 * SCALE
    bottom_margin = 4 * SCALE

    # ---------- Top-right updated time (keep) ----------
    updated = now.strftime("%m-%d %H:%M")
    uw = draw2.textlength(updated, font=font_label)
    draw2.text((W2 - side_margin - uw, 6 * SCALE), updated, fill=TEXT, font=font_label)

    # ---------- Big Month centered ----------
    mstr = str(month)
    mw = draw2.textlength(mstr, font=font_month)
    month_y = top_margin
    draw2.text(((W2 - mw) / 2, month_y), mstr, fill=TEXT, font=font_month)

    month_bottom = month_y + font_month.size

    # ---------- DOW + GRID positioning ----------
    month_to_dow_gap = 40 * SCALE  # 월 숫자와 요일 사이 간격
    dow_y = month_bottom + month_to_dow_gap

    # ---------- Bottom 5-day forecast area ----------
    # 화면 아래에 5일 예보를 깔기 위해 고정 높이 할당
    forecast_h = 150 * SCALE  # (최종 75px) -> 더 크고 싶으면 170~190으로 올려도 됨
    forecast_top = H2 - bottom_margin - forecast_h
    forecast_bottom = H2 - bottom_margin

    # ---------- Calendar grid occupies everything between grid_top and forecast_top ----------
    grid_left = side_margin
    grid_right = W2 - side_margin
    grid_w = grid_right - grid_left

    grid_top = dow_y + (40 * SCALE)
    grid_bottom = forecast_top - (10 * SCALE)  # forecast와 간격

    cols, rows = 7, 6
    cell_w = grid_w / cols
    cell_h = (grid_bottom - grid_top) / rows

    # Draw DOW
    for c, dch in enumerate(DOW):
        x = grid_left + c * cell_w + cell_w / 2
        color = RED if c == 0 else TEXT
        dw = draw2.textlength(dch, font=font_dow)
        draw2.text((x - dw / 2, dow_y), dch, fill=color, font=font_dow)

    # Events
    try:
        events_by_date = fetch_events_by_date(max_per_day=2)
    except Exception:
        events_by_date = {}

    # Month days
    cal = calendar.Calendar(firstweekday=6)
    days = list(cal.itermonthdates(year, month))[:42]

    for i, day in enumerate(days):
        r, c = divmod(i, cols)
        x0 = grid_left + c * cell_w
        y0 = grid_top + r * cell_h

        # Sunday red
        is_sunday = (c == 0)
        date_color = RED if is_sunday else TEXT

        # Date position: 위쪽, 일정과 간격 확보
        s = str(day.day)
        sw = draw2.textlength(s, font=font_date)
        sx = x0 + (cell_w - sw) / 2
        sy = y0 + int(cell_h * 0.12)
        draw2.text((sx, sy), s, fill=date_color, font=font_date)

        # Today underline
        if day == today:
            uy = sy + int(46 * SCALE)
            draw2.line(
                [(x0 + cell_w * 0.30, uy), (x0 + cell_w * 0.70, uy)],
                fill=RED,
                width=max(1, int(2 * SCALE))
            )

        # Events
        evs = events_by_date.get(day, [])
        if evs:
            # 날짜 밑에서 조금 더 내려가서 시작
            base_y = y0 + int(cell_h * 0.58)
            left_pad = x0 + (8 * SCALE)
            dot_r = int(3 * SCALE)

            text_x = left_pad + (12 * SCALE)
            max_text_w = (x0 + cell_w) - text_x - (6 * SCALE)
            line_gap = int(18 * SCALE)

            for idx, t in enumerate(evs[:2]):
                t2 = truncate(draw2, t, font_event, max_text_w)
                if not t2:
                    continue
                ty = base_y + idx * line_gap

                cx = left_pad + dot_r
                cy = ty + int(7 * SCALE)
                draw2.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=RED)
                draw2.text((text_x, ty), t2, fill=TEXT, font=font_event)

    # =========================
    # 5-day forecast (BOTTOM)
    # =========================
    ensure_icons()
    lat = float(os.getenv("OPENWEATHER_LAT", "37.5665"))
    lon = float(os.getenv("OPENWEATHER_LON", "126.9780"))

    try:
        fc = fetch_5day_forecast(lat, lon, tzname="Asia/Seoul", days=5)
    except Exception:
        fc = []

    # forecast layout (5 columns across full width)
    fx0 = grid_left
    fx1 = grid_right
    fw = fx1 - fx0
    fcols = 5
    fcell_w = fw / fcols

    # optional: a subtle separator line above forecast
    sep_y = forecast_top + (2 * SCALE)
    draw2.line([(fx0, sep_y), (fx1, sep_y)], fill=(0, 0, 0), width=1)

    # content region inside forecast
    content_top = forecast_top + (10 * SCALE)
    content_bottom = forecast_bottom - (6 * SCALE)
    content_h = content_bottom - content_top

    icon_size = int(40 * SCALE)
    # positions within each forecast cell
    label_y = content_top
    icon_y = content_top + int(22 * SCALE)
    temp_y = icon_y + icon_size + int(6 * SCALE)

    def fmt_minmax(tmin, tmax):
        if tmin is None or tmax is None:
            return ""
        return f"{int(round(tmin))}°/{int(round(tmax))}°"

    # if forecast missing, still draw placeholders to keep layout stable
    for idx in range(fcols):
        x_left = fx0 + idx * fcell_w
        x_center = x_left + fcell_w / 2

        if idx < len(fc):
            d = fc[idx]["date"]
            kind = fc[idx]["kind"]
            tmin = fc[idx]["tmin"]
            tmax = fc[idx]["tmax"]

            # label: "1/16" + 요일(한글 원하면 바꿔줄게)
            label = f"{d.month}/{d.day}"
            # draw label
            tw = draw2.textlength(label, font=font_wday)
            draw2.text((x_center - tw / 2, label_y), label, fill=TEXT, font=font_wday)

            # icon
            icon = load_icon(kind)
            if icon:
                icon = icon.resize((icon_size, icon_size))
                img2.paste(icon, (int(x_center - icon_size / 2), int(icon_y)), icon)

            # temps
            tstr = fmt_minmax(tmin, tmax)
            tw2 = draw2.textlength(tstr, font=font_temp)
            draw2.text((x_center - tw2 / 2, temp_y), tstr, fill=TEXT, font=font_temp)
        else:
            # placeholder (empty)
            pass

    # Downscale (anti-aliasing)
    img = img2.resize((W, H), resample=Image.Resampling.LANCZOS)

    # Save (DO NOT change these paths)
    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")
    img.save("docs/latest.bmp")

if __name__ == "__main__":
    main()
