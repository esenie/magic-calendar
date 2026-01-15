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
# 1) 회색(FADE) 쓰던 모든 글씨를 검정으로 통일
TEXT  = (0, 0, 0)
FADE  = TEXT
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

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    # 2) 요일/일자: 나눔고딕 Bold 사용(업로드 완료 가정)
    #    - month(큰 숫자)는 Regular 유지해도 되고, Bold로 바꿔도 됨(원하면 바꿔도 OK)
    FONT_REG = "assets/Inter-Regular.ttf"
    if not os.path.exists(FONT_REG):
        FONT_REG = "assets/NanumGothic.ttf"

    FONT_BOLD = "assets/NanumGothicBold.ttf"
    if not os.path.exists(FONT_BOLD):
        # 혹시 파일명이 다르면 여기만 바꿔주면 됨
        FONT_BOLD = "assets/NanumGothic-Bold.ttf"

    # 폰트 크기 조정: 굵게 + 약간 키워 가독성 업
    font_month  = ImageFont.truetype(FONT_REG, 200)
    font_dow    = ImageFont.truetype(FONT_BOLD, 30)  # (기존 26) -> 굵게 + 확대
    font_date   = ImageFont.truetype(FONT_BOLD, 40)  # (기존 34) -> 굵게 + 확대
    font_label  = ImageFont.truetype(FONT_REG, 12)   # TODAY/TMRO + update time
    font_event  = ImageFont.truetype(FONT_REG, 13)   # 일정

    side_margin = 60
    top_margin  = 90

    # ---- 공휴일 세트 (대한민국) ----
    kr_holidays = set()
    if holidays is not None:
        try:
            kr = holidays.KR(years=[year])
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
    try:
        events_by_date = fetch_events_by_date(max_per_day=2)
    except Exception:
        events_by_date = {}

    # ===== Update time (top-right) =====
    updated = now.strftime("%m-%d %H:%M")
    uw = draw.textlength(updated, font=font_label)
    draw.text((W - side_margin - uw, 22), updated, fill=FADE, font=font_label)

    # ===== Calendar grid =====
    # 3) 아래 여백 줄이기 + 날짜 위아래 간격(셀 높이) 늘리기
    #    - grid_bottom을 더 아래로 내리고, grid_top을 살짝 올려 셀 높이를 키움
    grid_top = 355          # (기존 380) -> 위로 올려서 캘린더 영역 늘림
    grid_bottom = 950       # (기존 900) -> 아래로 내려서 하단 여백 최소화
    grid_w = W - side_margin*2
    grid_h = grid_bottom - grid_top
    cols, rows = 7, 6
    cell_w = grid_w / cols
    cell_h = grid_h / rows
    grid_left = side_margin

    # DOW row
    dow_y = grid_top - 50   # (기존 -55) 약간 내려서 보기 좋게
    for c, dch in enumerate(DOW):
        x = grid_left + c*cell_w + cell_w/2
        color = RED if c == 0 else TEXT
        dw = draw.textlength(dch, font=font_dow)
        draw.text((x - dw/2, dow_y), dch, fill=color, font=font_dow)

    # Dates
    cal = calendar.Calendar(firstweekday=6)  # Sunday-first
    days = list(cal.itermonthdates(year, month))[:42]

    for i, day in enumerate(days):
        r, c = divmod(i, cols)
        x0 = grid_left + c*cell_w
        y0 = grid_top  + r*cell_h

        in_month = (day.month == month)
        is_sunday = (c == 0)
        is_holiday = (day in kr_holidays)

        # 날짜색: 공휴일/일요일=빨강, 그 외=검정, 다른달=검정(=FADE가 TEXT로 통일됨)
        if is_holiday or is_sunday:
            date_color = RED
        else:
            date_color = TEXT if in_month else FADE

        # 날짜 숫자 위치: 위아래 공간 더 쓰도록 "좀 더 위로" 배치 + 이벤트 공간 확보
        s = str(day.day)
        sw = draw.textlength(s, font=font_date)
        sx = x0 + (cell_w - sw)/2

        # 기존: sy = y0 + (cell_h - 40)/2
        # 개선: 위쪽으로 올려서 아래 이벤트/여백을 더 채움
        sy = y0 + int(cell_h * 0.30)

        draw.text((sx, sy), s, fill=date_color, font=font_date)

        # Today underline
        if day == today:
            line_y = sy + 42  # font_date 커졌으니 밑줄도 약간 아래로
            line_x1 = x0 + cell_w*0.28
            line_x2 = x0 + cell_w*0.72
            draw.line([(line_x1, line_y), (line_x2, line_y)], fill=RED, width=3)

        # Events under date (max 2 lines)
        evs = events_by_date.get(day, [])
        if evs:
            # 날짜가 위로 올라갔으니 이벤트는 중하단으로 넉넉히
            base_y = y0 + int(cell_h * 0.66)
            left_pad = x0 + 10
            dot_r = 3
            text_x = left_pad + 10
            max_text_w = (x0 + cell_w) - text_x - 6

            for idx, t in enumerate(evs[:2]):
                t = t.replace("\n", " ").strip()
                t = truncate_to_width(draw, t, font_event, max_text_w)

                ty = base_y + idx * 18
                cx = left_pad + dot_r
                cy = ty + 7
                draw.ellipse([cx-dot_r, cy-dot_r, cx+dot_r, cy+dot_r], fill=RED)
                draw.text((text_x, ty), t, fill=FADE, font=font_event)

    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")
    img.save("docs/latest.bmp")


if __name__ == "__main__":
    main()
