import os
import requests
import subprocess
import calendar
import pytz
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
from icalendar import Calendar
import holidays

# =========================
# Canvas (final output)
# =========================
W, H = 680, 960
SCALE = 2
W2, H2 = W * SCALE, H * SCALE

TEXT = (0, 0, 0)
RED  = (200, 0, 0)
DOW = ["S", "M", "T", "W", "T", "F", "S"]
ICON_DIR = "assets/weather"

# 폰트 로드 안전 장치
def get_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        print(f"Warning: Font {path} not found. Using default font.")
        return ImageFont.load_default()

# -------------------------
# Helpers
# -------------------------
def ensure_icons():
    if not os.path.exists(ICON_DIR):
        os.makedirs(ICON_DIR, exist_ok=True)
    # 아이콘이 없을 경우를 위한 최소한의 처리
    if os.path.exists("make_icons.py"):
        subprocess.run(["python", "make_icons.py"], check=False)

def load_icon(kind: str):
    if not kind: return None
    p = os.path.join(ICON_DIR, f"{kind}.png")
    if not os.path.exists(p): return None
    return Image.open(p).convert("RGBA")

def openmeteo_code_to_kind(code: int) -> str:
    c = int(code)
    if c == 0: return "sun"
    if c in (1, 2, 3): return "cloud"
    if c in (45, 48): return "fog"
    if 51 <= c <= 67: return "rain"
    if 71 <= c <= 77: return "snow"
    if 80 <= c <= 82: return "rain"
    if 85 <= c <= 86: return "snow"
    if c in (95, 96, 99): return "thunder"
    return "cloud"

def fetch_openmeteo_daily_5(lat, lon, tzname="Asia/Seoul"):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon, "timezone": tzname,
        "forecast_days": 5, "daily": "temperature_2m_min,temperature_2m_max,weathercode",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json().get("daily", {})
    out = []
    for i in range(len(data.get("time", []))):
        out.append({
            "date": datetime.strptime(data["time"][i], "%Y-%m-%d").date(),
            "kind": openmeteo_code_to_kind(data["weathercode"][i]),
            "tmin": data["temperature_2m_min"][i],
            "tmax": data["temperature_2m_max"][i],
        })
    return out

def fetch_events_by_date(tzname="Asia/Seoul"):
    url = os.getenv("ICAL_URL", "").strip()
    if not url: return {}
    if url.startswith("webcal://"): url = "https://" + url[len("webcal://"):]
    try:
        r = requests.get(url, timeout=25)
        r.raise_for_status()
        cal = Calendar.from_ical(r.text)
        tz = pytz.timezone(tzname)
        events = {}
        for comp in cal.walk():
            if comp.name != "VEVENT": continue
            dtstart = comp.get("dtstart").dt
            summary = str(comp.get("summary", "")).strip()
            if isinstance(dtstart, datetime):
                if dtstart.tzinfo is None: dtstart = tz.localize(dtstart)
                day = dtstart.astimezone(tz).date()
            else: day = dtstart
            events.setdefault(day, []).append(summary)
        return events
    except: return {}

def truncate(draw, text, font, max_w):
    if not text: return ""
    if draw.textlength(text, font=font) <= max_w: return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"

