from PIL import Image, ImageDraw
import os, math

OUT_DIR = "assets/weather"
SIZE = 128
STROKE = 10
PAD = 14

BLACK = (0, 0, 0, 255)
TRANSPARENT = (0, 0, 0, 0)

def new_canvas():
    img = Image.new("RGBA", (SIZE, SIZE), TRANSPARENT)
    return img, ImageDraw.Draw(img)

def save(img, name):
    os.makedirs(OUT_DIR, exist_ok=True)
    img.save(os.path.join(OUT_DIR, f"{name}.png"))

def draw_sun():
    img, d = new_canvas()
    cx, cy = SIZE//2, SIZE//2
    r = 26
    d.ellipse([cx-r, cy-r, cx+r, cy+r], outline=BLACK, width=STROKE)
    for a in range(0, 360, 45):
        rad = math.radians(a)
        x1 = cx + int((r+18)*math.cos(rad))
        y1 = cy + int((r+18)*math.sin(rad))
        x2 = cx + int((r+38)*math.cos(rad))
        y2 = cy + int((r+38)*math.sin(rad))
        d.line([(x1,y1),(x2,y2)], fill=BLACK, width=STROKE, joint="curve")
    save(img, "sun")

def draw_cloud():
    img, d = new_canvas()
    # cloud = 3 circles + base
    d.ellipse([PAD+10, 52, PAD+55, 92], outline=BLACK, width=STROKE)
    d.ellipse([PAD+38, 36, PAD+88, 92], outline=BLACK, width=STROKE)
    d.ellipse([PAD+78, 52, PAD+118, 92], outline=BLACK, width=STROKE)
    d.line([(PAD+18, 92), (SIZE-PAD-10, 92)], fill=BLACK, width=STROKE)
    save(img, "cloud")

def draw_rain():
    img, d = new_canvas()
    # cloud
    d.ellipse([PAD+10, 40, PAD+55, 80], outline=BLACK, width=STROKE)
    d.ellipse([PAD+38, 24, PAD+88, 80], outline=BLACK, width=STROKE)
    d.ellipse([PAD+78, 40, PAD+118, 80], outline=BLACK, width=STROKE)
    d.line([(PAD+18, 80), (SIZE-PAD-10, 80)], fill=BLACK, width=STROKE)
    # raindrops
    for x in [PAD+32, PAD+64, PAD+96]:
        d.line([(x, 90), (x-10, 112)], fill=BLACK, width=STROKE, joint="curve")
    save(img, "rain")

def draw_snow():
    img, d = new_canvas()
    # cloud
    d.ellipse([PAD+10, 40, PAD+55, 80], outline=BLACK, width=STROKE)
    d.ellipse([PAD+38, 24, PAD+88, 80], outline=BLACK, width=STROKE)
    d.ellipse([PAD+78, 40, PAD+118, 80], outline=BLACK, width=STROKE)
    d.line([(PAD+18, 80), (SIZE-PAD-10, 80)], fill=BLACK, width=STROKE)
    # snowflakes (simple asterisks)
    for (x,y) in [(PAD+36, 104), (PAD+64, 112), (PAD+92, 104)]:
        d.line([(x-10,y),(x+10,y)], fill=BLACK, width=STROKE-2)
        d.line([(x,y-10),(x,y+10)], fill=BLACK, width=STROKE-2)
        d.line([(x-8,y-8),(x+8,y+8)], fill=BLACK, width=STROKE-2)
        d.line([(x-8,y+8),(x+8,y-8)], fill=BLACK, width=STROKE-2)
    save(img, "snow")

def draw_thunder():
    img, d = new_canvas()
    # cloud
    d.ellipse([PAD+10, 38, PAD+55, 78], outline=BLACK, width=STROKE)
    d.ellipse([PAD+38, 22, PAD+88, 78], outline=BLACK, width=STROKE)
    d.ellipse([PAD+78, 38, PAD+118, 78], outline=BLACK, width=STROKE)
    d.line([(PAD+18, 78), (SIZE-PAD-10, 78)], fill=BLACK, width=STROKE)
    # bolt
    bolt = [(72,82),(54,112),(74,112),(56,142)]
    d.line(bolt, fill=BLACK, width=STROKE, joint="curve")
    save(img, "thunder")

def draw_fog():
    img, d = new_canvas()
    y = 44
    for i in range(3):
        d.line([(PAD, y+i*22), (SIZE-PAD, y+i*22)], fill=BLACK, width=STROKE)
    save(img, "fog")

def main():
    draw_sun()
    draw_cloud()
    draw_rain()
    draw_snow()
    draw_thunder()
    draw_fog()
    print("icons generated in assets/weather/")

if __name__ == "__main__":
    main()
