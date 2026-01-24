from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
import calendar
import pytz
import os
import requests
from icalendar import Calendar

# =========================
# Canvas & Scaling
# =========================
W, H = 680, 960
SCALE = 2
W2, H2 = W * SCALE, H * SCALE

# Colors
TEXT = (0, 0, 0)
FADE = (180, 180, 180) 
RED  = (200, 0, 0)
DOW = ["S", "M", "T", "W", "T", "F", "S"]
ICON_DIR = "assets/weather"

# -------------------------
# Helpers
# -------------------------
def code_to_kind(wid: int) -> str:
    if 200 <= wid <= 232: return "thunder"
    if 300 <= wid <= 531: return "rain"
    if 600 <= wid <= 622: return "snow"
    if 701 <= wid <= 781: return "fog"
    if wid == 800:        return "sun"
    return "cloud"

def load_icon(kind: str):
    p = os.path.join(ICON_DIR, f"{kind}.png")
    return Image.open(p).convert("RGBA") if os.path.exists(p) else None

def get_5day_forecast(lat, lon, tzname="Asia/Seoul"):
    api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if not api_key: return []
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"}
    try:
        r = requests.get(url, params=params, timeout=20)
        data = r.json()
        tz = pytz.timezone(tzname)
        today = datetime.now(tz).date()
        daily_data = {}
        for item in data.get("list", []):
            dt = datetime.fromtimestamp(item["dt"], tz)
            d = dt.date()
            if d <= today: continue
            if d not in daily_data:
                daily_data[d] = {"min": item["main"]["temp"], "max": item["main"]["temp"], "kind": item["weather"][0]["id"]}
            else:
                daily_data[d]["min"] = min(daily_data[d]["min"], item["main"]["temp"])
                daily_data[d]["max"] = max(daily_data[d]["max"], item["main"]["temp"])
        result = []
        for d in sorted(daily_data.keys())[:5]:
            result.append({"date": d, "kind": code_to_kind(daily_data[d]["kind"]), "min": daily_data[d]["min"], "max": daily_data[d]["max"]})
        return result
    except: return []

def fetch_events_by_date(tzname="Asia/Seoul", max_per_day=2):
    url = os.getenv("ICAL_URL", "").strip()
    if not url:
        return {}, "NO URL"

    # [핵심 수정 1] webcal 프로토콜을 https로 강제 변환 (이게 없어서 에러남)
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    
    # [핵심 수정 2] 일부 서버(구글/애플) 차단 방지용 헤더 추가
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        
        cal = Calendar.from_ical(r.text)
        tz = pytz.timezone(tzname)
        events = {}
        
        for comp in cal.walk():
            if comp.name != "VEVENT": continue
            
            if not comp.get("dtstart"): continue
            dtstart = comp.get("dtstart").dt
            summary = str(comp.get("summary", "")).strip()
            
            try:
                if isinstance(dtstart, datetime):
                    if dtstart.tzinfo is None: 
                        dtstart = tz.localize(dtstart)
                    day = dtstart.astimezone(tz).date()
                else: 
                    day = dtstart
                events.setdefault(day, []).append(summary)
            except Exception:
                continue
            
        for d in events: events[d] = events[d][:max_per_day]
        return events, "OK"
    except Exception as e:
        # 에러 메시지를 좀 더 명확하게 단축
        err_msg = str(e)
        if "No connection adapters" in err_msg:
            return {}, "ERR: Protocol"
        return {}, f"ERR: {err_msg[:10]}"

def truncate(draw, text, font, max_w):
    if not text: return ""
    text = text.replace("\n", " ").strip()
    if draw.textlength(text, font=font) <= max_w: return text
    while text and draw.textlength(text + "…", font=font) > max_w: text = text[:-1]
    return text + "…"

