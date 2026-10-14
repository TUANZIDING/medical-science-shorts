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
    "title": "title", "dnaros": "dnaros", "fate": "fate", "fibers": "fibers", "reserve": "reserve",
    "fap": "fap", "secretome": "secretome", "scseq": "scseq", "tgfb": "tgfb", "mito": "mito",
    "monkey": "monkey", "clinic": "clinic", "cascade": "cascade", "directions": "directions",
    "end": "end", "refs": "refs",
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


SEN_C = (0.90, 0.78, 0.60)
MITO_C = (1.00, 0.66, 0.42)


def model_tag(ctx, zh, en, a, x=960, y=800, c=(1.0, 0.80, 0.60)):
    """Small pill naming the study model (mouse / rat / macaque) so animal data is always marked."""
    if a <= 0.003:
        return
    tz = text(zh, "sans_med", 22, c, tracking=1)
    te = text(en, "sans_light", 15, SOFT, tracking=3)
    w = max(tz.tw, te.tw) - 20
    glass_panel(ctx, x - w / 2, y - 34, w, 68, 18, a, c, 0.55)
    blit(ctx, tz, x, y - 10, a)
    blit(ctx, te, x, y + 16, a)


def icon_monkey(ctx, c, a):
    for s in (-1, 1):
        ctx.arc(s * 96, -6, 34, 0, 2 * math.pi)
        ctx.set_source_rgba(*c, 0.10 * a)
        ctx.fill_preserve()
        gstroke(ctx, c, 2.6, a)
    ctx.arc(0, 0, 90, 0, 2 * math.pi)
    ctx.set_source_rgba(*c, 0.08 * a)
    ctx.fill_preserve()
    gstroke(ctx, c, 3.0, a)
    for s in (-1, 1):
        ctx.save()
        ctx.translate(s * 30, -20)
        ctx.scale(1.0, 0.8)
        ctx.arc(0, 0, 30, 0, 2 * math.pi)
        ctx.restore()
        gstroke(ctx, c, 2.0, a * 0.8, glow=0)
        glow_dot(ctx, s * 30, -20, 7, c, a)
    ctx.save()
    ctx.translate(0, 38)
    ctx.scale(1.0, 0.62)
    ctx.arc(0, 0, 44, 0, 2 * math.pi)
    ctx.restore()
    gstroke(ctx, c, 2.2, a * 0.85, glow=0)
    ctx.move_to(-16, 46)
    ctx.curve_to(-6, 54, 6, 54, 16, 46)
    gstroke(ctx, c, 2.0, a * 0.8, glow=0)


def mitochondrion(ctx, x, y, w, h, c, a, swell=0.0, t=0.0):
    if a <= 0.003:
        return
    hh = h * (1 + 0.8 * swell)
    ww = w * (1 + 0.12 * swell)
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(ww / 2, hh / 2)
    ctx.arc(0, 0, 1, 0, 2 * math.pi)
    ctx.restore()
    ctx.set_source_rgba(*c, 0.10 * a)
    ctx.fill_preserve()
    gstroke(ctx, c, 3.0, a, glow=0.8)
    n = 7
    for k in range(n):
        cx = x - ww * 0.36 + k * ww * 0.72 / (n - 1)
        top = (k % 2 == 0)
        ln = hh * 0.62 * (1 - 0.7 * swell)
        y0 = y - hh * 0.40 if top else y + hh * 0.40
        y1 = y0 + (ln if top else -ln)
        ctx.move_to(cx, y0)
        ctx.curve_to(cx + 10, lerp(y0, y1, 0.4), cx - 10, lerp(y0, y1, 0.7), cx, y1)
        gstroke(ctx, c, 2.0, a * (0.75 - 0.45 * swell), glow=0)


