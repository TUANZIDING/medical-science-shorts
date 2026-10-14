#!/usr/bin/env python3
"""Ionizing radiation injury to the skeletal muscle niche (v2).

Hand-authored SVG (BioRender-like anatomical niche) rasterised with cairosvg.
Evidence is encoded by line style only:
  thick solid = shown in irradiated skeletal muscle in vivo
  thin solid  = other tissue or review
  dashed      = proposed / inferred

Outputs (next to this script):
  radiation_muscle_mechanism_v2.svg / .png (300 dpi, 3600x2200) / .pdf
"""
import math
import random
import re
from pathlib import Path

import cairosvg
from PIL import Image, ImageFont

OUT = Path(__file__).resolve().parent
STEM = "radiation_muscle_mechanism_v2"
W, H = 1800, 1100
PX_W, PX_H = 3600, 2200

FONT = "Inter, 'Liberation Sans', 'DejaVu Sans', sans-serif"
SEMIBOLD = "'Inter SemiBold', " + FONT
INK = "#1F2933"
MUTED = "#6B7785"
ARROW = "#37424F"
BG = "#FAF9F7"

P = {
    "fibre_hi": "#F6DCD2", "fibre_mid": "#E2AE9F", "fibre_lo": "#B9766A",
    "fibre_edge": "#A7665B", "fibre_face": "#F1CCBF",
    "nuc_hi": "#A9B3D6", "nuc_lo": "#56628F", "nuc_edge": "#47527C",
    "sc_hi": "#CFE2F3", "sc_lo": "#6E9CC7", "sc_edge": "#3F6E9C",
    "rsc_hi": "#CDEBDD", "rsc_lo": "#4FA88B", "rsc_edge": "#2B7A62",
    "fap_hi": "#F8E1B9", "fap_lo": "#D5A055", "fap_edge": "#A9772F",
    "mac_hi": "#E6DCF0", "mac_lo": "#9C83C0", "mac_edge": "#6F5899",
    "sen": "#7E62A8", "sen_hi": "#E4DAF0",
    "ves_hi": "#F7CFCB", "ves_lo": "#D6837E", "ves_edge": "#B5605B",
    "lumen": "#8E3B3B", "rbc": "#C4504C",
    "per_hi": "#D7E5CB", "per_lo": "#86A876", "per_edge": "#5F8251",
    "col_hi": "#EBD6B1", "col_lo": "#BE9963", "col_band": "#97764A",
    "lamina": "#6E9C95",
    "ros": "#E07A4F", "dna1": "#4A6FA5", "dna2": "#86A9D6",
    "beam": "#E3A63B",
    "card": "#FFFFFF", "card_edge": "#E3E7EC",
    "ddr_hi": "#8FA3C4", "ddr_lo": "#4C5F82",
    "death_hi": "#EBD3D0", "death_lo": "#B98A86",
}

defs: list[str] = []
body: list[str] = []
_uid = [0]


def uid(prefix="g"):
    _uid[0] += 1
    return f"{prefix}{_uid[0]}"


def add(s):
    body.append(s)


def f(v):
    return f"{v:.1f}"


# ---------------------------------------------------------------- gradients
def radial(inner, outer, fx=0.35, fy=0.3, r=0.75, mid=None):
    gid = uid("r")
    stops = f'<stop offset="0" stop-color="{inner}"/>'
    if mid:
        stops += f'<stop offset="0.55" stop-color="{mid}"/>'
    stops += f'<stop offset="1" stop-color="{outer}"/>'
    defs.append(
        f'<radialGradient id="{gid}" cx="{fx + 0.1}" cy="{fy + 0.12}" r="{r}" '
        f'fx="{fx}" fy="{fy}">{stops}</radialGradient>')
    return f"url(#{gid})"


def linear(stops, x1=0, y1=0, x2=0, y2=1, user=None):
    gid = uid("l")
    st = "".join(
        f'<stop offset="{o}" stop-color="{c}" stop-opacity="{a}"/>'
        for o, c, a in stops)
    units = ""
    if user:
        units = 'gradientUnits="userSpaceOnUse" '
        x1, y1, x2, y2 = user
    defs.append(
        f'<linearGradient id="{gid}" {units}x1="{x1}" y1="{y1}" x2="{x2}" '
        f'y2="{y2}">{st}</linearGradient>')
    return f"url(#{gid})"


SHADOW_ID = "softshadow"
defs.append(
    f'<radialGradient id="{SHADOW_ID}" cx="0.5" cy="0.5" r="0.5">'
    '<stop offset="0" stop-color="#22303F" stop-opacity="0.30"/>'
    '<stop offset="0.6" stop-color="#22303F" stop-opacity="0.12"/>'
    '<stop offset="1" stop-color="#22303F" stop-opacity="0"/>'
    '</radialGradient>')


def shadow(cx, cy, rx, ry, op=1.0):
    add(f'<ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(rx)}" ry="{f(ry)}" '
        f'fill="url(#{SHADOW_ID})" opacity="{op}"/>')


# ---------------------------------------------------------------- paths
def smooth_closed(pts, k=1 / 6):
    n = len(pts)
    d = f"M{f(pts[0][0])},{f(pts[0][1])}"
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) * k, p1[1] + (p2[1] - p0[1]) * k)
        c2 = (p2[0] - (p3[0] - p1[0]) * k, p2[1] - (p3[1] - p1[1]) * k)
        d += (f" C{f(c1[0])},{f(c1[1])} {f(c2[0])},{f(c2[1])} "
              f"{f(p2[0])},{f(p2[1])}")
    return d + "Z"


def smooth_open(pts, k=1 / 6):
    d = f"M{f(pts[0][0])},{f(pts[0][1])}"
    n = len(pts)
    for i in range(n - 1):
        p0 = pts[max(i - 1, 0)]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[min(i + 2, n - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) * k, p1[1] + (p2[1] - p0[1]) * k)
        c2 = (p2[0] - (p3[0] - p1[0]) * k, p2[1] - (p3[1] - p1[1]) * k)
        d += (f" C{f(c1[0])},{f(c1[1])} {f(c2[0])},{f(c2[1])} "
              f"{f(p2[0])},{f(p2[1])}")
    return d


def blob(cx, cy, rx, ry, wobble, seed, n=14, rot=0.0):
    rnd = random.Random(seed)
    phases = [rnd.uniform(0, 2 * math.pi) for _ in range(3)]
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        r = 1 + wobble * (0.6 * math.sin(3 * t + phases[0])
                          + 0.4 * math.sin(5 * t + phases[1])
                          + 0.25 * math.sin(2 * t + phases[2]))
        x, y = rx * r * math.cos(t), ry * r * math.sin(t)
        xr = x * math.cos(rot) - y * math.sin(rot)
        yr = x * math.sin(rot) + y * math.cos(rot)
        pts.append((cx + xr, cy + yr))
    return smooth_closed(pts)


