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

# ===== 슈퍼샘플링(곡선 계단 완화) =====
# 2로 두면 2배 해상도로 그린 뒤 680x960으로 다운샘플링(LANCZOS)
SCALE = 2  # 1로 바꾸면 기존 방식(빠름)

# ===== Colors (e-ink friendly) =====
# 요청: 회색 글씨 전부 검정으로 => FADE도 TEXT로 통일
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

    # ===== 캔버스(슈퍼샘플링용으로 내부 사이즈 확장) =====
    w2, h2 = W * SCALE, H * SCALE
    img = Image.new("RGB", (w2, h2), "white")
    draw = ImageDraw.Draw(img)

    # ===== Fonts =====
    # Bold 폰트(사용자가 업로드 완료라고 했으니 우선 사용)
    FONT_REG = "assets/NanumGothic.ttf"
    FONT_BOLD = "assets/NanumGothicBold.ttf"

    # fallback
    if not os.path.exists(FONT_REG):
        FONT_REG = "assets/Inter-Regular.ttf"
    if not os.path.exists(FONT_BOLD):
        FONT_BOLD = FONT_REG  # 없으면 regular로

    def f(path, size):  # 스케일 적용
        return ImageFont.truetype(path, int(size * SCALE))

    font_month  = f(FONT_REG, 200)
    font_dow    = f(FONT_BOLD, 28)   # 굵게 + 살짝 키움
    font_date   = f(FONT_BOLD, 36)   # 굵게 + 살짝 키움
    font_label  = f(FONT_REG, 12)
    font_event  = f(FONT_REG, 14)    # 일정은 읽히게 약간 키움(색은 검정)

    # ===== 레이아웃(좌우/아래 여백 줄이기) =====
    side_margin = int(38 * SCALE)     # 기존 60 -> 38 (좌우 더 채움)
    top_margin  = int(70 * SCALE)     # 월 숫자를 살짝 위로
    header_y    = int(22 * SCALE)

    # ---- 공휴일 세트 (대한민국) ----
    kr_holidays = set()
    if holidays is not None:
        try:
            kr = holidays.KR(years=[year])
            kr2 = holidays.KR(years=[year + 1])
            kr_holidays = set(kr.keys()) | set(kr2.keys())
        except Exception:
            kr_holidays = set()

    # ===== Weather widget (top-left, compact) =====
    wx, wy = side_margin, header_y
    widget_w, gap = int(150 * SCALE), int(6 * SCALE)
    col_w = (widget_w - gap) / 2

    def label(x_left, t):
        tw = draw.textlength(t, font=font_label)
        draw.text((x_left + (col_w - tw) / 2, wy), t, fill=TEXT, font=font_label)

    label(wx, "TODAY")
    label(wx + col_w + gap, "TMRO")

    ensure_icons()
    lat = float(os.getenv("OPENWEATHER_LAT", "37.5665"))
    lon = float(os.getenv("OPENWEATHER_LON", "126.9780"))
    try:
        k_today, k_tmro = get_today_tmro_kind(lat, lon)
    except Exception:
        k_today, k_tmro = "", ""

    icon_size = int(44 * SCALE)
    icon_y = wy + int(14 * SCALE)

    def paste_icon(kind, x_left):
        icon = load_icon(kind)
        if not icon:
            return
        icon = icon.resize((icon_size, icon_size))
        x = int(x_left + (col_w - icon_size) / 2)
        img.paste(icon, (x, int(icon_y)), icon)

    paste_icon(k_today, wx)
    paste_icon(k_tmro, wx + col_w + gap)

    # ===== Update time (top-right) =====
    updated = now.strftime("%m-%d %H:%M")
    uw = draw.textlength(updated, font=font_label)
    draw.text((w2 - side_margin - uw, header_y), updated, fill=TEXT, font=font_label)

    # ===== Month (centered) =====
    mstr = str(month)
    mw = draw.textlength(mstr, font=font_month)
    draw.text(((w2 - mw) / 2, top_margin), mstr, fill=TEXT, font=font_month)
    # month text bottom y (폰트 크기 기반, 자동)
    month_bottom = top_margin + font_month.size
    month_to_dow_gap = 30  # 월과 요일 사이 간격(조절 포인트)


    # ===== iCal events =====
    try:
        events_by_date = fetch_events_by_date(max_per_day=2)
    except Exception:
        events_by_date = {}

    # ===== Calendar grid =====
    # 아래 여백을 확 줄여서 달력 셀이 더 커지도록
    grid_top = int(340 * SCALE)           # 기존 380 -> 340 (위쪽도 약간 올림)
    grid_bottom = h2 - int(24 * SCALE)    # 기존 900 -> 거의 끝까지
    grid_w = w2 - side_margin * 2
    grid_h = grid_bottom - grid_top

    cols, rows = 7, 6
    cell_w = grid_w / cols
    cell_h = grid_h / rows
    grid_left = side_margin

    # DOW row
    dow_y = month_bottom + month_to_dow_gap
    for c, dch in enumerate(DOW):
        x = grid_left + c * cell_w + cell_w / 2
        color = RED if c == 0 else TEXT  # 일요일 빨강
        dw = draw.textlength(dch, font=font_dow)
        draw.text((x - dw / 2, dow_y), dch, fill=color, font=font_dow)

    # Dates
    cal = calendar.Calendar(firstweekday=6)  # Sunday-first
    days = list(cal.itermonthdates(year, month))[:42]

    # 날짜/일정 간격 조절 파라미터
    date_y_ratio = 0.46     # 날짜를 셀 상단 쪽으로 조금 올림(아래에 일정 공간 확보)
    event_y_ratio = 0.76    # 일정 시작 위치를 더 아래로
    event_line_gap = int(18 * SCALE)

    for i, day in enumerate(days):
        r, c = divmod(i, cols)
        x0 = grid_left + c * cell_w
        y0 = grid_top + r * cell_h

        in_month = (day.month == month)
        is_sunday = (c == 0)
        is_holiday = (day in kr_holidays)

        # 날짜색: 공휴일/일요일 빨강, 그 외 검정 (요청: 회색 없앰)
        if is_holiday or is_sunday:
            date_color = RED
        else:
            date_color = TEXT

        # 날짜 숫자(가운데)
        s = str(day.day)
        sw = draw.textlength(s, font=font_date)
        sx = x0 + (cell_w - sw) / 2
        sy = y0 + int(cell_h * date_y_ratio) - int(18 * SCALE)
        draw.text((sx, sy), s, fill=date_color, font=font_date)

        # Today underline (얇게 유지)
        if day == today:
            line_y = sy + int(40 * SCALE)
            line_x1 = x0 + cell_w * 0.30
            line_x2 = x0 + cell_w * 0.70
            draw.line([(line_x1, line_y), (line_x2, line_y)], fill=RED, width=max(1, int(2 * SCALE)))

        # Events (검정 + 빨간 점)
        evs = events_by_date.get(day, [])
        if evs:
            base_y = y0 + int(cell_h * event_y_ratio)
            left_pad = x0 + int(10 * SCALE)
            dot_r = int(3 * SCALE)
            text_x = left_pad + int(10 * SCALE)
            max_text_w = (x0 + cell_w) - text_x - int(6 * SCALE)

            for idx, t in enumerate(evs[:2]):
                t = t.replace("\n", " ").strip()
                t = truncate_to_width(draw, t, font_event, max_text_w)
                ty = base_y + idx * event_line_gap

                # 빨간 점
                cx = left_pad + dot_r
                cy = ty + int(7 * SCALE)
                draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=RED)

                # 텍스트(검정)
                draw.text((text_x, ty), t, fill=TEXT, font=font_event)

    # ===== 최종 다운샘플링(슈퍼샘플링) =====
    if SCALE != 1:
        img = img.resize((W, H), resample=Image.LANCZOS)

    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")
    img.save("docs/latest.bmp")


if __name__ == "__main__":
    main()
