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
FADE = TEXT
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

def get_today_tmro_kind_and_temps(lat: float, lon: float, tzname="Asia/Seoul"):
    """
    Returns:
      (today_kind, tmro_kind, (tmin_today, tmax_today), (tmin_tmro, tmax_tmro))
    """
    api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if not api_key:
        return ("", "", (None, None), (None, None))

    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    tz = pytz.timezone(tzname)
    today = datetime.now(tz).date()
    tmro = today + timedelta(days=1)

    picked_kind = {}
    tmin = {today: None, tmro: None}
    tmax = {today: None, tmro: None}

    for item in data.get("list", []):
        dt = datetime.fromtimestamp(item["dt"], tz)
        d = dt.date()
        if d not in (today, tmro):
            continue

        # kind: first appearance for that day
        if d not in picked_kind and item.get("weather"):
            wid = int(item["weather"][0]["id"])
            picked_kind[d] = code_to_kind(wid)

        # min/max temps across all 3-hour slots
        main = item.get("main", {})
        temp = main.get("temp")
        if isinstance(temp, (int, float)):
            if tmin[d] is None or temp < tmin[d]:
                tmin[d] = temp
            if tmax[d] is None or temp > tmax[d]:
                tmax[d] = temp

        if today in picked_kind and tmro in picked_kind and tmin[today] is not None and tmin[tmro] is not None:
            # enough data
            pass

    return (
        picked_kind.get(today, ""),
        picked_kind.get(tmro, ""),
        (tmin.get(today), tmax.get(today)),
        (tmin.get(tmro), tmax.get(tmro)),
    )

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
    # 숫자(날짜/월): Inter_28pt-Regular.ttf
    font_month = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 220 * SCALE)
    font_date  = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 42 * SCALE)

    # 요일: NanumGothicBold.ttf
    font_dow   = ImageFont.truetype("assets/NanumGothicBold.ttf", 30 * SCALE)

    # 일정: NanumSquareEB.ttf
    font_event = ImageFont.truetype("assets/NanumSquareR.ttf", 14 * SCALE)

    # 라벨/업데이트/기온: 얇은 Inter
    font_label = ImageFont.truetype("assets/Inter_28pt-ExtraLight.ttf", 12 * SCALE)
    font_temp  = ImageFont.truetype("assets/Inter_28pt-ExtraLight.ttf", 11 * SCALE)

    # -------------------------
    # Layout (FULLSCREEN tuned)
    #  - 네 사진 기준: 아래 여백이 너무 크므로 grid를 아래로 확장
    #  - 클립/베젤 고려한 안전 여백은 아주 작게만 둠
    # -------------------------
    side_margin = 18 * SCALE   # 좌우 여백 대폭 축소 (60 -> 18)
    top_margin  = 20 * SCALE   # 상단도 축소

    # Weather widget (top-left)
    wx, wy = side_margin, 12 * SCALE
    widget_w, gap = 190 * SCALE, 10 * SCALE
    col_w = (widget_w - gap) / 2

    def center_text(x_left, y, t, font, fill=TEXT):
        tw = draw2.textlength(t, font=font)
        draw2.text((x_left + (col_w - tw) / 2, y), t, fill=fill, font=font)

    # Labels
    center_text(wx, wy, "TODAY", font_label, TEXT)
    center_text(wx + col_w + gap, wy, "TMRO", font_label, TEXT)

    # Icons + temps
    ensure_icons()
    lat = float(os.getenv("OPENWEATHER_LAT", "37.5665"))
    lon = float(os.getenv("OPENWEATHER_LON", "126.9780"))
    try:
        k_today, k_tmro, (tmin0, tmax0), (tmin1, tmax1) = get_today_tmro_kind_and_temps(lat, lon)
    except Exception:
        k_today, k_tmro, (tmin0, tmax0), (tmin1, tmax1) = "", "", (None, None), (None, None)

    icon_size = 44 * SCALE
    icon_y = wy + 16 * SCALE

    def paste_icon(kind, x_left):
        icon = load_icon(kind)
        if not icon:
            return
        icon = icon.resize((icon_size, icon_size))
        x = int(x_left + (col_w - icon_size) / 2)
        img2.paste(icon, (x, int(icon_y)), icon)

    paste_icon(k_today, wx)
    paste_icon(k_tmro, wx + col_w + gap)

    def fmt_minmax(tmin, tmax):
        if tmin is None or tmax is None:
            return ""
        return f"{int(round(tmin))}°/{int(round(tmax))}°"

    temp_y = icon_y + icon_size + (4 * SCALE)
    center_text(wx, temp_y, fmt_minmax(tmin0, tmax0), font_temp, TEXT)
    center_text(wx + col_w + gap, temp_y, fmt_minmax(tmin1, tmax1), font_temp, TEXT)

    # Update time (top-right)
    updated = now.strftime("%m-%d %H:%M")
    uw = draw2.textlength(updated, font=font_label)
    draw2.text((W2 - side_margin - uw, 12 * SCALE), updated, fill=TEXT, font=font_label)

    # Month (big number centered)
    mstr = str(month)
    mw = draw2.textlength(mstr, font=font_month)
    draw2.text(((W2 - mw) / 2, top_margin), mstr, fill=TEXT, font=font_month)

    # Month bottom & spacing to DOW
    month_bottom = top_margin + font_month.size
    month_to_dow_gap = 52 * SCALE  # (기존보다 크게) 월 숫자와 요일 사이 여백 확장

    dow_y = month_bottom + month_to_dow_gap

    # Grid (push DOWN to kill bottom whitespace)
    grid_left = side_margin
    grid_right = W2 - side_margin
    grid_w = grid_right - grid_left

    # 요일 아래에서 그리드 시작 (조금 위로 당겨서 전체를 더 크게 쓰되, 아래를 꽉 채움)
    grid_top = dow_y + (38 * SCALE)

    # 하단 안전 여백 최소화: 거의 끝까지
    grid_bottom = H2 - (12 * SCALE)

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
    events_by_date = {}
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

        # Date position: 위로 조금 올려서 "날짜-일정" 간격 확보
        s = str(day.day)
        sw = draw2.textlength(s, font=font_date)
        sx = x0 + (cell_w - sw) / 2
        sy = y0 + int(cell_h * 0.16)  # 날짜를 더 위로

        draw2.text((sx, sy), s, fill=date_color, font=font_date)

        # Today underline (얇게)
        if day == today:
            uy = sy + int(44 * SCALE)
            draw2.line(
                [(x0 + cell_w * 0.30, uy), (x0 + cell_w * 0.70, uy)],
                fill=RED,
                width=max(1, int(2 * SCALE))
            )

        # Events: 날짜와 더 떨어지게 아래로
        evs = events_by_date.get(day, [])
        if evs:
            base_y = y0 + int(cell_h * 0.62)  # 더 아래로
            left_pad = x0 + (10 * SCALE)
            dot_r = int(3 * SCALE)

            text_x = left_pad + (12 * SCALE)
            max_text_w = (x0 + cell_w) - text_x - (6 * SCALE)

            line_gap = int(18 * SCALE)

            for idx, t in enumerate(evs[:2]):
                t2 = truncate(draw2, t, font_event, max_text_w)
                if not t2:
                    continue
                ty = base_y + idx * line_gap

                # red dot
                cx = left_pad + dot_r
                cy = ty + int(7 * SCALE)
                draw2.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=RED)

                # text
                draw2.text((text_x, ty), t2, fill=TEXT, font=font_event)

    # Downscale (anti-aliasing)
    img = img2.resize((W, H), resample=Image.Resampling.LANCZOS)

    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")
    img.save("docs/latest.bmp")

if __name__ == "__main__":
    main()
