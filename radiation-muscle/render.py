"""Render the ionizing-radiation / skeletal-muscle explainer video frames and encode with ffmpeg.

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


# ---- radiation / muscle primitives ----------------------------------------
FIBER_C = (0.96, 0.58, 0.52)
GREY_C = (0.58, 0.56, 0.55)
SAT_C = (0.99, 0.86, 0.50)
RAY_C = (0.78, 0.72, 1.00)
ROS_C = (1.00, 0.48, 0.30)
DNA_A = (0.55, 0.86, 1.00)
DNA_B = (0.98, 0.62, 0.82)
VES_C = (0.96, 0.42, 0.42)
ENDO_C = (0.62, 0.86, 1.00)
FIB_C = (0.62, 0.95, 0.66)
COLL_C = (0.98, 0.86, 0.64)
IMM_C = (0.82, 0.86, 1.00)
O2_C = (0.55, 0.80, 1.00)


def wavy_line(ctx, x0, y0, x1, y1, amp, wl, phase=0.0, n=None):
    L = math.hypot(x1 - x0, y1 - y0)
    if L < 1:
        return
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    n = n or max(8, int(L / 6))
    for i in range(n + 1):
        s = L * i / n
        o = amp * math.sin(s / wl * 2 * math.pi + phase)
        px, py = x0 + ux * s - uy * o, y0 + uy * s + ux * o
        ctx.move_to(px, py) if i == 0 else ctx.line_to(px, py)


def wave_ray(ctx, x0, y0, x1, y1, prog, a, c=RAY_C, t=0.0, amp=14, wl=46, tail=0.55):
    """A photon-like wave packet travelling from (x0,y0) to (x1,y1)."""
    if prog <= 0 or a <= 0.003:
        return
    p = clamp(prog)
    s0 = clamp(p - tail)
    hx, hy = lerp(x0, x1, p), lerp(y0, y1, p)
    sx, sy = lerp(x0, x1, s0), lerp(y0, y1, s0)
    wavy_line(ctx, sx, sy, hx, hy, amp, wl, -t * 9)
    gstroke(ctx, c, 2.6, a, glow=1.2)
    if prog < 1.0:
        glow_dot(ctx, hx, hy, 34, c, a)


def spark(ctx, x, y, r, c, a, rot=0.0):
    if a <= 0.003:
        return
    glow_dot(ctx, x, y, r * 2.2, c, a * 0.7)
    for k in range(8):
        ang = rot + k * math.pi / 4
        rr = r * (1.0 if k % 2 == 0 else 0.55)
        ctx.move_to(x + math.cos(ang) * r * 0.25, y + math.sin(ang) * r * 0.25)
        ctx.line_to(x + math.cos(ang) * rr, y + math.sin(ang) * rr)
        gstroke(ctx, c, 2.0, a, glow=0.5)


def fiber_long(ctx, x0, x1, y, h, t, a, dmg=0.0, seed=0):
    """A myofiber seen lengthwise: rounded tube with striations and edge nuclei."""
    if a <= 0.003:
        return
    c = lerp3(FIBER_C, GREY_C, dmg * 0.7)
    rrect(ctx, x0, y - h / 2, x1 - x0, h, h / 2)
    g = cairo.LinearGradient(0, y - h / 2, 0, y + h / 2)
    g.add_color_stop_rgba(0, *c, 0.20 * a)
    g.add_color_stop_rgba(0.5, *c, 0.08 * a)
    g.add_color_stop_rgba(1, *c, 0.18 * a)
    ctx.set_source(g)
    ctx.fill_preserve()
    gstroke(ctx, c, 2.6, a, glow=0.8)
    rnd = random.Random(seed)
    x = x0 + h * 0.6
    while x < x1 - h * 0.6:
        broken = rnd.random() < dmg * 0.75
        wob = 2 * math.sin(x * 0.05 + t * 0.6)
        if not broken:
            ctx.move_to(x + wob, y - h * 0.40)
            ctx.line_to(x - wob, y + h * 0.40)
            gstroke(ctx, c, 1.4, a * 0.42, glow=0)
        x += 13
    for k in range(4):
        nx = lerp(x0 + h, x1 - h, (k + 0.3 + 0.4 * rnd.random()) / 4)
        ny = y + (h * 0.33 if k % 2 else -h * 0.33)
        ctx.save()
        ctx.translate(nx, ny)
        ctx.scale(1.0, 0.32)
        ctx.arc(0, 0, 15, 0, 2 * math.pi)
        ctx.restore()
        ctx.set_source_rgba(*c, 0.35 * a)
        ctx.fill()


def sat_cell(ctx, x, y, a, c=SAT_C, w=46, glow=1.0):
    """Satellite cell: a flattened cell hugging the fiber surface."""
    if a <= 0.003:
        return
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(1.0, 0.42)
    ctx.arc(0, 0, w, 0, 2 * math.pi)
    ctx.restore()
    ctx.set_source_rgba(*c, 0.22 * a)
    ctx.fill_preserve()
    gstroke(ctx, c, 2.2, a, glow=glow)
    glow_dot(ctx, x, y, w * 0.45, c, a * 0.8 * glow)


def helix(ctx, cx, cy, L, t, a, gap=0.0, amp=30, wl=150):
    """Horizontal DNA double helix with an optional break of width `gap`."""
    if a <= 0.003:
        return
    n = 160
    for strand, col in ((0.0, DNA_A), (math.pi, DNA_B)):
        segs = [[]]
        for i in range(n + 1):
            x = -L / 2 + L * i / n
            if abs(x) < gap / 2:
                if segs[-1]:
                    segs.append([])
                continue
            shift = (gap * 0.25 if x > 0 else -gap * 0.25) * (1 if strand == 0 else 0.6)
            y = math.sin(x / wl * 2 * math.pi + strand + t * 0.8) * amp
            segs[-1].append((cx + x + shift, cy + y))
        for s in segs:
            if len(s) < 2:
                continue
            ctx.move_to(*s[0])
            for p in s[1:]:
                ctx.line_to(*p)
            gstroke(ctx, col, 3.2, a, glow=0.9)
    x = -L / 2 + 10
    while x < L / 2 - 10:
        if abs(x) >= gap / 2 + 6:
            shift = (gap * 0.2 if x > 0 else -gap * 0.2)
            y1 = math.sin(x / wl * 2 * math.pi + t * 0.8) * amp
            y2 = math.sin(x / wl * 2 * math.pi + math.pi + t * 0.8) * amp
            ctx.move_to(cx + x + shift, cy + y1)
            ctx.line_to(cx + x + shift, cy + y2)
            gstroke(ctx, WHITE, 1.3, a * 0.35, glow=0)
        x += 16


def capillary_h(ctx, x0, x1, y, h, t, a, dead=0.0, seed=0, flow=True):
    """Capillary seen lengthwise: two walls lined with endothelial cells."""
    if a <= 0.003:
        return
    rnd = random.Random(seed)
    for side in (-1, 1):
        yy = y + side * h / 2
        ctx.move_to(x0, yy)
        ctx.line_to(x1, yy)
        gstroke(ctx, VES_C, 2.4, a * 0.85, glow=0.7)
    n = int((x1 - x0) / 74)
    for k in range(n):
        for side in (-1, 1):
            ex = x0 + 37 + k * 74
            ey = y + side * (h / 2 - 11)
            die = clamp(dead * 1.6 - rnd.random() * 0.9)
            if die > 0.95:
                for q in range(4):
                    ang = q * 1.57 + k
                    glow_dot(ctx, ex + math.cos(ang) * 18 * die, ey + math.sin(ang) * 6, 6,
                             GREY_C, a * 0.6 * (1.2 - die))
                continue
            sc = 1 - 0.45 * die
            ctx.save()
            ctx.translate(ex, ey)
            ctx.scale(sc, 0.34 * sc)
            ctx.arc(0, 0, 32, 0, 2 * math.pi)
            ctx.restore()
            ec = lerp3(ENDO_C, GREY_C, die)
            ctx.set_source_rgba(*ec, 0.18 * a)
            ctx.fill_preserve()
            gstroke(ctx, ec, 1.8, a, glow=0.4)
            glow_dot(ctx, ex, ey, 8, ec, a * 0.7)
    if flow:
        for k in range(7):
            ph = (t * 0.12 + k / 7) % 1
            rx = lerp(x0 + 20, x1 - 20, ph)
            ctx.save()
            ctx.translate(rx, y + 6 * math.sin(k * 2.0 + t))
            ctx.scale(1.0, 0.6)
            ctx.arc(0, 0, 13, 0, 2 * math.pi)
            ctx.restore()
            ctx.set_source_rgba(*VES_C, 0.45 * a * (1 - dead * 0.5))
            ctx.fill()


def spindle(ctx, x, y, L, rot, c, a, act=0.0):
    """Fibroblast: a spindle-shaped cell; `act` makes it brighter and bigger."""
    if a <= 0.003:
        return
    s = 1 + 0.25 * act
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    ctx.scale(s, s)
    ctx.move_to(-L / 2, 0)
    ctx.curve_to(-L / 4, -L * 0.17, L / 4, -L * 0.17, L / 2, 0)
    ctx.curve_to(L / 4, L * 0.17, -L / 4, L * 0.17, -L / 2, 0)
    ctx.close_path()
    ctx.restore()
    ctx.set_source_rgba(*c, (0.12 + 0.15 * act) * a)
    ctx.fill_preserve()
    gstroke(ctx, c, 2.0, a, glow=0.4 + act)
    glow_dot(ctx, x, y, L * 0.12, c, a * (0.6 + 0.4 * act))


def immune(ctx, x, y, r, t, a, seed=0):
    cell(ctx, x, y, r, t, IMM_C, a, seed=seed, nucleus=False, spiky=1.0, glow=0.6)
    glow_dot(ctx, x, y, r * 0.5, IMM_C, a * 0.5)


class Section:
    """Precomputed muscle cross-section layout (fibers, capillaries, niche cells)."""

    def __init__(self, R=300, s=82, seed=5):
        rnd = random.Random(seed)
        self.fibers, self.caps, self.fibros, self.sats = [], [], [], []
        rows = int(R / (s * 0.866)) + 1
        for r in range(-rows, rows + 1):
            for q in range(-rows - 1, rows + 2):
                x = q * s + (s / 2 if r % 2 else 0) + rnd.uniform(-6, 6)
                y = r * s * 0.866 + rnd.uniform(-6, 6)
                if math.hypot(x, y) < R - s * 0.45:
                    self.fibers.append((x, y, s * rnd.uniform(0.40, 0.47), rnd.randint(0, 999)))
        for (x, y, rr, sd) in self.fibers:
            ang = rnd.uniform(0, 6.28)
            if rnd.random() < 0.35:
                self.sats.append((x + math.cos(ang) * rr, y + math.sin(ang) * rr, ang))
            for k in range(2):
                a2 = math.pi / 6 + k * math.pi / 3
                cx, cy = x + math.cos(a2) * s * 0.58, y + math.sin(a2) * s * 0.58
                if math.hypot(cx, cy) < R - 20 and rnd.random() < 0.55:
                    (self.caps if rnd.random() < 0.7 else self.fibros).append(
                        (cx, cy, rnd.uniform(0, 6.28)))
        self.R = R

    def draw(self, ctx, cx, cy, t, a, dmg=0.0, scale=1.0, hi=None):
        """hi: optional dict of element -> highlight strength (fiber/cap/sat/fibro)."""
        if a <= 0.003:
            return
        hi = hi or {}
        ctx.save()
        ctx.translate(cx, cy)
        ctx.scale(scale, scale)
        R = self.R
        ctx.arc(0, 0, R + 18, 0, 2 * math.pi)
        ctx.set_source_rgba(*COLL_C, (0.03 + 0.10 * dmg) * a)
        ctx.fill_preserve()
        gstroke(ctx, COLL_C, 2.0 + 2 * dmg, a * (0.35 + 0.4 * dmg), glow=0.4)
        if dmg > 0:
            rnd = random.Random(77)
            for k in range(int(70 * dmg)):
                ang, rr = rnd.uniform(0, 6.28), rnd.uniform(20, R)
                x, y = math.cos(ang) * rr, math.sin(ang) * rr
                wavy_line(ctx, x - 22, y, x + 22, y + rnd.uniform(-10, 10), 3, 14, k)
                gstroke(ctx, COLL_C, 1.4, a * 0.5 * dmg, glow=0)
        fc = lerp3(FIBER_C, GREY_C, dmg * 0.6)
        fa = 1 + hi.get("fiber", 0)
        for (x, y, rr, sd) in self.fibers:
            blob_path(ctx, x, y, rr * (1 - 0.15 * dmg), t * 0.5, sd, amp=0.05)
            ctx.set_source_rgba(*fc, 0.12 * a * fa)
            ctx.fill_preserve()
            gstroke(ctx, fc, 2.0, min(1, a * 0.85 * fa), glow=0.4 * fa)
            glow_dot(ctx, x + rr * 0.55, y - rr * 0.4, 6, fc, a * 0.5)
        ka = 1 + hi.get("cap", 0)
        for i, (x, y, ph) in enumerate(self.caps):
            alive = 1 - dmg * (0.95 if i % 3 else 0.2)
            ctx.arc(x, y, 9, 0, 2 * math.pi)
            gstroke(ctx, VES_C, 2.0, min(1, a * alive * ka), glow=0.6 * ka)
            glow_dot(ctx, x, y, 5, VES_C, a * alive * 0.8)
        sa = 1 + hi.get("sat", 0)
        for (x, y, ang) in self.sats:
            ctx.save()
            ctx.translate(x, y)
            ctx.rotate(ang + math.pi / 2)
            ctx.scale(1.0, 0.45)
            ctx.arc(0, 0, 13, 0, 2 * math.pi)
            ctx.restore()
            sc = lerp3(SAT_C, GREY_C, dmg * 0.7)
            ctx.set_source_rgba(*sc, min(1, 0.7 * a * (1 - 0.5 * dmg) * sa))
            ctx.fill()
        ba = 1 + hi.get("fibro", 0)
        for (x, y, ph) in self.fibros:
            spindle(ctx, x, y, 34, ph, FIB_C, min(1, a * 0.8 * ba), act=dmg)
        ctx.restore()


SECTION = Section()


def icon_person(ctx, c, a, hl=None):
    ctx.arc(0, -150, 34, 0, 2 * math.pi)
    gstroke(ctx, c, 3.0, a)
    ctx.move_to(0, -112)
    ctx.line_to(0, 30)
    ctx.move_to(0, -80)
    ctx.line_to(-70, -10)
    ctx.move_to(0, -80)
    ctx.line_to(70, -10)
    ctx.move_to(0, 30)
    ctx.line_to(-46, 150)
    ctx.move_to(0, 30)
    ctx.line_to(46, 150)
    gstroke(ctx, c, 3.4, a)
    if hl:
        glow_dot(ctx, 0, -100, 70, hl, a * 0.55)
        glow_dot(ctx, 40, -50, 50, hl, a * 0.40)


def icon_mouse(ctx, c, a):
    ctx.save()
    ctx.scale(1.0, 0.62)
    ctx.arc(0, 0, 80, 0, 2 * math.pi)
    ctx.restore()
    ctx.set_source_rgba(*c, 0.08 * a)
    ctx.fill_preserve()
    gstroke(ctx, c, 3.0, a)
    ctx.arc(-58, -44, 22, 0, 2 * math.pi)
    gstroke(ctx, c, 2.6, a)
    glow_dot(ctx, -76, -8, 6, c, a)
    ctx.move_to(80, 10)
    ctx.curve_to(130, 30, 140, -40, 180, -20)
    gstroke(ctx, c, 2.6, a)


def icon_gauge(ctx, c, a, v=0.7):
    ctx.arc(0, 20, 80, math.pi, 2 * math.pi)
    gstroke(ctx, c, 3.0, a)
    ang = math.pi + v * math.pi
    ctx.move_to(0, 20)
    ctx.line_to(math.cos(ang) * 64, 20 + math.sin(ang) * 64)
    gstroke(ctx, c, 4.0, a)
    glow_dot(ctx, 0, 20, 12, c, a)


def icon_fractions(ctx, c, a):
    for k in range(5):
        rrect(ctx, -90 + k * 38, -50, 24, 100, 6)
        ctx.set_source_rgba(*c, 0.18 * a)
        ctx.fill_preserve()
        gstroke(ctx, c, 2.4, a)


def icon_target(ctx, c, a):
    for rr in (80, 52, 24):
        ctx.arc(0, 0, rr, 0, 2 * math.pi)
        gstroke(ctx, c, 2.4, a)
    glow_dot(ctx, 0, 0, 14, c, a)


def icon_clock(ctx, c, a, t=0.0):
    ctx.arc(0, 0, 80, 0, 2 * math.pi)
    gstroke(ctx, c, 3.0, a)
    for k in range(12):
        ang = k * math.pi / 6
        ctx.move_to(math.cos(ang) * 68, math.sin(ang) * 68)
        ctx.line_to(math.cos(ang) * 76, math.sin(ang) * 76)
        gstroke(ctx, c, 1.8, a * 0.7, glow=0)
    for L, sp in ((46, 0.08), (62, 0.9)):
        ang = t * sp - math.pi / 2
        ctx.move_to(0, 0)
        ctx.line_to(math.cos(ang) * L, math.sin(ang) * L)
        gstroke(ctx, c, 3.0, a)

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


GROUPS = {
    "hook": "hook", "title": "title", "ionize": "ionize", "dsb": "dsb", "ros": "ros",
    "fibers": "fibers", "beyond": "beyond", "vessel": "vessel", "hypoxia": "hypoxia",
    "fibrosis": "fibrosis", "remodel": "remodel", "clinic": "clinic", "cascade": "cascade",
    "whole": "whole", "directions": "directions", "reality": "reality", "end": "end", "refs": "refs",
}
PROT_C = (1.00, 0.76, 0.40)

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


def draw_hook(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    k = smooth(gt / 1.2)
    dmg = smooth((gt - 2.2) / 3.0)
    ys = [380 + i * 70 for i in range(6)]
    for i, y in enumerate(ys):
        x0 = 860 + 18 * math.sin(i * 1.7)
        fiber_long(ctx, x0, x0 + 860, y, 54, t, a * k, dmg * (0.4 + 0.6 * ((i * 37) % 5) / 4), seed=i)
    for i in range(3):
        p = (gt - 0.6 - i * 0.35) / 1.4
        wave_ray(ctx, 900 + i * 260, 150, 1060 + i * 260, 420, ease_io(p), a * (1 - smooth((gt - 2.6) / 0.8)),
                 t=t)
    if dmg > 0:
        rnd = random.Random(3)
        for j in range(28):
            x, y = rnd.uniform(880, 1700), rnd.uniform(400, 720)
            wavy_line(ctx, x - 40, y, x + 40, y + rnd.uniform(-8, 8), 4, 18, j)
            gstroke(ctx, COLL_C, 1.6, a * 0.55 * dmg, glow=0.3)
    blit_reveal(ctx, text("放疗之后很久……", "serif", 64, WHITE, tracking=4), 470, 420,
                ease_out((gt - 0.3) / 1.4), a)
    blit_reveal(ctx, text("LONG AFTER RADIOTHERAPY", "sans_light", 24, SOFT, tracking=7), 470, 490,
                ease_out((gt - 0.5) / 1.4), a)
    kq = ease_out((gt - dur * 0.55) / 1.0)
    blit_reveal(ctx, text("又僵 · 又弱", "serif_bold", 76, acc, tracking=10), 470, 620, kq, a)
    blit_reveal(ctx, text("STIFF  ·  WEAK", "sans_light", 24, SOFT, tracking=8), 470, 690, kq, a)
    blit(ctx, text("?", "serif_bold", 120, acc), 1300, 230, a * smooth((gt - dur * 0.85) / 0.6))


def draw_title(ctx, gt, g, a, acc, t):
    k = smooth(gt / 1.4)
    SECTION.draw(ctx, 1400, 470, t, a * k, dmg=0.0, scale=0.95)
    blit_reveal(ctx, text("辐射与骨骼肌", "serif_bold", 120, WHITE, tracking=12, shadow=0.6),
                600, 380, ease_out((gt - 0.2) / 1.8), a)
    blit_reveal(ctx, text("电离辐射如何损伤肌肉与它的微环境", "serif_light", 42, (0.92, 0.94, 0.98),
                          tracking=3), 600, 510, ease_out((gt - 1.0) / 1.6), a)
    kk = ease_io((gt - 1.6) / 1.4)
    if kk > 0:
        ctx.move_to(600 - 330 * kk, 580)
        ctx.line_to(600 + 330 * kk, 580)
        gstroke(ctx, acc, 1.6, a * 0.9, glow=0.6)
    blit_reveal(ctx, text("IONIZING RADIATION  ·  SKELETAL MUSCLE  ·  NICHE", "sans_light", 22, SOFT,
                          tracking=6), 600, 630, ease_out((gt - 2.0) / 1.6), a)
    blit(ctx, text("骨骼肌横截面  ·  muscle cross-section", "sans_light", 20, SOFT, tracking=2), 1400, 800,
         a * smooth((gt - 1.5) / 1.0))


def draw_ionize(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "高能射线把电子“打飞”", "KNOCKING ELECTRONS LOOSE")
    ax, ay = 1150, 540
    k = smooth(gt / 1.0)
    hit = dur * 0.45
    hk = smooth((gt - hit) / 0.4)
    glow_dot(ctx, ax, ay, 46, lerp3((1.0, 0.85, 0.6), ROS_C, hk), a * k)
    for i, rot in enumerate((0.3, -0.5, 1.4)):
        ctx.save()
        ctx.translate(ax, ay)
        ctx.rotate(rot)
        ctx.scale(1.0, 0.38)
        ctx.arc(0, 0, 190, 0, 2 * math.pi)
        ctx.restore()
        gstroke(ctx, SOFT, 1.4, a * k * 0.55, glow=0)
        ang = t * (0.9 + 0.3 * i) + i * 2.1
        ex, ey = math.cos(ang) * 190, math.sin(ang) * 190 * 0.38
        rx, ry = ex * math.cos(rot) - ey * math.sin(rot), ex * math.sin(rot) + ey * math.cos(rot)
        if i == 0 and hk > 0:
            fly = ease_out((gt - hit) / 2.2)
            rx, ry = rx + 520 * fly, ry - 260 * fly
        glow_dot(ctx, ax + rx, ay + ry, 22, DNA_A, a * k)
    wave_ray(ctx, 200, 760, ax - 20, ay + 10, ease_io((gt - 0.6) / (hit - 0.6)), a * (1 - hk), t=t)
    blit(ctx, text("+", "sans_med", 54, WHITE), ax, ay - 4, a * hk)
    label_pair(ctx, 400, 520, "X射线 / γ射线", "X-rays / gamma rays", a * smooth((gt - 0.6) / 0.8), 38, 22,
               zc=RAY_C)
    kr = ease_out((gt - hit - 0.4) / 1.0)
    label_pair(ctx, 1640, 300, "电子被打飞", "Electron ejected", a * kr, 34, 20, zc=DNA_A)
    label_pair(ctx, ax, ay + 240, "分子被“电离”", "The molecule is ionized", a * kr, 36, 22, zc=acc)


def draw_dsb(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "DNA 双链断裂", "DNA DOUBLE-STRAND BREAK")
    cx, cy = 960, 520
    k = smooth(gt / 1.0)
    hit = 1.4
    brk = ease_out((gt - hit) / 0.8)
    helix(ctx, cx, cy, 1300, t * 0.3, a * k, gap=110 * brk)
    wave_ray(ctx, cx - 300, 160, cx, cy - 10, ease_io((gt - 0.3) / (hit - 0.3)), a * (1 - brk), t=t)
    if brk > 0:
        spark(ctx, cx, cy, 46 * (1 - 0.5 * brk), ROS_C, a * (1 - smooth((gt - hit - 1.2) / 1.0)))
    resp = smooth((gt - dur * 0.45) / 1.2)
    if resp > 0:
        for j in range(10):
            side = -1 if j % 2 else 1
            ang = j * 0.7 + t * 0.5
            rr = 40 + 18 * math.sin(t * 1.1 + j)
            x = cx + side * (70 + 10 * (j % 3)) + math.cos(ang) * rr * (1 - 0.6 * resp)
            y = cy + math.sin(ang) * rr
            glow_dot(ctx, x, y, 18, PROT_C, a * resp)
        label_pair(ctx, cx, cy + 210, "细胞启动“损伤应答”", "Cells mount a DNA-damage response", a * resp, 38, 22,
                   zc=PROT_C)
    label_pair(ctx, cx + 420, cy - 150, "两条链同时断开", "Both strands broken", a * brk, 32, 20,
               zc=ROS_C)


def draw_ros(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "活性氧：持续的氧化损伤", "REACTIVE OXYGEN SPECIES")
    k = smooth(gt / 0.8)
    rnd = random.Random(21)
    pts = [(rnd.uniform(260, 1660), rnd.uniform(330, 720), rnd.uniform(0, 6.28)) for _ in range(34)]
    sweep = ease_io((gt - 0.2) / 1.6)
    wave_ray(ctx, 150, 520, 1780, 520, sweep, a * (1 - smooth((gt - 1.9) / 0.6)), t=t, amp=18)
    for i, (x, y, ph) in enumerate(pts):
        lit = smooth((sweep * 1700 + 150 - x) / 120)
        if lit < 1:
            ctx.arc(x, y, 9, 0, 2 * math.pi)
            gstroke(ctx, O2_C, 1.6, a * k * 0.6 * (1 - lit), glow=0)
            for s in (-1, 1):
                ctx.arc(x + s * 13, y - 9, 5, 0, 2 * math.pi)
                gstroke(ctx, O2_C, 1.2, a * k * 0.5 * (1 - lit), glow=0)
        if lit > 0:
            dx = 18 * math.sin(t * 0.7 + ph)
            spark(ctx, x + dx, y + 10 * math.cos(t * 0.6 + ph), 15 + 4 * math.sin(t * 3 + ph), ROS_C,
                  a * lit * (0.65 + 0.35 * math.sin(t * 2.5 + ph)), rot=t + ph)
    blit(ctx, text("H2O  →  ·OH  ·  H2O2  ·  O2·-", "sans_light", 28, SOFT, tracking=3), 960, 290,
         a * smooth((gt - 1.2) / 0.8))
    kb = ease_out((gt - dur * 0.45) / 1.0)
    if kb > 0:
        x0, x1, y = 460, 1460, 800
        ctx.move_to(x0, y)
        ctx.line_to(x1, y)
        gstroke(ctx, SOFT, 1.6, a * kb * 0.4, glow=0)
        ctx.move_to(x0, y)
        ctx.line_to(x0 + 70, y)
        gstroke(ctx, RAY_C, 6, a * kb)
        ctx.move_to(x0, y)
        ctx.line_to(lerp(x0, x1, kb), y)
        gstroke(ctx, ROS_C, 2.6, a * kb * 0.8, glow=0.6)
        blit(ctx, text("照射  exposure", "sans_light", 18, RAY_C), x0 + 35, y - 26, a * kb)
        blit(ctx, text("氧化损伤拖得更久  ·  oxidative injury persists", "sans_light", 22, ROS_C, tracking=1),
             lerp(x0, x1, 0.62), y - 28, a * kb)


def draw_fibers(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    k = smooth(gt / 1.0)
    dmg = smooth((gt - 1.0) / 2.0)
    sdim = smooth((gt - dur * 0.5) / 1.4)
    for i, y in enumerate((360, 500, 640)):
        fiber_long(ctx, 260, 1660, y, 96, t, a * k, dmg * (0.5 + 0.25 * i), seed=10 + i)
    for (x, y) in ((560, 312), (1180, 452), (860, 592), (1450, 592)):
        sat_cell(ctx, x, y, a * k * (1 - 0.55 * sdim), lerp3(SAT_C, GREY_C, sdim * 0.8), glow=1 - sdim)
        if sdim > 0:
            ctx.move_to(x - 14, y - 30)
            ctx.line_to(x + 14, y - 58)
            ctx.move_to(x + 14, y - 30)
            ctx.line_to(x - 14, y - 58)
            gstroke(ctx, ROS_C, 3.0, a * sdim, glow=0.5)
    label_pair(ctx, 400, 230, "肌纤维受伤", "Myofibers injured", a * smooth((gt - 1.0) / 0.8), 36, 20, zc=FIBER_C)
    label_pair(ctx, 1240, 230, "卫星细胞（肌肉干细胞）", "Satellite cells (muscle stem cells)", a * k, 36, 20,
               zc=SAT_C)
    kr = ease_out((gt - dur * 0.6) / 1.0)
    if kr > 0:
        x, y = 960, 790
        glass_panel(ctx, x - 300, y - 52, 600, 104, 22, a * kr, ROS_C, 0.6)
        blit(ctx, text("再生能力下降 ↓", "sans_med", 36, (1.0, 0.76, 0.60), tracking=2), x, y - 14, a * kr)
        blit(ctx, text("regeneration impaired", "sans_light", 20, SOFT, tracking=2), x, y + 26, a * kr)


def draw_beyond(ctx, gt, g, a, acc, t):
    heading(ctx, gt, a, "不只是肌肉细胞", "BEYOND THE FIBERS", y=190)
    k = smooth(gt / 1.0)
    z = lerp(1.6, 0.95, ease_io(gt / 2.0))
    cx, cy = 960, 540
    SECTION.draw(ctx, cx, cy, t, a * k, scale=z, hi={"cap": 0.6 * smooth((gt - 0.6) / 0.6),
                                                      "fibro": 0.6 * smooth((gt - 0.9) / 0.6)})
    kl = ease_out((gt - 1.0) / 0.9)
    for (lx, ly, zh, en, c) in ((420, 420, "微血管", "Microvessels", VES_C),
                                (1500, 420, "成纤维细胞", "Fibroblasts", FIB_C),
                                (1500, 680, "免疫细胞", "Immune cells", IMM_C),
                                (420, 680, "卫星细胞", "Satellite cells", SAT_C)):
        label_pair(ctx, lx, ly, zh, en, a * kl, 34, 20, zc=c)
    immune(ctx, cx + 230, cy + 170, 26, t, a * kl, seed=4)


def draw_vessel(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "微血管内皮：可能最先受伤", "MICROVASCULAR ENDOTHELIUM")
    k = smooth(gt / 1.0)
    dead = smooth((gt - dur * 0.45) / 2.2)
    capillary_h(ctx, 200, 1720, 470, 170, t, a * k, dead=dead, seed=3)
    for i in range(3):
        wave_ray(ctx, 420 + i * 420, 200, 560 + i * 420, 380, ease_io((gt - 0.8 - i * 0.3) / 1.2),
                 a * (1 - smooth((gt - 2.6) / 0.6)), t=t)
    label_pair(ctx, 960, 610, "血管内皮细胞", "Endothelial cells lining the vessel", a * k * (1 - dead), 32, 20,
               zc=ENDO_C)
    label_pair(ctx, 960, 610, "内皮细胞凋亡 → 早期关键环节", "Endothelial apoptosis: a key early step", a * dead,
               34, 20, zc=acc)
    kb = smooth((gt - dur * 0.35) / 0.8)
    glass_panel(ctx, 960 - 360, 680, 720, 80, 20, a * kb, (1.0, 0.75, 0.45), 0.6)
    blit(ctx, text("小鼠实验 · 肠道组织（不是肌肉）", "sans_med", 26, (1.0, 0.82, 0.62), tracking=1), 960, 706,
         a * kb)
    blit(ctx, text("IN MICE  ·  INTESTINE, NOT MUSCLE  ·  ANALOGY FOR MICROVASCULAR INJURY", "sans_light",
                   15, SOFT, tracking=2), 960, 738, a * kb)


def draw_hypoxia(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    k = smooth(gt / 0.8)
    loss = smooth((gt - 0.3) / max(1.5, dur * 0.6))
    rnd = random.Random(9)
    segs = []
    for i in range(7):
        y = 300 + i * 70
        xs = [200 + j * 190 for j in range(9)]
        for j in range(len(xs) - 1):
            segs.append((xs[j], y + rnd.uniform(-20, 20), xs[j + 1], y + rnd.uniform(-20, 20), rnd.random()))
    for (x0, y0, x1, y1, r) in segs:
        alive = 1 - smooth((loss - r * 0.75) / 0.25)
        ctx.move_to(x0, y0)
        ctx.curve_to(lerp(x0, x1, 0.4), y0 - 18, lerp(x0, x1, 0.6), y1 + 18, x1, y1)
        gstroke(ctx, lerp3(VES_C, GREY_C, 1 - alive), 2.4, a * k * (0.25 + 0.75 * alive), glow=0.6 * alive)
    for j in range(46):
        x, y = rnd.uniform(220, 1700), rnd.uniform(280, 740)
        o2 = 1 - loss * (0.85 if rnd.random() < 0.8 else 0.2)
        glow_dot(ctx, x + 6 * math.sin(t + j), y, 9, O2_C, a * k * 0.8 * o2)
    inf = smooth((gt - dur * 0.55) / 1.0)
    for j, (x, y) in enumerate(((520, 430), (980, 600), (1380, 380), (760, 700), (1560, 640))):
        immune(ctx, x, y, 30 + 4 * math.sin(t * 2 + j), t, a * inf, seed=30 + j)
        ctx.arc(x, y, 50 + 14 * ((t * 0.6 + j * 0.3) % 1), 0, 2 * math.pi)
        gstroke(ctx, ROS_C, 1.4, a * inf * 0.4, glow=0)
    for i, (zh, en, c, kk) in enumerate((("毛细血管减少", "Capillary loss", VES_C, ease_out((gt - 0.3) / 0.8)),
                                         ("局部缺氧", "Hypoxia", O2_C, ease_out((gt - dur * 0.3) / 0.8)),
                                         ("慢性炎症", "Chronic inflammation", IMM_C, inf))):
        label_pair(ctx, 520 + i * 440, 210, zh, en, a * kk, 36, 20, zc=c)


def draw_fibrosis(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    k = smooth(gt / 0.8)
    act = smooth((gt - 0.5) / 1.4)
    coll = smooth((gt - 1.4) / max(1.5, dur * 0.55))
    rnd = random.Random(12)
    fb = [(rnd.uniform(300, 1300), rnd.uniform(320, 720), rnd.uniform(0, 3.14)) for _ in range(7)]
    for j in range(int(120 * coll)):
        x, y = rnd.uniform(240, 1360), rnd.uniform(300, 740)
        ang = rnd.uniform(-0.4, 0.4)
        L = rnd.uniform(60, 140)
        wavy_line(ctx, x - math.cos(ang) * L / 2, y - math.sin(ang) * L / 2,
                  x + math.cos(ang) * L / 2, y + math.sin(ang) * L / 2, 4, 22, j)
        gstroke(ctx, COLL_C, 1.8, a * 0.55, glow=0.3)
    for j, (x, y, rot) in enumerate(fb):
        spindle(ctx, x, y, 110, rot + 0.1 * math.sin(t * 0.5 + j), FIB_C, a * k, act=act)
        if act > 0:
            for q in range(3):
                ph = (t * 0.4 + q / 3 + j * 0.13) % 1
                glow_dot(ctx, x + math.cos(q * 2 + j) * (40 + 60 * ph), y + math.sin(q * 2 + j) * (40 + 60 * ph),
                         9, acc, a * act * (1 - ph))
    blit(ctx, text("TGF-β 信号", "sans_med", 24, acc, tracking=2), 800, 270, a * act)
    gx, gy = 1600, 520
    rrect(ctx, gx - 30, gy - 200, 60, 400, 30)
    gstroke(ctx, SOFT, 2.0, a * k * 0.6, glow=0)
    lv = 0.1 + 0.85 * coll
    rrect(ctx, gx - 22, gy + 192 - 384 * lv, 44, 384 * lv, 22)
    ctx.set_source_rgba(*lerp3(FIB_C, ROS_C, coll), 0.55 * a * k)
    ctx.fill()
    label_pair(ctx, gx, gy + 260, "组织硬度", "Tissue stiffness", a * k, 30, 18)
    for i, (zh, en, c, kk) in enumerate((("成纤维细胞激活", "Fibroblasts activate", FIB_C, act),
                                         ("胶原沉积", "Collagen builds up", COLL_C, coll),
                                         ("纤维化", "Fibrosis", acc, smooth((gt - dur * 0.75) / 0.8)))):
        label_pair(ctx, 420 + i * 380, 830, zh, en, a * kk, 34, 20, zc=c)


def draw_remodel(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "晚期副作用的逻辑", "THE LOGIC OF LATE EFFECTS")
    x0, x1, y = 300, 1620, 530
    k = ease_out((gt - 0.3) / 0.8)
    prog = ease_io((gt - 1.0) / max(2.0, dur * 0.75))
    ctx.move_to(x0, y)
    ctx.line_to(x1, y)
    gstroke(ctx, SOFT, 2.0, a * k * 0.35, glow=0)
    px = lerp(x0, x1, prog)
    wavy_line(ctx, x0, y, px, y, 10, 60, -t * 2)
    gstroke(ctx, acc, 3.0, a * k, glow=0.8)
    glow_dot(ctx, px, y, 30, acc, a * k * smooth(prog * 5))
    stops = ((x0, "早期损伤", "Early damage", "数天–数周 · days–weeks", ROS_C, 0.0),
             ((x0 + x1) / 2, "漫长的组织重塑", "Long tissue remodeling", "数月–数年 · months–years", FIB_C, 0.4),
             (x1, "永久改变", "Lasting change", "", acc, 0.92))
    for (sx, zh, en, sub, c, th) in stops:
        kk = smooth((prog - th) / 0.08) if th > 0 else k
        ctx.arc(sx, y, 12, 0, 2 * math.pi)
        gfill(ctx, c, a * kk)
        label_pair(ctx, sx, y - 110, zh, en, a * kk, 36, 20, zc=c)
        if sub:
            blit(ctx, text(sub, "sans_light", 20, SOFT, tracking=1), sx, y + 60, a * kk)


def draw_clinic(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    k = smooth(gt / 1.0)
    icon_at(ctx, lambda: icon_person(ctx, WHITE, 1, hl=ROS_C), 470, 520, 1.25, a * k)
    blit(ctx, text("人类临床  ·  IN PATIENTS", "sans_light", 22, acc, tracking=4), 470, 790, a * k)
    blit_reveal(ctx, text("辐射纤维化综合征", "serif", 52, WHITE, tracking=3), 1220, 260,
                ease_out((gt - 0.3) / 1.2), a)
    blit_reveal(ctx, text("RADIATION FIBROSIS SYNDROME", "sans_light", 22, SOFT, tracking=6), 1220, 320,
                ease_out((gt - 0.5) / 1.2), a)
    for i, (zh, en) in enumerate((("肌肉僵硬", "Stiffness"), ("无力", "Weakness"), ("活动受限", "Limited movement"))):
        kk = ease_out((gt - dur * (0.4 + 0.15 * i)) / 0.8)
        y = 440 + i * 130 + (1 - kk) * 20
        glass_panel(ctx, 1220 - 260, y - 50, 520, 100, 22, a * kk)
        label_pair(ctx, 1220, y - 10, zh, en, a * kk, 36, 20, zc=acc)


CASCADE = (("DNA与氧化损伤", "DNA & oxidative injury", ROS_C, "DNA与"),
           ("细胞死亡或衰老", "Cell death or senescence", GREY_C, "细胞死亡"),
           ("干细胞微环境被打乱", "Stem-cell niche disrupted", SAT_C, "干细胞微"),
           ("血管与炎症重塑", "Vascular & inflammatory remodeling", VES_C, "血管与"),
           ("纤维化与长期功能障碍", "Fibrosis & lasting dysfunction", FIB_C, "纤维化与"))


def mini_icon(ctx, i, x, y, c, a, t):
    if i == 0:
        ctx.move_to(x - 40, y - 14)
        ctx.curve_to(x - 20, y - 34, x - 10, y + 6, x - 6, y - 4)
        ctx.move_to(x + 6, y + 4)
        ctx.curve_to(x + 10, y - 6, x + 20, y + 34, x + 40, y + 14)
        gstroke(ctx, DNA_A, 3, a)
        spark(ctx, x, y, 14, c, a, t)
    elif i == 1:
        cell(ctx, x, y, 34, t, c, a, seed=3, nucleus=False)
        for q in range(4):
            glow_dot(ctx, x + math.cos(q * 1.6) * 44, y + math.sin(q * 1.6) * 44, 7, c, a * 0.7)
    elif i == 2:
        sat_cell(ctx, x, y + 6, a, c, w=36)
        ctx.move_to(x - 30, y - 30)
        ctx.line_to(x + 30, y + 30)
        gstroke(ctx, ROS_C, 3, a)
    elif i == 3:
        ctx.move_to(x - 48, y - 16)
        ctx.line_to(x + 48, y - 16)
        ctx.move_to(x - 48, y + 16)
        ctx.line_to(x + 48, y + 16)
        gstroke(ctx, c, 3, a)
        immune(ctx, x + 6, y + 44, 14, t, a, seed=8)
    else:
        for q in range(4):
            wavy_line(ctx, x - 44, y - 24 + q * 16, x + 44, y - 24 + q * 16, 4, 20, q)
            gstroke(ctx, COLL_C, 2.0, a, glow=0.3)


def draw_cascade(ctx, gt, g, a, acc, t):
    line = g["lines"][0]
    dur = line["end"] - line["start"]
    say = SCENES[line["scene"]]["lines"][line["line"]].get("say", line["zh"])
    lt = t - line["start"]
    heading(ctx, gt, a, "底层逻辑：一条级联链", "THE UNDERLYING CASCADE", y=180)
    xs = [260 + i * 350 for i in range(5)]
    ys = [370, 500, 370, 500, 370]
    for i, (zh, en, c, key) in enumerate(CASCADE):
        on_t = dur * say.index(key) / len(say) - 0.3
        kk = ease_out((lt - on_t) / 0.7)
        x, y = xs[i], ys[i]
        if i > 0:
            pk = ease_io((lt - on_t + 0.4) / 0.6)
            if pk > 0:
                px, py = xs[i - 1] + 95, ys[i - 1]
                qx, qy = lerp(px, x - 95, pk), lerp(py, y, pk)
                ctx.move_to(px, py)
                ctx.line_to(qx, qy)
                gstroke(ctx, acc, 2.6, a * 0.8, glow=0.6)
                if pk > 0.9:
                    ang = math.atan2(y - py, x - 95 - px)
                    for s in (-1, 1):
                        ctx.move_to(qx, qy)
                        ctx.line_to(qx - 16 * math.cos(ang + s * 0.5), qy - 16 * math.sin(ang + s * 0.5))
                    gstroke(ctx, acc, 2.6, a * 0.8, glow=0.4)
        if kk <= 0:
            continue
        ctx.arc(x, y, 88, 0, 2 * math.pi)
        ctx.set_source_rgba(*c, 0.08 * a * kk)
        ctx.fill_preserve()
        gstroke(ctx, c, 2.4, a * kk, glow=0.8)
        mini_icon(ctx, i, x, y, c, a * kk, t)
        blit(ctx, text(f"{i + 1}", "serif_light", 26, c), x, y - 112, a * kk)
        label_pair(ctx, x, y + 124, zh, en, a * kk, 28, 17, zc=WHITE)


def draw_whole(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    k = ease_out(gt / 1.0)
    glass_panel(ctx, 200, 300, 560, 420, 28, a * k)
    fiber_long(ctx, 260, 700, 500, 90, t, a * k, 0.3, seed=2)
    label_pair(ctx, 480, 640, "只看一条肌纤维", "Just one fiber", a * k, 32, 20)
    ctx.move_to(450, 360)
    ctx.line_to(510, 420)
    ctx.move_to(510, 360)
    ctx.line_to(450, 420)
    gstroke(ctx, ROS_C, 4, a * smooth((gt - dur * 0.35) / 0.6), glow=0.5)
    kw = ease_out((gt - dur * 0.4) / 1.0)
    ctx.move_to(800, 510)
    ctx.line_to(lerp(800, 960, kw), 510)
    gstroke(ctx, acc, 3, a * kw, glow=0.6)
    SECTION.draw(ctx, 1350, 500, t, a * kw, dmg=0.25, scale=0.78,
                 hi={"cap": 0.5, "sat": 0.6, "fibro": 0.6})
    label_pair(ctx, 1350, 790, "看整个微环境", "The whole microenvironment", a * kw, 36, 22, zc=acc)


def draw_directions(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "候选研究方向", "CANDIDATE RESEARCH DIRECTIONS", y=190)
    items = (("氧化应激", "Oxidative stress", ROS_C), ("血管修复", "Vascular repair", VES_C),
             ("抗纤维化", "Anti-fibrosis", FIB_C), ("干细胞龛保护", "Stem-cell niche", SAT_C))
    for i, (zh, en, c) in enumerate(items):
        kk = ease_out((gt - 0.6 - dur * 0.17 * i) / 0.8)
        if kk <= 0:
            continue
        x, y = 960 + (i - 1.5) * 390, 510 + (1 - kk) * 30
        glass_panel(ctx, x - 165, y - 190, 330, 360, 26, a * kk, c, 0.35)
        ia = a * kk
        iy = y - 60
        if i == 0:
            spark(ctx, x, iy, 50, c, ia, t * 0.4)
        elif i == 1:
            capillary_h(ctx, x - 110, x + 110, iy, 70, t, ia, dead=0.0, seed=6)
        elif i == 2:
            for q in range(4):
                wavy_line(ctx, x - 80, iy - 36 + q * 24, x + 80, iy - 36 + q * 24, 5, 26, q)
                gstroke(ctx, COLL_C, 2.0, ia * 0.7, glow=0.3)
            ctx.arc(x, iy, 76, 0, 2 * math.pi)
            ctx.move_to(x - 54, iy + 54)
            ctx.line_to(x + 54, iy - 54)
            gstroke(ctx, c, 3.4, ia)
        else:
            fiber_long(ctx, x - 120, x + 120, iy + 26, 50, t, ia)
            sat_cell(ctx, x, iy, ia, c, w=40)
            ctx.arc(x, iy, 62, math.pi * 1.05, math.pi * 1.95)
            gstroke(ctx, c, 3.0, ia)
        label_pair(ctx, x, y + 90, zh, en, ia, 34, 20, zc=c)
    kd = smooth((gt - dur * 0.7) / 0.8)
    blit(ctx, text("这些是研究方向，不是医疗建议  ·  research directions, not medical advice", "sans_light", 24,
                   SOFT, tracking=1), 960, 770, a * kd)


def draw_reality(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "结果取决于条件", "CONTEXT CHANGES THE OUTCOME", y=180)
    items = (("剂量", "Dose", lambda: icon_gauge(ctx, acc, 1, 0.5 + 0.3 * math.sin(t))),
             ("分割方式", "Fractionation", lambda: icon_fractions(ctx, acc, 1)),
             ("照射范围", "Irradiated volume", lambda: icon_target(ctx, acc, 1)),
             ("伤后时间", "Time since exposure", lambda: icon_clock(ctx, acc, 1, t)))
    for i, (zh, en, fn) in enumerate(items):
        kk = ease_out((gt - 0.4 - dur * 0.09 * i) / 0.8)
        if kk <= 0:
            continue
        x, y = 960 + (i - 1.5) * 380, 380
        glass_panel(ctx, x - 160, y - 130, 320, 280, 24, a * kk)
        icon_at(ctx, fn, x, y - 30, 0.7, a * kk)
        label_pair(ctx, x, y + 70, zh, en, a * kk, 30, 18)
    km = ease_out((gt - dur * 0.55) / 0.9)
    if km > 0:
        icon_at(ctx, lambda: icon_mouse(ctx, (0.95, 0.85, 0.80), 1), 720, 640, 0.6, a * km)
        blit(ctx, text("≠", "serif_bold", 80, (1.0, 0.70, 0.50)), 960, 640, a * km)
        icon_at(ctx, lambda: icon_person(ctx, WHITE, 1), 1200, 640, 0.4, a * km)
        blit(ctx, text("动物 animal", "sans_light", 20, SOFT), 720, 715, a * km)
        blit(ctx, text("人体 human", "sans_light", 20, SOFT), 1200, 735, a * km)


def draw_end(ctx, gt, g, a, acc, t):
    line = g["lines"][0]
    SECTION.draw(ctx, 960, 480, t, a * 0.22 * smooth(gt / 2), dmg=0.3, scale=1.3)
    blit_reveal(ctx, text("一句话总结  ·  IN ONE SENTENCE", "sans_light", 24, acc, tracking=6), 960, 240,
                ease_out((gt - 0.2) / 1.2), a)
    blit_reveal(ctx, text("伤的是细胞，更是它的环境", "serif", 84, WHITE, tracking=8), 960, 350,
                ease_out((gt - 0.5) / 1.8), a)
    blit_reveal(ctx, text("Radiation injures not just muscle cells, but the niche they depend on.",
                          "serif_light", 34, (0.90, 0.95, 0.98), tracking=1), 960, 455,
                ease_out((gt - 1.3) / 1.6), a)
    kd = ease_out((t - line["start"] - 4.2) / 1.2)
    if kd > 0:
        y = 680 + (1 - kd) * 20
        glass_panel(ctx, 960 - 470, y - 85, 940, 170, 24, a * kd, acc, 0.45)
        blit(ctx, text("本视频仅供科普", "sans_med", 42, WHITE, tracking=4), 960, y - 22, a * kd)
        blit(ctx, text("For education only. Not medical advice.", "sans_light", 26, SOFT, tracking=2), 960,
             y + 34, a * kd)


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
    "hook": draw_hook, "title": draw_title, "ionize": draw_ionize, "dsb": draw_dsb, "ros": draw_ros,
    "fibers": draw_fibers, "beyond": draw_beyond, "vessel": draw_vessel, "hypoxia": draw_hypoxia,
    "fibrosis": draw_fibrosis, "remodel": draw_remodel, "clinic": draw_clinic, "cascade": draw_cascade,
    "whole": draw_whole, "directions": draw_directions, "reality": draw_reality, "end": draw_end,
    "refs": draw_refs,
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