def main():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.now(tz)
    year, month = now.year, now.month
    kr_holidays = holidays.KR(years=[year, year + 1])

    img2 = Image.new("RGB", (W2, H2), "white")
    draw2 = ImageDraw.Draw(img2)

    # 폰트 로드 (경로 주의!)
    f_m = get_font("assets/Inter_28pt-Regular.ttf", 235 * SCALE)
    f_d = get_font("assets/Inter_28pt-Regular.ttf", 44 * SCALE)
    f_dow = get_font("assets/NanumGothicBold.ttf", 32 * SCALE)
    f_ev = get_font("assets/NanumSquareEB.ttf", 12 * SCALE)
    f_lbl = get_font("assets/Inter_28pt-ExtraLight.ttf", 12 * SCALE)
    f_wd = get_font("assets/NanumGothicBold.ttf", 14 * SCALE)
    f_tmp = get_font("assets/Inter_28pt-ExtraLight.ttf", 12 * SCALE)

    # 상단 시간
    draw2.text((W2 - 12*SCALE - draw2.textlength(now.strftime("%m-%d %H:%M"), f_lbl), 12*SCALE), now.strftime("%m-%d %H:%M"), fill=TEXT, font=f_lbl)

    # 큰 월 표시
    mstr = str(month)
    draw2.text(((W2 - draw2.textlength(mstr, f_m))/2, 8*SCALE), mstr, fill=TEXT, font=f_m)

    # 그리드 설정
    grid_top, grid_bottom = 540*SCALE, 840*SCALE
    grid_w = W2 - 12*SCALE
    cell_w = grid_w / 7
    
    cal_obj = calendar.Calendar(firstweekday=6)
    days = [d for d in cal_obj.itermonthdates(year, month)]
    rows = (len(days) + 6) // 7
    cell_h = (grid_bottom - grid_top) / rows

    # 요일 표시
    for c, dch in enumerate(DOW):
        tx = 6*SCALE + c*cell_w + cell_w/2
        draw2.text((tx - draw2.textlength(dch, f_dow)/2, grid_top - 60*SCALE), dch, fill=RED if c==0 else TEXT, font=f_dow)

    events_by_date = fetch_events_by_date()

    # 날짜 루프
    for i, day in enumerate(days):
        r, c = divmod(i, 7) # 수정된 부분: 키워드 인자 제거
        x0, y0 = 6*SCALE + c*cell_w, grid_top + r*cell_h
        
        is_holiday = day in kr_holidays
        date_color = RED if (c == 0 or is_holiday) else TEXT

        # 날짜 숫자
        s = str(day.day)
        sw = draw2.textlength(s, f_d)
        draw2.text((x0 + (cell_w - sw)/2, y0 + cell_h*0.1), s, fill=date_color, font=f_d)

        # 오늘 표시
        if day == now.date():
            draw2.rounded_rectangle([x0+10*SCALE, y0+10*SCALE, x0+cell_w-10*SCALE, y0+cell_h-10*SCALE], radius=10*SCALE, outline=RED, width=3*SCALE)

        # 이벤트/공휴일
        evs = events_by_date.get(day, []).copy()
        if is_holiday:
            h_name = kr_holidays.get(day)
            if h_name not in evs: evs.insert(0, h_name)

        for idx, t in enumerate(evs[:2]):
            t2 = truncate(draw2, t, f_ev, cell_w - 20*SCALE)
            ty = y0 + cell_h*0.6 + idx*20*SCALE
            draw2.text((x0 + 10*SCALE, ty), t2, fill=TEXT, font=f_ev)

    # 날씨 (하단)
    ensure_icons()
    try:
        lat = os.getenv("FORECAST_LAT", "37.5665")
        lon = os.getenv("FORECAST_LON", "126.9780")
        fc = fetch_openmeteo_daily_5(float(lat), float(lon))
        for idx, item in enumerate(fc):
            cx = 6*SCALE + idx*(grid_w/5) + (grid_w/10)
            draw2.text((cx - draw2.textlength(f"{item['date'].day}", f_wd)/2, 860*SCALE), f"{item['date'].day}", fill=TEXT, font=f_wd)
            icon = load_icon(item['kind'])
            if icon:
                icon = icon.resize((40*SCALE, 40*SCALE))
                img2.paste(icon, (int(cx - 20*SCALE), 885*SCALE), icon)
            tstr = f"{int(item['tmin'])}/{int(item['tmax'])}"
            draw2.text((cx - draw2.textlength(tstr, f_tmp)/2, 930*SCALE), tstr, fill=TEXT, font=f_tmp)
    except: pass

    # 저장
    img = img2.resize((W, H), resample=Image.Resampling.LANCZOS)
    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")
    print("Build Success: docs/latest.png created.")

if __name__ == "__main__":
    main()
