from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
import calendar
import pytz
import os
import requests
import subprocess
from icalendar import Calendar

# 공휴일(대한민국) 표시용
try:
    import holidays  # pip install holidays
except Exception:
    holidays = None

# ===== Canvas =====
W, H = 680, 960

# ===== Colors (e-ink friendly) =====
TEXT  = (30, 30, 30)
FADE  = (180, 180, 180)
RED   = (200, 0, 0)

DOW = ["S", "M", "T", "W", "T", "F", "S"]

ICON_DIR = "assets/weather"


# ---------------- Weather helpers ----------------
def code_to_kind(wid: int) -> str:
    if 200 <= wid <= 232: return "thunder"
    if 300 <= wid <= 531: return "rain"
    if 600 <= wid <= 622: return "snow"
    if 701 <= wid <= 781: return "fog"
    if wid == 800:        return "sun"
    if 801 <= wid <= 804: return "cloud"
    return "cloud"


def get_today_tmro_kind(lat: float, lon: float) -> tuple[str, str]:
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
    from PIL import Image
    return Image.open(p).convert("RGBA")


# ---------------- Calendar (ICS) helpers ----------------
def fetch_events_by_date(tzname="Asia/Seoul", max_per_day=2):
    url = os.getenv("ICAL_URL", "").strip()
    if not url:
        return {}

    # webcal:// -> https:// (requests가 webcal을 못 가져옴)
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
            day = dtstart  # date

        events.setdefault(day, []).append(summary)

    for day in list(events.keys()):
        events[day] = events[day][:max_per_day]

    return events


def truncate_to_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: float) -> str:
    """픽셀 폭 기준으로 … 처리."""
    if draw.textlength(text, font=font) <= max_w:
        return text
    ell = "…"
    if max_w <= draw.textlength(ell, font=font):
        return ell
    s = text
    while s and draw.textlength(s + ell, font=font) > max_w:
        s = s[:-1]
    return s + ell


# ---------------- Main ----------------
def main():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.now(tz)
    today = now.date()
    year, month = now.year, now.month

    from PIL import Image
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    BASE_FONT = "assets/Inter-Regular.ttf"
    if not os.path.exists(BASE_FONT):
        BASE_FONT = "assets/NanumGothic.ttf"

    font_month  = ImageFont.truetype(BASE_FONT, 200)
    font_dow    = ImageFont.truetype(BASE_FONT, 26)
    font_date   = ImageFont.truetype(BASE_FONT, 34)
    font_label  = ImageFont.truetype(BASE_FONT, 12)  # TODAY/TMRO + update time
    font_event  = ImageFont.truetype(BASE_FONT, 13)  # 일정 더 작게

    side_margin = 60
    top_margin  = 90

    # ---- 공휴일 세트 (대한민국) ----
    kr_holidays = set()
    if holidays is not None:
        try:
            kr = holidays.KR(years=[year])
            # 다음달(회색으로 보이는 1~3 같은 날짜)도 공휴일이면 표시되게 year+1도 추가
            kr2 = holidays.KR(years=[year+1])
            kr_holidays = set(kr.keys()) | set(kr2.keys())
        except Exception:
            kr_holidays = set()

    # ===== Weather widget (top-left, compact) =====
    wx, wy = side_margin, 22
    widget_w, gap = 150, 6
    col_w = (widget_w - gap) / 2

    def label(x_left, t):
        tw = draw.textlength(t, font=font_label)
        draw.text((x_left + (col_w - tw)/2, wy), t, fill=FADE, font=font_label)

    label(wx, "TODAY")
    label(wx + col_w + gap, "TMRO")

    ensure_icons()
    lat = float(os.getenv("OPENWEATHER_LAT", "37.5665"))
    lon = float(os.getenv("OPENWEATHER_LON", "126.9780"))
    try:
        k_today, k_tmro = get_today_tmro_kind(lat, lon)
    except Exception:
        k_today, k_tmro = "", ""

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

    # ===== Month (centered) =====
    mstr = str(month)
    mw = draw.textlength(mstr, font=font_month)
    draw.text(((W - mw)/2, top_margin), mstr, fill=TEXT, font=font_month)

    # ===== iCal events =====
    events_by_date = {}
    try:
        events_by_date = fetch_events_by_date(max_per_day=2)
    except Exception:
        events_by_date = {}

    # ===== Update time (top-right) - SAME size as TODAY/TMRO =====
    updated = now.strftime("%m-%d %H:%M")
    uw = draw.textlength(updated, font=font_label)
    draw.text((W - side_margin - uw, 22), updated, fill=FADE, font=font_label)

    # ===== Calendar grid =====
    grid_top = 380
    grid_bottom = 900
    grid_w = W - side_margin*2
    grid_h = grid_bottom - grid_top
    cols, rows = 7, 6
    cell_w = grid_w / cols
    cell_h = grid_h / rows
    grid_left = side_margin

    # DOW row (일요일 빨강, 토요일은 파랑 불가 → 기본색 유지)
    dow_y = grid_top - 55
    for c, dch in enumerate(DOW):
        x = grid_left + c*cell_w + cell_w/2
        color = RED if c == 0 else TEXT
        dw = draw.textlength(dch, font=font_dow)
        draw.text((x - dw/2, dow_y), dch, fill=color, font=font_dow)

    # Dates (공휴일/일요일 빨강)
    cal = calendar.Calendar(firstweekday=6)  # Sunday-first
    days = list(cal.itermonthdates(year, month))[:42]

    for i, day in enumerate(days):
        r, c = divmod(i, cols)
        x0 = grid_left + c*cell_w
        y0 = grid_top  + r*cell_h

        in_month = (day.month == month)

        is_sunday = (c == 0)
        is_holiday = (day in kr_holidays)

        # 날짜색: 공휴일/일요일=빨강, 그 외=검정, 다른달=회색(단, 공휴일이면 빨강 유지)
        if is_holiday or is_sunday:
            date_color = RED
        else:
            date_color = TEXT if in_month else FADE

        # 날짜 숫자 위치(가운데)
        s = str(day.day)
        sw = draw.textlength(s, font=font_date)
        sx = x0 + (cell_w - sw)/2
        sy = y0 + (cell_h - 40)/2
        draw.text((sx, sy), s, fill=date_color, font=font_date)

        # --- Today underline (빨간 밑줄) ---
        if day == today:
            # 숫자 아래에 얇은 밑줄
            line_y = sy + 42
            line_x1 = x0 + cell_w*0.30
            line_x2 = x0 + cell_w*0.70
            draw.line([(line_x1, line_y), (line_x2, line_y)], fill=RED, width=4)

        # --- Events under date (max 2 lines, FADE, ellipsis, red dot bullet) ---
        evs = events_by_date.get(day, [])
        if evs:
            base_y = y0 + int(cell_h * 0.62)
            left_pad = x0 + 10
            dot_r = 3
            text_x = left_pad + 10  # 점 + 간격
            max_text_w = (x0 + cell_w) - text_x - 6

            for idx, t in enumerate(evs[:2]):
                t = t.replace("\n", " ").strip()
                t = truncate_to_width(draw, t, font_event, max_text_w)

                ty = base_y + idx * 16  # 줄간격(작게)
                # red dot
                cx = left_pad + dot_r
                cy = ty + 7
                draw.ellipse([cx-dot_r, cy-dot_r, cx+dot_r, cy+dot_r], fill=RED)
                # text
                draw.text((text_x, ty), t, fill=FADE, font=font_event)

    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")


if __name__ == "__main__":
    main()
