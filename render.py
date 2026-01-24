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
FADE = TEXT  # keep all text black (e-ink)
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

        # closest to 12:00
        target = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=tz)
        best_item = None
        best_dist = None
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

    # =========================
    # Tuning knobs (NEW)
    # =========================
    GRID_TO_FORECAST_GAP = 4 * SCALE   # (문제3) 마지막 주 ↔ 5일예보 사이 여백
    FORECAST_H = 130 * SCALE           # 5일예보 높이 (135~160 튜닝 추천)

    DATE_TOP_PAD_FRAC = 0.10           # 날짜 y 시작(셀 높이 대비 비율)
    EVENT_TOP_PAD = 10 * SCALE          # 날짜 bbox 아래로 이벤트 시작 여백 (문제1)
    EVENT_BOTTOM_PAD = 10 * SCALE      # 셀 바닥 여백
    EVENT_LINE_GAP = 22 * SCALE        # 이벤트 줄 간격

    UNDERLINE_GAP = 1 * SCALE          # (문제2) 글자 bbox 밑으로 밑줄 간격
    UNDERLINE_INSET_FRAC = 0.06        # 밑줄 좌/우 inset (bbox width 대비)
    UNDERLINE_W = max(1, int(2 * SCALE))

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

    # ---------- DOW + GRID positioning ----------
    month_to_dow_gap = 30 * SCALE
    dow_y = month_bottom + month_to_dow_gap

    # ---------- Bottom 5-day forecast area ----------
    forecast_h = FORECAST_H
    forecast_top = H2 - bottom_margin - forecast_h
    forecast_bottom = H2 - bottom_margin

    # ---------- Calendar grid occupies between grid_top and forecast_top ----------
    grid_left = side_margin
    grid_right = W2 - side_margin
    grid_w = grid_right - grid_left

    grid_top = dow_y + (28 * SCALE)
    grid_bottom = forecast_top - GRID_TO_FORECAST_GAP  # (NEW) gap control

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

    # --------- Event alignment knobs (기존 요청 반영) ----------
    EVENT_LEFT_PAD = 14 * SCALE       # dot 시작 x를 더 오른쪽으로
    EVENT_TEXT_GAP = 14 * SCALE       # dot 이후 텍스트 시작 오프셋

    for i, day in enumerate(days):
        r, c = divmod(i, cols)
        x0 = grid_left + c * cell_w
        y0 = grid_top + r * cell_h

        # Sunday red
        is_sunday = (c == 0)
        date_color = RED if is_sunday else TEXT

        # =========================
        # Date + TODAY underline (bbox 기반, 고정 노브 적용)
        # =========================
        s = str(day.day)
        sw = draw2.textlength(s, font=font_date)
        sx = x0 + (cell_w - sw) / 2
        sy = y0 + int(cell_h * DATE_TOP_PAD_FRAC)

        draw2.text((sx, sy), s, fill=date_color, font=font_date)

        bx1, by1, bx2, by2 = draw2.textbbox((sx, sy), s, font=font_date)

        if day == today:
            uy = by2 + UNDERLINE_GAP
            inset = int((bx2 - bx1) * UNDERLINE_INSET_FRAC)
            ux1 = bx1 + inset
            ux2 = bx2 - inset
            draw2.line([(ux1, uy), (ux2, uy)], fill=RED, width=UNDERLINE_W)

        # =========================
        # Events (bbox 기반: 날짜와 절대 안 겹치게 + 셀 남은공간에 맞춰 자동 줄수 조절)
        # =========================
        evs = events_by_date.get(day, [])
        if evs:
            # 날짜 bbox 아래에서 시작 (겹침 방지)
            base_y = by2 + EVENT_TOP_PAD

            # 최소 시작선 확보(특이 케이스 방지)
            min_base = y0 + int(cell_h * 0.45)
            if base_y < min_base:
                base_y = min_base

            left_pad = x0 + EVENT_LEFT_PAD
            dot_r = int(3 * SCALE)
            text_x = left_pad + EVENT_TEXT_GAP
            max_text_w = (x0 + cell_w) - text_x - (6 * SCALE)

            # 셀 하단을 넘지 않도록 표시 가능한 줄 수 계산
            cell_bottom_limit = y0 + cell_h - EVENT_BOTTOM_PAD
            available_h = cell_bottom_limit - base_y
            if available_h > 0:
                max_lines = int(available_h // EVENT_LINE_GAP) + 1
                max_lines = max(0, min(2, max_lines))  # 최대 2줄 유지
            else:
                max_lines = 0

            for idx, t in enumerate(evs[:max_lines]):
                t2 = truncate(draw2, t, font_event, max_text_w)
                if not t2:
                    continue
                ty = base_y + idx * EVENT_LINE_GAP

                # red dot
                cx = left_pad + dot_r
                cy = ty + int(7 * SCALE)
                draw2.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=RED)

                # text
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

    fx0 = grid_left
    fx1 = grid_right
    fw = fx1 - fx0
    fcols = 5
    fcell_w = fw / fcols

    # separator line
    sep_y = forecast_top + (2 * SCALE)
    draw2.line([(fx0, sep_y), (fx1, sep_y)], fill=(0, 0, 0), width=1)

    content_top = forecast_top + (10 * SCALE)
    content_bottom = forecast_bottom - (6 * SCALE)

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

    # Downscale (anti-aliasing)
    img = img2.resize((W, H), resample=Image.Resampling.LANCZOS)

    # Save (DO NOT change these paths)
    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")
    img.save("docs/latest.bmp")

if __name__ == "__main__":
    main()
