"""Render the tetanus-shot explainer video frames and encode with ffmpeg.

Reads build/timeline.json (from tts.py) and writes build/video.mp4 (silent).

Usage:
  python3 render.py                 # full render (parallel), build/video.mp4
  python3 render.py --stills 3,20   # write build/stills/t_XXX.png previews
"""
import json
import math
import os
import random
import subprocess
import sys
from multiprocessing import Pool

import cairo
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from script_data import SCENES

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
W, H, FPS = 1920, 1080, 24
FONT_DIR = "/usr/share/fonts/opentype/noto"
FONTS = {
    "sans": "NotoSansCJK-Regular.ttc",
    "sans_med": "NotoSansCJK-Medium.ttc",
    "sans_light": "NotoSansCJK-Light.ttc",
    "serif": "NotoSerifCJK-SemiBold.ttc",
    "serif_bold": "NotoSerifCJK-Bold.ttc",
    "serif_light": "NotoSerifCJK-Light.ttc",
    "serif_reg": "NotoSerifCJK-Regular.ttc",
}
SC_INDEX = 2  # Simplified Chinese face inside the Noto CJK .ttc collections

with open(os.path.join(BUILD, "timeline.json")) as f:
    TL = json.load(f)
DUR = TL["duration"]
NFRAMES = int(round(DUR * FPS))

PALETTES = {
    #         top                 bottom              glow A              glow B              accent
    "dusk":  ((0.050, 0.055, 0.080), (0.150, 0.095, 0.075), (1.00, 0.62, 0.32), (0.22, 0.45, 0.58), (0.98, 0.80, 0.52)),
    "earth": ((0.060, 0.050, 0.045), (0.190, 0.125, 0.075), (0.88, 0.55, 0.26), (0.42, 0.40, 0.26), (0.98, 0.78, 0.48)),
    "night": ((0.035, 0.050, 0.085), (0.090, 0.110, 0.170), (0.32, 0.52, 0.88), (0.95, 0.56, 0.36), (0.98, 0.80, 0.55)),
    "teal":  ((0.025, 0.065, 0.075), (0.060, 0.150, 0.160), (0.25, 0.75, 0.74), (0.95, 0.76, 0.42), (0.62, 0.93, 0.88)),
    "dawn":  ((0.070, 0.060, 0.080), (0.190, 0.130, 0.125), (1.00, 0.70, 0.50), (0.45, 0.60, 0.82), (0.99, 0.82, 0.62)),
}
WHITE = (0.97, 0.95, 0.91)
SOFT = (0.80, 0.78, 0.74)
RUST = (0.86, 0.42, 0.20)
TOXIN = (1.00, 0.42, 0.28)


# ---------------------------------------------------------------- easing ----
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def window(t, a, b, fin=0.6, fout=0.5):
    """1 inside [a, b] with smooth fades at both ends."""
    if t < a or t > b:
        return 0.0
    return smooth((t - a) / fin) * smooth((b - t) / fout)


def lerp(a, b, k):
    return a + (b - a) * k


def lerp3(a, b, k):
    return tuple(lerp(x, y, k) for x, y in zip(a, b))


# ----------------------------------------------------------------- text -----
_font_cache = {}
_text_cache = {}


def font(key, size):
    k = (key, size)
    if k not in _font_cache:
        _font_cache[k] = ImageFont.truetype(os.path.join(FONT_DIR, FONTS[key]),
                                            size, index=SC_INDEX)
    return _font_cache[k]


def pil_to_surface(img):
    a = np.asarray(img, dtype=np.float32)
    al = a[..., 3:4] / 255.0
    rgb = a[..., :3] * al
    bgra = np.dstack([rgb[..., 2], rgb[..., 1], rgb[..., 0], a[..., 3]])
    buf = bytearray(np.ascontiguousarray(np.round(bgra).astype(np.uint8)).tobytes())
    h, w = a.shape[:2]
    return Sprite(cairo.ImageSurface.create_for_data(buf, cairo.FORMAT_ARGB32, w, h, w * 4),
                  buf, w, h)


class Sprite:
    """A pre-rendered RGBA image (cairo surface + its backing buffer)."""

    def __init__(self, surf, buf, w, h):
        self.surf, self.buf, self.tw, self.th = surf, buf, w, h


def wrap(text, fnt, max_w, tracking):
    def width(s):
        return fnt.getlength(s) + tracking * max(0, len(s) - 1)
    if width(text) <= max_w:
        return [text]
    latin = all(ord(c) < 0x2E80 for c in text)
    units = text.split(" ") if latin else list(text)
    sep = " " if latin else ""
    lines, cur = [], ""
    for u in units:
        cand = (cur + sep + u) if cur else u
        if width(cand) <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = u
    lines.append(cur)
    # Avoid a line starting with closing punctuation in Chinese.
    for i in range(1, len(lines)):
        while lines[i] and lines[i][0] in "，。；、！？”）":
            lines[i - 1] += lines[i][0]
            lines[i] = lines[i][1:]
    return lines


def text(s, key="sans", size=40, rgb=WHITE, tracking=0, shadow=0.55,
         max_w=1650, line_gap=1.35, align="center"):
    k = (s, key, size, rgb, tracking, shadow, max_w, line_gap, align)
    if k in _text_cache:
        return _text_cache[k]
    fnt = font(key, size)
    lines = wrap(s, fnt, max_w, tracking)
    asc, desc = fnt.getmetrics()
    lh = int(size * line_gap)
    widths = [fnt.getlength(l) + tracking * max(0, len(l) - 1) for l in lines]
    pad = int(size * 0.7)
    w = int(max(widths)) + 2 * pad
    h = lh * (len(lines) - 1) + asc + desc + 2 * pad
    col = tuple(int(c * 255) for c in rgb)

    def draw_into(img, color):
        d = ImageDraw.Draw(img)
        for i, line in enumerate(lines):
            if align == "center":
                x = pad + (w - 2 * pad - widths[i]) / 2
            else:
                x = pad
            y = pad + i * lh
            if tracking:
                for ch in line:
                    d.text((x, y), ch, font=fnt, fill=color)
                    x += fnt.getlength(ch) + tracking
            else:
                d.text((x, y), line, font=fnt, fill=color)

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw_into(sh, (0, 0, 0, int(255 * shadow)))
        img = sh.filter(ImageFilter.GaussianBlur(max(2, size * 0.16)))
    draw_into(img, col + (255,))
    surf = pil_to_surface(img)
    _text_cache[k] = surf
    return surf


def blit(ctx, surf, x, y, alpha=1.0, scale=1.0):
    """Draw a text surface centered at (x, y)."""
    if alpha <= 0.003:
        return
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(scale, scale)
    ctx.set_source_surface(surf.surf, -surf.tw / 2, -surf.th / 2)
    ctx.paint_with_alpha(alpha)
    ctx.restore()


def blit_reveal(ctx, surf, x, y, prog, alpha=1.0):
    """Soft left-to-right wipe reveal (prog 0..1)."""
    if prog <= 0 or alpha <= 0.003:
        return
    if prog >= 1:
        return blit(ctx, surf, x, y, alpha)
    ox = x - surf.tw / 2
    oy = y - surf.th / 2
    p = lerp(-0.25, 1.0, prog)
    g = cairo.LinearGradient(ox, 0, ox + surf.tw, 0)
    g.add_color_stop_rgba(0, 0, 0, 0, alpha)
    g.add_color_stop_rgba(clamp(p), 0, 0, 0, alpha)
    g.add_color_stop_rgba(clamp(p + 0.25), 0, 0, 0, 0)
    ctx.save()
    ctx.set_source_surface(surf.surf, ox, oy)
    ctx.mask(g)
    ctx.restore()


# --------------------------------------------------------------- drawing ----
def gstroke(ctx, rgb, w=3.0, a=1.0, glow=1.0):
    """Stroke the current path with a soft neon-like glow."""
    path = ctx.copy_path()
    for gw, ga in ((w * 6, 0.045), (w * 3, 0.10)):
        if glow > 0:
            ctx.new_path()
            ctx.append_path(path)
            ctx.set_source_rgba(*rgb, ga * a * glow)
            ctx.set_line_width(gw)
            ctx.stroke()
    ctx.new_path()
    ctx.append_path(path)
    ctx.set_source_rgba(*rgb, a)
    ctx.set_line_width(w)
    ctx.stroke()


def gfill(ctx, rgb, a=1.0):
    ctx.set_source_rgba(*rgb, a)
    ctx.fill()


def glow_dot(ctx, x, y, r, rgb, a=1.0):
    g = cairo.RadialGradient(x, y, 0, x, y, r)
    g.add_color_stop_rgba(0, *rgb, a)
    g.add_color_stop_rgba(0.25, *rgb, a * 0.55)
    g.add_color_stop_rgba(1, *rgb, 0)
    ctx.set_source(g)
    ctx.arc(x, y, r, 0, 2 * math.pi)
    ctx.fill()


def rrect(ctx, x, y, w, h, r):
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    ctx.close_path()


