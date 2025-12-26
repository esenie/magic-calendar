from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
import calendar
import pytz
import os
import requests
import subprocess

# ===== 캔버스 (세로형) =====
W, H = 680, 960

# ===== 컬러 (3색 e-ink 친화) =====
TEXT = (30, 30, 30)
FADE = (180, 180, 180)
LIGHT = (220, 220, 220)
RED  = (200, 0, 0)

DOW = ["S", "M", "T", "W", "T", "F", "S"]

ICON_DIR = "assets/weather"  # PNG 아이콘 위치

def code_to_kind(weather_id: int) -> str:
    if 200 <= weather_id <= 232: return "thunder"
    if 300 <= weather_id <= 531: return "rain"
    if 600 <= weather_id <= 622: return "snow"
    if 701 <= weather_id <= 781: return "fog"
    if weather_id == 800:        return "sun"
    if 801 <= weather_id <= 804: return "cloud"
    return "cloud"

def get_today_tomorrow_kind(lat: float, lon: float, tzname="Asia/Seoul") -> tuple[str, str]:
    api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if not api_key:
        return ("", "")

    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()

    tz = pytz.timezone(tzname)
    today = datetime.now(tz).date()
    tomorrow = today + timedelta(days=1)

    picked = {}
    for item in data.get("list", []):
        dt = datetime.fromtimestamp(item["dt"], tz).date()
        if dt not in picked and item.get("weather"):
            wid = int(item["weather"][0]["id"])
            picked[dt] = code_to_kind(wid)
        if today in picked and tomorrow in picked:
            break

    return (picked.get(today, ""), picked.get(tomorrow, ""))

def ensure_icons_exist():
    needed = ["sun","cloud","rain","snow","thunder","fog"]
    ok = True
    for k in needed:
        if not os.path.exists(os.path.join(ICON_DIR, f"{k}.png")):
            ok = False
            break
    if ok:
        return

    # try auto-generate by running make_icons.py if present
    if os.path.exists("make_icons.py"):
        try:
            subprocess.run(["python", "make_icons.py"], check=True)
        except Exception:
            pass

def load_icon(kind: str) -> Image.Image | None:
    if not kind:
        return None
    path = os.path.join(ICON_DIR, f"{kind}.png")
    if not os.path.exists(path):
        return None
    return Image.open(path).convert("RGBA")

def main():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.now(tz)
    today_date = now.date()
    year, month = now.year, now.month

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    # ===== 폰트 =====
    BASE_FONT = "assets/Inter-Regular.ttf"
    if not os.path.exists(BASE_FONT):
        BASE_FONT = "assets/NanumGothic.ttf"

    font_month  = ImageFont.truetype(BASE_FONT, 200)
    font_dow    = ImageFont.truetype(BASE_FONT, 26)
    font_date   = ImageFont.truetype(BASE_FONT, 34)
    font_update = ImageFont.truetype(BASE_FONT, 16)
    font_label  = ImageFont.truetype(BASE_FONT, 18)

    # ===== 레이아웃 =====
    top_margin = 70
    side_margin = 60

    # (1) 업데이트 시간 우상단 (분까지)
    updated_txt = now.strftime("%m-%d %H:%M")
    utw = draw.textlength(updated_txt, font=font_update)
    draw.text((W - side_margin - utw, top_margin - 10), updated_txt, fill=FADE, font=font_update)

    # 월 숫자 가운데 정렬
    month_str = str(month)
    mw = draw.textlength(month_str, font=font_month)
    draw.text(((W - mw) / 2, top_margin), month_str, fill=TEXT, font=font_month)

    # (2) 날씨 영역 (고정 레이아웃)
    weather_top = top_margin + 235
    weather_h = 110
    weather_left = side_margin
    weather_w = W - side_margin * 2

    # 원하면 매우 연한 박스 윤곽(싫으면 주석)
    # draw.rectangle([weather_left, weather_top, weather_left+weather_w, weather_top+weather_h], outline=LIGHT, width=2)

    # 두 칸 레이아웃
    gap = 22
    col_w = (weather_w - gap) / 2
    col1_x = weather_left
    col2_x = weather_left + col_w + gap

    # 라벨: TODAY / TMRO
    def draw_label(x_left: float, text: str):
        tw = draw.textlength(text, font=font_label)
        draw.text((x_left + (col_w - tw)/2, weather_top + 4), text, fill=FADE, font=font_label)

    draw_label(col1_x, "TODAY")
    draw_label(col2_x, "TMRO")

    # 아이콘 준비
    ensure_icons_exist()

    lat = float(os.getenv("OPENWEATHER_LAT", "37.5665"))
    lon = float(os.getenv("OPENWEATHER_LON", "126.9780"))

    try:
        kind_today, kind_tmro = get_today_tomorrow_kind(lat, lon)
    except Exception:
        kind_today, kind_tmro = ("", "")

    icon_today = load_icon(kind_today)
    icon_tmro = load_icon(kind_tmro)

    def paste_icon(icon: Image.Image | None, x_left: float):
        # 아이콘만 표시(텍스트 없음)
        icon_y = weather_top + 32
        if icon is None:
            # 데이터 없으면 작은 점선/대시로라도 표시
            dash = "—"
            dw = draw.textlength(dash, font=font_month)
            draw.text((x_left + (col_w - dw)/2, icon_y+6), dash, fill=LIGHT, font=font_month)
            return

        # 아이콘 크기(고정)
        target = 70
        icon2 = icon.resize((target, target))
        x = int(x_left + (col_w - target)/2)
        y = int(icon_y)
        img.paste(icon2, (x, y), icon2)

    paste_icon(icon_today, col1_x)
    paste_icon(icon_tmro, col2_x)

    # ===== 그리드 영역 (줄 간격 넉넉) =====
    grid_top = 380
    grid_bottom = 900
    grid_h = grid_bottom - grid_top
    grid_w = W - side_margin * 2
    cols, rows = 7, 6
    cell_w = grid_w / cols
    cell_h = grid_h / rows
    grid_left = side_margin

    # 요일
    dow_y = grid_top - 55
    for c, d in enumerate(DOW):
        x_center = grid_left + c * cell_w + cell_w / 2
        color = RED if c in (0, 6) else TEXT
        w_txt = draw.textlength(d, font=font_dow)
        draw.text((x_center - w_txt / 2, dow_y), d, fill=color, font=font_dow)

    # 날짜
    cal = calendar.Calendar(firstweekday=6)
    days = list(cal.itermonthdates(year, month))[:42]

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

        if d == today_date:
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