# ---------------------------------------------------------------- text
def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


FONT_DIR = Path("/usr/share/fonts/truetype/macos")
# cairo resolves Inter weight 400 to the Medium face, so measure with it.
_WEIGHT_NAME = {400: "Medium", 500: "Medium", 600: "SemiBold", 700: "Bold"}
_font_cache: dict = {}


def text_width(s, size, weight=400, italic=False):
    key = (weight, italic)
    if key not in _font_cache:
        name = _WEIGHT_NAME[weight]
        if italic:
            name += "Italic"
        _font_cache[key] = ImageFont.truetype(
            str(FONT_DIR / f"Inter-{name}.ttf"), 200)
    return _font_cache[key].getlength(s) * size / 200


def text(x, y, s, size=17, weight=400, color=INK, anchor="start",
         lh=1.28, italic=False, op=1.0, pill=False):
    """Multi-line text; `^{..}` renders a superscript.

    Segments are measured and placed individually because cairosvg anchors
    each tspan separately when text-anchor is middle/end.
    """
    style = ' font-style="italic"' if italic else ""
    sup = size * 0.64
    for li, line in enumerate(s.split("\n")):
        yy = y + li * size * lh
        parts = re.split(r"\^\{([^}]*)\}", line)
        segs = []
        for i, part in enumerate(parts):
            if not part:
                continue
            is_sup = i % 2 == 1
            sz = sup if is_sup else size
            w = text_width(part, sz, weight, italic)
            segs.append((part, is_sup, w + (1.2 if is_sup else 0)))
        total = sum(w for _, _, w in segs)
        x0 = {"start": x, "middle": x - total / 2, "end": x - total}[anchor]
        if pill:
            add(f'<rect x="{f(x0 - 7)}" y="{f(yy - size * 0.92)}" '
                f'width="{f(total + 14)}" height="{f(size * 1.3)}" '
                f'rx="{f(size * 0.5)}" fill="#FFFFFF" opacity="0.82"/>')
        cx = x0
        for part, is_sup, w in segs:
            sz = sup if is_sup else size
            dy = -0.4 * size if is_sup else 0
            lead = len(part) - len(part.lstrip(" "))
            shift = text_width(" " * lead, sz, weight, italic) if lead else 0
            part = part.strip(" ")
            add(f'<text x="{f(cx + shift + (1.2 if is_sup else 0))}" '
                f'y="{f(yy + dy)}" font-family="{SEMIBOLD if weight == 600 else FONT}" '
                f'font-size="{f(sz)}" '
                f'font-weight="{weight}" fill="{color}" opacity="{op}"'
                f'{style}>{esc(part)}</text>')
            cx += w


# ---------------------------------------------------------------- arrows
STYLE = {
    "thick": dict(w=6.5, hl=21, hw=21, dash=None),
    "thin": dict(w=2.4, hl=13, hw=11, dash=None),
    "dashed": dict(w=3.4, hl=15, hw=14, dash="10 7"),
}


def arrow(p0, p1, kind="thick", bend=0.0, inhibit=False, color=ARROW,
          halo=True, bar=0.75):
    st = STYLE[kind]
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    nx, ny = -dy / L, dx / L
    cx, cy = (x0 + x1) / 2 + nx * bend * L, (y0 + y1) / 2 + ny * bend * L
    tx, ty = x1 - cx, y1 - cy
    tl = math.hypot(tx, ty)
    tx, ty = tx / tl, ty / tl
    px, py = -ty, tx
    hl, hw, w = st["hl"], st["hw"], st["w"]
    if inhibit:
        ex, ey = x1, y1
    else:
        ex, ey = x1 - tx * hl * 0.7, y1 - ty * hl * 0.7
    d = f"M{f(x0)},{f(y0)} Q{f(cx)},{f(cy)} {f(ex)},{f(ey)}"
    dash = f' stroke-dasharray="{st["dash"]}"' if st["dash"] else ""
    if halo:
        add(f'<path d="{d}" fill="none" stroke="#FFFFFF" stroke-width="'
            f'{w + 5}" stroke-linecap="round" opacity="0.85"/>')
    add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}" '
        f'stroke-linecap="round"{dash}/>')
    if inhibit:
        bw = hw * bar
        add(f'<line x1="{f(x1 + px * bw)}" y1="{f(y1 + py * bw)}" '
            f'x2="{f(x1 - px * bw)}" y2="{f(y1 - py * bw)}" stroke="{color}" '
            f'stroke-width="{w}" stroke-linecap="round"/>')
        return
    bx, by = x1 - tx * hl, y1 - ty * hl
    notch = (x1 - tx * hl * 0.72, y1 - ty * hl * 0.72)
    head = (f"M{f(x1)},{f(y1)} L{f(bx + px * hw / 2)},{f(by + py * hw / 2)} "
            f"L{f(notch[0])},{f(notch[1])} "
            f"L{f(bx - px * hw / 2)},{f(by - py * hw / 2)} Z")
    if halo:
        add(f'<path d="{head}" fill="none" stroke="#FFFFFF" stroke-width="3" '
            f'stroke-linejoin="round" opacity="0.85"/>')
    add(f'<path d="{head}" fill="{color}" stroke="{color}" '
        f'stroke-width="1.2" stroke-linejoin="round"/>')


# ---------------------------------------------------------------- cards
def card(x, y, w, h, letter, title):
    add(f'<rect x="{x + 2}" y="{y + 5}" width="{w}" height="{h}" rx="22" '
        f'fill="#1E2A38" opacity="0.045"/>')
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" '
        f'fill="{P["card"]}" stroke="{P["card_edge"]}" stroke-width="1.4"/>')
    text(x + 26, y + 36, letter, size=23, weight=700, color=INK)
    text(x + 52, y + 36, title, size=19, weight=600, color="#3B4654")


# ---------------------------------------------------------------- cells
def nucleus(cx, cy, rx, ry, rot=0, fill=None, edge=None):
    fill = fill or radial(P["nuc_hi"], P["nuc_lo"])
    edge = edge or P["nuc_edge"]
    add(f'<ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(rx)}" ry="{f(ry)}" '
        f'transform="rotate({rot} {f(cx)} {f(cy)})" fill="{fill}" '
        f'stroke="{edge}" stroke-width="1"/>')