def glass_panel(ctx, x, y, w, h, r=26, a=1.0, edge=(1, 1, 1), edge_a=0.16):
    g = cairo.LinearGradient(x, y, x, y + h)
    g.add_color_stop_rgba(0, 1, 1, 1, 0.075 * a)
    g.add_color_stop_rgba(1, 1, 1, 1, 0.025 * a)
    rrect(ctx, x, y, w, h, r)
    ctx.set_source(g)
    ctx.fill_preserve()
    ctx.set_source_rgba(*edge, edge_a * a)
    ctx.set_line_width(1.5)
    ctx.stroke()


def cubic(p0, p1, p2, p3, t):
    u = 1 - t
    return (u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
            u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1])


# ---- icons: drawn around (0, 0), roughly within a 200 x 200 box ----------
def icon_nail(ctx, c, a, rust=True):
    ctx.save()
    rrect(ctx, -62, -96, 124, 20, 8)
    gstroke(ctx, c, 3.2, a)
    ctx.move_to(-13, -76)
    ctx.line_to(-11, 52)
    ctx.line_to(0, 96)
    ctx.line_to(11, 52)
    ctx.line_to(13, -76)
    gstroke(ctx, c, 3.2, a)
    for yy in (-50, -26, -2, 22):
        ctx.move_to(-12, yy)
        ctx.line_to(12, yy + 8)
        gstroke(ctx, c, 1.6, a * 0.55, glow=0)
    if rust:
        rnd = random.Random(3)
        for _ in range(9):
            ctx.arc(rnd.uniform(-16, 16), rnd.uniform(-90, 40), rnd.uniform(2.5, 6), 0, 2 * math.pi)
            gfill(ctx, RUST, 0.75 * a)
    ctx.restore()


def icon_soil(ctx, c, a, rust_dots=False):
    ctx.move_to(-100, 60)
    ctx.curve_to(-70, -40, 70, -40, 100, 60)
    gstroke(ctx, c, 3.2, a)
    ctx.move_to(-110, 62)
    ctx.line_to(110, 62)
    gstroke(ctx, c, 3.2, a)
    for (x1, y1, x2) in ((-55, 20, 40), (-30, -2, 10)):
        ctx.move_to(x1, y1)
        ctx.line_to(x2, y1)
        gstroke(ctx, c, 1.8, a * 0.6, glow=0)
    rnd = random.Random(7)
    for _ in range(14):
        x, y = rnd.uniform(-70, 70), rnd.uniform(-5, 50)
        ctx.arc(x, y, rnd.uniform(2, 4.5), 0, 2 * math.pi)
        gfill(ctx, RUST if rust_dots and rnd.random() < 0.6 else c, 0.7 * a)
    # sprout
    ctx.move_to(0, -18)
    ctx.curve_to(0, -50, 4, -70, 0, -84)
    gstroke(ctx, c, 2.6, a)
    ctx.move_to(0, -60)
    ctx.curve_to(16, -84, 40, -82, 44, -74)
    ctx.curve_to(30, -60, 12, -58, 0, -60)
    gstroke(ctx, c, 2.4, a)


def icon_dust(ctx, c, a, t=0.0):
    for i, r in enumerate((80, 56, 32)):
        ctx.arc(0, 0, r, math.radians(200 + 25 * i + t * 20), math.radians(340 + 25 * i + t * 20))
        gstroke(ctx, c, 3.0 - 0.5 * i, a * (1 - 0.18 * i))
    rnd = random.Random(11)
    for _ in range(26):
        ang = rnd.uniform(0, 2 * math.pi) + t * rnd.uniform(-0.25, 0.25)
        rr = rnd.uniform(20, 105)
        ctx.arc(math.cos(ang) * rr, math.sin(ang) * rr * 0.8 + 18, rnd.uniform(1.6, 4), 0, 2 * math.pi)
        gfill(ctx, c, a * rnd.uniform(0.35, 0.85))


def icon_puncture(ctx, c, a):
    ctx.move_to(-110, 40)
    ctx.curve_to(-50, 26, 40, 54, 110, 38)
    gstroke(ctx, c, 3.0, a)
    ctx.save()
    ctx.translate(18, -30)
    ctx.rotate(math.radians(28))
    ctx.scale(0.72, 0.72)
    icon_nail(ctx, c, a, rust=True)
    ctx.restore()
    ctx.move_to(-4, 58)
    ctx.curve_to(-14, 76, -10, 88, 0, 88)
    ctx.curve_to(10, 88, 14, 76, 4, 58)
    ctx.close_path()
    gfill(ctx, (0.85, 0.30, 0.25), 0.85 * a)


def icon_paw(ctx, c, a):
    ctx.move_to(0, 4)
    ctx.curve_to(40, 4, 70, 50, 54, 78)
    ctx.curve_to(40, 100, 14, 84, 0, 84)
    ctx.curve_to(-14, 84, -40, 100, -54, 78)
    ctx.curve_to(-70, 50, -40, 4, 0, 4)
    ctx.close_path()
    gstroke(ctx, c, 3.2, a)
    for (x, y, rx, ry, rot) in ((-70, -14, 17, 24, -0.4), (-27, -56, 18, 26, -0.12),
                                (27, -56, 18, 26, 0.12), (70, -14, 17, 24, 0.4)):
        ctx.save()
        ctx.translate(x, y)
        ctx.rotate(rot)
        ctx.scale(rx, ry)
        ctx.arc(0, 0, 1, 0, 2 * math.pi)
        ctx.restore()
        gstroke(ctx, c, 3.2, a)


def icon_flame(ctx, c, a, t=0.0):
    f = 1 + 0.03 * math.sin(t * 7)
    ctx.save()
    ctx.scale(1, f)
    ctx.move_to(0, 92)
    ctx.curve_to(-70, 92, -84, 30, -50, -10)
    ctx.curve_to(-40, 20, -24, 26, -20, 18)
    ctx.curve_to(-30, -30, -6, -70, 16, -96)
    ctx.curve_to(20, -50, 76, -20, 70, 34)
    ctx.curve_to(66, 74, 40, 92, 0, 92)
    ctx.close_path()
    gstroke(ctx, c, 3.2, a)
    ctx.move_to(0, 84)
    ctx.curve_to(-30, 84, -36, 50, -14, 26)
    ctx.curve_to(-10, 44, 4, 44, 6, 36)
    ctx.curve_to(4, 16, 14, 4, 22, -6)
    ctx.curve_to(26, 20, 40, 34, 36, 56)
    ctx.curve_to(32, 76, 18, 84, 0, 84)
    ctx.close_path()
    gstroke(ctx, (1.0, 0.62, 0.35), 2.4, a)
    ctx.restore()


def icon_syringe(ctx, c, a):
    ctx.save()
    ctx.rotate(math.radians(-35))
    rrect(ctx, -26, -60, 52, 120, 10)
    gstroke(ctx, c, 3.0, a)
    for yy in (-30, -6, 18, 42):
        ctx.move_to(-26, yy)
        ctx.line_to(-6, yy)
        gstroke(ctx, c, 1.8, a * 0.7, glow=0)
    ctx.move_to(0, -60)
    ctx.line_to(0, -92)
    gstroke(ctx, c, 3.0, a)
    ctx.move_to(-26, -92)
    ctx.line_to(26, -92)
    gstroke(ctx, c, 3.4, a)
    ctx.move_to(-10, 60)
    ctx.line_to(10, 60)
    ctx.line_to(4, 74)
    ctx.line_to(-4, 74)
    ctx.close_path()
    gstroke(ctx, c, 2.4, a)
    ctx.move_to(0, 74)
    ctx.line_to(0, 112)
    gstroke(ctx, c, 2.0, a)
    ctx.restore()


def drop_path(ctx, s=1.0):
    ctx.move_to(0, -100 * s)
    ctx.curve_to(30 * s, -50 * s, 70 * s, -6 * s, 70 * s, 34 * s)
    ctx.curve_to(70 * s, 76 * s, 38 * s, 100 * s, 0, 100 * s)
    ctx.curve_to(-38 * s, 100 * s, -70 * s, 76 * s, -70 * s, 34 * s)
    ctx.curve_to(-70 * s, -6 * s, -30 * s, -50 * s, 0, -100 * s)
    ctx.close_path()


def icon_drop(ctx, c, a):
    drop_path(ctx)
    g = cairo.LinearGradient(0, -100, 0, 100)
    g.add_color_stop_rgba(0, *c, 0.02 * a)
    g.add_color_stop_rgba(1, *c, 0.22 * a)
    ctx.set_source(g)
    ctx.fill_preserve()
    gstroke(ctx, c, 3.2, a)
    ctx.arc(-26, 40, 26, math.radians(100), math.radians(180))
    gstroke(ctx, WHITE, 3.0, a * 0.8, glow=0)


def icon_faucet(ctx, c, a, t=0.0):
    ctx.move_to(-100, -60)
    ctx.line_to(10, -60)
    ctx.curve_to(50, -60, 60, -40, 60, -10)
    ctx.line_to(60, 4)
    ctx.move_to(30, 4)
    ctx.line_to(30, -12)
    ctx.curve_to(30, -26, 24, -30, 10, -30)
    ctx.line_to(-100, -30)
    gstroke(ctx, c, 3.2, a)
    ctx.move_to(24, 4)
    ctx.line_to(66, 4)
    gstroke(ctx, c, 3.4, a)
    rrect(ctx, -60, -92, 40, 32, 6)
    gstroke(ctx, c, 3.0, a)
    ctx.move_to(-80, -92)
    ctx.line_to(0, -92)
    gstroke(ctx, c, 3.0, a)
    water = (0.55, 0.82, 1.0)
    for k in range(4):
        ph = (t * 1.3 + k / 4) % 1
        y = 20 + ph * 80
        ctx.save()
        ctx.translate(45, y)
        drop_path(ctx, 0.11)
        ctx.restore()
        gfill(ctx, water, a * (1 - ph) * 0.95)
    ctx.move_to(45, 10)
    ctx.line_to(45, 34)
    gstroke(ctx, water, 2.2, a * 0.6)