def draw_dnaros(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "DNA损伤与活性氧", "DNA DAMAGE & REACTIVE OXYGEN SPECIES")
    cx, cy = 960, 510
    k = smooth(gt / 1.0)
    hit = 1.3
    brk = ease_out((gt - hit) / 0.8)
    helix(ctx, cx, cy, 1300, t * 0.3, a * k, gap=110 * brk)
    wave_ray(ctx, cx - 300, 160, cx, cy - 10, ease_io((gt - 0.3) / (hit - 0.3)), a * (1 - brk), t=t)
    if brk > 0:
        spark(ctx, cx, cy, 46 * (1 - 0.5 * brk), ROS_C, a * (1 - smooth((gt - hit - 1.2) / 1.0)))
    ros = smooth((gt - hit - 0.5) / 1.0)
    rnd = random.Random(5)
    for j in range(16):
        ang, d = rnd.uniform(0, 6.28), rnd.uniform(170, 330)
        x = cx + math.cos(ang + t * 0.04) * d * 2.2
        y = cy + math.sin(ang + t * 0.04) * d * 0.62
        if abs(y - cy) < 70:
            y += 90 if y > cy else -90
        spark(ctx, x, y, 12 + 3 * math.sin(t * 3 + j), ROS_C, a * ros * (0.6 + 0.4 * math.sin(t * 2 + j)),
              rot=t + j)
    label_pair(ctx, 330, 330, "活性氧 ROS", "Reactive oxygen species", a * ros, 34, 20, zc=ROS_C)
    label_pair(ctx, 1500, 360, "双链断裂", "Double-strand break", a * brk, 32, 20, zc=DNA_B)
    resp = smooth((gt - dur * 0.55) / 1.0)
    if resp > 0:
        for j in range(10):
            side = -1 if j % 2 else 1
            ang = j * 0.7 + t * 0.5
            rr = 40 + 18 * math.sin(t * 1.1 + j)
            x = cx + side * (70 + 10 * (j % 3)) + math.cos(ang) * rr * (1 - 0.6 * resp)
            y = cy + math.sin(ang) * rr
            glow_dot(ctx, x, y, 18, PROT_C, a * resp)
        label_pair(ctx, cx, cy + 200, "启动损伤应答", "DNA-damage response switched on", a * resp, 36, 22,
                   zc=PROT_C)


def draw_fate(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "细胞的两种命运", "TWO FATES OF A DAMAGED CELL", y=190)
    k = smooth(gt / 0.8)
    top = (960, 340)
    cell(ctx, *top, 70, t, ENDO_C, a * k, seed=2)
    spark(ctx, top[0] + 20, top[1] - 10, 16, ROS_C, a * k * 0.8, t)
    blit(ctx, text("受损细胞  damaged cell", "sans_light", 20, SOFT, tracking=1), top[0], top[1] + 100, a * k)
    L, R = (520, 530), (1400, 530)
    for i, (dst, start) in enumerate(((L, dur * 0.08), (R, dur * 0.42))):
        pk = ease_io((gt - start) / 0.8)
        if pk <= 0:
            continue
        sx, sy = top[0] + (-90 if i == 0 else 90), top[1] + 40
        ex, ey = dst[0] + (120 if i == 0 else -170), dst[1] - 90
        ctx.move_to(sx, sy)
        ctx.line_to(lerp(sx, ex, pk), lerp(sy, ey, pk))
        gstroke(ctx, acc, 2.4, a * 0.8, glow=0.5)
    die = smooth((gt - dur * 0.15) / 2.2)
    kl = smooth((gt - dur * 0.1) / 0.6)
    cell(ctx, L[0], L[1], 90, t, lerp3(ENDO_C, GREY_C, die), a * kl * (1 - 0.75 * die), seed=4, nucleus=die < 0.5)
    rnd = random.Random(8)
    for j in range(12):
        ang = rnd.uniform(0, 6.28)
        d = 60 + 110 * die * rnd.uniform(0.6, 1.0)
        glow_dot(ctx, L[0] + math.cos(ang) * d, L[1] + math.sin(ang) * d, rnd.uniform(8, 14), GREY_C,
                 a * kl * die * 0.8)
    label_pair(ctx, L[0], L[1] + 150, "扛不住：细胞死亡", "Can't cope: cell death", a * kl, 34, 20, zc=GREY_C)
    kr = smooth((gt - dur * 0.45) / 0.8)
    cell(ctx, R[0], R[1], 120 + 10 * kr, t, SEN_C, a * kr, seed=6, glow=0.6)
    sasp = smooth((gt - dur * 0.62) / 0.8)
    for j in range(14):
        ph = (gt * 0.18 + j / 14) % 1
        ang = j * 2 * math.pi / 14 + 0.3
        d = 140 + ph * 230
        c = ROS_C if j % 2 else FIB_C
        glow_dot(ctx, R[0] + math.cos(ang) * d, R[1] + math.sin(ang) * d * 0.7, 11, c,
                 a * sasp * math.sin(ph * math.pi))
    label_pair(ctx, R[0], R[1] + 170, "扛住了：进入衰老", "Survives: becomes senescent", a * kr, 34, 20, zc=SEN_C)
    blit(ctx, text("长期分泌促炎、促纤维化信号  ·  long-term pro-inflammatory, pro-fibrotic signals",
                   "sans_light", 22, SOFT, tracking=1), 960, 790, a * sasp)