def fibre(x0, y0, x1, y1, nuc_top=(), nuc_bot=(), seed=1, face=True):
    h = y1 - y0
    cy = (y0 + y1) / 2
    rx = h * 0.2
    grad = linear([(0, P["fibre_lo"], 1), (0.14, P["fibre_mid"], 1),
                   (0.3, P["fibre_hi"], 1), (0.58, P["fibre_mid"], 1),
                   (0.9, P["fibre_lo"], 1), (1, "#9F5F55", 1)],
                  user=(0, y0, 0, y1))
    sh = linear([(0, "#2A1A16", 0.22), (1, "#2A1A16", 0)],
                user=(0, y1, 0, y1 + 16))
    add(f'<rect x="{x0}" y="{y1 - 2}" width="{x1 - x0}" height="18" '
        f'fill="{sh}"/>')
    cid = uid("clip")
    defs.append(f'<clipPath id="{cid}"><rect x="{x0}" y="{y0}" '
                f'width="{x1 - x0}" height="{h}"/></clipPath>')
    add(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{h}" '
        f'fill="{grad}"/>')
    add(f'<g clip-path="url(#{cid})">')
    x = x0 + rx + 4
    while x < x1:
        bow = 2.5
        add(f'<path d="M{f(x)},{y0} Q{f(x + bow)},{f(cy)} {f(x)},{y1}" '
            f'stroke="#8E4E44" stroke-width="4.2" opacity="0.13" '
            f'fill="none"/>')
        add(f'<path d="M{f(x + 6.5)},{y0} Q{f(x + 6.5 + bow)},{f(cy)} '
            f'{f(x + 6.5)},{y1}" stroke="#7F433A" stroke-width="0.9" '
            f'opacity="0.22" fill="none"/>')
        x += 11
    yy = y0 + 9
    while yy < y1 - 4:
        add(f'<line x1="{x0}" y1="{f(yy)}" x2="{x1}" y2="{f(yy)}" '
            f'stroke="#FFFFFF" stroke-width="0.8" opacity="0.16"/>')
        yy += 9
    for nx in nuc_top:
        nucleus(nx, y0 + 7.5, 24, 6)
    for nx in nuc_bot:
        nucleus(nx, y1 - 7.5, 24, 6)
    add("</g>")
    add(f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" '
        f'stroke="{P["fibre_edge"]}" stroke-width="1.5"/>')
    add(f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" '
        f'stroke="{P["fibre_edge"]}" stroke-width="1.5"/>')
    if not face:
        return
    fg = radial("#FBE7DF", "#DDA192", fx=0.4, fy=0.35, r=0.7)
    add(f'<ellipse cx="{x0}" cy="{f(cy)}" rx="{f(rx)}" ry="{f(h / 2)}" '
        f'fill="{fg}" stroke="{P["fibre_edge"]}" stroke-width="1.5"/>')
    rnd = random.Random(seed)
    step = 6.2
    yy = y0 + 5
    row = 0
    while yy < y1 - 3:
        xx = x0 - rx + (step / 2 if row % 2 else 0)
        while xx < x0 + rx:
            if ((xx - x0) / (rx - 3)) ** 2 + ((yy - cy) / (h / 2 - 4)) ** 2 < 1:
                add(f'<circle cx="{f(xx + rnd.uniform(-.6, .6))}" '
                    f'cy="{f(yy)}" r="2.1" fill="#C27E70" opacity="0.55"/>')
            xx += step
        yy += step * 0.87
        row += 1
    a = math.radians(205)
    nucleus(x0 + (rx - 3) * math.cos(a), cy + (h / 2 - 5) * math.sin(a),
            3.5, 7.5, rot=-30)


def sc_shape(cx, ybase, L, hgt, down=True):
    s = 1 if down else -1
    return (f"M{f(cx - L / 2)},{f(ybase)} "
            f"C{f(cx - L / 3)},{f(ybase + s * hgt * 1.35)} "
            f"{f(cx + L / 3)},{f(ybase + s * hgt * 1.35)} "
            f"{f(cx + L / 2)},{f(ybase)} Z")


def satellite(cx, ybase, L=62, hgt=19, kind="sc", down=True, ghost=False):
    s = 1 if down else -1
    if ghost:
        add(f'<path d="{sc_shape(cx, ybase, L, hgt, down)}" fill="'
            f'{P["sc_hi"]}" fill-opacity="0.45" stroke="{P["sc_edge"]}" '
            f'stroke-width="1.1" stroke-opacity="0.55"/>')
        return
    hi, lo, ed = ((P["sc_hi"], P["sc_lo"], P["sc_edge"]) if kind == "sc"
                  else (P["rsc_hi"], P["rsc_lo"], P["rsc_edge"]))
    shadow(cx, ybase + s * hgt * 0.9, L * 0.55, hgt * 0.55, op=0.6)
    add(f'<path d="{sc_shape(cx, ybase, L, hgt, down)}" '
        f'fill="{radial(hi, lo, fx=0.4, fy=0.25 if down else 0.6)}" '
        f'stroke="{ed}" stroke-width="1.3"/>')
    nucleus(cx, ybase + s * hgt * 0.5, L * 0.24, hgt * 0.3,
            fill=radial("#F2F6FA", ed, fx=0.35, fy=0.3), edge=ed)


def lamina(x0, x1, ybase, bumps, down=True, label_at=None):
    s = 1 if down else -1
    pts = []
    x = x0
    while x <= x1:
        off = 5.5
        for bx, L, hgt in bumps:
            u = (x - bx) / (L * 0.62)
            if abs(u) < 1:
                off = max(off, 5.5 + hgt * 1.02 * math.cos(u * math.pi / 2) ** 2)
        pts.append((x, ybase + s * off))
        x += 4
    add(f'<path d="{smooth_open(pts)}" fill="none" stroke="{P["lamina"]}" '
        f'stroke-width="2.4" stroke-linecap="round" opacity="0.85"/>')


def fap(cx, cy, seed=3, scale=1.0):
    s = scale
    pts = [(-150, 6), (-95, -2), (-55, -20), (-18, -32), (25, -30),
           (60, -16), (98, -14), (128, -30), (152, -36), (132, -18),
           (100, 0), (70, 16), (35, 30), (-10, 32), (-50, 22), (-95, 12)]
    pts = [(cx + x * s, cy + y * s) for x, y in pts]
    shadow(cx, cy + 34 * s, 130 * s, 16 * s, op=0.7)
    add(f'<path d="{smooth_closed(pts)}" '
        f'fill="{radial(P["fap_hi"], P["fap_lo"], fx=0.4, fy=0.25, r=0.8)}" '
        f'stroke="{P["fap_edge"]}" stroke-width="1.4"/>')
    nucleus(cx - 4 * s, cy + 1 * s, 34 * s, 17 * s, rot=-6,
            fill=radial("#EFE6F6", P["sen"], fx=0.35, fy=0.3),
            edge="#5E4787")