def icon_cross(ctx, c, a):
    ctx.arc(0, 0, 92, 0, 2 * math.pi)
    gstroke(ctx, c, 3.0, a)
    s, l = 18, 54
    ctx.move_to(-s, -l)
    for x, y in ((s, -l), (s, -s), (l, -s), (l, s), (s, s), (s, l), (-s, l), (-s, s),
                 (-l, s), (-l, -s), (-s, -s)):
        ctx.line_to(x, y)
    ctx.close_path()
    ctx.set_source_rgba(0.92, 0.38, 0.34, 0.25 * a)
    ctx.fill_preserve()
    gstroke(ctx, (1.0, 0.52, 0.46), 3.0, a)


def icon_calendar(ctx, c, a):
    rrect(ctx, -90, -70, 180, 160, 18)
    gstroke(ctx, c, 3.2, a)
    ctx.move_to(-90, -26)
    ctx.line_to(90, -26)
    gstroke(ctx, c, 2.4, a)
    for x in (-46, 46):
        ctx.move_to(x, -90)
        ctx.line_to(x, -54)
        gstroke(ctx, c, 4.0, a)
    for r in range(3):
        for col in range(5):
            x, y = -64 + col * 32, 6 + r * 30
            if (r, col) == (1, 3):
                ctx.arc(x, y, 15, 0, 2 * math.pi)
                gstroke(ctx, (1.0, 0.62, 0.36), 2.6, a)
            ctx.arc(x, y, 3.5, 0, 2 * math.pi)
            gfill(ctx, c, 0.8 * a)


def icon_thermo(ctx, c, a):
    ctx.move_to(-18, 40)
    ctx.line_to(-18, -78)
    ctx.arc(0, -78, 18, math.pi, 0)
    ctx.line_to(18, 40)
    ctx.arc(0, 66, 32, -math.pi / 2 + 0.6, 1.5 * math.pi - 0.6)
    ctx.close_path()
    gstroke(ctx, c, 3.2, a)
    ctx.arc(0, 66, 20, 0, 2 * math.pi)
    gfill(ctx, (1.0, 0.50, 0.38), 0.9 * a)
    rrect(ctx, -6, -40, 12, 100, 6)
    gfill(ctx, (1.0, 0.50, 0.38), 0.9 * a)
    for i in range(5):
        y = -70 + i * 22
        ctx.move_to(30, y)
        ctx.line_to(46 if i % 2 == 0 else 40, y)
        gstroke(ctx, c, 2.0, a * 0.7, glow=0)


def icon_alert(ctx, c, a):
    rrect(ctx, -100, -80, 200, 136, 32)
    gstroke(ctx, c, 3.2, a)
    ctx.move_to(-40, 56)
    ctx.line_to(-62, 96)
    ctx.line_to(-6, 56)
    gstroke(ctx, c, 3.2, a)
    ctx.move_to(0, -48)
    ctx.line_to(0, 2)
    gstroke(ctx, (1.0, 0.66, 0.40), 7, a)
    ctx.arc(0, 26, 5, 0, 2 * math.pi)
    gfill(ctx, (1.0, 0.66, 0.40), a)


def icon_stetho(ctx, c, a):
    ctx.move_to(-46, -96)
    ctx.curve_to(-62, -60, -62, -10, -30, 14)
    ctx.curve_to(-14, 26, 14, 26, 30, 14)
    ctx.curve_to(62, -10, 62, -60, 46, -96)
    gstroke(ctx, c, 3.4, a)
    for x in (-46, 46):
        ctx.arc(x, -100, 7, 0, 2 * math.pi)
        gfill(ctx, c, a)
    ctx.move_to(0, 24)
    ctx.curve_to(0, 90, 70, 100, 76, 40)
    gstroke(ctx, c, 3.4, a)
    ctx.arc(76, 22, 22, 0, 2 * math.pi)
    gstroke(ctx, c, 3.4, a)
    ctx.arc(76, 22, 9, 0, 2 * math.pi)
    gfill(ctx, (1.0, 0.66, 0.40), a)


def icon_clipboard(ctx, c, a):
    rrect(ctx, -80, -96, 160, 196, 16)
    gstroke(ctx, c, 3.2, a)
    rrect(ctx, -36, -110, 72, 30, 10)
    gstroke(ctx, c, 3.0, a)
    s, l = 9, 28
    ctx.save()
    ctx.translate(0, -36)
    ctx.move_to(-s, -l)
    for x, y in ((s, -l), (s, -s), (l, -s), (l, s), (s, s), (s, l), (-s, l), (-s, s),
                 (-l, s), (-l, -s), (-s, -s)):
        ctx.line_to(x, y)
    ctx.close_path()
    ctx.restore()
    gstroke(ctx, (1.0, 0.52, 0.46), 2.6, a)
    for y in (22, 50, 76):
        ctx.move_to(-50, y)
        ctx.line_to(50 if y != 76 else 10, y)
        gstroke(ctx, c, 2.4, a * 0.7, glow=0)


def antibody(ctx, x, y, s, rot, c, a):
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    ctx.scale(s, s)
    ctx.move_to(0, 22)
    ctx.line_to(0, 0)
    ctx.line_to(-15, -18)
    ctx.move_to(0, 0)
    ctx.line_to(15, -18)
    ctx.restore()
    gstroke(ctx, c, 3.0, a)


def bacterium(ctx, x, y, L, rot, c, a):
    """Drumstick-shaped rod with a terminal spore (C. tetani morphology)."""
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    r = 11
    ctx.new_sub_path()
    ctx.arc(-L / 2, 0, r, math.pi / 2, 1.5 * math.pi)
    ctx.line_to(L / 2 - 6, -r)
    ctx.line_to(L / 2 - 6, r)
    ctx.close_path()
    ctx.restore()
    ctx.set_source_rgba(*c, 0.10 * a)
    ctx.fill_preserve()
    gstroke(ctx, c, 2.6, a)
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    ctx.arc(L / 2 + 8, 0, 16, 0, 2 * math.pi)
    ctx.restore()
    ctx.set_source_rgba(*c, 0.22 * a)
    ctx.fill_preserve()
    gstroke(ctx, c, 2.6, a)


# ------------------------------------------------------------ background ----
class Particles:
    def __init__(self, seed):
        rnd = random.Random(seed)
        self.bokeh = [(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(30, 110),
                       rnd.uniform(-6, 6), rnd.uniform(-10, -2), rnd.uniform(0, 6.28),
                       rnd.random() < 0.55, rnd.uniform(0.04, 0.12)) for _ in range(26)]
        self.motes = [(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(1.0, 2.6),
                       rnd.uniform(-8, 8), rnd.uniform(-14, -3), rnd.uniform(0, 6.28),
                       rnd.uniform(0.25, 0.75)) for _ in range(70)]

    def draw(self, ctx, t, ca, cb):
        for (x, y, r, vx, vy, ph, which, al) in self.bokeh:
            px = (x + vx * t + 30 * math.sin(t * 0.13 + ph)) % (W + 240) - 120
            py = (y + vy * t) % (H + 240) - 120
            a = al * (0.65 + 0.35 * math.sin(t * 0.5 + ph))
            c = ca if which else cb
            g = cairo.RadialGradient(px, py, 0, px, py, r)
            g.add_color_stop_rgba(0, *c, a * 0.7)
            g.add_color_stop_rgba(0.72, *c, a)
            g.add_color_stop_rgba(0.86, *c, a * 0.55)
            g.add_color_stop_rgba(1, *c, 0)
            ctx.set_source(g)
            ctx.arc(px, py, r, 0, 2 * math.pi)
            ctx.fill()
        for (x, y, r, vx, vy, ph, al) in self.motes:
            px = (x + vx * t + 12 * math.sin(t * 0.4 + ph)) % W
            py = (y + vy * t) % H
            a = al * (0.5 + 0.5 * math.sin(t * 1.3 + ph * 3))
            glow_dot(ctx, px, py, r * 3.2, (1.0, 0.92, 0.80), a * 0.7)


PARTICLES = Particles(42)


def palette_at(t):
    scenes = TL["scenes"]
    cur = 0
    for i, sc in enumerate(scenes):
        if sc["vis_start"] <= t:
            cur = i
    p = PALETTES[SCENES[cur]["palette"]]
    if cur > 0:
        k = smooth((t - scenes[cur]["vis_start"] + 1.0) / 2.0)
        prev = PALETTES[SCENES[cur - 1]["palette"]]
        p = tuple(lerp3(a, b, k) for a, b in zip(prev, p))
    if cur + 1 < len(scenes):
        b = scenes[cur]["vis_end"]
        if t > b - 1.0:
            k = smooth((t - b + 1.0) / 2.0)
            nxt = PALETTES[SCENES[cur + 1]["palette"]]
            p = tuple(lerp3(a, b2, k) for a, b2 in zip(p, nxt))
    return p


