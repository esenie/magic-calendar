from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import calendar
import pytz
import os

# ===== 패널 해상도 고정 (GDEM133Z91) =====
W, H = 960, 680

# 미니멀 컬러 (3색 E-ink 친화)
TEXT = (30, 30, 30)
FADE = (175, 175, 175)
RED  = (200, 0, 0)

DOW = ["S", "M", "T", "W", "T", "F", "S"]  # 이미지 느낌처럼 1글자

def main():
    tz = pytz.timezone("Asia/Seoul")
    now = datetime.now(tz)
    today = now.date()
    year, month = now.year, now.month

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    # ===== 폰트 =====
    # Inter를 쓰고 있으면 이걸 추천 (없으면 NanumGothic.ttf로 바꿔도 됨)
    # 예: "assets/Inter-Regular.ttf"
    FONT_PATH = "assets/Inter-Regular.ttf"
    if not os.path.exists(FONT_PATH):
        FONT_PATH = "assets/NanumGothic.ttf"

    font_month = ImageFont.truetype(FONT_PATH, 170)  # 큰 월 숫자
    font_dow   = ImageFont.truetype(FONT_PATH, 24)   # 요일
    font_date  = ImageFont.truetype(FONT_PATH, 30)   # 날짜
    font_small = ImageFont.truetype(FONT_PATH, 18)   # 우측 상단 요일(선택)

    # ===== 레이아웃: 포스터 느낌 + 그리드 가운데 =====
    # 상단 큰 월 숫자 영역
    top_margin = 50
    left_margin = 70

    # 그리드 크기/위치(가운데 정렬)
    grid_w = 760
    grid_h = 360
    grid_left = (W - grid_w) // 2
    grid_top  = (H - grid_h) // 2 + 20  # 살짝 아래로(포스터 감성)

    cols, rows = 7, 6
    cell_w = grid_w / cols
    cell_h = grid_h / rows

    # ===== 상단: 큰 월 숫자 =====
    draw.text((left_margin, top_margin - 10), str(month), fill=TEXT, font=font_month)

    # 오른쪽 위: 요일 텍스트(연하게)
    dow_word = now.strftime("%A").upper()
    tw = draw.textlength(dow_word, font=font_small)
    draw.text((W - left_margin - tw, top_margin + 55), dow_word, fill=FADE, font=font_small)

    # ===== 요일(그리드 바로 위, 가운데) =====
    dow_y = grid_top - 40
    for c, d in enumerate(DOW):
        x_center = grid_left + c * cell_w + cell_w / 2
        color = RED if c in (0, 6) else TEXT
        w_txt = draw.textlength(d, font=font_dow)
        draw.text((x_center - w_txt / 2, dow_y), d, fill=color, font=font_dow)

    # ===== 날짜 계산 (42칸) =====
    cal = calendar.Calendar(firstweekday=6)  # 일요일 시작
    days = list(cal.itermonthdates(year, month))[:42]

    # ===== 날짜 출력 (완전 미니멀: 선 없음) =====
    for i, d in enumerate(days):
        r, c = divmod(i, cols)
        x0 = grid_left + c * cell_w
        y0 = grid_top  + r * cell_h

        in_month = (d.month == month)
        color = TEXT if in_month else FADE

        s = str(d.day)
        sw = draw.textlength(s, font=font_date)
        sx = x0 + (cell_w - sw) / 2
        sy = y0 + (cell_h - 34) / 2  # 글자 높이 보정

        if d == today:
            cx = x0 + cell_w / 2
            cy = y0 + cell_h / 2 + 1
            radius = min(cell_w, cell_h) * 0.38
            draw.ellipse([cx-radius, cy-radius, cx+radius, cy+radius], fill=RED)
            draw.text((sx, sy), s, fill="white", font=font_date)
        else:
            draw.text((sx, sy), s, fill=color, font=font_date)

    os.makedirs("docs", exist_ok=True)
    img.save("docs/latest.png")

if __name__ == "__main__":
    main()