def draw_reserve(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "储备卫星细胞", "RESERVE SATELLITE CELLS", y=190)
    k = smooth(gt / 0.8)
    fy = 560
    fiber_long(ctx, 220, 1700, fy, 120, t, a * k, 0.35, seed=7)
    xs = [330 + i * 210 for i in range(7)]
    res = 3
    lose = smooth((gt - dur * 0.12) / 1.2)
    glow_r = smooth((gt - dur * 0.3) / 0.8)
    refill = clamp((gt - dur * 0.55) / (dur * 0.4))
    for i, x in enumerate(xs):
        y = fy - 66
        if i == res:
            sat_cell(ctx, x, y, a * k, SAT_C, w=50, glow=1 + glow_r)
            glow_dot(ctx, x, y, 110, SAT_C, a * glow_r * 0.35)
            continue
        order = abs(i - res)
        back = smooth((refill * 3.2 - (order - 1)) / 1.0)
        if back < 1:
            sat_cell(ctx, x, y, a * k * (1 - 0.8 * lose) * (1 - back), lerp3(SAT_C, GREY_C, lose), w=46,
                     glow=1 - lose)
            if lose > 0.3 and back == 0:
                ctx.move_to(x - 12, y - 30)
                ctx.line_to(x + 12, y - 54)
                ctx.move_to(x + 12, y - 30)
                ctx.line_to(x - 12, y - 54)
                gstroke(ctx, ROS_C, 2.6, a * lose, glow=0.4)
        if back > 0:
            sx = lerp(xs[res], x, ease_io(min(1, back * 1.4)))
            sat_cell(ctx, sx, y, a * k * back, SAT_C, w=46)
    label_pair(ctx, xs[res], fy - 200, "活性氧更低 · 更耐辐射", "Lower ROS · more radiation-tolerant", a * glow_r,
               32, 20, zc=SAT_C)
    label_pair(ctx, 960, fy + 140, "多数卫星细胞减少", "Most satellite cells are lost", a * lose * (1 - smooth(refill * 3)),
               30, 20, zc=GREY_C)
    label_pair(ctx, 960, fy + 140, "克隆扩增，重新补齐干细胞池", "Clonal expansion refills the stem-cell pool",
               a * smooth(refill * 3), 32, 20, zc=SAT_C)
    model_tag(ctx, "小鼠谱系示踪", "MOUSE LINEAGE TRACING", a * k, y=800)


def draw_fap(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "成纤维脂肪祖细胞（FAP）", "FIBRO-ADIPOGENIC PROGENITORS", y=190)
    k = smooth(gt / 0.8)
    L, R = (520, 440), (1400, 440)
    spindle(ctx, L[0], L[1], 230, -0.25 + 0.05 * math.sin(t * 0.6), FIB_C, a * k)
    for j in range(5):
        ph = (gt * 0.25 + j / 5) % 1
        glow_dot(ctx, L[0] + 120 + ph * 60, L[1] - 60 + j * 30, 8, FIB_C, a * k * math.sin(ph * math.pi))
    label_pair(ctx, L[0], L[1] + 130, "正常：帮助修复", "Normally: supports repair", a * k, 32, 20, zc=FIB_C)
    s = ease_out((gt - dur * 0.35) / 1.0)
    ctx.move_to(780, 440)
    ctx.line_to(lerp(780, 1120, s), 440)
    gstroke(ctx, acc, 2.6, a * s, glow=0.6)
    for i in range(2):
        wave_ray(ctx, 840 + i * 140, 260, 940 + i * 140, 410, ease_io((gt - dur * 0.3 - i * 0.2) / 0.9),
                 a * (1 - smooth((gt - dur * 0.55) / 0.5)), t=t)
    sen = smooth((gt - dur * 0.45) / 1.2)
    fib = smooth((gt - dur * 0.6) / 1.4)
    rnd = random.Random(14)
    for j in range(int(40 * fib)):
        ang = rnd.uniform(-0.6, 0.6) + (math.pi if j % 2 else 0)
        d = rnd.uniform(130, 300)
        x, y = R[0] + math.cos(ang) * d, R[1] + math.sin(ang) * d * 0.8 + rnd.uniform(-60, 60)
        wavy_line(ctx, x - 40, y, x + 40, y + rnd.uniform(-10, 10), 4, 18, j)
        gstroke(ctx, COLL_C, 1.7, a * 0.6, glow=0.3)
    spindle(ctx, R[0], R[1], 250, -0.25, lerp3(FIB_C, SEN_C, sen), a * s, act=sen)
    blit(ctx, text("衰老", "sans_med", 24, SEN_C), R[0] + 40, R[1] - 90, a * sen)
    label_pair(ctx, R[0], R[1] + 130, "照射后：衰老 → 纤维化表型", "After irradiation: senescence → fibrotic phenotype",
               a * s, 32, 20, zc=acc)
    model_tag(ctx, "小鼠 · 单侧后肢 16 Gy · 第56天出现纤维化", "MOUSE · ONE HINDLIMB 16 GY · FIBROSIS BY DAY 56",
              a * smooth((gt - 0.6) / 0.8), y=715)