def draw_background(ctx, t):
    top, bot, ga, gb, _ = palette_at(t)
    g = cairo.LinearGradient(0, 0, 0, H)
    g.add_color_stop_rgb(0, *top)
    g.add_color_stop_rgb(1, *bot)
    ctx.set_source(g)
    ctx.paint()
    blobs = ((ga, 0.30 + 0.08 * math.sin(t * 0.07), 0.38 + 0.06 * math.cos(t * 0.05), 900, 0.22),
             (gb, 0.78 + 0.06 * math.cos(t * 0.06), 0.30 + 0.08 * math.sin(t * 0.08), 800, 0.18),
             (ga, 0.62 + 0.10 * math.sin(t * 0.045 + 1), 0.92, 1000, 0.12))
    for c, fx, fy, r, a in blobs:
        x, y = fx * W, fy * H
        rg = cairo.RadialGradient(x, y, 0, x, y, r)
        rg.add_color_stop_rgba(0, *c, a)
        rg.add_color_stop_rgba(0.45, *c, a * 0.35)
        rg.add_color_stop_rgba(1, *c, 0)
        ctx.set_source(rg)
        ctx.paint()
    PARTICLES.draw(ctx, t, ga, gb)
    # Diagonal soft light shaft.
    ctx.save()
    ctx.translate(W * 0.22 + 60 * math.sin(t * 0.05), -100)
    ctx.rotate(math.radians(24))
    lg = cairo.LinearGradient(-220, 0, 220, 0)
    lg.add_color_stop_rgba(0, 1, 0.9, 0.75, 0)
    lg.add_color_stop_rgba(0.5, 1, 0.9, 0.75, 0.035)
    lg.add_color_stop_rgba(1, 1, 0.9, 0.75, 0)
    ctx.set_source(lg)
    ctx.rectangle(-220, -200, 440, H * 1.8)
    ctx.fill()
    ctx.restore()


def draw_light_leaks(ctx, t):
    scenes = TL["scenes"]
    for sc in scenes[:-1]:
        b = sc["vis_end"]
        if b - 1.2 < t < b + 1.2:
            k = (t - (b - 1.2)) / 2.4
            inten = math.sin(k * math.pi) ** 2 * 0.30
            x = lerp(-300, W + 300, ease_io(k))
            y = H * 0.35
            ctx.save()
            ctx.set_operator(cairo.OPERATOR_SCREEN)
            for (c, r, dx) in (((1.0, 0.55, 0.25), 900, 0), ((1.0, 0.85, 0.6), 500, 120)):
                g = cairo.RadialGradient(x + dx, y, 0, x + dx, y, r)
                g.add_color_stop_rgba(0, *c, inten)
                g.add_color_stop_rgba(1, *c, 0)
                ctx.set_source(g)
                ctx.paint()
            ctx.restore()


# --------------------------------------------------------------- scenes -----
GROUPS = {
    "title": "title", "bacteria": "bacteria", "sources": "sources",
    "nerves": "nerves", "wash": "wash",
    "wounds1": "wounds", "wounds2": "wounds", "wounds3": "wounds",
    "timeline": "timeline", "timeline10": "timeline", "timeline5": "timeline",
    "doctor": "doctor", "shield": "shield", "curve": "curve", "clock": "clock",
    "tip0": "tipstitle", "tip1": "tips", "tip2": "tips", "tip3": "tips",
    "tip4": "tips", "tip5": "tips", "tip6": "tips", "tip7": "decide", "end": "end",
}


def build_groups():
    """Group consecutive lines that share a visual; compute show windows."""
    out = []
    lines = TL["lines"]
    for sc in TL["scenes"]:
        sl = [l for l in lines if l["scene"] == sc["idx"]]
        cur = None
        for l in sl:
            g = GROUPS[l["cue"]]
            if cur is None or cur["name"] != g:
                cur = {"name": g, "scene": sc["idx"], "lines": []}
                out.append(cur)
            cur["lines"].append(l)
        for i, g in enumerate([g for g in out if g["scene"] == sc["idx"]]):
            first = g["lines"][0]
            g["show_start"] = (sc["vis_start"] + 0.15) if i == 0 else first["start"] - 0.45
        sg = [g for g in out if g["scene"] == sc["idx"]]
        for i, g in enumerate(sg):
            g["show_end"] = sg[i + 1]["show_start"] + 0.45 if i + 1 < len(sg) else sc["vis_end"]
    return out


GROUP_LIST = build_groups()


def section_tag(ctx, sc, a, accent):
    s = SCENES[sc["idx"]]
    if not s.get("num") or a <= 0:
        return
    x0, y0 = 120, 112
    blit(ctx, text(s["num"], "serif_light", 64, accent, shadow=0.4), x0 + 40, y0, a)
    ctx.move_to(x0 + 92, y0 - 34)
    ctx.line_to(x0 + 92, y0 + 34)
    ctx.set_source_rgba(*accent, 0.55 * a)
    ctx.set_line_width(1.4)
    ctx.stroke()
    t1 = text(s["tag_zh"], "serif", 34, WHITE, shadow=0.4)
    t2 = text(s["tag_en"].upper(), "sans_light", 18, SOFT, tracking=4, shadow=0.4)
    blit(ctx, t1, x0 + 112 + t1.tw / 2 - int(34 * 0.7), y0 - 14, a)
    blit(ctx, t2, x0 + 112 + t2.tw / 2 - int(18 * 0.7), y0 + 24, a)


def label_pair(ctx, x, y, zh, en, a, zsize=40, esize=24, zkey="serif", zc=WHITE,
               ec=SOFT, gap=None, reveal=None):
    gap = gap if gap is not None else zsize * 0.62 + esize * 0.62
    tz = text(zh, zkey, zsize, zc)
    te = text(en, "sans_light", esize, ec, tracking=1)
    if reveal is None:
        blit(ctx, tz, x, y, a)
        blit(ctx, te, x, y + gap, a)
    else:
        blit_reveal(ctx, tz, x, y, reveal, a)
        blit_reveal(ctx, te, x, y + gap, clamp(reveal * 1.1 - 0.1), a)


def place(ctx, x, y, s=1.0):
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(s, s)


def draw_title(ctx, gt, g, a, acc, t):
    ctx.save()
    ctx.translate(1500, 470)
    ctx.rotate(math.radians(-24 + 1.5 * math.sin(t * 0.3)))
    ctx.scale(2.9, 2.9)
    icon_nail(ctx, acc, 0.20 * a, rust=True)
    ctx.restore()
    gx = 1500 + math.sin(math.radians(24)) * lerp(-260, 260, (gt * 0.18) % 1)
    gy = 470 - math.cos(math.radians(24)) * lerp(-260, 260, (gt * 0.18) % 1)
    glow_dot(ctx, gx, gy, 60, (1, 0.9, 0.7), 0.35 * a)
    cx = 820
    blit_reveal(ctx, text("破伤风针", "serif_bold", 168, WHITE, tracking=14, shadow=0.6),
                cx, 380, ease_out((gt - 0.3) / 1.8), a)
    blit_reveal(ctx, text("什么时候该打？为什么要打？", "serif_light", 54, (0.95, 0.88, 0.78),
                          tracking=4), cx, 530, ease_out((gt - 1.2) / 1.6), a)
    k = ease_io((gt - 1.8) / 1.4)
    if k > 0:
        ctx.move_to(cx - 330 * k, 610)
        ctx.line_to(cx + 330 * k, 610)
        gstroke(ctx, acc, 1.6, a * 0.9, glow=0.6)
    blit_reveal(ctx, text("TETANUS SHOTS  ·  WHEN & WHY", "sans_light", 28, SOFT, tracking=9),
                cx, 662, ease_out((gt - 2.2) / 1.6), a)


def draw_bacteria(ctx, gt, g, a, acc, t):
    c = (0.80, 0.92, 0.62)
    rnd = random.Random(5)
    for i in range(9):
        bx = rnd.uniform(-330, 330)
        by = rnd.uniform(-150, 120)
        L = rnd.uniform(70, 120)
        rot = rnd.uniform(0, 6.28) + 0.15 * math.sin(t * 0.5 + i)
        bx += 14 * math.sin(t * 0.6 + i * 1.7)
        by += 10 * math.cos(t * 0.5 + i)
        app = smooth((gt - 0.15 * i) / 0.8)
        bacterium(ctx, 960 + bx, 420 + by, L, rot, c, a * app * (0.55 + 0.45 * (i % 3 == 0)))
    label_pair(ctx, 960, 690, "破伤风梭菌", "Clostridium tetani", a, 46, 26,
               reveal=ease_out((gt - 0.8) / 1.4))