def receptor(x, y, ang, color="#4D3B6E"):
    """Y-shaped receptor glyph whose stem sits on the membrane at (x, y)."""
    a = math.radians(ang)
    ux, uy = math.cos(a), math.sin(a)
    px, py = -uy, ux
    sx, sy = x + ux * 12, y + uy * 12
    add(f'<line x1="{f(x)}" y1="{f(y)}" x2="{f(sx)}" y2="{f(sy)}" '
        f'stroke="{color}" stroke-width="3.2" stroke-linecap="round"/>')
    for sgn in (1, -1):
        add(f'<line x1="{f(sx)}" y1="{f(sy)}" '
            f'x2="{f(sx + ux * 8 + px * 6 * sgn)}" '
            f'y2="{f(sy + uy * 8 + py * 6 * sgn)}" stroke="{color}" '
            f'stroke-width="3.2" stroke-linecap="round"/>')


def ligand(x, y, color="#6F5899"):
    add(f'<circle cx="{f(x - 3)}" cy="{f(y)}" r="3.6" fill="{color}"/>')
    add(f'<circle cx="{f(x + 3)}" cy="{f(y)}" r="3.6" fill="{color}" '
        f'opacity="0.8"/>')


def macrophage(cx, cy, r=44, seed=11):
    rnd = random.Random(seed)
    pts = []
    n = 22
    for i in range(n):
        t = 2 * math.pi * i / n
        rr = r * (1 + 0.1 * math.sin(3 * t + 0.7) + 0.06 * math.sin(7 * t))
        if i % 5 == 0:
            rr *= 1.32
        pts.append((cx + rr * math.cos(t), cy + rr * 0.86 * math.sin(t)))
    shadow(cx, cy + r * 0.85, r * 1.1, r * 0.3, op=0.7)
    add(f'<path d="{smooth_closed(pts)}" '
        f'fill="{radial(P["mac_hi"], P["mac_lo"], fx=0.38, fy=0.28)}" '
        f'stroke="{P["mac_edge"]}" stroke-width="1.4"/>')
    for _ in range(6):
        a = rnd.uniform(0, 2 * math.pi)
        d = rnd.uniform(0.45, 0.7) * r
        add(f'<circle cx="{f(cx + d * math.cos(a))}" '
            f'cy="{f(cy + d * 0.8 * math.sin(a))}" r="{f(rnd.uniform(3, 5))}" '
            f'fill="#FFFFFF" opacity="0.45" stroke="{P["mac_edge"]}" '
            f'stroke-opacity="0.35" stroke-width="0.8"/>')
    k = (f"M{f(cx - 16)},{f(cy - 10)} C{f(cx - 4)},{f(cy - 22)} "
         f"{f(cx + 18)},{f(cy - 16)} {f(cx + 16)},{f(cy)} "
         f"C{f(cx + 14)},{f(cy + 14)} {f(cx - 2)},{f(cy + 16)} "
         f"{f(cx - 6)},{f(cy + 6)} C{f(cx - 10)},{f(cy - 2)} "
         f"{f(cx - 22)},{f(cy + 4)} {f(cx - 16)},{f(cy - 10)} Z")
    add(f'<path d="{k}" fill="{radial("#F1ECF7", "#5E4787")}" '
        f'stroke="#4E3B74" stroke-width="1"/>')


def mito(cx, cy, L, Wd, rot=0, swollen=False, fission=False):
    g = (radial("#FBEFD9", "#E2B66C", fx=0.4, fy=0.3) if swollen else
         radial("#F7D9A8", "#D39A45", fx=0.4, fy=0.3))
    if fission:
        hL, hW = L / 2, Wd / 2
        d = (f"M{f(-hL)},0 C{f(-hL)},{f(-hW * 1.3)} {f(-hL * 0.1)},"
             f"{f(-hW * 1.2)} 0,{f(-hW * 0.35)} "
             f"C{f(hL * 0.1)},{f(-hW * 1.2)} {f(hL)},{f(-hW * 1.3)} "
             f"{f(hL)},0 C{f(hL)},{f(hW * 1.3)} {f(hL * 0.1)},{f(hW * 1.2)} "
             f"0,{f(hW * 0.35)} C{f(-hL * 0.1)},{f(hW * 1.2)} "
             f"{f(-hL)},{f(hW * 1.3)} {f(-hL)},0 Z")
    else:
        d = (f"M{f(-L / 2 + Wd / 2)},{f(-Wd / 2)} H{f(L / 2 - Wd / 2)} "
             f"A{f(Wd / 2)},{f(Wd / 2)} 0 0 1 {f(L / 2 - Wd / 2)},{f(Wd / 2)} "
             f"H{f(-L / 2 + Wd / 2)} A{f(Wd / 2)},{f(Wd / 2)} 0 0 1 "
             f"{f(-L / 2 + Wd / 2)},{f(-Wd / 2)} Z")
    add(f'<g transform="translate({f(cx)} {f(cy)}) rotate({rot})">')
    add(f'<path d="{d}" fill="{g}" stroke="#A9772F" stroke-width="1.6"/>')
    n = 5 if not swollen else 3
    for i in range(n):
        x = -L / 2 + L * (i + 1) / (n + 1)
        if swollen:
            add(f'<path d="M{f(x - 3)},{f(-Wd * 0.18)} q4,6 0,12" '
                f'stroke="#B78638" stroke-width="1.4" fill="none" '
                f'opacity="0.7"/>')
        elif fission and abs(x) < L * 0.08:
            continue
        else:
            add(f'<path d="M{f(x)},{f(-Wd * 0.42)} q-5,{f(Wd * 0.21)} 0,'
                f'{f(Wd * 0.42)} q5,{f(Wd * 0.21)} 0,{f(Wd * 0.42)}" '
                f'stroke="#B07A2E" stroke-width="1.6" fill="none"/>')
    add("</g>")


def star(cx, cy, r, color, op=1.0):
    pts = []
    for i in range(8):
        a = math.pi / 4 * i - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.38
        pts.append(f"{f(cx + rr * math.cos(a))},{f(cy + rr * math.sin(a))}")
    add(f'<polygon points="{" ".join(pts)}" fill="{color}" opacity="{op}"/>')


def collagen(x0, x1, y, n=5, gap=8.5, seed=5):
    rnd = random.Random(seed)
    for i in range(n):
        yy = y + i * gap
        ph = rnd.uniform(0, 6)
        amp = rnd.uniform(3, 5)
        pts = [(x, yy + amp * math.sin(x / 26 + ph) + 2 * math.sin(x / 9 + ph))
               for x in range(int(x0 + rnd.uniform(0, 30)),
                              int(x1 - rnd.uniform(0, 30)), 8)]
        d = smooth_open(pts)
        add(f'<path d="{d}" fill="none" stroke="{P["col_lo"]}" '
            f'stroke-width="6.4" stroke-linecap="round"/>')
        add(f'<path d="{d}" fill="none" stroke="{P["col_hi"]}" '
            f'stroke-width="3" stroke-linecap="round" opacity="0.9"/>')
        add(f'<path d="{d}" fill="none" stroke="{P["col_band"]}" '
            f'stroke-width="6.4" stroke-dasharray="1.6 5.2" opacity="0.45"/>')