def draw_secretome(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "再生被卡住", "REGENERATION STALLS", y=190)
    k = smooth(gt / 0.8)
    fx, fy = 360, 480
    spindle(ctx, fx, fy, 230, -0.2, SEN_C, a * k, act=0.6)
    label_pair(ctx, fx, fy + 150, "衰老的FAP", "Senescent FAP", a * k, 32, 20, zc=SEN_C)
    flow = smooth((gt - 0.6) / 0.8)
    for j in range(10):
        ph = (gt * 0.22 + j / 10) % 1
        x = lerp(fx + 130, 1000, ph)
        y = fy + 60 * math.sin(j * 1.7 + ph * 3)
        glow_dot(ctx, x, y, 10, acc, a * flow * math.sin(ph * math.pi))
    blit(ctx, text("分泌物  secreted factors", "sans_light", 20, acc, tracking=1), 700, 380, a * flow)
    block = smooth((gt - dur * 0.4) / 1.0)
    mx = [1120, 1260, 1400, 1540]
    pull = 0.5 + 0.5 * math.sin(gt * 1.6)
    for i, x in enumerate(mx):
        target = 1330 + (i - 1.5) * 70
        ox = lerp(x, target, pull * (1 - 0.75 * block) * smooth(gt / 1.5))
        cell(ctx, ox, fy, 46, t + i, lerp3(SAT_C, GREY_C, block * 0.6), a * k, seed=40 + i, nucleus=False,
             glow=0.6)
        glow_dot(ctx, ox, fy, 14, SAT_C, a * k * 0.7)
    rrect(ctx, 1080, fy - 70, 500, 140, 70)
    ctx.set_dash([10, 12])
    gstroke(ctx, SOFT, 1.6, a * k * 0.6, glow=0)
    ctx.set_dash([])
    blit(ctx, text("肌管  myotube", "sans_light", 20, SOFT, tracking=1), 1330, fy - 100, a * k)
    if block > 0:
        cx, cy = 1330, fy
        ctx.move_to(cx - 40, cy - 40)
        ctx.line_to(cx + 40, cy + 40)
        ctx.move_to(cx + 40, cy - 40)
        ctx.line_to(cx - 40, cy + 40)
        gstroke(ctx, ROS_C, 5, a * block, glow=0.6)
    label_pair(ctx, 1330, fy + 150, "卫星细胞分化与融合受抑制", "Satellite-cell differentiation & fusion inhibited",
               a * block, 32, 20, zc=ROS_C)
    model_tag(ctx, "小鼠研究", "IN MICE", a * k, y=790)


SC_CLUSTERS = (("卫星细胞", "Satellite cells", SAT_C, (620, 420)),
               ("FAP", "FAPs", FIB_C, (1000, 360)),
               ("内皮细胞", "Endothelial cells", ENDO_C, (1340, 470)),
               ("巨噬细胞", "Macrophages", IMM_C, (820, 640)),
               ("其他驻留细胞", "Other resident cells", (0.85, 0.70, 0.95), (1200, 680)))