def draw_sources(ctx, gt, g, a, acc, t):
    items = (("泥土", "Soil", lambda: icon_soil(ctx, acc, 1)),
             ("灰尘", "Dust", lambda: icon_dust(ctx, acc, 1, t)),
             ("铁锈", "Rust", lambda: (ctx.rotate(math.radians(18)), icon_nail(ctx, acc, 1))))
    for i, (zh, en, fn) in enumerate(items):
        k = ease_out((gt - 0.35 - 0.55 * i) / 0.9)
        if k <= 0:
            continue
        x = 960 + (i - 1) * 400
        y = 400 + (1 - k) * 30
        glass_panel(ctx, x - 165, y - 175, 330, 420, 28, a * k)
        ctx.push_group()
        place(ctx, x, y - 30, 0.9)
        fn()
        ctx.restore()
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(a * k)
        label_pair(ctx, x, y + 140, zh, en, a * k, 40, 24)
    dur = g["lines"][0]["end"] - g["lines"][0]["start"]
    k = ease_out((gt - dur * 0.62) / 1.0)
    blit_reveal(ctx, text("经伤口进入身体  ·  enters through wounds", "sans_light", 28,
                          (0.95, 0.85, 0.72), tracking=2), 960, 760, k, a)


NEURON = None


def neuron_geometry():
    rnd = random.Random(21)
    dend = []
    for i in range(7):
        ang = math.radians(110 + i * 23 + rnd.uniform(-8, 8))
        L = rnd.uniform(110, 170)
        p0 = (-380 + math.cos(ang) * 36, math.sin(ang) * 36)
        p3 = (-380 + math.cos(ang) * L, math.sin(ang) * L)
        p1 = (lerp(p0[0], p3[0], 0.4) + rnd.uniform(-20, 20), lerp(p0[1], p3[1], 0.4) + rnd.uniform(-20, 20))
        p2 = (lerp(p0[0], p3[0], 0.7) + rnd.uniform(-20, 20), lerp(p0[1], p3[1], 0.7) + rnd.uniform(-20, 20))
        dend.append((p0, p1, p2, p3))
        bang = ang + rnd.choice((-0.5, 0.5))
        q3 = (p3[0] + math.cos(bang) * 50, p3[1] + math.sin(bang) * 50)
        dend.append((p2, (lerp(p2[0], q3[0], 0.5), lerp(p2[1], q3[1], 0.5) - 6), q3, q3))
    axon = ((-344, 4), (-150, 80), (40, -80), (300, 10))
    term = []
    for i in range(5):
        ang = math.radians(-50 + i * 25)
        p3 = (300 + math.cos(ang) * 90, 10 + math.sin(ang) * 90)
        term.append(((300, 10), (330, 10 + math.sin(ang) * 20), (p3[0] - 20, p3[1]), p3))
    return dend, axon, term


def draw_nerves(ctx, gt, g, a, acc, t):
    global NEURON
    if NEURON is None:
        NEURON = neuron_geometry()
    dend, axon, term = NEURON
    line = g["lines"][0]
    dur = line["end"] - line["start"]
    tox = smooth((gt - dur * 0.25) / 1.5)
    nc = lerp3((0.70, 0.88, 1.0), (1.0, 0.70, 0.55), tox * 0.7)
    ox, oy = 1000, 400
    ctx.save()
    ctx.translate(ox, oy)
    grow = ease_out(gt / 1.6)
    for d in dend:
        ctx.move_to(*d[0])
        ctx.curve_to(*d[1], *d[2], *d[3])
        gstroke(ctx, nc, 2.4, a * grow)
    ctx.move_to(*axon[0])
    ctx.curve_to(*axon[1], *axon[2], *axon[3])
    gstroke(ctx, nc, 3.4, a * grow)
    for s in np.linspace(0.12, 0.85, 6):
        p, q = cubic(*axon, s), cubic(*axon, s + 0.06)
        ctx.move_to(*p)
        ctx.line_to(*q)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.set_source_rgba(*nc, 0.16 * a * grow)
        ctx.set_line_width(22)
        ctx.stroke()
    for d in term:
        ctx.move_to(*d[0])
        ctx.curve_to(*d[1], *d[2], *d[3])
        gstroke(ctx, nc, 2.4, a * grow)
        glow_dot(ctx, *d[3], 14, nc, 0.6 * a * grow)
    ctx.arc(-380, 0, 38, 0, 2 * math.pi)
    ctx.set_source_rgba(*nc, 0.12 * a * grow)
    ctx.fill_preserve()
    gstroke(ctx, nc, 3.0, a * grow)
    glow_dot(ctx, -380, 0, 26, nc, 0.7 * a * grow)
    # Signal pulses travel down the axon; toxin makes them erratic.
    rate = lerp(0.55, 1.6, tox)
    for k in range(3):
        ph = (gt * rate + k / 3 + (0.08 * math.sin(gt * 9 + k) * tox)) % 1
        px, py = cubic(*axon, ph)
        pc = lerp3((0.75, 0.95, 1.0), TOXIN, tox)
        glow_dot(ctx, px, py, 26, pc, a * grow)
    rnd = random.Random(9)
    for i in range(22):
        sx, sy = rnd.uniform(380, 640), rnd.uniform(-220, 220)
        tx, ty = 300 + rnd.uniform(40, 120), 10 + rnd.uniform(-110, 110)
        k = smooth((gt - dur * 0.2 - i * 0.06) / 2.2)
        px = lerp(sx, tx, k) + 6 * math.sin(t * 2 + i)
        py = lerp(sy, ty, k) + 6 * math.cos(t * 1.7 + i)
        glow_dot(ctx, px, py, 9, TOXIN, a * tox * 0.9)
    ctx.restore()
    blit(ctx, text("毒素", "sans_med", 26, TOXIN), ox + 520, oy - 230, a * tox)
    blit(ctx, text("TOXIN", "sans_light", 18, TOXIN, tracking=4), ox + 520, oy - 198, a * tox)
    label_pair(ctx, 700, 700, "牙关紧闭", "Lockjaw", a, 44, 26, zc=(1.0, 0.86, 0.76),
               reveal=ease_out((gt - dur * 0.58) / 0.9))
    label_pair(ctx, 1240, 700, "肌肉痉挛", "Muscle spasms", a, 44, 26, zc=(1.0, 0.86, 0.76),
               reveal=ease_out((gt - dur * 0.74) / 0.9))


def draw_wash(ctx, gt, g, a, acc, t):
    water = (0.62, 0.86, 1.0)
    for i in range(3):
        ph = (gt * 0.45 + i / 3) % 1
        ctx.save()
        ctx.translate(960, 560)
        ctx.scale(1, 0.28)
        ctx.arc(0, 0, 80 + ph * 260, 0, 2 * math.pi)
        ctx.restore()
        gstroke(ctx, water, 2.0, a * (1 - ph) * 0.6, glow=0.5)
    place(ctx, 960, 390 + 8 * math.sin(t * 1.2), 1.25)
    icon_drop(ctx, water, a)
    ctx.restore()
    line = g["lines"][0]
    dur = line["end"] - line["start"]
    blit_reveal(ctx, text("不常见  ·  但严重", "serif", 38, (0.98, 0.86, 0.72), tracking=3),
                960, 180, ease_out((gt - 0.3) / 1.0), a)
    blit_reveal(ctx, text("UNCOMMON  ·  BUT SERIOUS", "sans_light", 20, SOFT, tracking=6),
                960, 226, ease_out((gt - 0.5) / 1.0), a)
    label_pair(ctx, 960, 690, "光清洗伤口，有时还不够", "Cleaning alone is sometimes not enough",
               a, 46, 26, reveal=ease_out((gt - dur * 0.45) / 1.2))


WOUND_ITEMS = (("深或脏的扎伤", "Deep / dirty punctures", "puncture"),
               ("泥土、铁锈", "Soil or rust", "soil"),
               ("动物咬伤", "Animal bites", "paw"),
               ("烧伤、烫伤", "Burns", "flame"))


def sub_state(g, t):
    """Index of current line in the group and time since it started."""
    idx = 0
    for i, l in enumerate(g["lines"]):
        if t >= l["start"] - 0.3:
            idx = i
    l = g["lines"][idx]
    return idx, t - l["start"], l["end"] - l["start"]


def draw_wounds(ctx, gt, g, a, acc, t):
    sub, st, sd = sub_state(g, t)
    blit_reveal(ctx, text("高风险伤口", "serif", 50, WHITE, tracking=6), 960, 205,
                ease_out(gt / 1.2), a)
    blit_reveal(ctx, text("HIGH-RISK WOUNDS", "sans_light", 20, SOFT, tracking=7), 960, 258,
                ease_out((gt - 0.2) / 1.2), a)
    lit = [0.0] * 4
    if sub >= 1:
        lit[0] = 1.0 if sub == 1 else 0.85
    if sub >= 2:
        for i in (1, 2, 3):
            lit[i] = smooth((st - (i - 1) * sd * 0.30 + 0.1) / 0.5)
    for i, (zh, en, ic) in enumerate(WOUND_ITEMS):
        k = ease_out((gt - 0.3 - 0.18 * i) / 0.9)
        if k <= 0:
            continue
        x = 960 + (i - 1.5) * 380
        y = 520 + (1 - k) * 30 - 10 * lit[i]
        L = lit[i]
        ca = a * k * (0.5 + 0.5 * L)
        edge = lerp3((1, 1, 1), acc, L)
        glass_panel(ctx, x - 160, y - 200, 320, 420, 28, a * k * (0.8 + 0.6 * L), edge, 0.16 + 0.5 * L)
        if L > 0:
            glow_dot(ctx, x, y - 60, 170, acc, 0.10 * L * a)
        ctx.push_group()
        place(ctx, x, y - 60, 0.85)
        {"puncture": lambda: icon_puncture(ctx, acc, 1),
         "soil": lambda: icon_soil(ctx, acc, 1, rust_dots=True),
         "paw": lambda: icon_paw(ctx, acc, 1),
         "flame": lambda: icon_flame(ctx, acc, 1, t)}[ic]()
        ctx.restore()
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(ca)
        label_pair(ctx, x, y + 108, zh, en, ca, 36, 22, zc=lerp3(SOFT, WHITE, L))


