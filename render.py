from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import calendar
import pytz
import os

# ===== 세로형 캔버스 =====
W, H = 960, 1280

# 여백/레이아웃
M = 90
TOP_H = 300
GRID_TOP = M + TOP_H
GRID_BOTTOM = H - 120
GRID_H = GRID_BOTTOM - GRID_TOP

COLS, ROWS = 7, 6
CELL_W = (W - 2*M) // COLS
CELL_H = GRID_H // ROWS

# 색상 (3색 e-ink 친화)
TEXT = (30, 30, 30)
FADE = (175, 175, 175)
RED  = (200, 0, 0)

DOW = ["S", "M", "T", "W", "T", "F", "S"]

def main():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.now(tz)
    today = now.date()
    year, month = now.year, now.month

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    # 폰트
    font_month = ImageFont.truetype("assets/NanumGothic.ttf", 200)
    font_dow   = ImageFont.truetype("assets/NanumGothic.ttf", 26)
    font_date  = ImageFont.truetype("assets/NanumGothic.ttf", 34)

    # ===== 상단: 큰 월 숫자 =====
    draw.text((M, M - 10), str(month), fill=TEXT, font=font_month)

    # 오른쪽 위 작은 요일 텍스트
    dow_word = now.strftime("%A").upper()
    tw = draw.textlength(dow_word, font=font_dow)
    draw.text((W - M - tw, M + 70), dow_word, fill=FADE, font=font_dow)

    # ===== 요일 한 줄 =====
    dow_y = GRID_TOP - 70
    for c, d in enumerate(DOW):
        x = M + c * CELL_W + CELL_W / 2
        color = RED if c == 0 else (RED if c == 6 else TEXT)
        tw = draw.textlength(d, font=font_dow)
        draw.text((x - tw / 2, dow_y), d, fill=color, font=font_dow)

    # ===== 날짜 계산 =====
    cal = calendar.Calendar(firstweekday=6)
    days = list(cal.itermonthdates(year, month))[:42]

    # ===== 날짜 표시 =====
    for i, d in enumerate(days):
        r, c = divmod(i, COLS)
        x0 = M + c * CELL_W
        y0 = GRID_TOP + r * CELL_H

        in_month = (d.month == month)
        color = TEXT if in_month else FADE

        s = str(d.day)
        sw = draw.textlength(s, font=font_date)
        sx = x0 + (CELL_W - sw) / 2
        sy = y0 + (CELL_H - 36) / 2

        if d == today:
            cx = x0 + CELL_W / 2
            cy = y0 + CELL_H / 2
            radius = min(CELL_W, CELL_H) * 0.38
            draw.ellipse(
                [cx-radius, cy-radius, cx+radius, cy+radius],
                fill=RED
            )
            draw.text((sx, sy), s, fill="white", font=font_date)
        else:
            draw.text((sx, sy), s, fill=color, font=font_date)

    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")

if __name__ == "__main__":
    main()