def _cluster_pts():
    rnd = random.Random(31)
    return [[(cx + rnd.gauss(0, 55), cy + rnd.gauss(0, 38)) for _ in range(60)]
            for (_, _, _, (cx, cy)) in SC_CLUSTERS]


SC_PTS = _cluster_pts()


def draw_scseq(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "单细胞测序", "SINGLE-CELL RNA-SEQ", y=190)
    ctx.move_to(420, 780)
    ctx.line_to(420, 300)
    ctx.move_to(420, 780)
    ctx.line_to(1560, 780)
    gstroke(ctx, SOFT, 1.4, a * 0.4, glow=0)
    blit(ctx, text("UMAP", "sans_light", 16, SOFT, tracking=3), 470, 800, a * 0.6)
    for ci, (zh, en, c, (cx, cy)) in enumerate(SC_CLUSTERS):
        kc = smooth((gt - 0.2 - ci * 0.25) / 0.8)
        p21 = smooth((gt - dur * 0.4 - ci * 0.35) / 0.7)
        col = lerp3(c, ROS_C, 0.45 * p21)
        for (x, y) in SC_PTS[ci]:
            ctx.arc(x, y, 5, 0, 2 * math.pi)
            ctx.set_source_rgba(*col, 0.75 * a * kc)
            ctx.fill()
        blit(ctx, text(zh, "sans_med", 24, c), cx, cy + 92, a * kc)
        if p21 > 0:
            bx, by = cx + 70, cy - 62
            glass_panel(ctx, bx - 38, by - 20, 76, 40, 14, a * p21, ROS_C, 0.8)
            blit(ctx, text("p21", "sans_med", 22, ROS_C), bx, by - 2, a * p21)
    blit(ctx, text("持续的 p21 (Cdkn1a) 衰老标记  ·  persistent p21 senescence signature", "sans_light", 24,
                   ROS_C, tracking=1), 990, 835, a * smooth((gt - dur * 0.75) / 0.8))
    model_tag(ctx, "小鼠肌肉", "MOUSE MUSCLE", a * smooth(gt / 0.8), x=1660, y=760)


def draw_tgfb(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "巨噬细胞 → TGF-β → FAP → 瘢痕", "MACROPHAGE → TGF-β → FAP → SCAR", y=190)
    k = smooth(gt / 0.8)
    mx, my = 360, 490
    immune(ctx, mx, my, 80 + 4 * math.sin(t * 2), t, a * k, seed=12)
    label_pair(ctx, mx, my + 160, "巨噬细胞", "Macrophage", a * k, 32, 20, zc=IMM_C)
    sig = smooth((gt - 0.8) / 0.8)
    fx, fy = 900, 490
    for j in range(9):
        ph = (gt * 0.3 + j / 9) % 1
        x = lerp(mx + 100, fx - 140, ph)
        y = my + 30 * math.sin(j * 2.1 + ph * 4)
        glow_dot(ctx, x, y, 11, acc, a * sig * math.sin(ph * math.pi))
    blit(ctx, text("TGF-β", "sans_med", 30, acc, tracking=2), (mx + fx) / 2, my - 70, a * sig)
    blit(ctx, text("→ TGF-βR2", "sans_light", 18, SOFT, tracking=1), (mx + fx) / 2, my - 36, a * sig)
    act = smooth((gt - dur * 0.3) / 1.0)
    spindle(ctx, fx, fy, 230, 0.0, FIB_C, a * k, act=act)
    label_pair(ctx, fx, fy + 160, "FAP", "Main source of ECM", a * k, 32, 20, zc=FIB_C)
    ecm = smooth((gt - dur * 0.4) / max(1.5, dur * 0.5))
    rnd = random.Random(19)
    for j in range(int(90 * ecm)):
        x, y = rnd.uniform(1200, 1720), rnd.uniform(330, 650)
        ang = rnd.uniform(-0.7, 0.7)
        L = rnd.uniform(50, 120)
        wavy_line(ctx, x - math.cos(ang) * L / 2, y - math.sin(ang) * L / 2,
                  x + math.cos(ang) * L / 2, y + math.sin(ang) * L / 2, 4, 20, j)
        gstroke(ctx, COLL_C, 1.8, a * 0.6, glow=0.3)
    ctx.move_to(fx + 140, fy)
    ctx.line_to(lerp(fx + 140, 1180, act), fy)
    gstroke(ctx, acc, 2.4, a * act * 0.8, glow=0.5)
    label_pair(ctx, 1460, fy + 160, "瘢痕基质（细胞外基质）", "Scar matrix (ECM)", a * ecm, 32, 20, zc=COLL_C)
    blit(ctx, text("纤维化由此固化  ·  fibrosis locks in", "serif", 30, WHITE, tracking=2), 960, 790,
         a * smooth((gt - dur * 0.75) / 0.8))
    model_tag(ctx, "小鼠", "MOUSE", a * k, x=1700, y=260)