# -------------------------
# Main Logic
# -------------------------
def main():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.now(tz)
    year, month = now.year, now.month
    lat = float(os.getenv("OPENWEATHER_LAT", "37.5665"))
    lon = float(os.getenv("OPENWEATHER_LON", "126.9780"))

    img2 = Image.new("RGB", (W2, H2), "white")
    draw2 = ImageDraw.Draw(img2)

    # Fonts
    font_month = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 230 * SCALE)
    font_date  = ImageFont.truetype("assets/Inter_28pt-Regular.ttf", 40 * SCALE)
    font_dow   = ImageFont.truetype("assets/NanumGothicBold.ttf", 32 * SCALE)
    font_event = ImageFont.truetype("assets/NanumSquareR.ttf", 16 * SCALE)
    font_label = ImageFont.truetype("assets/Inter_28pt-ExtraLight.ttf", 14 * SCALE)
    font_temp  = ImageFont.truetype("assets/Inter_28pt-ExtraLight.ttf", 13 * SCALE)
    font_debug = ImageFont.truetype("assets/NanumGothicBold.ttf", 12 * SCALE)

    SIDE_MARGIN = 15 * SCALE
    TOP_MARGIN = 20 * SCALE
    BOTTOM_WIDGET_H = 150 * SCALE 

    # 1. Update Time
    updated = now.strftime("%Y-%m-%d %H:%M")
    uw = draw2.textlength(updated, font=font_label)
    draw2.text((W2 - SIDE_MARGIN - uw, TOP_MARGIN), updated, fill=TEXT, font=font_label)

    # 2. Month
    mstr = str(month)
    mw = draw2.textlength(mstr, font=font_month)
    draw2.text(((W2 - mw) / 2, TOP_MARGIN - 10*SCALE), mstr, fill=TEXT, font=font_month)

    # 3. Grid Calculation
    grid_top = TOP_MARGIN + (260 * SCALE) 
    grid_bottom = H2 - BOTTOM_WIDGET_H - (10 * SCALE)
    cell_w = (W2 - 2 * SIDE_MARGIN) / 7
    cell_h = (grid_bottom - grid_top) / 7

    # Draw DOW
    for c, dch in enumerate(DOW):
        x = SIDE_MARGIN + c * cell_w + cell_w / 2
        color = RED if c == 0 else TEXT
        dw = draw2.textlength(dch, font=font_dow)
        draw2.text((x - dw / 2, grid_top + 10*SCALE), dch, fill=color, font=font_dow)

    # ---------------------------------------------------------
    # ICS Fetching
    # ---------------------------------------------------------
    events, status_msg = fetch_events_by_date()
    
    # 에러 메시지 표시 (성공시 표시 안함)
    if status_msg != "OK":
        draw2.text((W2 - SIDE_MARGIN - 120*SCALE, TOP_MARGIN + 20*SCALE), f"ICS: {status_msg}", fill=RED, font=font_debug)

    # [테스트용 코드 삭제됨] 이제 실제 데이터가 나올 것이므로 테스트 일정 삭제
    # events.setdefault(now.date(), []).insert(0, "●테스트일정")

    # Draw Days
    grid_days_top = grid_top + cell_h
    cal_obj = calendar.Calendar(firstweekday=6)
    days = list(cal_obj.itermonthdates(year, month))[:42]

    for i, day in enumerate(days):
        r, c = divmod(i, 7)
        x0 = SIDE_MARGIN + c * cell_w
        y0 = grid_days_top + r * cell_h
        
        # Date Number
        d_color = RED if c == 0 else TEXT
        if day.month != month: d_color = FADE 
        
        ds = str(day.day)
        dw = draw2.textlength(ds, font=font_date)
        draw2.text((x0 + (cell_w - dw)/2, y0 + 5*SCALE), ds, fill=d_color, font=font_date)

        # Today Underline
        if day == now.date():
            ux = x0 + cell_w * 0.3
            draw2.line([(ux, y0 + 48*SCALE), (x0 + cell_w * 0.7, y0 + 48*SCALE)], fill=RED, width=3)

        # Events
        day_evs = events.get(day, [])
        for idx, ev in enumerate(day_evs):
            # 좌표: y0 + 56 (날짜 바로 아래)
            ev_y = y0 + (56 * SCALE) + (idx * 24 * SCALE)
            
            txt = truncate(draw2, ev, font_event, cell_w - 4*SCALE)
            tw = draw2.textlength(txt, font=font_event)
            draw2.text((x0 + (cell_w - tw)/2, ev_y), txt, fill=TEXT, font=font_event)

    # 4. Bottom 5-Day Forecast
    forecasts = get_5day_forecast(lat, lon)
    if forecasts:
        line_y = H2 - BOTTOM_WIDGET_H
        draw2.line([(SIDE_MARGIN, line_y), (W2 - SIDE_MARGIN, line_y)], fill=TEXT, width=2)
        f_box_w = (W2 - 2 * SIDE_MARGIN) / 5
        for i, f in enumerate(forecasts):
            fx = SIDE_MARGIN + (i * f_box_w)
            d_str = f["date"].strftime("%a").upper()
            draw2.text((fx + (f_box_w - draw2.textlength(d_str, font=font_label))/2, line_y + 20*SCALE), d_str, fill=TEXT, font=font_label)
            icon = load_icon(f["kind"])
            if icon:
                icon = icon.resize((50*SCALE, 50*SCALE))
                img2.paste(icon, (int(fx + (f_box_w - 50*SCALE)/2), int(line_y + 45*SCALE)), icon)
            t_str = f"{int(round(f['min']))}°/{int(round(f['max']))}°"
            draw2.text((fx + (f_box_w - draw2.textlength(t_str, font=font_temp))/2, line_y + 105*SCALE), t_str, fill=TEXT, font=font_temp)

    # Final Save
    img = img2.resize((W, H), resample=Image.Resampling.LANCZOS)
    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")

if __name__ == "__main__":
    main()