def draw_timeline(ctx, gt, g, a, acc, t):
    sub, st, sd = sub_state(g, t)
    blit_reveal(ctx, text("距离上一次加强针", "serif", 50, WHITE, tracking=4), 960, 205,
                ease_out(gt / 1.2), a)
    blit_reveal(ctx, text("TIME SINCE YOUR LAST BOOSTER", "sans_light", 20, SOFT, tracking=7),
                960, 258, ease_out((gt - 0.2) / 1.2), a)
    x0, x1, y = 400, 1560, 575
    grow = ease_io((gt - 0.4) / 1.6)
    ctx.move_to(x0, y)
    ctx.line_to(lerp(x0, x1, grow), y)
    gstroke(ctx, SOFT, 2.0, a * 0.8, glow=0.4)
    xs = {0: x0, 5: lerp(x0, x1, 0.5), 10: x1}
    for yr, x in xs.items():
        k = smooth((grow - (x - x0) / (x1 - x0)) * 6 + 0.5)
        ctx.move_to(x, y - 14)
        ctx.line_to(x, y + 14)
        gstroke(ctx, SOFT, 2.0, a * k, glow=0)
        lab = "0" if yr == 0 else f"{yr} 年"
        blit(ctx, text(lab, "serif", 34, WHITE), x, y + 52, a * k)
        blit(ctx, text("years" if yr else "last shot", "sans_light", 18, SOFT, tracking=2),
             x, y + 86, a * k)
    place(ctx, x0, y - 120, 0.55)
    icon_syringe(ctx, acc, a * smooth(gt / 0.8))
    ctx.restore()
    if sub == 0:
        k = ease_io((st - 0.5) / max(1.0, sd - 0.6))
        px = lerp(x0, x1, k)
        ctx.move_to(x0, y)
        ctx.line_to(px, y)
        gstroke(ctx, acc, 4.0, a * 0.9)
        glow_dot(ctx, px, y, 30, acc, a)
    else:
        ctx.move_to(x0, y)
        ctx.line_to(x1, y)
        gstroke(ctx, acc, 4.0, a * 0.55, glow=0.5)
    k10 = smooth(st / 0.6) if sub == 1 else (1.0 if sub > 1 else 0.0)
    if k10 > 0:
        w = 0.55 if sub > 1 else 1.0
        glow_dot(ctx, x1, y, 70, acc, 0.6 * k10 * w * a)
        glass_panel(ctx, x1 - 230, y - 250, 300, 130, 22, a * k10 * w, acc, 0.5)
        label_pair(ctx, x1 - 80, y - 205, "常规加强", "Routine: ~10 yrs", a * k10 * w, 36, 22,
                   zc=acc)
    k5 = smooth(st / 0.6) if sub == 2 else 0.0
    if k5 > 0:
        ra = (1.0, 0.62, 0.38)
        ctx.move_to(xs[5], y)
        ctx.line_to(x1, y)
        gstroke(ctx, ra, 5.0, a * k5)
        glow_dot(ctx, xs[5], y, 70, ra, 0.7 * k5 * a)
        glass_panel(ctx, xs[5] - 190, y - 250, 380, 130, 22, a * k5, ra, 0.55)
        label_pair(ctx, xs[5], y - 205, "脏伤口：超过约5年", "Dirty wound: > ~5 yrs", a * k5,
                   36, 22, zc=(1.0, 0.80, 0.62))
        blit_reveal(ctx, text("考虑补打  ·  consider a booster", "sans_light", 28,
                              (1.0, 0.82, 0.66), tracking=2), 960, 720,
                    ease_out((st - sd * 0.5) / 1.0), a)


def draw_doctor(ctx, gt, g, a, acc, t):
    k = ease_out(gt / 1.0)
    place(ctx, 640, 440 + 6 * math.sin(t), 1.2)
    icon_clipboard(ctx, acc, a * k)
    ctx.restore()
    x = 1150
    blit_reveal(ctx, text("记不清？告诉医生", "serif", 60, WHITE, tracking=4), x, 380,
                ease_out((gt - 0.3) / 1.2), a)
    blit_reveal(ctx, text("Not sure? Tell your doctor.", "sans_light", 30, SOFT, tracking=1),
                x, 450, ease_out((gt - 0.6) / 1.2), a)
    ctx.move_to(x - 260, 510)
    ctx.line_to(x + 260, 510)
    gstroke(ctx, acc, 1.4, a * 0.7 * ease_io((gt - 1.0) / 1.0), glow=0)
    dur = g["lines"][0]["end"] - g["lines"][0]["start"]
    kk = ease_out((gt - dur * 0.5) / 1.2)
    blit_reveal(ctx, text("以当地医生的判断为准", "serif_reg", 36, acc, tracking=2), x, 568, kk, a)
    blit_reveal(ctx, text("Follow local medical advice", "sans_light", 24, SOFT, tracking=2),
                x, 616, kk, a)


def shield_path(ctx):
    ctx.move_to(0, -190)
    ctx.curve_to(60, -150, 120, -140, 160, -140)
    ctx.curve_to(165, 20, 110, 140, 0, 200)
    ctx.curve_to(-110, 140, -165, 20, -160, -140)
    ctx.curve_to(-120, -140, -60, -150, 0, -190)
    ctx.close_path()


def draw_shield(ctx, gt, g, a, acc, t):
    cx, cy = 960, 430
    draw_k = ease_io(gt / 2.0)
    ctx.save()
    ctx.translate(cx, cy)
    shield_path(ctx)
    fill_k = smooth((gt - 1.2) / 2.0)
    lg = cairo.LinearGradient(0, 200, 0, -190)
    lg.add_color_stop_rgba(0, *acc, 0.28 * fill_k * a)
    lg.add_color_stop_rgba(clamp(fill_k), *acc, 0.10 * fill_k * a)
    lg.add_color_stop_rgba(1, *acc, 0.0)
    ctx.set_source(lg)
    ctx.fill_preserve()
    ctx.set_dash([1300 * draw_k + 0.1, 1400])
    gstroke(ctx, acc, 3.4, a)
    ctx.set_dash([])
    ctx.move_to(0, -80)
    ctx.line_to(0, 80)
    ctx.move_to(-80, 0)
    ctx.line_to(80, 0)
    gstroke(ctx, WHITE, 5, a * fill_k * 0.8)
    ctx.restore()
    n = 10
    for i in range(n):
        ang = 2 * math.pi * i / n + t * 0.18
        r = 290 + 10 * math.sin(t * 1.3 + i)
        k = smooth((gt - 0.8 - 0.1 * i) / 0.8)
        antibody(ctx, cx + math.cos(ang) * r, cy + math.sin(ang) * r * 0.82, 1.3,
                 ang - math.pi / 2, (0.75, 1.0, 0.95), a * k * 0.95)
    rnd = random.Random(4)
    for i in range(14):
        ang = rnd.uniform(0, 2 * math.pi)
        ph = (gt * 0.35 + rnd.random()) % 1
        r = lerp(560, 330, ease_out(ph))
        fa = math.sin(ph * math.pi) * smooth((gt - 1.5) / 1.0)
        glow_dot(ctx, cx + math.cos(ang) * r, cy + math.sin(ang) * r * 0.8, 10, TOXIN, a * fa * 0.85)
    blit(ctx, text("抗体  ANTIBODIES", "sans_light", 22, (0.75, 1.0, 0.95), tracking=3),
         cx + 420, cy - 210, a * smooth((gt - 1.6) / 0.8))
    label_pair(ctx, cx, 760, "提前产生抗体  ·  预防发病", "Antibodies ahead of time  ·  prevents disease",
               a, 40, 24, reveal=ease_out((gt - 1.4) / 1.4))


def protection(x):
    last = 0 if x < 10 else 10 if x < 20 else 20
    return 0.22 + 0.74 * math.exp(-(x - last) / 8.5)


