from PIL import Image, ImageDraw
import os, math

OUT_DIR = "assets/weather"
SIZE = 128

# MUJI/Apple 느낌: 얇고 균일한 선
STROKE = 6
BLACK = (0, 0, 0, 255)
TRANSPARENT = (0, 0, 0, 0)

def canvas():
    img = Image.new("RGBA", (SIZE, SIZE), TRANSPARENT)
    return img, ImageDraw.Draw(img)

def save(img, name):
    os.makedirs(OUT_DIR, exist_ok=True)
    img.save(os.path.join(OUT_DIR, f"{name}.png"))

def sun():
    img, d = canvas()
    cx, cy = SIZE//2, SIZE//2
    r = 24
    d.ellipse([cx-r, cy-r, cx+r, cy+r], outline=BLACK, width=STROKE)
    for a in range(0, 360, 60):
        rad = math.radians(a)
        x1 = cx + int((r+14)*math.cos(rad))
        y1 = cy + int((r+14)*math.sin(rad))
        x2 = cx + int((r+30)*math.cos(rad))
        y2 = cy + int((r+30)*math.sin(rad))
        d.line([(x1,y1),(x2,y2)], fill=BLACK, width=STROKE)
    save(img, "sun")

def cloud():
    img, d = canvas()
    # 3 원 + 아래 베이스(둥글게 느낌)
    d.ellipse([22, 58, 62, 92], outline=BLACK, width=STROKE)
    d.ellipse([44, 44, 86, 92], outline=BLACK, width=STROKE)
    d.ellipse([76, 58, 108, 92], outline=BLACK, width=STROKE)
    d.line([(28, 92), (104, 92)], fill=BLACK, width=STROKE)
    save(img, "cloud")

def rain():
    img, d = canvas()
    # cloud
    d.ellipse([22, 48, 62, 82], outline=BLACK, width=STROKE)
    d.ellipse([44, 34, 86, 82], outline=BLACK, width=STROKE)
    d.ellipse([76, 48, 108, 82], outline=BLACK, width=STROKE)
    d.line([(28, 82), (104, 82)], fill=BLACK, width=STROKE)
    # rain lines (세로 짧게)
    for x in [44, 64, 84]:
        d.line([(x, 94), (x, 114)], fill=BLACK, width=STROKE)
    save(img, "rain")

def snow():
    img, d = canvas()
    # cloud
    d.ellipse([22, 48, 62, 82], outline=BLACK, width=STROKE)
    d.ellipse([44, 34, 86, 82], outline=BLACK, width=STROKE)
    d.ellipse([76, 48, 108, 82], outline=BLACK, width=STROKE)
    d.line([(28, 82), (104, 82)], fill=BLACK, width=STROKE)
    # snow dots (MUJI 느낌: 점 3개)
    for (x,y) in [(48,104),(64,112),(80,104)]:
        d.ellipse([x-4,y-4,x+4,y+4], fill=BLACK)
    save(img, "snow")

def thunder():
    img, d = canvas()
    # cloud
    d.ellipse([22, 46, 62, 80], outline=BLACK, width=STROKE)
    d.ellipse([44, 32, 86, 80], outline=BLACK, width=STROKE)
    d.ellipse([76, 46, 108, 80], outline=BLACK, width=STROKE)
    d.line([(28, 80), (104, 80)], fill=BLACK, width=STROKE)
    # bolt (단순한 번개)
    bolt = [(66, 84), (54, 108), (68, 108), (56, 124)]
    d.line(bolt, fill=BLACK, width=STROKE, joint="curve")
    save(img, "thunder")

def fog():
    img, d = canvas()
    # 3개 얇은 수평선
    for y in [52, 72, 92]:
        d.line([(24, y), (104, y)], fill=BLACK, width=STROKE)
    save(img, "fog")

def main():
    sun()
    cloud()
    rain()
    snow()
    thunder()
    fog()
    print("MUJI-style weather icons generated -> assets/weather/*.png")

if __name__ == "__main__":
    main()
