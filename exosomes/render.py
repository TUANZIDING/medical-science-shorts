"""Render the extracellular-vesicle / exosome explainer video frames and encode with ffmpeg.

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

from script_data import REF_ORDER, REFS, SCENES

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


# ---- biology primitives ----------------------------------------------------
def blob_path(ctx, x, y, r, t, seed, amp=0.035, sx=1.0, sy=1.0):
    rnd = random.Random(seed)
    ph = [rnd.uniform(0, 6.28) for _ in range(3)]
    n = 120
    for i in range(n + 1):
        th = 2 * math.pi * i / n
        rr = r * (1 + amp * math.sin(3 * th + ph[0] + t * 0.7)
                  + amp * 0.6 * math.sin(5 * th + ph[1] - t * 0.9)
                  + amp * 0.4 * math.sin(2 * th + ph[2] + t * 0.4))
        px, py = x + math.cos(th) * rr * sx, y + math.sin(th) * rr * sy
        if i == 0:
            ctx.move_to(px, py)
        else:
            ctx.line_to(px, py)
    ctx.close_path()


def cell(ctx, x, y, r, t, c, a, seed=0, nucleus=True, glow=1.0, spiky=0.0):
    if a <= 0.003:
        return
    if spiky:
        rnd = random.Random(seed)
        n = 150
        ph = [rnd.uniform(0, 6.28) for _ in range(4)]
        for i in range(n + 1):
            th = 2 * math.pi * i / n
            rr = r * (1 + 0.06 * math.sin(3 * th + ph[0] + t * 0.5)
                      + spiky * 0.10 * abs(math.sin(9 * th + ph[1])) ** 3
                      + 0.04 * math.sin(7 * th + ph[2] - t * 0.8))
            px, py = x + math.cos(th) * rr, y + math.sin(th) * rr
            ctx.move_to(px, py) if i == 0 else ctx.line_to(px, py)
        ctx.close_path()
    else:
        blob_path(ctx, x, y, r, t, seed)
    g = cairo.RadialGradient(x - r * 0.2, y - r * 0.3, r * 0.1, x, y, r * 1.05)
    g.add_color_stop_rgba(0, *c, 0.13 * a)
    g.add_color_stop_rgba(1, *c, 0.035 * a)
    ctx.set_source(g)
    ctx.fill_preserve()
    gstroke(ctx, c, 3.0, a, glow)
    if not spiky:
        blob_path(ctx, x, y, r - 9, t, seed)
        gstroke(ctx, c, 1.3, a * 0.45, glow=0)
    if nucleus:
        nx, ny, nr = x - r * 0.14, y - r * 0.08, r * 0.34
        blob_path(ctx, nx, ny, nr, t * 0.6, seed + 1, 0.05)
        ctx.set_source_rgba(*c, 0.12 * a)
        ctx.fill_preserve()
        gstroke(ctx, c, 2.2, a * 0.8, glow=0.5)
        glow_dot(ctx, nx + nr * 0.25, ny - nr * 0.15, nr * 0.35, c, 0.35 * a)
        rnd = random.Random(seed + 7)
        for _ in range(7):
            ang, rr = rnd.uniform(0, 6.28), rnd.uniform(r * 0.5, r * 0.78)
            ox, oy = x + math.cos(ang) * rr, y + math.sin(ang) * rr
            ctx.save()
            ctx.translate(ox, oy)
            ctx.rotate(ang + 1.2)
            ctx.scale(1.0, 0.45)
            ctx.arc(0, 0, r * rnd.uniform(0.05, 0.09), 0, 2 * math.pi)
            ctx.restore()
            gstroke(ctx, c, 1.4, a * 0.45, glow=0)


RNA_C = (0.98, 0.55, 0.78)
PROT_C = (1.00, 0.76, 0.40)


def squiggle(ctx, x, y, L, rot, c, a, w=2.4, t=0.0, waves=3):
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    n = 40
    for i in range(n + 1):
        u = i / n
        px = (u - 0.5) * L
        py = math.sin(u * waves * 2 * math.pi + t * 2) * L * 0.09
        ctx.move_to(px, py) if i == 0 else ctx.line_to(px, py)
    ctx.restore()
    gstroke(ctx, c, w, a, glow=0.6)


def vesicle(ctx, x, y, r, c, a, seed=0, cargo=True, t=0.0):
    if a <= 0.003:
        return
    if r < 7:
        glow_dot(ctx, x, y, r * 2.6, c, a * 0.9)
        return
    g = cairo.RadialGradient(x - r * 0.35, y - r * 0.4, r * 0.05, x, y, r)
    g.add_color_stop_rgba(0, 1, 1, 1, 0.20 * a)
    g.add_color_stop_rgba(0.6, *c, 0.08 * a)
    g.add_color_stop_rgba(1, *c, 0.16 * a)
    ctx.arc(x, y, r, 0, 2 * math.pi)
    ctx.set_source(g)
    ctx.fill()
    ctx.arc(x, y, r, 0, 2 * math.pi)
    gstroke(ctx, c, max(1.3, min(3.0, r * 0.11)), a, glow=0.8)
    ctx.arc(x, y, r * 0.80, 0, 2 * math.pi)
    gstroke(ctx, c, max(0.8, min(1.6, r * 0.05)), a * 0.45, glow=0)
    ctx.arc(x - r * 0.32, y - r * 0.32, r * 0.30, math.radians(190), math.radians(260))
    gstroke(ctx, WHITE, max(1.0, r * 0.06), a * 0.55, glow=0)
    if cargo and r >= 14:
        rnd = random.Random(seed)
        for _ in range(3):
            ang, rr = rnd.uniform(0, 6.28), rnd.uniform(0, r * 0.45)
            glow_dot(ctx, x + math.cos(ang) * rr, y + math.sin(ang) * rr, r * 0.16, PROT_C, a * 0.8)
        if r >= 22:
            squiggle(ctx, x + r * 0.08, y + r * 0.18, r * 0.75, rnd.uniform(-0.5, 0.5),
                     RNA_C, a * 0.9, w=max(1.2, r * 0.06), t=t)


def icon_lungs(ctx, c, a):
    ctx.move_to(0, -110)
    ctx.line_to(0, -44)
    ctx.move_to(0, -44)
    ctx.curve_to(-10, -30, -24, -24, -34, -14)
    ctx.move_to(0, -44)
    ctx.curve_to(10, -30, 24, -24, 34, -14)
    gstroke(ctx, c, 3.2, a)
    for s in (-1, 1):
        ctx.move_to(s * 16, -36)
        ctx.curve_to(s * 64, -84, s * 118, -6, s * 110, 64)
        ctx.curve_to(s * 106, 104, s * 56, 108, s * 22, 88)
        ctx.curve_to(s * 12, 44, s * 10, 0, s * 16, -36)
        ctx.close_path()
        ctx.set_source_rgba(*c, 0.08 * a)
        ctx.fill_preserve()
        gstroke(ctx, c, 3.0, a)
        for k in range(3):
            ctx.move_to(s * 34, -14 + k * 4)
            ctx.curve_to(s * (50 + k * 8), 10 + k * 18, s * (66 + k * 6), 30 + k * 16,
                         s * (74 + k * 4), 52 + k * 12)
            gstroke(ctx, c, 1.4, a * 0.5, glow=0)


def icon_liver(ctx, c, a):
    ctx.move_to(-120, -30)
    ctx.curve_to(-70, -84, 70, -76, 124, -52)
    ctx.curve_to(112, 0, 46, 62, -16, 74)
    ctx.curve_to(-84, 76, -130, 26, -120, -30)
    ctx.close_path()
    ctx.set_source_rgba(*c, 0.08 * a)
    ctx.fill_preserve()
    gstroke(ctx, c, 3.0, a)
    ctx.move_to(10, -70)
    ctx.curve_to(0, -30, 6, 10, -10, 60)
    gstroke(ctx, c, 1.6, a * 0.55, glow=0)


def icon_brain(ctx, c, a):
    n = 160
    for i in range(n + 1):
        th = 2 * math.pi * i / n
        bump = 1 + 0.05 * math.sin(11 * th)
        px = math.cos(th) * 165 * bump
        py = math.sin(th) * 118 * bump * (0.8 if math.sin(th) > 0 else 1.0)
        ctx.move_to(px, py) if i == 0 else ctx.line_to(px, py)
    ctx.close_path()
    ctx.set_source_rgba(*c, 0.07 * a)
    ctx.fill_preserve()
    gstroke(ctx, c, 3.2, a)
    ctx.move_to(0, -116)
    ctx.curve_to(10, -60, -12, -20, 4, 30)
    gstroke(ctx, c, 2.0, a * 0.7, glow=0)
    rnd = random.Random(13)
    for _ in range(9):
        x0, y0 = rnd.uniform(-130, 120), rnd.uniform(-80, 50)
        if abs(x0) < 20:
            continue
        ctx.move_to(x0, y0)
        ctx.curve_to(x0 + 20, y0 - 22, x0 + 36, y0 + 18, x0 + 54, y0 - 4)
        gstroke(ctx, c, 1.6, a * 0.5, glow=0)
    ctx.move_to(40, 90)
    ctx.curve_to(46, 120, 40, 150, 30, 170)
    gstroke(ctx, c, 3.0, a)


def icon_flask(ctx, c, a, t=0.0):
    ctx.move_to(-26, -100)
    ctx.line_to(-26, -30)
    ctx.line_to(-86, 76)
    ctx.curve_to(-94, 92, -84, 100, -66, 100)
    ctx.line_to(66, 100)
    ctx.curve_to(84, 100, 94, 92, 86, 76)
    ctx.line_to(26, -30)
    ctx.line_to(26, -100)
    gstroke(ctx, c, 3.2, a)
    ctx.move_to(-40, -100)
    ctx.line_to(40, -100)
    gstroke(ctx, c, 3.4, a)
    ctx.move_to(-62, 40)
    ctx.curve_to(-20, 30, 20, 50, 62, 40)
    ctx.line_to(86, 76)
    ctx.curve_to(94, 92, 84, 100, 66, 100)
    ctx.line_to(-66, 100)
    ctx.curve_to(-84, 100, -94, 92, -86, 76)
    ctx.close_path()
    ctx.set_source_rgba(*c, 0.20 * a)
    ctx.fill()
    for k in range(3):
        ph = (t * 0.5 + k / 3) % 1
        ctx.arc(-20 + k * 20, 80 - ph * 90, 5 + 3 * k, 0, 2 * math.pi)
        gstroke(ctx, c, 1.6, a * (1 - ph), glow=0)


def icon_clipboard(ctx, c, a):
    rrect(ctx, -80, -96, 160, 196, 16)
    gstroke(ctx, c, 3.2, a)
    rrect(ctx, -36, -110, 72, 30, 10)
    gstroke(ctx, c, 3.0, a)
    for i, y in enumerate((-40, 0, 40)):
        ctx.move_to(-52, y)
        ctx.line_to(-42, y + 10)
        ctx.line_to(-26, y - 10)
        gstroke(ctx, c, 2.6, a)
        ctx.move_to(-10, y)
        ctx.line_to(54, y)
        gstroke(ctx, c, 2.2, a * 0.7, glow=0)


def icon_badge(ctx, c, a):
    n = 24
    for i in range(n + 1):
        th = 2 * math.pi * i / n
        rr = 92 if i % 2 == 0 else 80
        px, py = math.cos(th) * rr, math.sin(th) * rr
        ctx.move_to(px, py) if i == 0 else ctx.line_to(px, py)
    ctx.close_path()
    gstroke(ctx, c, 3.0, a)
    ctx.move_to(-34, 2)
    ctx.line_to(-8, 28)
    ctx.line_to(38, -24)
    gstroke(ctx, c, 6, a)


def icon_jar(ctx, c, a):
    rrect(ctx, -90, -20, 180, 110, 26)
    ctx.set_source_rgba(*c, 0.08 * a)
    ctx.fill_preserve()
    gstroke(ctx, c, 3.2, a)
    rrect(ctx, -80, -58, 160, 38, 12)
    gstroke(ctx, c, 3.0, a)
    ctx.move_to(-50, 30)
    ctx.line_to(50, 30)
    gstroke(ctx, c, 1.8, a * 0.6, glow=0)
    for k in range(3):
        ctx.arc(-24 + k * 24, 56, 7, 0, 2 * math.pi)
        gstroke(ctx, c, 1.6, a * 0.7, glow=0)


def icon_dropper(ctx, c, a):
    rrect(ctx, -40, -30, 80, 140, 18)
    ctx.set_source_rgba(*c, 0.08 * a)
    ctx.fill_preserve()
    gstroke(ctx, c, 3.2, a)
    rrect(ctx, -26, -70, 52, 40, 8)
    gstroke(ctx, c, 3.0, a)
    ctx.move_to(-18, -70)
    ctx.curve_to(-22, -120, 22, -120, 18, -70)
    gstroke(ctx, c, 3.0, a)
    ctx.move_to(-24, 40)
    ctx.line_to(24, 40)
    gstroke(ctx, c, 1.6, a * 0.6, glow=0)


def icon_warning(ctx, c, a):
    ctx.move_to(0, -90)
    ctx.line_to(96, 76)
    ctx.line_to(-96, 76)
    ctx.close_path()
    ctx.set_source_rgba(*c, 0.10 * a)
    ctx.fill_preserve()
    gstroke(ctx, c, 4.0, a)
    ctx.move_to(0, -34)
    ctx.line_to(0, 22)
    gstroke(ctx, c, 8, a)
    ctx.arc(0, 48, 6, 0, 2 * math.pi)
    gfill(ctx, c, a)


def icon_tube(ctx, c, a, fill=(0.85, 0.30, 0.28), level=0.55):
    ctx.move_to(-30, -100)
    ctx.line_to(-30, 70)
    ctx.arc_negative(0, 70, 30, math.pi, 0)
    ctx.line_to(30, -100)
    gstroke(ctx, c, 3.2, a)
    y0 = lerp(70, -100, level)
    ctx.move_to(-30, y0)
    ctx.line_to(-30, 70)
    ctx.arc_negative(0, 70, 30, math.pi, 0)
    ctx.line_to(30, y0)
    ctx.close_path()
    ctx.set_source_rgba(*fill, 0.45 * a)
    ctx.fill()
    rrect(ctx, -38, -122, 76, 26, 8)
    gstroke(ctx, c, 3.0, a)


def icon_cup(ctx, c, a):
    ctx.move_to(-70, -60)
    ctx.line_to(-56, 90)
    ctx.line_to(56, 90)
    ctx.line_to(70, -60)
    gstroke(ctx, c, 3.2, a)
    ctx.move_to(-62, 10)
    ctx.line_to(-56, 90)
    ctx.line_to(56, 90)
    ctx.line_to(62, 10)
    ctx.close_path()
    ctx.set_source_rgba(1.0, 0.86, 0.40, 0.30 * a)
    ctx.fill()
    rrect(ctx, -80, -84, 160, 24, 8)
    gstroke(ctx, c, 3.0, a)


def icon_centrifuge(ctx, c, a, t=0.0):
    ctx.arc(0, 0, 90, 0, 2 * math.pi)
    gstroke(ctx, c, 3.0, a)
    for k in range(6):
        ang = t * 2.5 + k * math.pi / 3
        ctx.save()
        ctx.rotate(ang)
        rrect(ctx, 30, -11, 50, 22, 10)
        ctx.restore()
        gstroke(ctx, c, 2.4, a)
    ctx.arc(0, 0, 12, 0, 2 * math.pi)
    gfill(ctx, c, a)


def icon_ruler(ctx, c, a):
    rrect(ctx, -110, -30, 220, 60, 8)
    gstroke(ctx, c, 3.0, a)
    for i in range(11):
        x = -95 + i * 19
        ctx.move_to(x, -30)
        ctx.line_to(x, -30 + (26 if i % 5 == 0 else 14))
        gstroke(ctx, c, 1.8, a * 0.8, glow=0)
    ctx.arc(0, 70, 16, 0, 2 * math.pi)
    gstroke(ctx, c, 2.4, a)
    ctx.arc(-40, 74, 9, 0, 2 * math.pi)
    gstroke(ctx, c, 2.0, a)
    ctx.arc(36, 72, 12, 0, 2 * math.pi)
    gstroke(ctx, c, 2.0, a)


def icon_grid(ctx, c, a):
    for r in range(3):
        for col in range(3):
            rrect(ctx, -84 + col * 60, -84 + r * 60, 48, 48, 10)
            gstroke(ctx, c, 2.4, a * (1.0 if (r + col) % 2 == 0 else 0.6))


def icon_envelope(ctx, c, a):
    rrect(ctx, -60, -40, 120, 80, 8)
    ctx.set_source_rgba(*c, 0.12 * a)
    ctx.fill_preserve()
    gstroke(ctx, c, 2.8, a)
    ctx.move_to(-60, -36)
    ctx.line_to(0, 6)
    ctx.line_to(60, -36)
    gstroke(ctx, c, 2.4, a)


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
    "title": "title", "bubble": "bubble", "scale": "scale", "mvb": "mvb",
    "types": "types", "misev": "misev", "cargo": "cargo",
    "valadi": "transfer", "message": "transfer", "health": "health",
    "tumor": "tumor", "hoshino": "tumor", "biopsy": "biopsy", "melo": "biopsy",
    "deliver": "deliver", "stem": "stem", "trials": "trials", "beauty": "beauty",
    "standard": "standard", "end": "end", "refs": "refs",
}
CELL_C = (0.62, 0.86, 1.00)
EV_C = (0.70, 1.00, 0.92)
TUMOR_C = (1.00, 0.52, 0.42)
LUNG_C = (0.55, 0.75, 1.00)
LIVER_C = (0.70, 0.95, 0.55)


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
        sg = [g for g in out if g["scene"] == sc["idx"]]
        for i, g in enumerate(sg):
            first = g["lines"][0]
            g["show_start"] = (sc["vis_start"] + 0.15) if i == 0 else first["start"] - 0.45
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


def heading(ctx, gt, a, zh, en, y=205):
    blit_reveal(ctx, text(zh, "serif", 48, WHITE, tracking=5), 960, y, ease_out(gt / 1.2), a)
    blit_reveal(ctx, text(en, "sans_light", 20, SOFT, tracking=7), 960, y + 52,
                ease_out((gt - 0.2) / 1.2), a)


def place(ctx, x, y, s=1.0):
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(s, s)


def icon_at(ctx, fn, x, y, s, a):
    """Draw an icon into a group so overlapping strokes fade as one."""
    if a <= 0.003:
        return
    ctx.push_group()
    place(ctx, x, y, s)
    fn()
    ctx.restore()
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(a)


def sub_state(g, t):
    """Index of current line in the group and time since it started."""
    idx = 0
    for i, l in enumerate(g["lines"]):
        if t >= l["start"] - 0.3:
            idx = i
    l = g["lines"][idx]
    return idx, t - l["start"], l["end"] - l["start"]


def line_dur(g, i=0):
    return g["lines"][i]["end"] - g["lines"][i]["start"]


def travel(ctx, p0, p1, p2, p3, n, gt, speed, r, c, a, seed=0, t=0.0, cargo=True):
    """Vesicles streaming along a cubic path, fading in and out."""
    for k in range(n):
        ph = (gt * speed + k / n) % 1
        x, y = cubic(p0, p1, p2, p3, ph)
        y += 8 * math.sin(t * 1.3 + k * 2.1)
        vesicle(ctx, x, y, r * (0.85 + 0.3 * ((k * 37) % 7) / 7), c,
                a * math.sin(ph * math.pi) ** 0.7, seed + k, cargo, t)


def draw_title(ctx, gt, g, a, acc, t):
    sx, sy, sr = 1350, 430, 160
    rx, ry, rr = 1730, 660, 110
    cell(ctx, sx, sy, sr, t, CELL_C, a * smooth(gt / 1.5), seed=1)
    cell(ctx, rx, ry, rr, t + 2, CELL_C, a * smooth((gt - 0.6) / 1.5), seed=2)
    k = smooth((gt - 1.6) / 1.5)
    travel(ctx, (sx + sr * 0.8, sy + sr * 0.4), (sx + 330, sy + 40), (rx - 230, ry - 160),
           (rx - rr * 0.8, ry - rr * 0.45), 6, gt, 0.16, 17, EV_C, a * k, 3, t)
    rnd = random.Random(8)
    for i in range(10):
        ang = rnd.uniform(math.radians(150), math.radians(320))
        ph = (gt * rnd.uniform(0.05, 0.09) + rnd.random()) % 1
        d = sr + 20 + ph * 300
        vesicle(ctx, sx + math.cos(ang) * d, sy + math.sin(ang) * d, rnd.uniform(8, 16),
                EV_C, a * k * math.sin(ph * math.pi) * 0.8, i, False, t)
    cx = 600
    blit_reveal(ctx, text("细胞外囊泡", "serif_bold", 140, WHITE, tracking=12, shadow=0.6),
                cx, 380, ease_out((gt - 0.3) / 1.8), a)
    blit_reveal(ctx, text("与外泌体：细胞之间的“快递包裹”", "serif_light", 48, (0.90, 0.95, 0.98),
                          tracking=3), cx, 525, ease_out((gt - 1.2) / 1.6), a)
    kk = ease_io((gt - 1.8) / 1.4)
    if kk > 0:
        ctx.move_to(cx - 330 * kk, 600)
        ctx.line_to(cx + 330 * kk, 600)
        gstroke(ctx, acc, 1.6, a * 0.9, glow=0.6)
    blit_reveal(ctx, text("EXTRACELLULAR VESICLES  ·  EXOSOMES", "sans_light", 26, SOFT,
                          tracking=8), cx, 650, ease_out((gt - 2.2) / 1.6), a)


def draw_bubble(ctx, gt, g, a, acc, t):
    cx, cy, r = 960, 470, 200
    cell(ctx, cx, cy, r, t, CELL_C, a * smooth(gt / 1.0), seed=4)
    for k in range(20):
        ang = 2 * math.pi * k / 20 + 0.13 * math.sin(k * 3.1)
        ph = (gt * 0.10 + (k * 0.618) % 1) % 1
        d = r + 6 + ease_out(ph) * 280
        size = 9 + (k * 7) % 11
        vesicle(ctx, cx + math.cos(ang) * d, cy + math.sin(ang) * d * 0.82, size, EV_C,
                a * smooth(gt / 1.2) * math.sin(ph * math.pi) ** 0.6, k, size > 14, t)
    dur = line_dur(g)
    label_pair(ctx, 300, 470, "细胞外囊泡", "Extracellular vesicles (EVs)", a, 46, 24,
               reveal=ease_out((gt - 0.6) / 1.2))
    label_pair(ctx, 1630, 470, "膜包裹的小泡泡", "Membrane-bound bubbles", a, 38, 22,
               zc=EV_C, reveal=ease_out((gt - dur * 0.35) / 1.2))
    blit_reveal(ctx, text("几乎所有细胞都会释放  ·  released by almost all cells", "sans_light", 28,
                          (0.92, 0.90, 0.85), tracking=2), 960, 770,
                ease_out((gt - dur * 0.65) / 1.2), a)


def draw_scale(ctx, gt, g, a, acc, t):
    ccx, ccy, cr = 560, 500, 220
    k0 = smooth(gt / 1.0)
    cell(ctx, ccx, ccy, cr, t, CELL_C, a * k0, seed=5)
    label_pair(ctx, ccx, ccy + cr + 62, "细胞  约10微米以上", "Cell: ~10 µm and up", a * k0, 34, 22)
    dx, dy = ccx + cr + 18, ccy - 90
    k1 = smooth((gt - 0.8) / 0.8)
    glow_dot(ctx, dx, dy, 16, EV_C, a * k1)
    ctx.arc(dx, dy, 2.6, 0, 2 * math.pi)
    gfill(ctx, WHITE, a * k1)
    zx, zy, zr = 1390, 450, 200
    k2 = ease_out((gt - 1.4) / 1.2)
    if k2 > 0:
        for s in (-1, 1):
            ang = math.atan2(zy - dy, zx - dx) + s * math.pi / 2
            ctx.move_to(dx, dy)
            ctx.line_to(zx + math.cos(ang) * zr * k2, zy + math.sin(ang) * zr * k2)
            gstroke(ctx, EV_C, 1.2, a * 0.45 * k2, glow=0)
        ctx.arc(zx, zy, zr * k2, 0, 2 * math.pi)
        ctx.set_source_rgba(0.02, 0.05, 0.08, 0.55 * a)
        ctx.fill_preserve()
        gstroke(ctx, EV_C, 2.0, a * k2, glow=0.6)
        vesicle(ctx, zx, zy - 10, 110 * k2, EV_C, a * k2, 6, True, t)
        bx = zx - 70
        ctx.move_to(bx, zy + 150)
        ctx.line_to(bx + 140 * k2, zy + 150)
        gstroke(ctx, WHITE, 3, a * k2, glow=0)
        blit(ctx, text("≈ 100 nm", "sans_light", 22, WHITE), zx, zy + 178, a * k2)
    label_pair(ctx, zx, zy + zr + 72, "外泌体  约30–150纳米", "Exosome: ~30–150 nm", a * k2, 34, 22,
               zc=EV_C)
    dur = line_dur(g)
    blit_reveal(ctx, text("小上百倍  ·  100× + smaller", "serif", 40, acc, tracking=3), 960, 196,
                ease_out((gt - dur * 0.7) / 1.0), a)


def draw_mvb(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    p = clamp(gt / max(1.0, dur + 0.3))
    s_form, s_move, s_rel = smooth(p / 0.32), smooth((p - 0.36) / 0.26), smooth((p - 0.64) / 0.3)
    mx = lerp(720, 1190, ease_io(s_move))
    my, mr = 440, 150
    gap = 70 * s_rel
    memx = lambda y: 1345 + 26 * math.sin(y / 170 + 0.6)
    for (y0, y1) in ((170, my - gap), (my + gap, 700)):
        for off, w, al in ((0, 3.0, 1.0), (14, 1.3, 0.45)):
            for i in range(41):
                y = lerp(y0, y1, i / 40)
                ctx.move_to(memx(y) + off, y) if i == 0 else ctx.line_to(memx(y) + off, y)
            gstroke(ctx, CELL_C, w, a * al, glow=1.0 if off == 0 else 0)
    blit(ctx, text("细胞内  INSIDE", "sans_light", 22, SOFT, tracking=3), 560, 200, a)
    blit(ctx, text("细胞外  OUTSIDE", "sans_light", 22, SOFT, tracking=3), 1650, 200, a)
    glow_dot(ctx, 470, 620, 90, CELL_C, 0.10 * a)
    ka = smooth(gt / 0.8)
    open_ang = math.asin(clamp(gap / mr, 0, 0.95)) if gap > 0 else 0
    ctx.new_path()
    ctx.arc(mx, my, mr, open_ang, 2 * math.pi - open_ang)
    if open_ang == 0:
        ctx.close_path()
    ctx.set_source_rgba(*acc, 0.06 * a * ka)
    ctx.fill_preserve()
    gstroke(ctx, acc, 3.0, a * ka)
    rnd = random.Random(31)
    for i in range(8):
        ang, rr = rnd.uniform(0, 6.28), rnd.uniform(22, 96)
        rel = (math.cos(ang) * rr, math.sin(ang) * rr)
        app = smooth((s_form - i * 0.1) / 0.3)
        out = ease_out(clamp((s_rel - 0.1 - i * 0.04) / 0.8))
        x = mx + rel[0] + out * (240 + i * 35)
        y = my + rel[1] * (1 + out * 1.6) + 6 * math.sin(t + i)
        vesicle(ctx, x, y, 21, EV_C, a * app, i, False, t)
    label_pair(ctx, mx, my + mr + 60, "多囊泡体", "Multivesicular body (MVB)", a * ka * (1 - s_rel), 32, 20,
               zc=acc)
    label_pair(ctx, 1660, 620, "外泌体", "Exosomes", a * s_rel, 36, 22, zc=EV_C)
    steps = (("① 内部形成", "Form inside", s_form), ("② 运往细胞膜", "Move to membrane", s_move),
             ("③ 融合释放", "Fuse & release", s_rel))
    for i, (zh, en, k) in enumerate(steps):
        on = 0.35 + 0.65 * k
        label_pair(ctx, 560 + i * 400, 772, zh, en, a * on, 30, 18,
                   zc=lerp3(SOFT, WHITE, k), zkey="sans_med")


def draw_types(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "细胞外囊泡家族", "THE EV FAMILY")
    starts = (0.2, dur * 0.22, dur * 0.62)
    items = (("外泌体", "Exosomes", "约30–150 nm · 经多囊泡体", "~30–150 nm · via MVBs"),
             ("微囊泡", "Microvesicles", "细胞膜直接出芽 · 通常更大", "bud off the membrane · larger"),
             ("凋亡小体", "Apoptotic bodies", "细胞凋亡时产生 · 最大", "from dying cells · largest"))
    for i, (zh, en, d1, d2) in enumerate(items):
        k = ease_out((gt - starts[i]) / 0.9)
        if k <= 0:
            continue
        x, y = 960 + (i - 1) * 470, 540 + (1 - k) * 30
        glass_panel(ctx, x - 205, y - 230, 410, 470, 28, a * k)
        ia = a * k
        ix, iy = x, y - 70
        if i == 0:
            ctx.arc(ix, iy, 80, 0, 2 * math.pi)
            ctx.set_source_rgba(*acc, 0.05 * ia)
            ctx.fill_preserve()
            gstroke(ctx, acc, 2.4, ia)
            for j, (ox, oy) in enumerate(((-30, -20), (22, -32), (8, 22), (-26, 34), (40, 14))):
                vesicle(ctx, ix + ox, iy + oy, 13, EV_C, ia, j, False, t)
            for j in range(3):
                ph = (gt * 0.3 + j / 3) % 1
                vesicle(ctx, ix + 95 + ph * 80, iy - 30 + j * 30, 11, EV_C, ia * math.sin(ph * math.pi), j,
                        False, t)
        elif i == 1:
            ctx.move_to(ix - 150, iy + 80)
            ctx.curve_to(ix - 60, iy + 80, ix - 60, iy + 30, ix - 40, iy + 10)
            ctx.move_to(ix + 40, iy + 10)
            ctx.curve_to(ix + 60, iy + 30, ix + 60, iy + 80, ix + 150, iy + 80)
            gstroke(ctx, CELL_C, 3.0, ia)
            bud = 0.5 + 0.5 * math.sin(gt * 1.2)
            vesicle(ctx, ix, iy - 20 - bud * 30, 44, EV_C, ia, 9, True, t)
            blit(ctx, text("细胞膜", "sans_light", 18, SOFT), ix - 110, iy + 108, ia)
        else:
            for j, (ox, oy, rr) in enumerate(((-30, -10, 52), (42, -40, 38), (36, 40, 34),
                                              (-60, 52, 26), (78, 8, 22))):
                jitter = 5 * math.sin(t * 0.9 + j)
                vesicle(ctx, ix + ox + jitter, iy + oy, rr, (0.95, 0.80, 0.70), ia, 20 + j, j == 0, t)
        label_pair(ctx, x, y + 75, zh, en, ia, 40, 22, zc=WHITE if i else EV_C)
        label_pair(ctx, x, y + 165, d1, d2, ia * 0.9, 22, 17, zkey="sans", zc=SOFT, ec=SOFT)


def draw_misev(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    cx, cy = 960, 420
    k = ease_io(gt / 1.4)
    w = 380 * k
    if w > 1:
        ctx.move_to(cx - w, cy)
        ctx.curve_to(cx - w, cy - 230 * k, cx + w, cy - 230 * k, cx + w, cy)
        n = 6
        for i in range(n):
            x0 = cx + w - 2 * w * i / n
            x1 = cx + w - 2 * w * (i + 1) / n
            ctx.curve_to(x0 - (x0 - x1) * 0.2, cy - 34, x1 + (x0 - x1) * 0.2, cy - 34, x1, cy)
        ctx.close_path()
        ctx.set_source_rgba(*acc, 0.10 * a)
        ctx.fill_preserve()
        gstroke(ctx, acc, 3.2, a)
        ctx.move_to(cx, cy - 175 * k)
        ctx.line_to(cx, cy - 210 * k)
        gstroke(ctx, acc, 3.2, a)
        ctx.move_to(cx, cy - 20)
        ctx.line_to(cx, cy + 320 * k)
        gstroke(ctx, acc, 3.0, a * 0.7)
        ctx.arc_negative(cx - 24, cy + 320 * k, 24, 0, math.pi)
        gstroke(ctx, acc, 3.0, a * 0.7 * k)
    blit_reveal(ctx, text("细胞外囊泡  EV", "serif_bold", 54, WHITE, tracking=4), cx, cy - 92,
                ease_out((gt - 0.9) / 1.0), a)
    for i, (dx, r, c, zh) in enumerate(((-250, 26, EV_C, "外泌体"), (-110, 46, EV_C, "微囊泡"),
                                        (150, 72, (0.95, 0.80, 0.70), "凋亡小体"))):
        kk = smooth((gt - 0.4 - 0.25 * i) / 0.8)
        vesicle(ctx, cx + dx + (dx > 0) * 80, cy + 130 + 6 * math.sin(t + i), r, c, a * kk, 40 + i,
                r > 30, t)
        blit(ctx, text(zh, "sans_light", 22, SOFT), cx + dx + (dx > 0) * 80, cy + 230, a * kk * 0.9)
    blit_reveal(ctx, text("大小重叠，难以区分  ·  overlapping, hard to separate", "sans_light", 26,
                          (0.92, 0.90, 0.85), tracking=2), cx, 210, ease_out((gt - 0.4) / 1.0), a)
    kb = ease_out((gt - dur * 0.45) / 1.0)
    if kb > 0:
        bx, by = 1490, 420
        glass_panel(ctx, bx - 150, by - 70, 300, 140, 22, a * kb, acc, 0.5)
        label_pair(ctx, bx, by - 18, "MISEV2023", "统一用总称  ·  umbrella term", a * kb, 34, 20,
                   zkey="sans_med", zc=acc)


def draw_cargo(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    cx, cy, R = 720, 480, 250
    k = ease_out(gt / 1.2)
    g0 = cairo.RadialGradient(cx - 60, cy - 80, 20, cx, cy, R)
    g0.add_color_stop_rgba(0, 1, 1, 1, 0.09 * a * k)
    g0.add_color_stop_rgba(1, *EV_C, 0.05 * a * k)
    ctx.arc(cx, cy, R, 0, 2 * math.pi)
    ctx.set_source(g0)
    ctx.fill()
    kl = smooth((gt - dur * 0.25) / 0.8)
    kp = smooth((gt - dur * 0.05) / 0.8)
    kr = smooth((gt - dur * 0.45) / 0.8)
    lip = lerp3(SOFT, (1.0, 0.92, 0.75), kl)
    prot_angles = [0.3, 1.25, 2.1, 3.0, 3.9, 4.75, 5.6]
    n = 84
    for i in range(n):
        ang = 2 * math.pi * i / n + t * 0.02
        if any(abs(((ang - pa + math.pi) % (2 * math.pi)) - math.pi) < 0.11 for pa in prot_angles):
            continue
        ca, sa = math.cos(ang), math.sin(ang)
        for (rh, r1, r2) in ((R, R - 7, R - 22), (R - 46, R - 39, R - 24)):
            ctx.arc(cx + ca * rh, cy + sa * rh, 5.2, 0, 2 * math.pi)
            gfill(ctx, lip, a * k * (0.55 + 0.45 * kl))
            for off in (-0.012, 0.012):
                ctx.move_to(cx + math.cos(ang + off) * r1, cy + math.sin(ang + off) * r1)
                ctx.line_to(cx + math.cos(ang + off) * r2, cy + math.sin(ang + off) * r2)
                gstroke(ctx, lip, 1.3, a * k * 0.5, glow=0)
    for j, pa in enumerate(prot_angles):
        ctx.save()
        ctx.translate(cx + math.cos(pa) * (R - 20), cy + math.sin(pa) * (R - 20))
        ctx.rotate(pa + math.pi / 2)
        rrect(ctx, -15, -40, 30, 72, 13)
        ctx.restore()
        ctx.set_source_rgba(*PROT_C, 0.30 * a * k * (0.4 + 0.6 * kp))
        ctx.fill_preserve()
        gstroke(ctx, PROT_C, 2.2, a * k * (0.4 + 0.6 * kp), glow=kp)
    rnd = random.Random(17)
    for j in range(7):
        ang, rr = rnd.uniform(0, 6.28), rnd.uniform(30, 150)
        x, y = cx + math.cos(ang) * rr + 6 * math.sin(t * 0.7 + j), cy + math.sin(ang) * rr
        if j < 4:
            for (ox, oy, s) in ((0, 0, 12), (12, 6, 9), (-8, 10, 8)):
                ctx.arc(x + ox, y + oy, s, 0, 2 * math.pi)
                ctx.set_source_rgba(*PROT_C, 0.28 * a * k * (0.4 + 0.6 * kp))
                ctx.fill()
    for j in range(6):
        ang, rr = rnd.uniform(0, 6.28), rnd.uniform(20, 160)
        squiggle(ctx, cx + math.cos(ang) * rr, cy + math.sin(ang) * rr, rnd.uniform(50, 80),
                 rnd.uniform(0, 3.14), RNA_C, a * k * (0.25 + 0.75 * kr), 2.6, t + j, 2 + j % 2)
    rows = (("蛋白质", "Proteins", PROT_C, kp, (cx + math.cos(5.6) * R, cy + math.sin(5.6) * R)),
            ("脂质", "Lipids (the membrane)", lip, kl, (cx + R, cy + 40)),
            ("RNA  如微小RNA", "RNA, e.g. microRNA", RNA_C, kr, (cx + 110, cy + 90)))
    for i, (zh, en, c, kk, (px, py)) in enumerate(rows):
        ly = 320 + i * 160
        lx = 1290
        if kk <= 0:
            continue
        ctx.move_to(px, py)
        ctx.line_to(lerp(px, lx - 40, kk), lerp(py, ly, kk))
        gstroke(ctx, c, 1.3, a * 0.6 * kk, glow=0)
        glow_dot(ctx, lx - 40, ly, 18, c, a * kk)
        tz = text(zh, "serif", 42, c)
        te = text(en, "sans_light", 24, SOFT, tracking=1)
        blit(ctx, tz, lx + tz.tw / 2 - 29, ly - 14, a * kk)
        blit(ctx, te, lx + te.tw / 2 - 17, ly + 32, a * kk)


def draw_transfer(ctx, gt, g, a, acc, t):
    sub, st, sd = sub_state(g, t)
    lx, rx, cy, r = 470, 1450, 480, 185
    k = smooth(gt / 1.0)
    cycle = 3.6
    ph = (gt % cycle) / cycle
    arrive = smooth((ph - 0.72) / 0.12) * (1 - smooth((ph - 0.95) / 0.05))
    cell(ctx, lx, cy, r, t, CELL_C, a * k, seed=11)
    rc = lerp3(CELL_C, (1.0, 0.85, 0.65), arrive * 0.6)
    cell(ctx, rx, cy, r, t + 1, rc, a * k, seed=12)
    glow_dot(ctx, rx, cy, r * 1.1, (1.0, 0.85, 0.6), 0.18 * arrive * a)
    p0, p1, p2, p3 = (lx + r * 0.6, cy - 40), (lx + 420, cy - 260), (rx - 420, cy - 260), (rx - r * 0.55, cy - 30)
    vk = smooth(ph / 0.1) * (1 - smooth((ph - 0.74) / 0.06))
    vx, vy = cubic(p0, p1, p2, p3, ease_io(clamp(ph / 0.78)))
    env = smooth((st + 0.2) / 0.6) if sub == 1 else 0.0
    vesicle(ctx, vx, vy, 34, EV_C, a * k * vk * (1 - env), 3, True, t)
    if env > 0:
        place(ctx, vx, vy, 0.65)
        icon_envelope(ctx, (1.0, 0.88, 0.65), a * k * vk * env)
        ctx.restore()
    for j in range(4):
        rel = smooth((ph - 0.74 - j * 0.03) / 0.12) * (1 - smooth((ph - 0.94) / 0.06))
        ang = j * 1.6 + 0.4
        squiggle(ctx, rx - r * 0.45 + math.cos(ang) * 70 * rel, cy - 20 + math.sin(ang) * 60 * rel, 46,
                 ang, RNA_C, a * rel, 2.4, t)
    for j in range(6):
        pk = smooth((ph - 0.8 - j * 0.02) / 0.1) * (1 - smooth((ph - 0.95) / 0.05))
        ang = j * 1.05
        glow_dot(ctx, rx + math.cos(ang) * 95, cy + 30 + math.sin(ang) * 70, 12, PROT_C, a * pk)
    label_pair(ctx, lx, cy + r + 60, "发出信息的细胞", "Sending cell", a * k, 32, 20)
    label_pair(ctx, rx, cy + r + 60, "接收信息的细胞", "Receiving cell", a * k, 32, 20)
    if sub == 0:
        label_pair(ctx, 960, 205, "RNA 被送进另一个细胞", "RNA delivered into another cell — and it still works",
                   a, 42, 22, reveal=ease_out((st - 0.4) / 1.2))
    a1 = smooth((st + 0.2) / 0.6) if sub == 1 else 0.0
    label_pair(ctx, 960, 205, "细胞之间的“信件”", "A letter between cells", a * a1, 42, 22)


def draw_health(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    for i in range(2):
        k = ease_out((gt - 0.2 - (dur * 0.45) * i) / 0.9)
        if k <= 0:
            continue
        x, y = 960 + (i - 0.5) * 760, 480 + (1 - k) * 30
        glass_panel(ctx, x - 350, y - 260, 700, 520, 30, a * k)
        ia = a * k
        if i == 0:
            cell(ctx, x - 170, y - 40, 80, t, CELL_C, ia, seed=21, nucleus=True)
            ix, iy = x + 150, y - 40
            cell(ctx, ix, iy, 95, t, (0.80, 0.85, 1.0), ia, seed=22, spiky=1.0)
            travel(ctx, (x - 95, y - 60), (x - 20, y - 150), (x + 40, y - 120), (ix - 90, iy - 30), 4, gt,
                   0.3, 13, EV_C, ia, 50, t, False)
            for j in range(3):
                ph = (gt * 0.5 + j / 3) % 1
                ctx.arc(ix, iy, 100 + ph * 80, 0, 2 * math.pi)
                gstroke(ctx, (0.80, 0.85, 1.0), 1.6, ia * (1 - ph) * 0.5, glow=0)
            label_pair(ctx, x, y + 150, "免疫信号传递", "Immune signaling", ia, 40, 22)
        else:
            close = smooth((gt - dur * 0.5) / max(1.0, dur * 0.6))
            for row in range(2):
                for col in range(8):
                    cx_ = x - 280 + col * 80
                    cy_ = y - 10 + row * 64
                    gap_amt = 1 - close if col in (3, 4) else 0
                    if gap_amt > 0.98:
                        continue
                    s = 1 - gap_amt
                    rrect(ctx, cx_ - 34 * s, cy_ - 26 * s, 68 * s, 52 * s, 12 * s + 0.1)
                    ctx.set_source_rgba(*CELL_C, 0.10 * ia)
                    ctx.fill_preserve()
                    gstroke(ctx, CELL_C, 2.0, ia * (0.5 + 0.5 * s), glow=0.4)
            for j in range(5):
                ph = (gt * 0.32 + j / 5) % 1
                vx = x - 40 + 80 * math.sin(j * 2.3) * (1 - ph)
                vy = lerp(y - 200, y + 10, ease_out(ph))
                vesicle(ctx, vx, vy, 12, EV_C, ia * math.sin(ph * math.pi), j, False, t)
            label_pair(ctx, x, y + 150, "帮助组织修复", "Tissue repair", ia, 40, 22)


def draw_tumor(ctx, gt, g, a, acc, t):
    sub, st, sd = sub_state(g, t)
    tx, ty = 470, 480
    k = smooth(gt / 1.0)
    cell(ctx, tx, ty, 190, t, TUMOR_C, a * k, seed=31, spiky=1.0)
    label_pair(ctx, tx, ty + 255, "肿瘤细胞", "Tumor cell", a * k, 34, 20, zc=TUMOR_C)
    hk = smooth((st + 0.2) / 1.0) if sub == 1 else 0.0
    gen = (1 - hk) * k
    for j in range(12):
        ang = math.radians(-60 + j * 11)
        ph = (gt * 0.12 + (j * 0.618) % 1) % 1
        d = 200 + ease_out(ph) * 700
        vesicle(ctx, tx + math.cos(ang) * d, ty + math.sin(ang) * d * 0.7, 14, TUMOR_C,
                a * gen * math.sin(ph * math.pi), j, False, t)
    if sub == 0:
        blit_reveal(ctx, text("为癌细胞扩散“铺路”", "serif", 46, WHITE, tracking=3), 1300, 470,
                    ease_out((st - 0.8) / 1.2), a)
        blit_reveal(ctx, text("PAVING THE WAY FOR SPREAD", "sans_light", 22, SOFT, tracking=6), 1300, 530,
                    ease_out((st - 1.0) / 1.2), a)
    if hk <= 0:
        return
    targets = ((1500, 320, LUNG_C, "肺  Lung", "整合素 α6β4 / α6β1", icon_lungs, 0.0),
               (1500, 690, LIVER_C, "肝  Liver", "整合素 αvβ5", icon_liver, sd * 0.45))
    for (ox, oy, c, zh, sub_zh, icon, delay) in targets:
        kk = smooth((st - 0.3 - delay * 0.3) / 0.9)
        icon_at(ctx, lambda: icon(ctx, c, 1), ox, oy, 0.9, a * kk)
        label_pair(ctx, ox + 230, oy - 16, zh, sub_zh, a * kk, 34, 20, zc=c, ec=SOFT)
        p0, p3 = (tx + 175, ty + (oy - ty) * 0.3), (ox - 110, oy)
        p1, p2 = (tx + 450, p0[1] - 60), (ox - 380, oy)
        for j in range(4):
            ph = (gt * 0.22 + j / 4) % 1
            x, y = cubic(p0, p1, p2, p3, ease_io(ph))
            vesicle(ctx, x, y, 18, TUMOR_C, a * kk * math.sin(ph * math.pi), j, False, t)
            for q in range(3):
                qa = q * 2.1 + t
                ctx.move_to(x + math.cos(qa) * 18, y + math.sin(qa) * 18)
                ctx.line_to(x + math.cos(qa) * 27, y + math.sin(qa) * 27)
                gstroke(ctx, c, 3.0, a * kk * math.sin(ph * math.pi), glow=0.6)
    blit(ctx, text("小鼠实验  ·  IN MICE", "sans_light", 22, acc, tracking=4), 960, 200, a * hk)


def draw_biopsy(ctx, gt, g, a, acc, t):
    sub, st, sd = sub_state(g, t)
    heading(ctx, gt, a, "液体活检", "LIQUID BIOPSY")
    m = smooth((st + 0.2) / 1.0) if sub == 1 else 0.0
    k1 = ease_out((gt - 0.5) / 0.9)
    k2 = ease_out((gt - 1.0) / 0.9)
    dim = 1 - 0.5 * m
    icon_at(ctx, lambda: icon_tube(ctx, WHITE, 1), 470, 520, 1.05, a * k1 * dim)
    label_pair(ctx, 470, 700, "血液", "Blood", a * k1 * dim, 32, 20)
    icon_at(ctx, lambda: icon_cup(ctx, WHITE, 1), 740, 540, 0.95, a * k2 * dim)
    label_pair(ctx, 740, 700, "尿液", "Urine", a * k2 * dim, 32, 20)
    mx, my, mr = 1330, 480, 200
    km = ease_out((gt - 1.6) / 1.0)
    if km <= 0:
        return
    ctx.move_to(mx + mr * 0.72, my - mr * 0.72)
    ctx.line_to(mx + mr * 1.1, my - mr * 1.1)
    gstroke(ctx, WHITE, 12, a * km, glow=0.3)
    ctx.arc(mx, my, mr, 0, 2 * math.pi)
    ctx.set_source_rgba(0.02, 0.05, 0.09, 0.5 * a * km)
    ctx.fill_preserve()
    gstroke(ctx, WHITE, 3.0, a * km)
    ctx.save()
    ctx.arc(mx, my, mr - 4, 0, 2 * math.pi)
    ctx.clip()
    rnd = random.Random(44)
    for j in range(9):
        x = mx + rnd.uniform(-150, 150) + 10 * math.sin(t * 0.6 + j)
        y = my + rnd.uniform(-140, 140) + 8 * math.cos(t * 0.5 + j)
        vesicle(ctx, x, y, rnd.uniform(14, 26), EV_C, a * km * (1 - 0.7 * m), j, True, t)
    if m > 0:
        vesicle(ctx, mx, my, 92 * m, EV_C, a * m, 7, True, t)
        for q in range(8):
            qa = q * math.pi / 4 + t * 0.15
            bx, by = mx + math.cos(qa) * 92 * m, my + math.sin(qa) * 92 * m
            ctx.move_to(bx, by)
            ctx.line_to(bx + math.cos(qa) * 22, by + math.sin(qa) * 22)
            gstroke(ctx, PROT_C, 2.6, a * m)
            glow_dot(ctx, bx + math.cos(qa) * 28, by + math.sin(qa) * 28, 12, PROT_C, a * m)
    ctx.restore()
    for i, (x, y) in enumerate(((560, 440), (840, 440))):
        ctx.move_to(x + 70, y)
        ctx.line_to(mx - mr - 20, my - 40 + i * 30)
        gstroke(ctx, SOFT, 1.2, a * km * 0.5 * dim, glow=0)
    blit(ctx, text("囊泡带着来源细胞的“身份信息”", "sans_light", 26, SOFT, tracking=1), mx, my + mr + 50,
         a * km * (1 - m))
    if m > 0:
        label_pair(ctx, mx, my + mr + 52, "GPC1 阳性外泌体：提示早期胰腺癌？", "GPC1+ exosomes: early pancreatic cancer?",
                   a * m, 32, 20, zc=PROT_C)
        kc = ease_out((st - sd * 0.55) / 0.9)
        if kc > 0:
            x, y = 605, 335
            glass_panel(ctx, x - 230, y - 44, 460, 88, 20, a * kc, (1.0, 0.70, 0.45), 0.7)
            blit(ctx, text("后续结果不一 · 仍需验证", "sans_med", 28, (1.0, 0.80, 0.60)), x, y - 12, a * kc)
            blit(ctx, text("later studies mixed · needs validation", "sans_light", 18, SOFT, tracking=1),
                 x, y + 22, a * kc)


def draw_deliver(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "送药的“快递车”", "A DRUG-DELIVERY VEHICLE")
    k = ease_out(gt / 1.2)
    y0 = 560
    for off in (-58, 58):
        for i in range(61):
            x = lerp(180, 1260, i / 60)
            y = y0 + off + 16 * math.sin(x / 140)
            ctx.move_to(x, y) if i == 0 else ctx.line_to(x, y)
        gstroke(ctx, (0.95, 0.45, 0.42), 2.2, a * k * 0.7, glow=0.5)
    blit(ctx, text("血管  blood vessel", "sans_light", 20, SOFT, tracking=2), 360, y0 + 100, a * k)
    bx, by = 1520, 500
    kb = ease_out((gt - 0.6) / 1.0)
    ph = (gt % 4.0) / 4.0
    arrive = smooth((ph - 0.78) / 0.1) * (1 - smooth((ph - 0.95) / 0.05))
    icon_at(ctx, lambda: icon_brain(ctx, lerp3((0.90, 0.80, 1.0), (1.0, 0.85, 0.65), arrive), 1), bx, by,
            1.05, a * kb)
    glow_dot(ctx, bx, by, 220, (1.0, 0.85, 0.65), 0.20 * arrive * a)
    label_pair(ctx, bx, by + 215, "小鼠大脑", "Mouse brain", a * kb, 32, 20)
    tag_k = smooth((gt - dur * 0.42) / 0.8)
    px = lerp(220, bx - 150, ease_io(clamp(ph / 0.82)))
    py = y0 + 16 * math.sin(px / 140) if px < 1260 else lerp(y0 + 16 * math.sin(9), by, (px - 1260) / (bx - 150 - 1260))
    va = a * k * smooth(ph / 0.06) * (1 - smooth((ph - 0.82) / 0.06))
    vesicle(ctx, px, py, 36, EV_C, va, 5, False, t)
    for j in range(2):
        squiggle(ctx, px - 6 + j * 10, py - 8 + j * 16, 32, 0.3 + j, RNA_C, va, 2.4, t)
    if tag_k > 0:
        fx, fy = px + 26, py - 26
        ctx.move_to(fx, fy)
        ctx.line_to(fx + 16, fy - 40)
        gstroke(ctx, acc, 2.4, va * tag_k)
        ctx.move_to(fx + 16, fy - 40)
        ctx.line_to(fx + 46, fy - 34)
        ctx.line_to(fx + 22, fy - 20)
        ctx.close_path()
        gfill(ctx, acc, va * tag_k)
    kl = ease_out((gt - dur * 0.45) / 1.0)
    label_pair(ctx, 560, 360, "导航标签", "Homing tag", a * kl, 34, 20, zc=acc)
    label_pair(ctx, 960, 360, "小干扰RNA", "siRNA cargo", a * kl, 34, 20, zc=RNA_C)


def draw_stem(ctx, gt, g, a, acc, t):
    sx, sy = 520, 470
    k = smooth(gt / 1.0)
    for j in range(5):
        ang = t * 0.6 + j * 1.256
        glow_dot(ctx, sx + math.cos(ang) * 230, sy + math.sin(ang) * 200, 14, (1.0, 0.95, 0.75), a * k * 0.7)
    cell(ctx, sx, sy, 170, t, (0.95, 0.88, 0.62), a * k, seed=61)
    label_pair(ctx, sx, sy + 240, "干细胞", "Stem cell", a * k, 34, 20, zc=(0.98, 0.90, 0.66))
    heal = smooth((gt - 1.0) / 3.0)
    for row in range(3):
        for col in range(5):
            x = 1180 + col * 96
            y = 360 + row * 96
            hk = smooth(heal * 2.2 - ((col + row) % 4) * 0.3)
            rrect(ctx, x - 40, y - 40, 80, 80, 16)
            ctx.set_source_rgba(*CELL_C, (0.04 + 0.12 * hk) * a * k)
            ctx.fill_preserve()
            gstroke(ctx, lerp3(SOFT, CELL_C, hk), 2.0, a * k * (0.4 + 0.6 * hk), glow=hk)
    travel(ctx, (sx + 170, sy - 20), (sx + 360, sy - 160), (960, sy - 140), (1140, sy - 30), 6, gt, 0.22,
           14, EV_C, a * k, 70, t, False)
    label_pair(ctx, 1372, 690, "组织再生（研究中）", "Tissue regeneration (under study)", a * k, 34, 20)
    blit_reveal(ctx, text("干细胞来源的囊泡  ·  stem-cell-derived EVs", "sans_light", 28, (0.92, 0.90, 0.85),
                          tracking=2), 960, 205, ease_out((gt - 0.6) / 1.2), a)


def draw_trials(ctx, gt, g, a, acc, t):
    heading(ctx, gt, a, "大多数仍在研究阶段", "MOSTLY STILL IN RESEARCH")
    stages = (("实验室研究", "Lab research", lambda: icon_flask(ctx, acc, 1, t)),
              ("临床试验", "Clinical trials", lambda: icon_clipboard(ctx, acc, 1)),
              ("获批治疗", "Approved therapy", lambda: icon_badge(ctx, SOFT, 1)))
    xs = (520, 960, 1400)
    y = 500
    prog = ease_io((gt - 0.8) / 2.2)
    ctx.move_to(xs[0], y + 190)
    ctx.line_to(xs[2], y + 190)
    gstroke(ctx, SOFT, 2.0, a * 0.35, glow=0)
    px = lerp(xs[0], lerp(xs[1], xs[2], 0.28), prog)
    ctx.move_to(xs[0], y + 190)
    ctx.line_to(px, y + 190)
    gstroke(ctx, acc, 4.0, a)
    glow_dot(ctx, px, y + 190, 30, acc, a * smooth(prog * 4))
    for i, (zh, en, fn) in enumerate(stages):
        kk = ease_out((gt - 0.3 - 0.3 * i) / 0.9)
        dimk = 0.45 if i == 2 else 1.0
        glass_panel(ctx, xs[i] - 160, y - 160, 320, 300, 26, a * kk * dimk)
        icon_at(ctx, fn, xs[i], y - 40, 0.75, a * kk * dimk)
        label_pair(ctx, xs[i], y + 80, zh, en, a * kk * dimk, 32, 18)
        ctx.arc(xs[i], y + 190, 8, 0, 2 * math.pi)
        gfill(ctx, acc if i < 2 else SOFT, a * kk * (1 if i < 2 else 0.5))
    blit(ctx, text("多数尚未到达  ·  most aren't here yet", "sans_light", 22, SOFT, tracking=2), xs[2], y + 232,
         a * smooth((gt - 2.6) / 0.8))


def draw_beauty(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    k = ease_out(gt / 1.0)
    icon_at(ctx, lambda: icon_jar(ctx, (1.0, 0.85, 0.80), 1), 560, 520, 1.25, a * k)
    icon_at(ctx, lambda: icon_dropper(ctx, (1.0, 0.85, 0.80), 1), 800, 470, 1.15, a * k)
    blit(ctx, text("“EXOSOME”", "sans_light", 22, (1.0, 0.85, 0.80), tracking=5), 560, 690, a * k)
    kw = ease_out((gt - dur * 0.45) / 0.7)
    wob = 1 + 0.03 * math.sin(t * 4) * kw
    icon_at(ctx, lambda: icon_warning(ctx, (1.0, 0.66, 0.40), 1), 1000, 300, 0.75 * wob, a * kw)
    x = 1400
    blit_reveal(ctx, text("“外泌体”美容 / 抗衰老", "serif", 52, WHITE, tracking=2), x, 380,
                ease_out((gt - 0.4) / 1.2), a)
    blit_reveal(ctx, text("\"Exosome\" beauty & anti-aging", "sans_light", 28, SOFT, tracking=1), x, 445,
                ease_out((gt - 0.6) / 1.2), a)
    if kw > 0:
        glass_panel(ctx, x - 270, 500, 540, 100, 22, a * kw, (1.0, 0.62, 0.40), 0.75)
        blit(ctx, text("很多未获监管批准", "sans_med", 36, (1.0, 0.76, 0.58), tracking=2), x, 535, a * kw)
        blit(ctx, text("Many are not approved by regulators", "sans_light", 20, SOFT, tracking=1), x, 575,
             a * kw)
    blit_reveal(ctx, text("多加小心  ·  be cautious", "serif", 38, acc, tracking=3), x, 670,
                ease_out((gt - dur * 0.75) / 1.0), a)


def draw_standard(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "仍待解决的难题", "OPEN CHALLENGES")
    items = (("分离", "Isolate", lambda: icon_centrifuge(ctx, acc, 1, t)),
             ("测量", "Measure", lambda: icon_ruler(ctx, acc, 1)),
             ("统一标准", "Standardize", lambda: icon_grid(ctx, acc, 1)))
    for i, (zh, en, fn) in enumerate(items):
        kk = ease_out((gt - 0.5 - dur * 0.16 * i) / 0.9)
        if kk <= 0:
            continue
        x, y = 960 + (i - 1) * 440, 520 + (1 - kk) * 30
        glass_panel(ctx, x - 170, y - 190, 340, 380, 28, a * kk)
        icon_at(ctx, fn, x, y - 50, 0.95, a * kk)
        label_pair(ctx, x, y + 105, zh, en, a * kk, 42, 22)


def draw_end(ctx, gt, g, a, acc, t):
    line = g["lines"][0]
    rnd = random.Random(90)
    for i in range(16):
        x0, y0 = rnd.uniform(150, W - 150), rnd.uniform(150, H - 300)
        vesicle(ctx, x0 + 20 * math.sin(t * 0.3 + i), y0 - (t * 6 + i * 40) % 60, rnd.uniform(8, 24), EV_C,
                a * 0.35 * smooth(gt / 2), i, False, t)
    blit_reveal(ctx, text("一句话总结  ·  IN ONE SENTENCE", "sans_light", 24, acc, tracking=6), 960, 250,
                ease_out((gt - 0.2) / 1.2), a)
    blit_reveal(ctx, text("细胞之间的“快递包裹”", "serif", 92, WHITE, tracking=10), 960, 360,
                ease_out((gt - 0.5) / 1.8), a)
    blit_reveal(ctx, text("EVs: the parcels cells use to send messages.", "serif_light", 36,
                          (0.90, 0.95, 0.98), tracking=2), 960, 468, ease_out((gt - 1.3) / 1.6), a)
    kd = ease_out((t - line["start"] - 3.6) / 1.2)
    if kd > 0:
        y = 680 + (1 - kd) * 20
        glass_panel(ctx, 960 - 470, y - 85, 940, 170, 24, a * kd, acc, 0.45)
        blit(ctx, text("本视频仅供科普", "sans_med", 42, WHITE, tracking=4), 960, y - 22, a * kd)
        blit(ctx, text("For education only.", "sans_light", 26, SOFT, tracking=2), 960, y + 34, a * kd)


def draw_refs(ctx, gt, g, a, acc, t):
    blit_reveal(ctx, text("参考文献  ·  REFERENCES", "serif", 44, WHITE, tracking=4), 960, 120,
                ease_out(gt / 1.2), a)
    ctx.move_to(960 - 300, 172)
    ctx.line_to(960 + 300, 172)
    gstroke(ctx, acc, 1.2, a * ease_io((gt - 0.4) / 1.0), glow=0)
    x0, y = 230, 222
    for i, key in enumerate(REF_ORDER):
        r = REFS[key]
        kk = ease_out((gt - 0.6 - 0.18 * i) / 0.8)
        num = text(f"{i + 1}", "serif_light", 34, acc, shadow=0.3)
        blit(ctx, num, x0 - 40, y + 14, a * kk)
        tf = text(r["full"], "sans_light", 25, WHITE, max_w=1440, align="left", line_gap=1.3, shadow=0.4)
        td = text(f"doi: {r['doi']}   ·   PMID {r['pmid']}", "sans_light", 21, acc, tracking=1, shadow=0.4)
        pf, pd = int(25 * 0.7), int(21 * 0.7)
        blit(ctx, tf, x0 + tf.tw / 2 - pf, y + tf.th / 2 - pf, a * kk)
        y += tf.th - 2 * pf + 4
        blit(ctx, td, x0 + td.tw / 2 - pd, y + td.th / 2 - pd, a * kk)
        y += td.th - 2 * pd + 22
    blit(ctx, text("本视频仅供科普  ·  For education only", "sans", 22, SOFT, tracking=3), 960, 1030,
         a * smooth((gt - 1.6) / 1.0))


DRAWERS = {
    "title": draw_title, "bubble": draw_bubble, "scale": draw_scale, "mvb": draw_mvb,
    "types": draw_types, "misev": draw_misev, "cargo": draw_cargo, "transfer": draw_transfer,
    "health": draw_health, "tumor": draw_tumor, "biopsy": draw_biopsy, "deliver": draw_deliver,
    "stem": draw_stem, "trials": draw_trials, "beauty": draw_beauty, "standard": draw_standard,
    "end": draw_end, "refs": draw_refs,
}


def draw_cite(ctx, t):
    """Small citation line, top-right, while a line stating that finding is spoken."""
    lines = TL["lines"]
    for i, l in enumerate(lines):
        if not l.get("cite"):
            continue
        nxt = lines[i + 1]["start"] if i + 1 < len(lines) else DUR
        a0, b0 = l["start"] - 0.2, min(l["end"] + 0.9, nxt + 0.2)
        if not (a0 <= t <= b0):
            continue
        a = window(t, a0, b0, 0.45, 0.45)
        acc = palette_at(t)[4]
        tc = text(REFS[l["cite"]]["short"], "sans", 25, acc, tracking=1, shadow=0.6)
        tl = text("SOURCE  ·  研究出处", "sans_light", 16, SOFT, tracking=4, shadow=0.5)
        xr = W - 110
        pc, pl = int(25 * 0.7), int(16 * 0.7)
        blit(ctx, tl, xr - tl.tw / 2 + pl, 92, a)
        blit(ctx, tc, xr - tc.tw / 2 + pc, 126, a)
        x_left = xr - (tc.tw - 2 * pc) - 22
        ctx.move_to(x_left, 84)
        ctx.line_to(x_left, 142)
        ctx.set_source_rgba(*acc, 0.7 * a)
        ctx.set_line_width(2)
        ctx.stroke()


def draw_captions(ctx, t):
    lines = TL["lines"]
    for i, l in enumerate(lines):
        if l["cue"] in ("end", "refs"):
            continue
        nxt = lines[i + 1]["start"] if i + 1 < len(lines) else DUR
        a0, b0 = l["start"] - 0.12, min(l["end"] + 0.45, nxt - 0.12)
        if not (a0 <= t <= b0):
            continue
        a = window(t, a0, b0, 0.22, 0.22)
        rise = (1 - ease_out((t - a0) / 0.4)) * 10
        tz = text(l["zh"], "sans_med", 44, WHITE, tracking=1, shadow=0.85, max_w=1640)
        te = text(l["en"], "sans", 28, (0.90, 0.88, 0.84), tracking=1, shadow=0.85,
                  max_w=1640)
        ez, ee = int(44 * 0.7), int(28 * 0.7)
        bottom = H - 52
        ye = bottom - (te.th - 2 * ee) / 2 + rise
        yz = bottom - (te.th - 2 * ee) - 12 - (tz.th - 2 * ez) / 2 + rise
        blit(ctx, tz, W / 2, yz, a)
        blit(ctx, te, W / 2, ye, a)


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
    draw_cite(ctx, t)
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