def draw_curve(ctx, gt, g, a, acc, t):
    ox, oy, gw, gh = 470, 650, 980, 380
    dur = g["lines"][0]["end"] - g["lines"][0]["start"]
    k_ax = ease_io(gt / 1.0)
    ctx.move_to(ox, oy - gh)
    ctx.line_to(ox, oy)
    ctx.line_to(ox + gw * k_ax, oy)
    gstroke(ctx, SOFT, 1.8, a * 0.8, glow=0)
    thr = 0.42
    ctx.set_dash([10, 10])
    ctx.move_to(ox, oy - thr * gh)
    ctx.line_to(ox + gw * k_ax, oy - thr * gh)
    gstroke(ctx, (0.75, 1.0, 0.95), 1.6, a * 0.7, glow=0)
    ctx.set_dash([])
    blit(ctx, text("可靠保护水平", "sans", 24, (0.75, 1.0, 0.95)), ox + gw + 110, oy - thr * gh - 16,
         a * k_ax)
    blit(ctx, text("reliable protection", "sans_light", 18, SOFT, tracking=1), ox + gw + 110,
         oy - thr * gh + 16, a * k_ax)
    for yr in (0, 10, 20, 30):
        x = ox + gw * yr / 30
        blit(ctx, text(f"{yr}" if yr < 30 else "30 年 / yrs", "sans_light", 22, SOFT), x,
             oy + 34, a * k_ax)
    blit(ctx, text("保护力  PROTECTION", "sans_light", 20, SOFT, tracking=3), ox + 70, oy - gh - 34,
         a * k_ax)
    prog = ease_io((gt - 0.6) / (dur * 0.85))
    xmax = 30 * prog
    if xmax > 0.05:
        pts = []
        steps = int(240 * prog) + 2
        for i in range(steps):
            x = xmax * i / (steps - 1)
            pts.append((ox + gw * x / 30, oy - gh * protection(x)))
        for b in (10, 20):
            if xmax > b:
                idx = next(i for i, p in enumerate(pts) if p[0] >= ox + gw * b / 30)
                pts.insert(idx, (ox + gw * b / 30, oy - gh * protection(b - 1e-6)))
        ctx.move_to(ox, oy)
        for p in pts:
            ctx.line_to(*p)
        ctx.line_to(pts[-1][0], oy)
        ctx.close_path()
        fg = cairo.LinearGradient(0, oy - gh, 0, oy)
        fg.add_color_stop_rgba(0, *acc, 0.22 * a)
        fg.add_color_stop_rgba(1, *acc, 0.0)
        ctx.set_source(fg)
        ctx.fill()
        ctx.move_to(*pts[0])
        for p in pts[1:]:
            ctx.line_to(*p)
        gstroke(ctx, acc, 3.6, a)
        glow_dot(ctx, *pts[-1], 26, acc, a)
        for b in (10, 20):
            if xmax > b:
                kb = smooth((xmax - b) / 1.5)
                bx = ox + gw * b / 30
                glow_dot(ctx, bx, oy - gh * protection(b), 46, (1, 0.9, 0.7), 0.8 * kb * a)
                place(ctx, bx, oy - gh * protection(b) - 80, 0.32)
                icon_syringe(ctx, (1, 0.9, 0.7), a * kb)
                ctx.restore()
                blit(ctx, text("加强针 Booster", "sans", 20, (1, 0.9, 0.7)), bx, oy - gh - 4,
                     a * kb * (0 if b == 20 else 1))


def draw_clock(ctx, gt, g, a, acc, t):
    cx, cy, r = 680, 450, 170
    k = ease_out(gt / 1.0)
    ctx.arc(cx, cy, r, 0, 2 * math.pi)
    ctx.set_source_rgba(1, 1, 1, 0.04 * a * k)
    ctx.fill_preserve()
    gstroke(ctx, acc, 3.2, a * k)
    for i in range(12):
        ang = i * math.pi / 6
        r1 = r - (22 if i % 3 == 0 else 12)
        ctx.move_to(cx + math.cos(ang) * r1, cy + math.sin(ang) * r1)
        ctx.line_to(cx + math.cos(ang) * (r - 4), cy + math.sin(ang) * (r - 4))
        gstroke(ctx, SOFT, 2.4 if i % 3 == 0 else 1.4, a * k, glow=0)
    ma = -math.pi / 2 + gt * 1.4
    ha = -math.pi / 2 + gt * 0.12 + 1.0
    ctx.move_to(cx, cy)
    ctx.line_to(cx + math.cos(ha) * r * 0.5, cy + math.sin(ha) * r * 0.5)
    gstroke(ctx, WHITE, 5, a * k)
    ctx.move_to(cx, cy)
    ctx.line_to(cx + math.cos(ma) * r * 0.78, cy + math.sin(ma) * r * 0.78)
    gstroke(ctx, acc, 3, a * k)
    glow_dot(ctx, cx, cy, 14, acc, a * k)
    ctx.arc(cx, cy, r + 26, -math.pi / 2, -math.pi / 2 + 2 * math.pi * ((gt * 0.2) % 1))
    gstroke(ctx, acc, 2.0, a * k * 0.5, glow=0.4)
    x = 1240
    blit_reveal(ctx, text("及时处理", "serif", 70, WHITE, tracking=8), x, 360,
                ease_out((gt - 0.3) / 1.0), a)
    blit_reveal(ctx, text("及时接种", "serif", 70, acc, tracking=8), x, 470,
                ease_out((gt - 0.9) / 1.0), a)
    blit_reveal(ctx, text("PROMPT CARE  ·  TIMELY SHOT", "sans_light", 24, SOFT, tracking=6), x, 560,
                ease_out((gt - 1.4) / 1.0), a)


def draw_tipstitle(ctx, gt, g, a, acc, t):
    blit_reveal(ctx, text("注意事项", "serif_bold", 140, WHITE, tracking=20), 960, 420,
                ease_out((gt - 0.1) / 1.5), a)
    k = ease_io((gt - 0.8) / 1.2)
    for s in (-1, 1):
        ctx.move_to(960 + s * 120, 545)
        ctx.line_to(960 + s * (120 + 220 * k), 545)
        gstroke(ctx, acc, 1.5, a, glow=0.5)
    glow_dot(ctx, 960, 545, 10, acc, a * k)
    blit_reveal(ctx, text("THINGS TO KEEP IN MIND", "sans_light", 28, SOFT, tracking=10), 960, 600,
                ease_out((gt - 1.0) / 1.4), a)


TIPS = (("流动清水冲洗伤口", "Rinse under clean running water", "faucet"),
        ("伤口深或脏，尽快就医", "Deep or dirty wound: get care promptly", "cross"),
        ("记下上次打针的时间", "Record the date of your last shot", "calendar"),
        ("动物咬伤，还要考虑狂犬病", "Animal bite: consider rabies too", "paw"),
        ("局部酸痛、轻微发热，是常见反应", "Soreness or mild fever is common", "thermo"),
        ("过敏或怀孕，请告诉医生", "Allergies or pregnancy: tell your doctor", "alert"))


def draw_tip_item(ctx, i, a, dx, acc, t):
    zh, en, ic = TIPS[i]
    cx, cy = 560 + dx, 440
    ctx.arc(cx, cy, 175, 0, 2 * math.pi)
    rg = cairo.RadialGradient(cx, cy - 60, 20, cx, cy, 175)
    rg.add_color_stop_rgba(0, 1, 1, 1, 0.10 * a)
    rg.add_color_stop_rgba(1, 1, 1, 1, 0.02 * a)
    ctx.set_source(rg)
    ctx.fill_preserve()
    gstroke(ctx, acc, 1.6, a * 0.7, glow=0.6)
    ctx.push_group()
    place(ctx, cx, cy, 0.95)
    {"faucet": lambda: icon_faucet(ctx, acc, 1, t),
     "cross": lambda: icon_cross(ctx, acc, 1),
     "calendar": lambda: icon_calendar(ctx, acc, 1),
     "paw": lambda: icon_paw(ctx, acc, 1),
     "thermo": lambda: icon_thermo(ctx, acc, 1),
     "alert": lambda: icon_alert(ctx, acc, 1)}[ic]()
    ctx.restore()
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(a)
    x = 830 + dx * 1.4
    num = text(f"0{i + 1}", "serif_light", 120, acc, shadow=0.3)
    blit(ctx, num, x + num.tw / 2 - 84, 330, a * 0.9)
    tz = text(zh, "serif", 58, WHITE, tracking=2, max_w=960, align="left")
    te = text(en, "sans_light", 30, SOFT, tracking=1, max_w=960, align="left")
    blit(ctx, tz, x + tz.tw / 2 - 40, 470, a)
    blit(ctx, te, x + te.tw / 2 - 21, 470 + tz.th / 2 + 18, a)


def draw_tips(ctx, gt, g, a, acc, t):
    sub, st, sd = sub_state(g, t)
    kin = ease_out((st + 0.3) / 0.7) if sub > 0 else ease_out(gt / 0.9)
    draw_tip_item(ctx, sub, a * kin, (1 - kin) * 60, acc, t)
    if sub > 0:
        kout = smooth((st + 0.3) / 0.5)
        if kout < 1:
            draw_tip_item(ctx, sub - 1, a * (1 - kout), -kout * 60, acc, t)
    for i in range(6):
        x = 830 + i * 34
        on = i <= sub
        ctx.arc(x, 760, 6 if i == sub else 4.5, 0, 2 * math.pi)
        gfill(ctx, acc if on else SOFT, a * (1.0 if on else 0.35))


def draw_decide(ctx, gt, g, a, acc, t):
    k = ease_out(gt / 1.0)
    place(ctx, 620, 440 + 6 * math.sin(t * 0.9), 1.5)
    icon_stetho(ctx, acc, a * k)
    ctx.restore()
    glow_dot(ctx, 620, 440, 260, acc, 0.07 * a)
    x = 1180
    dur = g["lines"][0]["end"] - g["lines"][0]["start"]
    blit_reveal(ctx, text("不要自己判断“不用打”", "serif", 58, WHITE, tracking=3), x, 370,
                ease_out((gt - 0.3) / 1.4), a)
    blit_reveal(ctx, text("交给医生来决定", "serif_bold", 72, acc, tracking=8), x, 480,
                ease_out((gt - dur * 0.55) / 1.2), a)
    blit_reveal(ctx, text("Don't self-decide. Let a doctor decide.", "sans_light", 28, SOFT,
                          tracking=2), x, 572, ease_out((gt - dur * 0.65) / 1.2), a)