# =================================================================== layout
A = dict(x=40, y=92, w=1210, h=262)
B = dict(x=40, y=374, w=1210, h=622)
Cc = dict(x=1340, y=92, w=420, h=904)

add(f'<rect width="{W}" height="{H}" fill="{BG}"/>')
text(42, 58, "Ionizing radiation injury to the skeletal muscle niche",
     size=33, weight=700, color=INK)

card(A["x"], A["y"], A["w"], A["h"], "a", "Acute DNA damage and cell fate")
card(B["x"], B["y"], B["w"], B["h"], "b", "Niche remodelling")
card(Cc["x"], Cc["y"], Cc["w"], Cc["h"], "c", "Long-term outcomes")

# ------------------------------------------------------------- panel a
ay = 238
# radiation beam: wavy photon tracks converging onto the fibre
for i, (sx, sy) in enumerate([(78, 150), (66, 196), (84, 246)]):
    ex, ey = 290, 212 + i * 22
    pts = []
    for k in range(41):
        t = k / 40
        x = sx + (ex - sx) * t
        y = sy + (ey - sy) * t
        dx, dy = ex - sx, ey - sy
        L = math.hypot(dx, dy)
        amp = 6 * math.sin(math.pi * t) ** 0.5
        w = amp * math.sin(t * 2 * math.pi * 4.2)
        pts.append((x - dy / L * w, y + dx / L * w))
    bg = linear([(0, P["beam"], 0.0), (0.35, P["beam"], 0.75),
                 (1, P["beam"], 1)], user=(sx, sy, ex, ey))
    add(f'<path d="{smooth_open(pts)}" fill="none" stroke="{bg}" '
        f'stroke-width="3.6" stroke-linecap="round"/>')
text(150, 312, "Ionizing radiation", size=16, weight=500, color="#9A6A16",
     anchor="middle")

fibre(300, 190, 640, 292, nuc_top=(390, 520, 610), nuc_bot=(455, 585),
      seed=2)
add(f'<rect x="560" y="186" width="84" height="122" '
    f'fill="{linear([(0, "#FFFFFF", 0), (1, "#FFFFFF", 1)], 0, 0, 1, 0)}"/>')
add(f'<rect x="300" y="190" width="340" height="102" '
    f'fill="{linear([(0, P["beam"], 0.22), (1, P["beam"], 0)], 0, 0, 1, 0)}"/>')
for (sx, sy, r) in [(352, 238, 6), (430, 262, 4.5), (500, 226, 5),
                    (560, 268, 4)]:
    star(sx, sy, r * 1.6, "#FFFFFF", op=0.85)
    star(sx, sy, r, P["ros"])

# zoom from a peripheral nucleus to the DNA lens
zx, zy, zr = 760, 228, 60
add(f'<path d="M610,191 L{zx - 34},{zy - 50} M610,204 L{zx - 50},{zy + 34}" '
    f'stroke="#9AA3AE" stroke-width="1.1" fill="none"/>')
add(f'<circle cx="610" cy="197.5" r="12" fill="none" stroke="#9AA3AE" '
    f'stroke-width="1.1"/>')
shadow(zx, zy + zr * 0.92, zr * 0.95, 10, op=0.8)
add(f'<circle cx="{zx}" cy="{zy}" r="{zr}" fill="{radial("#FFFFFF", "#EEF2F8", fx=0.4, fy=0.3)}" '
    f'stroke="#B8C2CF" stroke-width="1.5"/>')
for side in (-1, 1):
    xs = [zx + side * x for x in range(8, 50, 2)]
    for strand, col, ph in ((0, P["dna1"], 0), (1, P["dna2"], math.pi)):
        pts = [(x, zy - 4 + 15 * math.sin((x - zx) / 9.5 + ph)) for x in xs]
        add(f'<path d="{smooth_open(pts)}" fill="none" stroke="{col}" '
            f'stroke-width="4.4" stroke-linecap="round"/>')
    for x in range(10, 48, 6):
        xx = zx + side * x
        y1 = zy - 4 + 15 * math.sin((xx - zx) / 9.5)
        y2 = zy - 4 + 15 * math.sin((xx - zx) / 9.5 + math.pi)
        add(f'<line x1="{f(xx)}" y1="{f(y1)}" x2="{f(xx)}" y2="{f(y2)}" '
            f'stroke="#B9C8DD" stroke-width="1.6"/>')
star(zx, zy - 4, 9, "#D9534F")
star(zx - 22, zy + 32, 6.5, P["ros"])
star(zx + 20, zy + 36, 5, P["ros"])
star(zx + 30, zy - 38, 5, P["ros"])
text(zx, zy + zr + 30, "DNA DSB + ROS", size=17, weight=600,
     anchor="middle")

# DDR hub
dx_, dy_ = 920, ay - 10
shadow(dx_, dy_ + 40, 42, 9, op=0.9)
add(f'<circle cx="{dx_}" cy="{dy_}" r="42" '
    f'fill="{radial(P["ddr_hi"], P["ddr_lo"], fx=0.38, fy=0.3)}" '
    f'stroke="#3D4C6A" stroke-width="1.4"/>')
text(dx_, dy_ + 7, "DDR", size=20, weight=700, color="#FFFFFF",
     anchor="middle")
arrow((zx + zr + 6, dy_), (dx_ - 50, dy_), "thin")
text((zx + zr + dx_ - 50) / 2 + 2, dy_ - 12, "^{1}", size=17,
     color=MUTED, anchor="middle")

# fates
death = (1060, 160)
sen = (1060, 296)
arrow((dx_ + 36, dy_ - 22), (death[0] - 40, death[1] + 6), "thick",
      bend=-0.12)
arrow((dx_ + 36, dy_ + 22), (sen[0] - 46, sen[1] - 8), "thick", bend=0.12)
# apoptotic cell
shadow(death[0], death[1] + 26, 30, 7, op=0.8)
add(f'<path d="{blob(death[0], death[1], 26, 22, 0.13, 4)}" '
    f'fill="{radial(P["death_hi"], P["death_lo"])}" stroke="#93625E" '
    f'stroke-width="1.3"/>')
for (ox, oy, r) in [(-6, -4, 6), (6, 4, 5), (-2, 8, 3.5), (8, -8, 3.5)]:
    add(f'<circle cx="{death[0] + ox}" cy="{death[1] + oy}" r="{r}" '
        f'fill="#7B4D4A" opacity="0.85"/>')
for (ox, oy, r) in [(32, -16, 8), (36, 12, 6.5), (-30, 20, 6), (20, 28, 5)]:
    add(f'<circle cx="{death[0] + ox}" cy="{death[1] + oy}" r="{r}" '
        f'fill="{radial(P["death_hi"], P["death_lo"])}" stroke="#93625E" '
        f'stroke-width="1"/>')