def draw_mito(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "电镜下的损伤", "UNDER THE ELECTRON MICROSCOPE", y=190)
    k = smooth(gt / 0.8)
    sw = smooth((gt - 0.6) / 2.0)
    glass_panel(ctx, 230, 290, 640, 420, 28, a * k)
    mitochondrion(ctx, 550, 470, 380, 150, MITO_C, a * k, swell=sw, t=t)
    label_pair(ctx, 550, 640, "线粒体肿胀", "Swollen mitochondria", a * k, 32, 20, zc=MITO_C)
    kr = smooth((gt - dur * 0.3) / 0.8)
    glass_panel(ctx, 1050, 290, 640, 420, 28, a * kr)
    vx, vy, vr = 1370, 470, 120
    dmg = smooth((gt - dur * 0.4) / 1.2)
    for e in range(6):
        a0 = e * math.pi / 3 + 0.15 * dmg
        a1 = a0 + math.pi / 3 - 0.35 * dmg
        ctx.new_path()
        ctx.arc(vx, vy, vr, a0, a1)
        gstroke(ctx, lerp3(ENDO_C, GREY_C, dmg * 0.7), 10, a * kr, glow=0.5)
        mid = (a0 + a1) / 2
        glow_dot(ctx, vx + math.cos(mid) * vr, vy + math.sin(mid) * vr, 10, ENDO_C, a * kr * (1 - 0.5 * dmg))
    for j in range(4):
        ctx.save()
        ctx.translate(vx + math.cos(j * 1.6 + t * 0.3) * 45, vy + math.sin(j * 1.6 + t * 0.3) * 45)
        ctx.scale(1.0, 0.6)
        ctx.arc(0, 0, 18, 0, 2 * math.pi)
        ctx.restore()
        ctx.set_source_rgba(*VES_C, 0.55 * a * kr)
        ctx.fill()
    for j in range(12):
        gap = j % 6 * math.pi / 3 + math.pi / 6
        ph = (gt * 0.35 + j / 12) % 1
        d = vr - 10 + ph * 150
        glow_dot(ctx, vx + math.cos(gap) * d, vy + math.sin(gap) * d, 8, VES_C, a * dmg * math.sin(ph * math.pi))
    label_pair(ctx, 1370, 640, "内皮损伤 · 通透性升高", "Endothelial damage · leakier vessel", a * kr, 32, 20,
               zc=ENDO_C)
    model_tag(ctx, "大鼠模型 · 电镜观察", "RAT MODEL · ELECTRON MICROSCOPY", a * k, y=790)


def draw_monkey(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "灵长类的长期证据", "LONG-TERM EVIDENCE IN PRIMATES", y=190)
    k = smooth(gt / 0.8)
    icon_at(ctx, lambda: icon_monkey(ctx, (0.95, 0.85, 0.75), 1), 400, 470, 1.15, a * k)
    blit(ctx, text("恒河猴  rhesus macaque", "sans_light", 22, SOFT, tracking=1), 400, 620, a * k)
    x0, x1, y = 720, 1700, 400
    prog = ease_io((gt - 0.6) / max(1.5, dur * 0.45))
    ctx.move_to(x0, y)
    ctx.line_to(x1, y)
    gstroke(ctx, SOFT, 1.6, a * k * 0.35, glow=0)
    ctx.move_to(x0, y)
    ctx.line_to(lerp(x0, x1, prog), y)
    gstroke(ctx, acc, 3.0, a * k, glow=0.7)
    glow_dot(ctx, lerp(x0, x1, prog), y, 26, acc, a * k * smooth(prog * 6))
    for yr in range(5):
        x = lerp(x0, x1, yr / 4)
        ctx.move_to(x, y - 10)
        ctx.line_to(x, y + 10)
        gstroke(ctx, SOFT, 1.6, a * k * 0.6, glow=0)
        blit(ctx, text(f"{yr}", "sans_light", 20, SOFT), x, y + 34, a * k * 0.8)
    blit(ctx, text("年  years", "sans_light", 18, SOFT, tracking=2), x1 + 40, y + 34, a * k * 0.8)
    label_pair(ctx, x0, y - 70, "全身照射", "Whole-body irradiation", a * k, 28, 18, zc=RAY_C)
    label_pair(ctx, x1, y - 70, "约4年后", "~4 years later", a * smooth((prog - 0.85) / 0.15), 28, 18, zc=acc)
    for i, (zh, en, c) in enumerate((("胰岛素抵抗", "Insulin resistance", acc),
                                     ("线粒体异常", "Mitochondrial abnormalities", MITO_C))):
        kk = ease_out((gt - dur * (0.6 + 0.12 * i)) / 0.8)
        bx, by = 1000 + i * 420, 600
        glass_panel(ctx, bx - 190, by - 56, 380, 112, 22, a * kk, c, 0.5)
        label_pair(ctx, bx, by - 12, zh, en, a * kk, 34, 20, zc=c)
    model_tag(ctx, "非人灵长类", "NONHUMAN PRIMATE", a * k, x=400, y=760)


