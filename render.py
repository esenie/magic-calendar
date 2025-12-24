from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import calendar
import pytz
import os

# ===== 세로형 해상도 (GoodDisplay 회전 설치 기준) =====
W, H = 680, 960

# ===== 컬러 (3색 e-ink 친화) =====
TEXT = (30, 30, 30)
FADE = (180, 180, 180)
RED  = (200, 0, 0)

DOW = ["S", "M", "T", "W", "T", "F", "S"]

def main():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.now(tz)
    today = now.date()
    year, month = now.year, now.month

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    # ===== 폰트 =====
    FONT_PATH = "assets/Inter-Regular.ttf"
    if not os.path.exists(FONT_PATH):
        FONT_PATH = "assets/NanumGothic.ttf"

    font_month = ImageFont.truetype(FONT_PATH, 200)  # 월 숫자 크게
    font_dow   = ImageFont.truetype(FONT_PATH, 26)
    font_date  = ImageFont.truetype(FONT_PATH, 34)
    font_small = ImageFont.truetype(FONT_PATH, 18)

    # ===== 레이아웃 (세로 포스터 전용) =====
    top_margin = 70
    side_margin = 60

    # 그리드: 세로 중앙, 줄 간격 넓게
    grid_top = 360
    grid_bottom = 880
    grid_h = grid_bottom - grid_top
    grid_w = W - side_margin * 2

    cols, rows = 7, 6
    cell_w = grid_w / cols
    cell_h = grid_h / rows  # ← 줄 간격 여기서 결정됨

    grid_left = side_margin

    # ===== 상단: 큰 월 숫자 =====
    draw.text((side_margin, top_margin), str(month), fill=TEXT, font=font_month)

    # 우측 상단: 요일 (연한 텍스트)
    dow_word = now.strftime("%A").upper()
    tw = draw.textlength(dow_word, font=font_small)
    draw.text((W - side_margin - tw, top_margin + 90), dow_word, fill=FADE, font=font_small)

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
        sy = y0 + (cell_h - 40) / 2  # ← 세로 여백 늘림

        if d == today:
            cx = x0 + cell_w / 2
            cy = y0 + cell_h / 2
            radius = min(cell_w, cell_h) * 0.36
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=RED
            )
            draw.text((sx, sy), s, fill="white", font=font_date)
        else:
            draw.text((sx, sy), s, fill=color, font=font_date)

    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")

if __name__ == "__main__":
    main()