from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
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

        target = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=tz)
        best_item, best_dist = None, None
        for dt, item in items:
            dist = abs((dt - target).total_seconds())
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_item = item
        if best_item is None:
            best_item = items[0][1]

        kind = ""
        if best_item.get("weather"):
            wid = int(best_item["weather"][0]["id"])
            kind = code_to_kind(wid)

        tmin, tmax = None, None
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
    if draw.textlength(ell, font=font) >= max_w:
        return ell
    while text and draw.textlength(text + ell, font=font) > max_w:
        text = text[:-1]
    return text + ell

def needed_week_rows(days42, month: int) -> int:
    last_idx = 0
    for i, d in enumerate(days42):
        if d.month == month:
            last_idx = i
    return (last_idx // 7) + 1  # 5 or 6

# =========================
# Main
# =========================
def main():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.now(tz)
    today = now.date()
    year, month = now.year, now.month

    img2 = Image.new("RGB", (W2, H2), "white")
    draw2 = ImageDraw.Draw(img2)

    # -------------------------
    # Fonts (scaled)
    # -------------------------
    font_month = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 235 * SCALE)
    font_date  = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 44 * SCALE)
    font_dow   = ImageFont.truetype("assets/NanumGothicBold.ttf", 32 * SCALE)
    font_event = ImageFont.truetype("assets/NanumSquareEB.ttf", 12 * SCALE)

    font_label = ImageFont.truetype("assets/Inter_28pt-ExtraLight.ttf", 12 * SCALE)
    font_wday  = ImageFont.truetype("assets/NanumGothicBold.ttf", 14 * SCALE)
    font_temp  = ImageFont.truetype("assets/Inter_28pt-ExtraLight.ttf", 12 * SCALE)

    # -------------------------
    # Layout
    # -------------------------
    side_margin = 6 * SCALE
    top_margin  = 4 * SCALE
    bottom_margin = 4 * SCALE

    # =========================
    # Tuning knobs (applied)
    # =========================
    GRID_TO_FORECAST_GAP = 2 * SCALE
    FORECAST_H = 110 * SCALE

    # 날짜 위치
    DATE_TOP_PAD_FRAC = 0.08

    # ✅ 요청 반영:
    # - 날짜 ↔ 이벤트 더 멀게: EVENT_BASE_FRAC ↑
    # - 이벤트 1줄 ↔ 2줄 더 가깝게: EVENT_LINE_GAP ↓
    EVENT_BASE_FRAC = 0.56
    EVENT_LINE_GAP = 6 * SCALE
    EVENT_BOTTOM_PAD = 4 * SCALE

    # 오늘 네모 박스
    TODAY_BOX_PAD_X = 10 * SCALE
    TODAY_BOX_PAD_Y = 8 * SCALE
    TODAY_BOX_W = max(2, int(3 * SCALE))
    TODAY_BOX_RADIUS = 10 * SCALE

    # 오늘 박스 아래로 이벤트 시작 밀어내기 여유
    TODAY_BOX_TO_EVENT_GAP = 6 * SCALE

    # ---------- Top-right updated time ----------
    updated = now.strftime("%m-%d %H:%M")
    uw = draw2.textlength(updated, font=font_label)
    draw2.text((W2 - side_margin - uw, 6 * SCALE), updated, fill=TEXT, font=font_label)

    # ---------- Big Month centered ----------
    mstr = str(month)
    mw = draw2.textlength(mstr, font=font_month)
    month_y = top_margin
    draw2.text(((W2 - mw) / 2, month_y), mstr, fill=TEXT, font=font_month)
    month_bottom = month_y + font_month.size

    # ---------- DOW positioning ----------
    month_to_dow_gap = 24 * SCALE
    dow_y = month_bottom + month_to_dow_gap

    # ---------- Forecast area ----------
    forecast_top = H2 - bottom_margin - FORECAST_H
    forecast_bottom = H2 - bottom_margin

    # ---------- Grid area ----------
    grid_left = side_margin
    grid_right = W2 - side_margin
    grid_w = grid_right - grid_left

    # ✅ 요청 반영: 요일 ↔ 날짜 간격 넓히기 (grid_top 증가)
    grid_top = dow_y + (30 * SCALE)
    grid_bottom = forecast_top - GRID_TO_FORECAST_GAP

    cols = 7

    # Month days
    cal = calendar.Calendar(firstweekday=6)
    days42 = list(cal.itermonthdates(year, month))[:42]
    rows = needed_week_rows(days42, month)
    days = days42[:rows * 7]

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

    # Event alignment knobs
    EVENT_LEFT_PAD = 14 * SCALE
    EVENT_TEXT_GAP = 14 * SCALE
    dot_r = int(3 * SCALE)

    # event line height
    _, e_y1, _, e_y2 = draw2.textbbox((0, 0), "가A", font=font_event)
    event_line_h = (e_y2 - e_y1)

    for i, day in enumerate(days):
        r, c = divmod(i, cols)
        x0 = grid_left + c * cell_w
        y0 = grid_top + r * cell_h

        date_color = RED if c == 0 else TEXT

        # -------------------------
        # Date draw
        # -------------------------
        s = str(day.day)
        sw = draw2.textlength(s, font=font_date)
        sx = x0 + (cell_w - sw) / 2
        sy = y0 + int(cell_h * DATE_TOP_PAD_FRAC)
        draw2.text((sx, sy), s, fill=date_color, font=font_date)

        bx1, by1, bx2, by2 = draw2.textbbox((sx, sy), s, font=font_date)

        # -------------------------
        # TODAY highlight (rounded rectangle)
        # -------------------------
        today_box_bottom = None
        if day == today:
            rx1 = bx1 - TODAY_BOX_PAD_X
            ry1 = by1 - TODAY_BOX_PAD_Y
            rx2 = bx2 + TODAY_BOX_PAD_X
            ry2 = by2 + TODAY_BOX_PAD_Y
            today_box_bottom = ry2

            try:
                draw2.rounded_rectangle(
                    [rx1, ry1, rx2, ry2],
                    radius=TODAY_BOX_RADIUS,
                    outline=RED,
                    width=TODAY_BOX_W
                )
            except Exception:
                draw2.rectangle([rx1, ry1, rx2, ry2], outline=RED, width=TODAY_BOX_W)

        # -------------------------
        # Events (2 lines)
        # -------------------------
        evs = events_by_date.get(day, [])
        if evs:
            # ✅ 요청 반영: 날짜 ↔ 이벤트 더 멀게 (EVENT_BASE_FRAC)
            base_y = y0 + int(cell_h * EVENT_BASE_FRAC)

            # ✅ 오늘은 박스 아래로 이벤트 시작을 밀어내서 절대 안 겹치게
            if today_box_bottom is not None:
                base_y = max(base_y, today_box_bottom + TODAY_BOX_TO_EVENT_GAP)

            left_pad = x0 + EVENT_LEFT_PAD
            text_x = left_pad + EVENT_TEXT_GAP
            max_text_w = (x0 + cell_w) - text_x - (6 * SCALE)

            for idx, t in enumerate(evs[:2]):
                t2 = truncate(draw2, t, font_event, max_text_w)
                if not t2:
                    continue

                # ✅ 요청 반영: 이벤트 1~2줄 더 가깝게 (EVENT_LINE_GAP 감소)
                ty = base_y + idx * (event_line_h + EVENT_LINE_GAP)

                if ty + event_line_h > (y0 + cell_h - EVENT_BOTTOM_PAD):
                    break

                cx = left_pad + dot_r
                cy = ty + int(event_line_h * 0.55)
                draw2.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=RED)
                draw2.text((text_x, ty), t2, fill=TEXT, font=font_event)

    # =========================
    # 5-day forecast
    # =========================
    ensure_icons()
    lat = float(os.getenv("OPENWEATHER_LAT", "37.5665"))
    lon = float(os.getenv("OPENWEATHER_LON", "126.9780"))

    try:
        fc = fetch_5day_forecast(lat, lon, tzname="Asia/Seoul", days=5)
    except Exception:
        fc = []

    fx0 = grid_left
    fx1 = grid_right
    fw = fx1 - fx0
    fcols = 5
    fcell_w = fw / fcols

    # separator line
    sep_y = forecast_top + (2 * SCALE)
    draw2.line([(fx0, sep_y), (fx1, sep_y)], fill=(0, 0, 0), width=1)

    content_top = forecast_top + (10 * SCALE)
    icon_size = int(40 * SCALE)
    label_y = content_top
    icon_y = content_top + int(22 * SCALE)
    temp_y = icon_y + icon_size + int(6 * SCALE)

    def fmt_minmax(tmin, tmax):
        if tmin is None or tmax is None:
            return ""
        return f"{int(round(tmin))}°/{int(round(tmax))}°"

    for idx in range(fcols):
        x_left = fx0 + idx * fcell_w
        x_center = x_left + fcell_w / 2

        if idx < len(fc):
            d = fc[idx]["date"]
            kind = fc[idx]["kind"]
            tmin = fc[idx]["tmin"]
            tmax = fc[idx]["tmax"]

            label = f"{d.month}/{d.day}"
            tw = draw2.textlength(label, font=font_wday)
            draw2.text((x_center - tw / 2, label_y), label, fill=TEXT, font=font_wday)

            icon = load_icon(kind)
            if icon:
                icon = icon.resize((icon_size, icon_size))
                img2.paste(icon, (int(x_center - icon_size / 2), int(icon_y)), icon)

            tstr = fmt_minmax(tmin, tmax)
            tw2 = draw2.textlength(tstr, font=font_temp)
            draw2.text((x_center - tw2 / 2, temp_y), tstr, fill=TEXT, font=font_temp)

    # Downscale
    img = img2.resize((W, H), resample=Image.Resampling.LANCZOS)

    # Save (DO NOT change these paths)
    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")
    img.save("docs/latest.bmp")

if __name__ == "__main__":
    main()