CASCADE = (("DNA与活性氧", "DNA damage & ROS", ROS_C, "DNA与"),
           ("死亡或衰老", "Death or senescence", GREY_C, "死亡或"),
           ("干细胞与FAP龛位失衡", "Stem-cell & FAP niche imbalance", SAT_C, "干细胞与"),
           ("血管炎症重塑", "Vascular & inflammatory remodeling", VES_C, "血管炎"),
           ("纤维化", "Fibrosis", FIB_C, "最后是"))


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
        sat_cell(ctx, x - 14, y - 18, a, c, w=32)
        spindle(ctx, x + 12, y + 24, 70, -0.3, FIB_C, a)
        ctx.move_to(x - 44, y - 44)
        ctx.line_to(x + 44, y + 44)
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


def draw_directions(ctx, gt, g, a, acc, t):
    dur = line_dur(g)
    heading(ctx, gt, a, "值得盯住的机制节点", "MECHANISMS WORTH WATCHING", y=190)
    items = (("卫星细胞储备群", "Reserve satellite-cell pool", SAT_C),
             ("FAP 衰老", "FAP senescence", FIB_C),
             ("巨噬细胞–TGF-β–FAP 轴", "Macrophage–TGF-β–FAP axis", IMM_C),
             ("长期线粒体与代谢改变", "Long-term mitochondria & metabolism", MITO_C))
    for i, (zh, en, c) in enumerate(items):
        kk = ease_out((gt - 0.6 - dur * 0.16 * i) / 0.8)
        if kk <= 0:
            continue
        x, y = 960 + (i - 1.5) * 420, 500 + (1 - kk) * 30
        glass_panel(ctx, x - 190, y - 190, 380, 360, 26, a * kk, c, 0.35)
        ia = a * kk
        iy = y - 60
        if i == 0:
            fiber_long(ctx, x - 130, x + 130, iy + 30, 50, t, ia)
            sat_cell(ctx, x, iy - 4, ia, c, w=40, glow=1.6)
            glow_dot(ctx, x, iy - 4, 80, c, ia * 0.3)
        elif i == 1:
            spindle(ctx, x, iy, 190, -0.25, lerp3(FIB_C, SEN_C, 0.6), ia, act=0.6)
            blit(ctx, text("p21", "sans_med", 22, ROS_C), x + 60, iy - 56, ia)
        elif i == 2:
            immune(ctx, x - 100, iy, 34, t, ia, seed=5)
            for j in range(4):
                ph = (gt * 0.4 + j / 4) % 1
                glow_dot(ctx, lerp(x - 60, x + 20, ph), iy, 7, acc, ia * math.sin(ph * math.pi))
            spindle(ctx, x + 80, iy, 110, 0.0, FIB_C, ia, act=0.5)
        else:
            mitochondrion(ctx, x, iy, 200, 90, c, ia, swell=0.35 + 0.15 * math.sin(t), t=t)
        label_pair(ctx, x, y + 90, zh, en, ia, 28, 18, zc=c)
    kd = smooth((gt - dur * 0.75) / 0.8)
    blit(ctx, text("这些是研究方向，不是医疗建议  ·  research directions, not medical advice", "sans_light", 22,
                   SOFT, tracking=1), 960, 760, a * kd)


