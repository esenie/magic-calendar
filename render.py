from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
import calendar
import pytz
import os
import requests
import subprocess

W, H = 680, 960

TEXT  = (30, 30, 30)
FADE  = (180, 180, 180)
RED   = (200, 0, 0)

DOW = ["S", "M", "T", "W", "T", "F", "S"]
ICON_DIR = "assets/weather"

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
    return Image.open(p).convert("RGBA")

def main():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.now(tz)
    today = now.date()
    year, month = now.year, now.month

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    BASE_FONT = "assets/Inter-Regular.ttf"
    if not os.path.exists(BASE_FONT):
        BASE_FONT = "assets/NanumGothic.ttf"

    font_month  = ImageFont.truetype(BASE_FONT, 200)
    font_dow    = ImageFont.truetype(BASE_FONT, 26)
    font_date   = ImageFont.truetype(BASE_FONT, 34)
    font_update = ImageFont.truetype(BASE_FONT, 16)
    font_label  = ImageFont.truetype(BASE_FONT, 12)

    # ===== Margins =====
    side_margin = 60
    top_margin  = 90  # ← 월 숫자를 살짝 아래로 내려서(겹침 방지)

    # ===== Update time (top-right) =====
    updated = now.strftime("%m-%d %H:%M")
    uw = draw.textlength(updated, font=font_update)
    draw.text((W - side_margin - uw, 26), updated, fill=FADE, font=font_update)

    font_label  = ImageFont.truetype(BASE_FONT, 12)  # 기존 14

    # Weather widget
    wx = side_margin
    wy = 22
    widget_w = 150   # 기존 190
    gap = 6          # 기존 12
    col_w = (widget_w - gap) / 2
    
    # Labels
    def label(x_left, t):
        tw = draw.textlength(t, font=font_label)
        draw.text((x_left + (col_w - tw)/2, wy), t, fill=FADE, font=font_label)
    
    label(wx, "TODAY")
    label(wx + col_w + gap, "TMRO")
    
    icon_size = 44   # 기존 52
    icon_y = wy + 14 # 기존 wy + 18
   
    ensure_icons()

    lat = float(os.getenv("OPENWEATHER_LAT", "37.5665"))
    lon = float(os.getenv("OPENWEATHER_LON", "126.9780"))
    try:
        k_today, k_tmro = get_today_tmro_kind(lat, lon)
    except Exception:
        k_today, k_tmro = "", ""

    icon_size = 52  # MUJI 스타일엔 52px가 깔끔
    icon_y = wy + 18

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

    # ===== Grid layout =====
    grid_top = 380
    grid_bottom = 900
    grid_w = W - side_margin*2
    grid_h = grid_bottom - grid_top
    cols, rows = 7, 6
    cell_w = grid_w / cols
    cell_h = grid_h / rows
    grid_left = side_margin

    # DOW row
    dow_y = grid_top - 55
    for c, d in enumerate(DOW):
        x = grid_left + c*cell_w + cell_w/2
        color = RED if c in (0,6) else TEXT
        dw = draw.textlength(d, font=font_dow)
        draw.text((x - dw/2, dow_y), d, fill=color, font=font_dow)

    # Dates
    cal = calendar.Calendar(firstweekday=6)
    days = list(cal.itermonthdates(year, month))[:42]

    for i, d in enumerate(days):
        r, c = divmod(i, cols)
        x0 = grid_left + c*cell_w
        y0 = grid_top  + r*cell_h

        in_month = (d.month == month)
        color = TEXT if in_month else FADE

        s = str(d.day)
        sw = draw.textlength(s, font=font_date)
        sx = x0 + (cell_w - sw)/2
        sy = y0 + (cell_h - 40)/2

        if d == today:
            cx = x0 + cell_w/2
            cy = y0 + cell_h/2
            r0 = min(cell_w, cell_h)*0.36
            draw.ellipse([cx-r0, cy-r0, cx+r0, cy+r0], fill=RED)
            draw.text((sx, sy), s, fill="white", font=font_date)
        else:
            draw.text((sx, sy), s, fill=color, font=font_date)

    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")

if __name__ == "__main__":
    main()
