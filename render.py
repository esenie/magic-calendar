from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import calendar
import pytz
import os

W, H = 960, 680
MARGIN = 24
HEADER_H = 72
DOW_H = 40
COLS, ROWS = 7, 6
DOW = ["일", "월", "화", "수", "목", "금", "토"]

def main():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.now(tz)
    year, month = now.year, now.month

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    font_title = ImageFont.truetype("assets/NanumGothic.ttf", 44)
    font_dow   = ImageFont.truetype("assets/NanumGothic.ttf", 22)
    font_date  = ImageFont.truetype("assets/NanumGothic.ttf", 22)

    draw.text((MARGIN, MARGIN), f"{year}년 {month}월", fill="black", font=font_title)

    updated = now.strftime("업데이트 %m-%d %H:%M")
    tw = draw.textlength(updated, font=font_dow)
    draw.text((W - MARGIN - tw, MARGIN + 14), updated, fill="black", font=font_dow)

    grid_top = MARGIN + HEADER_H + DOW_H
    grid_bottom = H - MARGIN
    cell_w = (W - MARGIN * 2) // COLS
    cell_h = (grid_bottom - grid_top) // ROWS

    for c in range(COLS):
        x = MARGIN + c * cell_w + 6
        color = "red" if c == 0 else "black"
        draw.text((x, MARGIN + HEADER_H + 6), DOW[c], fill=color, font=font_dow)

    for r in range(ROWS + 1):
        y = grid_top + r * cell_h
        draw.line([(MARGIN, y), (W - MARGIN, y)], fill="black", width=2)

    for c in range(COLS + 1):
        x = MARGIN + c * cell_w
        draw.line([(x, grid_top), (x, grid_bottom)], fill="black", width=2)

    cal = calendar.Calendar(firstweekday=6)
    days = list(cal.itermonthdates(year, month))[:42]

    for i, d in enumerate(days):
        r, c = divmod(i, COLS)
        x = MARGIN + c * cell_w + 6
        y = grid_top + r * cell_h + 6

        color = "black" if d.month == month else (150, 150, 150)
        if d.month == month and d.weekday() == 6:
            color = "red"

        draw.text((x, y), str(d.day), fill=color, font=font_date)

    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")

if __name__ == "__main__":
    main()
