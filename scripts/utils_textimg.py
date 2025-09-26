
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import textwrap

def load_font(font_path: str, size: int):
    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except Exception:
            return ImageFont.load_default()

def render_text_frame(text, w=1080, h=1920, font_path="assets/fonts/Inter-Bold.ttf",
                      size=64, color=(232,230,227), align="center", pad=36, shadow=True):
    img = Image.new("RGBA", (w, h), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    font = load_font(font_path, size)

    lines = []
    for raw in text.split("\n"):
        wrapped = textwrap.wrap(raw, width=26) or [""]
        lines.extend(wrapped)

    # backdrop under captions
    # make backdrop slimmer so it doesn't cover too much of the background
    backdrop_h = int(h*0.13)
    mask = Image.new("L", (w, backdrop_h), 0)
    ImageDraw.Draw(mask).rectangle([0,0,w,backdrop_h], fill=160)
    # reduce backdrop opacity to make background more visible behind captions
    backdrop = Image.new("RGBA", (w, backdrop_h), (12,12,12,120)).filter(ImageFilter.GaussianBlur(6))
    img.paste(backdrop, (0, int(h*0.66)), mask)

    # position captions slightly higher
    y = int(h*0.68)
    for line in lines:
        bbox = draw.textbbox((0,0), line, font=font)
        line_w = bbox[2]-bbox[0]
        line_h = bbox[3]-bbox[1]
        x = (w - line_w)//2 if align=="center" else pad
        if shadow: draw.text((x+2, y+2), line, font=font, fill=(0,0,0,180))
        draw.text((x, y), line, font=font, fill=color)
        y += int(line_h*1.15)
    return img