def draw_end(ctx, gt, g, a, acc, t):
    line = g["lines"][0]
    blit_reveal(ctx, text("小小一针，守护安心", "serif", 96, WHITE, tracking=12), 960, 360,
                ease_out((gt - 0.4) / 1.8), a)
    blit_reveal(ctx, text("A small shot for peace of mind.", "serif_light", 36, (0.95, 0.88, 0.78),
                          tracking=2), 960, 468, ease_out((gt - 1.2) / 1.6), a)
    kd = ease_out((t - line["start"] - 2.0) / 1.2)
    if kd > 0:
        y = 680 + (1 - kd) * 20
        glass_panel(ctx, 960 - 520, y - 85, 1040, 170, 24, a * kd, acc, 0.45)
        blit(ctx, text("本视频仅供科普，具体请遵医嘱", "sans_med", 40, WHITE, tracking=3), 960,
             y - 22, a * kd)
        blit(ctx, text("For education only; follow your clinician.", "sans_light", 26, SOFT,
                       tracking=2), 960, y + 34, a * kd)


DRAWERS = {
    "title": draw_title, "bacteria": draw_bacteria, "sources": draw_sources,
    "nerves": draw_nerves, "wash": draw_wash, "wounds": draw_wounds,
    "timeline": draw_timeline, "doctor": draw_doctor, "shield": draw_shield,
    "curve": draw_curve, "clock": draw_clock, "tipstitle": draw_tipstitle,
    "tips": draw_tips, "decide": draw_decide, "end": draw_end,
}


def draw_captions(ctx, t):
    lines = TL["lines"]
    for i, l in enumerate(lines):
        if l["cue"] == "end":
            continue
        nxt = lines[i + 1]["start"] if i + 1 < len(lines) else DUR
        a0, b0 = l["start"] - 0.12, min(l["end"] + 0.45, nxt - 0.12)
        if not (a0 <= t <= b0):
            continue
        a = window(t, a0, b0, 0.22, 0.22)
        rise = (1 - ease_out((t - a0) / 0.4)) * 10
        tz = text(l["zh"], "sans_med", 46, WHITE, tracking=1, shadow=0.85, max_w=1640)
        te = text(l["en"], "sans", 29, (0.90, 0.88, 0.84), tracking=1, shadow=0.85,
                  max_w=1640)
        ez = 46 * 0.7
        yz = H - 150 + rise - (tz.th - 2 * ez - 46 * 1.4) / 2
        blit(ctx, tz, W / 2, yz, a)
        blit(ctx, te, W / 2, yz + tz.th / 2 - ez + 22 + te.th / 2 - 29 * 0.7, a)


# ---------------------------------------------------------------- grade -----
def make_luts():
    x = np.arange(256) / 255.0
    s = x + 0.10 * np.sin(2 * np.pi * x) * -0.5 * (1 - x) * 1.6  # gentle S-curve
    s = np.clip(0.035 + s * 0.95, 0, 1)
    shadows = (1 - x) ** 2
    highs = x ** 2
    r = s - 0.012 * shadows + 0.030 * highs
    g = s + 0.006 * shadows + 0.008 * highs
    b = s + 0.022 * shadows - 0.030 * highs
    return [np.clip(c * 255 + 0.5, 0, 255).astype(np.uint8) for c in (r, g, b)]


LUTS = make_luts()


def make_vignette():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.70)) ** 2)
    v = 1 - 0.55 * np.clip(d - 0.45, 0, 1) ** 1.6
    return (v * 256).astype(np.uint16)[..., None]


VIGNETTE = None
GRAIN = None


def make_grain(n=12):
    rng = np.random.default_rng(1)
    out = []
    for _ in range(n):
        g = rng.normal(0, 1, (H // 2, W // 2)).astype(np.float32)
        img = Image.fromarray(np.clip(g * 40 + 128, 0, 255).astype(np.uint8))
        img = img.resize((W, H), Image.BILINEAR)
        out.append((np.asarray(img).astype(np.int16) - 128) // 15)
    return out


def finish(surface, t, fi):
    global VIGNETTE, GRAIN
    if VIGNETTE is None:
        VIGNETTE = make_vignette()
        GRAIN = make_grain()
    buf = np.ndarray((H, W, 4), np.uint8, surface.get_data())
    rgb = buf[..., 2::-1]
    # Bloom: blurred highlights screened back over the frame (halation).
    small = Image.fromarray(np.ascontiguousarray(rgb)).resize((W // 8, H // 8), Image.BILINEAR)
    sm = np.asarray(small).astype(np.float32)
    sm = np.clip((sm - 120) * 1.6, 0, 255).astype(np.uint8)
    bloom = Image.fromarray(sm).filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BILINEAR)
    bl = (np.asarray(bloom).astype(np.uint16) * np.array([70, 58, 46], np.uint16)) >> 8
    base = rgb.astype(np.uint16)
    scr = base + bl - ((base * bl) >> 8)
    out = np.empty((H, W, 3), np.uint8)
    for c in range(3):
        out[..., c] = LUTS[c][np.minimum(scr[..., c], 255)]
    out = ((out.astype(np.uint16) * VIGNETTE) >> 8).astype(np.int16)
    out += GRAIN[fi % len(GRAIN)][..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- frame -----
def render_frame(t, fi=0):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    draw_background(ctx, t)
    acc = palette_at(t)[4]
    for sc in TL["scenes"]:
        if not (sc["vis_start"] - 0.01 <= t <= sc["vis_end"] + 0.01):
            continue
        last = sc["idx"] == len(TL["scenes"]) - 1
        sa = window(t, sc["vis_start"], sc["vis_end"] + (5 if last else 0), 0.8, 0.7)
        if sc["idx"] == 0:
            sa = smooth((sc["vis_end"] - t) / 0.7)
        if sa <= 0:
            continue
        prog = (t - sc["vis_start"]) / max(1, sc["vis_end"] - sc["vis_start"])
        ctx.push_group()
        ctx.save()
        s = 1.0 + 0.03 * prog
        ctx.translate(W / 2, H / 2 - 10)
        ctx.scale(s, s)
        ctx.translate(-W / 2 + 6 * math.sin(t * 0.21), -H / 2 + 4 * math.cos(t * 0.17))
        for g in GROUP_LIST:
            if g["scene"] != sc["idx"]:
                continue
            ga = window(t, g["show_start"], g["show_end"], 0.6, 0.45)
            if ga > 0:
                DRAWERS[g["name"]](ctx, t - g["show_start"], g, ga, acc, t)
        ctx.restore()
        section_tag(ctx, sc, smooth((t - sc["vis_start"] - 0.3) / 0.8), acc)
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(sa)
    draw_light_leaks(ctx, t)
    cg = cairo.LinearGradient(0, H - 330, 0, H)
    cg.add_color_stop_rgba(0, 0, 0, 0, 0)
    cg.add_color_stop_rgba(1, 0, 0, 0, 0.55)
    ctx.set_source(cg)
    ctx.rectangle(0, H - 330, W, 330)
    ctx.fill()
    draw_captions(ctx, t)
    fade = smooth(t / 1.2) * smooth((DUR - t) / 1.8)
    if fade < 1:
        ctx.set_source_rgba(0, 0, 0, 1 - fade)
        ctx.paint()
    surf.flush()
    return finish(surf, t, fi)


def render_chunk(args):
    ci, f0, f1 = args
    path = os.path.join(BUILD, "chunks", f"chunk_{ci:02d}.mp4")
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
         "-c:v", "libx264", "-preset", "slow", "-crf", "22", "-tune", "film",
         "-maxrate", "2400k", "-bufsize", "4800k", "-g", str(FPS * 2),
         "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
         path], stdin=subprocess.PIPE)
    for fi in range(f0, f1):
        enc.stdin.write(render_frame(fi / FPS, fi).tobytes())
        if (fi - f0) % 120 == 0:
            print(f"chunk {ci}: frame {fi - f0}/{f1 - f0}", flush=True)
    enc.stdin.close()
    enc.wait()
    return path


def main():
    if "--stills" in sys.argv:
        ts = [float(x) for x in sys.argv[sys.argv.index("--stills") + 1].split(",")]
        os.makedirs(os.path.join(BUILD, "stills"), exist_ok=True)
        for t in ts:
            Image.fromarray(render_frame(t, int(t * FPS))).save(
                os.path.join(BUILD, "stills", f"t_{t:06.2f}.png"))
            print("still", t)
        return
    os.makedirs(os.path.join(BUILD, "chunks"), exist_ok=True)
    nproc = os.cpu_count() or 4
    nchunks = nproc * 3
    bounds = [round(NFRAMES * i / nchunks) for i in range(nchunks + 1)]
    jobs = [(i, bounds[i], bounds[i + 1]) for i in range(nchunks)]
    with Pool(nproc) as pool:
        paths = pool.map(render_chunk, jobs, chunksize=1)
    lst = os.path.join(BUILD, "chunks", "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{p}'\n" for p in paths)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", os.path.join(BUILD, "video.mp4")], check=True)
    print("wrote build/video.mp4", NFRAMES, "frames")


if __name__ == "__main__":
    main()