def draw_end(ctx, gt, g, a, acc, t):
    line = g["lines"][0]
    SECTION.draw(ctx, 960, 480, t, a * 0.20 * smooth(gt / 2), dmg=0.3, scale=1.3)
    blit_reveal(ctx, text("一句话总结  ·  IN ONE SENTENCE", "sans_light", 24, acc, tracking=6), 960, 210,
                ease_out((gt - 0.2) / 1.2), a)
    blit_reveal(ctx, text("理解这条链", "serif", 88, WHITE, tracking=10), 960, 320,
                ease_out((gt - 0.4) / 1.6), a)
    blit_reveal(ctx, text("是后续干预和实验设计的起点", "serif_light", 46, WHITE, tracking=4), 960, 420,
                ease_out((gt - 0.8) / 1.6), a)
    blit_reveal(ctx, text("Understanding this chain is the starting point for interventions and experimental design.",
                          "serif_light", 28, (0.90, 0.95, 0.98), tracking=1), 960, 490,
                ease_out((gt - 1.2) / 1.6), a)
    for i, (zh, en, c, key) in enumerate(CASCADE):
        kk = ease_out((gt - 1.0 - 0.18 * i) / 0.7)
        x = 960 + (i - 2) * 300
        glass_panel(ctx, x - 135, 560, 270, 64, 18, a * kk, c, 0.6)
        blit(ctx, text(zh, "sans_med", 22, c), x, 590, a * kk)
        if i:
            blit(ctx, text("→", "sans", 24, acc), x - 150, 590, a * kk)
    kd = ease_out((t - line["start"] - 2.0) / 1.0)
    if kd > 0:
        y = 760 + (1 - kd) * 20
        glass_panel(ctx, 960 - 420, y - 70, 840, 140, 24, a * kd, acc, 0.45)
        blit(ctx, text("本视频仅供科普", "sans_med", 40, WHITE, tracking=4), 960, y - 18, a * kd)
        blit(ctx, text("For education only. Not medical advice.", "sans_light", 24, SOFT, tracking=2), 960,
             y + 30, a * kd)


def draw_refs(ctx, gt, g, a, acc, t):
    blit_reveal(ctx, text("参考文献  ·  REFERENCES", "serif", 44, WHITE, tracking=4), 960, 120,
                ease_out(gt / 1.2), a)
    ctx.move_to(960 - 300, 172)
    ctx.line_to(960 + 300, 172)
    gstroke(ctx, acc, 1.2, a * ease_io((gt - 0.4) / 1.0), glow=0)
    x0, y = 210, 205
    for i, key in enumerate(REF_ORDER):
        r = REFS[key]
        kk = ease_out((gt - 0.6 - 0.15 * i) / 0.8)
        num = text(f"{i + 1}", "serif_light", 28, acc, shadow=0.3)
        blit(ctx, num, x0 - 36, y + 12, a * kk)
        tf = text(r["full"], "sans_light", 21, WHITE, max_w=1540, align="left", line_gap=1.25, shadow=0.4)
        td = text(f"doi: {r['doi']}   ·   PMID {r['pmid']}", "sans_light", 18, acc, tracking=1, shadow=0.4)
        pf, pd = int(21 * 0.7), int(18 * 0.7)
        blit(ctx, tf, x0 + tf.tw / 2 - pf, y + tf.th / 2 - pf, a * kk)
        y += tf.th - 2 * pf + 4
        blit(ctx, td, x0 + td.tw / 2 - pd, y + td.th / 2 - pd, a * kk)
        y += td.th - 2 * pd + 14
    blit(ctx, text("本视频仅供科普  ·  For education only", "sans", 22, SOFT, tracking=3), 960, 1030,
         a * smooth((gt - 1.6) / 1.0))


DRAWERS = {
    "title": draw_title, "dnaros": draw_dnaros, "fate": draw_fate, "fibers": draw_fibers,
    "reserve": draw_reserve, "fap": draw_fap, "secretome": draw_secretome, "scseq": draw_scseq,
    "tgfb": draw_tgfb, "mito": draw_mito, "monkey": draw_monkey, "clinic": draw_clinic,
    "cascade": draw_cascade, "directions": draw_directions, "end": draw_end, "refs": draw_refs,
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