text(death[0] + 58, death[1] + 6, "Cell death", size=17, weight=600)
# senescent cell
shadow(sen[0], sen[1] + 26, 44, 8, op=0.8)
add(f'<path d="{blob(sen[0], sen[1], 44, 25, 0.12, 9, n=16)}" '
    f'fill="{radial(P["sen_hi"], "#A994CB", fx=0.38, fy=0.3)}" '
    f'stroke="#6D5596" stroke-width="1.3"/>')
nucleus(sen[0] - 2, sen[1], 19, 13, fill=radial("#F3EEF9", P["sen"]),
        edge="#5E4787")
text(sen[0] - 2, sen[1] + 4.5, "p21", size=12, weight=700, color="#FFFFFF",
     anchor="middle")
rnd = random.Random(7)
for k in range(9):
    a = -0.9 + k * 0.32
    d = 54 + rnd.uniform(0, 14)
    add(f'<circle cx="{f(sen[0] + d * math.cos(a))}" '
        f'cy="{f(sen[1] + d * 0.62 * math.sin(a))}" r="{f(rnd.uniform(2.2, 3.6))}" '
        f'fill="{P["sen"]}" opacity="0.75"/>')
text(sen[0] + 80, sen[1] - 4, "p21^{+} senescence\n+ SASP^{3}", size=17,
     weight=600)

# ------------------------------------------------------------- panel b
bx0, by0 = B["x"], B["y"]
cid = uid("clip")
defs.append(f'<clipPath id="{cid}"><rect x="{B["x"]}" y="{B["y"]}" '
            f'width="{B["w"]}" height="{B["h"]}" rx="22"/></clipPath>')
add(f'<g clip-path="url(#{cid})">')

FA = (140, 432, 1250, 566)    # upper myofibre
FB = (140, 898, 1250, 1032)   # lower myofibre

# interstitial tint
add(f'<rect x="{B["x"]}" y="{FA[3]}" width="{B["w"]}" '
    f'height="{FB[1] - FA[3]}" fill="#FBF6EF"/>')

ghosts = [(232, 60, 18), (330, 60, 18)]
fibre(*FA, nuc_top=(300, 520, 760, 1000, 1200),
      nuc_bot=(430, 680, 900, 1120), seed=3)
lamina(FA[0], 1250, FA[3], ghosts, down=True)
lamina(FA[0], 1250, FA[1], [], down=False)
for gx, L, hg in ghosts:
    satellite(gx, FA[3], L, hg, ghost=True)

reserve = [(250, 66, 20, "r"), (352, 52, 16, "d"), (440, 52, 16, "d")]
fibre(*FB, nuc_top=(560, 820, 1060), nuc_bot=(), seed=4)
lamina(FB[0], 1250, FB[1], [(x, L, h) for x, L, h, _ in reserve], down=False)
for x, L, hg, k in reserve:
    satellite(x, FB[1], L, hg, kind="rsc", down=False)

add("</g>")

text(196, 506, "Myofibre", size=15, weight=600, color="#6E3A31", pill=True)
text(196, 972, "Myofibre", size=15, weight=600, color="#6E3A31", pill=True)
text(1236, 596, "basal lamina", size=13.5, color=P["lamina"],
     anchor="end", italic=True)

text(281, 626, "Satellite cells \u2193^{2}", size=17, weight=600,
     anchor="middle", color="#3F6E9C")
arrow((282, 858), (342, 858), "thick", bend=0.35)
arrow((370, 858), (426, 858), "thick", bend=0.35)
text(292, 796, "Reserve Mx1^{+} Pax3^{high} SC\nlow ROS \u00b7 survives, re-expands^{4}",
     size=16, weight=600, anchor="middle", color="#2B7A62")

# FAP + macrophage + TGF-beta
fx_, fy_ = 690, 712
fap(fx_, fy_, scale=1.0)
text(fx_ - 40, fy_ + 66, "Senescent, fibrogenic FAP^{2}", size=17,
     weight=600, anchor="middle", color="#8A5F22")
rec = (fx_ + 64, fy_ - 21)
receptor(*rec, ang=-70)
mx, my = 900, 650
macrophage(mx, my)
text(mx + 2, my - 58, "Macrophage", size=16, weight=600, anchor="middle",
     color="#6F5899")
arrow((mx - 40, my + 18), (rec[0] + 10, rec[1] - 24), "dashed", bend=-0.25)
for t in (0.3, 0.55):
    ligand(mx - 40 + (rec[0] + 10 - mx + 40) * t,
           my + 18 + (rec[1] - 24 - my - 18) * t + 12)
text(mx + 22, my + 76, "TGF-\u03b2 \u2192 TGF-\u03b2R2^{3}", size=15.5,
     weight=600, anchor="middle", color="#5E4787")

# SASP / secretome dots + inhibition of SC differentiation
for (ox, oy) in [(-140, 30), (-158, 44), (-178, 16), (-196, 38)]:
    add(f'<circle cx="{fx_ + ox}" cy="{fy_ + oy}" r="3.2" fill="{P["sen"]}" '
        f'opacity="0.7"/>')
arrow((fx_ - 166, fy_ + 22), (474, 860), "thick", bend=-0.2, inhibit=True)
text(478, 730, "inhibits SC\ndifferentiation / fusion^{2}", size=15.5,
     anchor="end", color="#4A5563")

# collagen / ECM
collagen(600, 1000, 822, n=5)
arrow((fx_ + 104, fy_ + 6), (fx_ + 150, 812), "thick", bend=-0.25)
text(918, 880, "Collagen / ECM^{2,3}", size=16, weight=600, anchor="middle",
     color="#8A6A3A")

# capillary with endothelium, pericyte, leak
add(f'<g clip-path="url(#{cid})">')
vy, vr = 728, 40
vx0, vx1 = 1040, 1260
shadow((vx0 + vx1) / 2, vy + vr + 6, 120, 10, op=0.8)
vg = linear([(0, P["ves_lo"], 1), (0.25, P["ves_hi"], 1),
             (0.7, "#E8A39E", 1), (1, "#B9605B", 1)],
            user=(0, vy - vr, 0, vy + vr))
add(f'<rect x="{vx0}" y="{vy - vr}" width="{vx1 - vx0}" height="{2 * vr}" '
    f'fill="{vg}"/>')
add(f'<line x1="{vx0}" y1="{vy - vr}" x2="{vx1}" y2="{vy - vr}" '
    f'stroke="{P["ves_edge"]}" stroke-width="1.4"/>')
add(f'<line x1="{vx0}" y1="{vy + vr}" x2="{vx1}" y2="{vy + vr}" '
    f'stroke="{P["ves_edge"]}" stroke-width="1.4"/>')
seams = [1092, 1150, 1206]
for i, sx in enumerate(seams):
    add(f'<path d="M{sx},{vy - vr} Q{sx + 12},{vy} {sx},{vy + vr}" '
        f'stroke="{P["ves_edge"]}" stroke-width="1.1" fill="none" '
        f'opacity="0.7"/>')
