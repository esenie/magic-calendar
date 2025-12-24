from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
import calendar
import pytz
import os
import requests

# ===== 세로형 해상도 =====
W, H = 680, 960  # (가로, 세로)

# ===== 컬러 (3색 e-ink 친화) =====
TEXT = (30, 30, 30)
FADE = (180, 180, 180)
RED  = (200, 0, 0)

DOW = ["S", "M", "T", "W", "T", "F", "S"]

def code_to_symbol(weather_id: int) -> str:
    # OpenWeather condition codes: https://openweathermap.org/weather-conditions
    if 200 <= weather_id <= 232:
        return "⚡"   # 뇌우
    if 300 <= weather_id <= 531:
        return "☂"   # 비
    if 600 <= weather_id <= 622:
        return "❄"   # 눈
    if 701 <= weather_id <= 781:
        return "〰"   # 안개/연무
    if weather_id == 800:
        return "☀"   # 맑음
    if 801 <= weather_id <= 804:
        return "☁"   # 구름
    return "☁"

def get_today_tomorrow_symbols(lat: float, lon: float, tzname="Asia/Seoul") -> tuple[str, str]:
    api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if not api_key:
        return ("", "")

    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": "metric",
    }

    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()

    tz = pytz.timezone(tzname)
    today = datetime.now(tz).date()
    tomorrow = today + timedelta(days=1)

    # 날짜별로 "가장 먼저 나오는 예보"를 대표로 사용
    picked = {}
    for item in data.get("list", []):
        dt = datetime.fromtimestamp(item["dt"], tz).date()
        if dt not in picked and "weather" in item and item["weather"]:
            wid = int(item["weather"][0]["id"])
            picked[dt] = code_to_symbol(wid)
        if today in picked and tomorrow in picked:
            break

    return (picked.get(today, ""), picked.get(tomorrow, ""))

def main():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.now(tz)
    today = now.date()
    year, month = now.year, now.month

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    # ===== 폰트 =====
    # Inter가 있으면 우선 사용, 없으면 NanumGothic
    FONT_PATH = "assets/Inter-Regular.ttf"
    if not os.path.exists(FONT_PATH):
        FONT_PATH = "assets/NanumGothic.ttf"

    font_month = ImageFont.truetype(FONT_PATH, 200)
    font_dow   = ImageFont.truetype(FONT_PATH, 26)
    font_date  = ImageFont.truetype(FONT_PATH, 34)
    font_weather = ImageFont.truetype(FONT_PATH, 44)

    # ===== 레이아웃 (세로 포스터 + 줄 간격 넓게) =====
    top_margin = 70
    side_margin = 60

    grid_top = 360
    grid_bottom = 880
    grid_h = grid_bottom - grid_top
    grid_w = W - side_margin * 2

    cols, rows = 7, 6
    cell_w = grid_w / cols
    cell_h = grid_h / rows

    grid_left = side_margin

    # ===== 상단: 월 숫자(가운데 정렬) =====
    month_str = str(month)
    mw = draw.textlength(month_str, font=font_month)
    draw.text(((W - mw) / 2, top_margin), month_str, fill=TEXT, font=font_month)

    # ===== 날씨(오늘/내일) 기호: 12 아래 중앙 =====
    # 기본값: 서울(위/경도). 다른 지역은 env로 덮어쓸 수 있게 함.
    lat = float(os.getenv("OPENWEATHER_LAT", "37.5665"))
    lon = float(os.getenv("OPENWEATHER_LON", "126.9780"))

    debug = ""
    try:
        sym_today, sym_tomorrow = get_today_tomorrow_symbols(lat, lon)
        if not sym_today and not sym_tomorrow:
            debug = "NO_KEY_OR_NO_DATA"
    except Exception as e:
        sym_today, sym_tomorrow = ("", "")
        debug = f"ERR:{type(e).__name__}"
    
    weather_text = f"{sym_today}  {sym_tomorrow}".strip()
    
    # 날씨 기호가 안 나오면 디버그 문구라도 표시
    if not weather_text and debug:
        weather_text = debug
    
    if weather_text:
        ww = draw.textlength(weather_text, font=font_weather)
        draw.text(((W - ww) / 2, top_margin + 220), weather_text, fill=FADE, font=font_weather)    

    # ===== 요일 헤더 =====
    dow_y = grid_top - 55
    for c, d in enumerate(DOW):
        x_center = grid_left + c * cell_w + cell_w / 2
        color = RED if c in (0, 6) else TEXT
        w_txt = draw.textlength(d, font=font_dow)
        draw.text((x_center - w_txt / 2, dow_y), d, fill=color, font=font_dow)

    # ===== 날짜 데이터 =====
    cal = calendar.Calendar(firstweekday=6)
    days = list(cal.itermonthdates(year, month))[:42]

    # ===== 날짜 출력 (선 없음 / 여백 강조) =====
    for i, d in enumerate(days):
        r, c = divmod(i, cols)
        x0 = grid_left + c * cell_w
        y0 = grid_top  + r * cell_h

        in_month = (d.month == month)
        color = TEXT if in_month else FADE

        s = str(d.day)
        sw = draw.textlength(s, font=font_date)
        sx = x0 + (cell_w - sw) / 2
        sy = y0 + (cell_h - 40) / 2

        if d == today:
            cx = x0 + cell_w / 2
            cy = y0 + cell_h / 2
            radius = min(cell_w, cell_h) * 0.36
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=RED)
            draw.text((sx, sy), s, fill="white", font=font_date)
        else:
            draw.text((sx, sy), s, fill=color, font=font_date)

    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")

if __name__ == "__main__":
    main()