for nx_ in (1066, 1180, 1232):
    nucleus(nx_, vy - 4, 13, 6.5, fill=radial("#F6D9D6", "#B3605B"),
            edge="#97504B")
# lost endothelial cell: gap exposing the lumen
gap_d = (f"M1104,{vy - 26} C1120,{vy - 34} 1142,{vy - 30} 1146,{vy - 10} "
         f"C1150,{vy + 12} 1136,{vy + 34} 1116,{vy + 30} "
         f"C1098,{vy + 26} 1094,{vy - 14} 1104,{vy - 26} Z")
add(f'<path d="{gap_d}" fill="{radial("#B4554F", P["lumen"])}" '
    f'stroke="{P["ves_edge"]}" stroke-width="1.2"/>')
add(f'<ellipse cx="1122" cy="{vy + 2}" rx="11" ry="7" fill="{P["rbc"]}" '
    f'stroke="#9B3532" stroke-width="1"/>')
add(f'<ellipse cx="1122" cy="{vy + 2}" rx="4.5" ry="2.6" fill="#A43C38" '
    f'opacity="0.6"/>')
# leak
for (lx, ly, r) in [(1112, vy + 54, 3), (1128, vy + 64, 2.6),
                    (1104, vy + 72, 2.2), (1136, vy + 80, 2),
                    (1118, vy + 86, 1.8)]:
    add(f'<circle cx="{lx}" cy="{ly}" r="{r}" fill="#D9827D" opacity="0.8"/>')
add(f'<ellipse cx="1146" cy="{vy + 58}" rx="8.5" ry="5" fill="{P["rbc"]}" '
    f'opacity="0.85" transform="rotate(20 1146 {vy + 58})"/>')
# cut face (lumen) at the left end
add(f'<ellipse cx="{vx0}" cy="{vy}" rx="13" ry="{vr}" '
    f'fill="{radial("#F6C9C4", "#D98A84")}" stroke="{P["ves_edge"]}" '
    f'stroke-width="1.4"/>')
add(f'<ellipse cx="{vx0}" cy="{vy}" rx="8" ry="{vr - 8}" '
    f'fill="{radial("#A84A45", P["lumen"])}"/>')
add(f'<ellipse cx="{vx0 + 1}" cy="{vy + 6}" rx="4" ry="8" fill="{P["rbc"]}"/>')
# pericyte wrapping the vessel
per = (f"M1168,{vy - vr - 2} C1176,{vy - vr - 16} 1206,{vy - vr - 16} "
       f"1214,{vy - vr - 2} C1230,{vy - vr + 4} 1244,{vy - vr + 18} "
       f"1250,{vy - vr + 34} L1244,{vy - vr + 36} "
       f"C1236,{vy - vr + 22} 1226,{vy - vr + 10} 1210,{vy - vr + 6} "
       f"C1196,{vy - vr + 4} 1184,{vy - vr + 4} 1172,{vy - vr + 8} "
       f"C1160,{vy - vr + 14} 1152,{vy - vr + 26} 1148,{vy - vr + 38} "
       f"L1142,{vy - vr + 36} C1146,{vy - vr + 20} 1154,{vy - vr + 4} "
       f"1168,{vy - vr - 2} Z")
add(f'<path d="{per}" fill="{radial(P["per_hi"], P["per_lo"], fx=0.4, fy=0.2)}" '
    f'stroke="{P["per_edge"]}" stroke-width="1.2"/>')
nucleus(1191, vy - vr - 4, 11, 5.5, fill=radial("#EEF4E8", P["per_edge"]),
        edge=P["per_edge"])
add("</g>")
text(1044, vy - vr - 14, "Capillary", size=16, weight=600,
     color="#A0504B")
text(1180, vy + vr + 72, "EC loss^{2} \u00b7 leaky^{5}", size=15.5,
     weight=600, anchor="middle", color="#A0504B")
text(1240, vy - vr - 26, "pericyte", size=13.5, italic=True,
     color=P["per_edge"], anchor="end")

# swollen mitochondria zoom (myofibre, EM)
mzx, mzy, mzr = 1080, 498, 50
add(f'<circle cx="1000" cy="520" r="9" fill="none" stroke="#9AA3AE" '
    f'stroke-width="1.1"/>')
add(f'<path d="M1008,516 L{mzx - mzr + 2},{mzy + 6}" stroke="#9AA3AE" '
    f'stroke-width="1.1"/>')
shadow(mzx, mzy + mzr * 0.95, mzr * 0.9, 8, op=0.8)
add(f'<circle cx="{mzx}" cy="{mzy}" r="{mzr}" fill="#FFF9F1" '
    f'stroke="#C9B48E" stroke-width="1.5"/>')
mito(mzx - 10, mzy - 14, 52, 30, rot=-12, swollen=True)
mito(mzx + 14, mzy + 18, 44, 26, rot=8, swollen=True)
text(mzx + mzr + 12, mzy - 6, "Swollen\nmitochondria^{5}", size=15.5,
     weight=600, color="#8A6A3A", pill=True)

# ------------------------------------------------------------- a -> b link
arrow((sen[0] - 10, sen[1] + 38), (sen[0] - 10, B["y"] + 46), "thick",
      bend=0.0)
text(sen[0] + 6, B["y"] + 4, "all resident cell types^{3}", size=14.5,
     color="#4A5563")

# ------------------------------------------------------------- panel c
ccx = Cc["x"] + Cc["w"] / 2 + 14
# 1. fascicle cross-section: atrophic fibres in a collagen-rich matrix
fcx, fcy = ccx, 262
shadow(fcx, fcy + 96, 100, 12, op=0.9)
add(f'<path d="{blob(fcx, fcy, 100, 88, 0.05, 21, n=18)}" '
    f'fill="{radial(P["col_hi"], P["col_lo"], fx=0.4, fy=0.3)}" '
    f'stroke="#A88250" stroke-width="1.5"/>')
fcid = uid("clip")
defs.append(f'<clipPath id="{fcid}"><path d="{blob(fcx, fcy, 96, 84, 0.05, 21, n=18)}"/></clipPath>')
add(f'<g clip-path="url(#{fcid})">')
rnd = random.Random(31)
for k in range(10):
    yy = fcy - 84 + k * 18
    pts = [(x, yy + 3 * math.sin(x / 9 + k)) for x in range(int(fcx - 100),
                                                          int(fcx + 100), 8)]
    add(f'<path d="{smooth_open(pts)}" fill="none" stroke="#FFFFFF" '
        f'stroke-width="1" opacity="0.35"/>')
sp = 33
for row in range(-3, 4):
    for col in range(-3, 4):
        ox = col * sp + (sp / 2 if row % 2 else 0) + rnd.uniform(-3, 3)
        oy = row * sp * 0.87 + rnd.uniform(-3, 3)
        if (ox / 92) ** 2 + (oy / 80) ** 2 > 1:
            continue
        r = rnd.uniform(11, 13.8)
        cxp, cyp = fcx + ox, fcy + oy
        add(f'<path d="{blob(cxp, cyp, r, r * 0.95, 0.1, 40 + row * 9 + col, n=6, rot=rnd.uniform(0, 1))}" '
            f'fill="{radial("#F6DACF", "#C98374", fx=0.38, fy=0.32)}" '
            f'stroke="{P["fibre_edge"]}" stroke-width="1.1"/>')
        a = rnd.uniform(0, 2 * math.pi)
        nucleus(cxp + (r - 3.5) * math.cos(a), cyp + (r - 3.5) * math.sin(a),
                3.2, 2.2, rot=math.degrees(a) + 90)
add("</g>")
add(f'<path d="{blob(fcx, fcy, 96, 84, 0.05, 21, n=18)}" fill="none" '
    f'stroke="#A88250" stroke-width="5" opacity="0.55"/>')
text(ccx, 394, "Persistent fibrosis\n+ myofibre atrophy^{2}", size=18,
     weight=700, anchor="middle")

# 2. long-term mitochondrial / insulin-resistance changes
my2 = 548
add(f'<ellipse cx="{ccx}" cy="{my2}" rx="128" ry="62" '
    f'fill="{radial("#FFFCF5", "#F6EBD6", fx=0.4, fy=0.3)}" '
    f'stroke="#E7D5B0" stroke-width="1.3"/>')
mito(ccx - 62, my2 - 12, 66, 28, rot=-14, fission=True)
mito(ccx + 8, my2 + 18, 58, 24, rot=10)
mito(ccx + 70, my2 - 18, 48, 22, rot=-28)
text(ccx, 644, "Long-term mitochondrial &\ninsulin-resistance changes^{6}",
     size=18, weight=700, anchor="middle")
text(ccx, 693, "rhesus macaque", size=14.5, italic=True, color=MUTED,
     anchor="middle")

# 3. clinical radiation fibrosis syndrome
hx, hy = ccx, 800
shadow(hx, hy + 92, 54, 9, op=0.9)
hum = radial("#DDE3EA", "#9AA6B5", fx=0.4, fy=0.25)
add(f'<circle cx="{hx}" cy="{hy - 58}" r="15" fill="{hum}" stroke="#7D8A9B" '
    f'stroke-width="1.2"/>')
torso = (f"M{hx - 22},{hy - 36} C{hx - 30},{hy - 36} {hx - 32},{hy - 28} "
         f"{hx - 33},{hy - 18} L{hx - 37},{hy + 18} C{hx - 38},{hy + 24} "
         f"{hx - 28},{hy + 25} {hx - 27},{hy + 18} L{hx - 23},{hy - 8} "
         f"L{hx - 20},{hy + 16} L{hx - 22},{hy + 86} "
         f"C{hx - 22},{hy + 92} {hx - 8},{hy + 92} {hx - 8},{hy + 86} "
         f"L{hx - 3},{hy + 30} L{hx + 3},{hy + 30} L{hx + 8},{hy + 86} "
         f"C{hx + 8},{hy + 92} {hx + 22},{hy + 92} {hx + 22},{hy + 86} "
         f"L{hx + 20},{hy + 16} L{hx + 23},{hy - 8} L{hx + 27},{hy + 18} "
         f"C{hx + 28},{hy + 25} {hx + 38},{hy + 24} {hx + 37},{hy + 18} "
         f"L{hx + 33},{hy - 18} C{hx + 32},{hy - 28} {hx + 30},{hy - 36} "
         f"{hx + 22},{hy - 36} Z")
add(f'<path d="{torso}" fill="{hum}" stroke="#7D8A9B" stroke-width="1.2"/>')
add(f'<rect x="{hx + 5}" y="{hy + 34}" width="20" height="30" rx="6" '
    f'fill="{P["beam"]}" opacity="0.45" stroke="#C98A20" stroke-width="1.2"/>')
text(ccx, 922, "Radiation fibrosis syndrome^{7}", size=18, weight=700,
     anchor="middle")
text(ccx, 948, "clinical", size=14.5, italic=True, color=MUTED,
     anchor="middle")

# ------------------------------------------------------------- b -> c
arrow((1254, 600), (Cc["x"] + 20, 262), "thick", bend=-0.18)
arrow((1254, 690), (Cc["x"] + 26, my2), "thick", bend=-0.1)
arrow((1254, 780), (hx - 62, hy + 10), "thin", bend=0.1)

# ------------------------------------------------------------- legend
ly = 1030
text(42, ly + 6, "Evidence", size=15.5, weight=700)
items = [("thick", "irradiated muscle, in vivo"),
         ("thin", "other tissue or review"),
         ("dashed", "proposed / inferred")]
x = 132
for kind, lab in items:
    arrow((x, ly), (x + 52, ly), kind, halo=False)
    text(x + 64, ly + 5.5, lab, size=14.5, color="#3F4A57")
    x += 64 + len(lab) * 8.0 + 34
arrow((x, ly), (x + 44, ly), "thick", inhibit=True, halo=False, bar=0.42)
text(x + 58, ly + 5.5, "inhibition", size=14.5, color="#3F4A57")

refs = ("^{1}Jackson & Bartek, Nature 2009   ^{2}Collao et al., J Cachexia "
        "Sarcopenia Muscle 2023   ^{3}Collao et al., Am J Physiol Cell "
        "Physiol 2025   ^{4}Scaramozza et al., Cell Stem Cell 2019\n"
        "^{5}Zhou et al., Radiat Oncol 2018 (rat)   ^{6}Lee et al., Radiat "
        "Res 2025 (rhesus)   ^{7}Stubblefield, PM&R 2011   \u00b7   mouse "
        "unless stated   \u00b7   fibrosis shown as persistent, not "
        "irreversible")
text(42, ly + 34, refs, size=12.5, color=MUTED, lh=1.45)

# =================================================================== write
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="12in" '
       f'height="{H / W * 12:.4f}in" viewBox="0 0 {W} {H}">'
       f'<defs>{"".join(defs)}</defs>{"".join(body)}</svg>')
svg_path = OUT / f"{STEM}.svg"
svg_path.write_text(svg, encoding="utf-8")
png_path = OUT / f"{STEM}.png"
cairosvg.svg2png(bytestring=svg.encode(), write_to=str(png_path),
                 output_width=PX_W, output_height=PX_H)
im = Image.open(png_path).convert("RGB")
im.save(png_path, dpi=(300, 300))
cairosvg.svg2pdf(bytestring=svg.encode(), write_to=str(OUT / f"{STEM}.pdf"))
print("wrote", svg_path, png_path, OUT / f"{STEM}.pdf", im.size)
