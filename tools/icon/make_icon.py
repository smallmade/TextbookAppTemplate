#!/usr/bin/env python3
"""The application icon for every app in the series, drawn rather than stored.

Why a generator and not a folder of PNGs
----------------------------------------
An icon has to exist at eleven sizes and be the same drawing at all of them.
Eleven stored files are eleven chances for one size to drift out of step, and
nothing reports it. One drawing plus one rebuild command cannot drift.

The series shares one visual language
-------------------------------------
Four applications will sit in one Dock. They share the ground (a dark vertical
gradient), the ink (one near-white engineering figure, no text, no gloss) and
the shape (Apple's squircle on macOS; full bleed on iOS, where the system
applies the mask itself). **Only the figure and the hue change.** That is what
makes them read as a family rather than as four unrelated purchases.

What the figure has to survive
------------------------------
Sixteen points. Not 1024 -- at 1024 anything looks considered. This script
writes a contact sheet with the icon at 128, 64, 32 and 16 beside the large
one, because that row is what decides whether a figure works. A circle with a
line through it was rejected on that row: at 32 points it reads as a
prohibition sign.

Adding an application
---------------------
Write one function in `GLYPHS` and one entry in `PALETTES`. Nothing else.

    python3 tools/icon/make_icon.py --app mechanicsone --out build/icon
"""
from __future__ import annotations

import argparse
import math
import pathlib

from PIL import Image, ImageDraw

SUPERSAMPLE = 8
INK = (247, 249, 252)
#: macOS draws the icon exactly as given, so the squircle and the air around it
#: are ours to draw. Apple's own icons sit on about this much.
MAC_MARGIN = 0.085

#: One hue per application, all at the same weight so they sit together.
PALETTES = {
    "steel":  ((36, 52, 84), (18, 26, 46)),     # MechanicsOne  · members and sections
    "slate":  ((30, 62, 70), (14, 30, 36)),     # StructureMechOne · frames and trusses
    "ember":  ((84, 47, 30), (40, 20, 14)),     # ThermoOne · heat and cycles
    "ink":    ((44, 44, 52), (20, 20, 26)),     # spare
}


def _lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _ground(size: int, palette: str) -> Image.Image:
    top, bottom = PALETTES[palette]
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        draw.line([(0, y), (size, y)],
                  fill=_lerp(top, bottom, y / max(size - 1, 1)))
    return img


def _squircle(size: int, margin: float, n: float = 5.0) -> Image.Image:
    """A superellipse. Apple's icon outline is not a rounded rectangle, and at
    n = 5 the difference is under one pixel at 1024 -- but visible in a Dock
    beside real system icons, which is where it matters."""
    inset = size * margin
    side = size - 2 * inset
    cx = cy = size / 2
    a = b = side / 2
    points = []
    for i in range(2048):
        t = 2 * math.pi * i / 2048
        ct, st = math.cos(t), math.sin(t)
        points.append((cx + a * math.copysign(abs(ct) ** (2 / n), ct),
                       cy + b * math.copysign(abs(st) ** (2 / n), st)))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    return mask


def _stroke(draw, points, width, ink):
    """A polyline with round joins. PIL's own `width=` leaves the joins on a
    curve visibly faceted; drawn as quads plus discs at 8x supersample it does
    not."""
    r = width / 2
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        nx, ny = -dy / length * r, dx / length * r
        draw.polygon([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
                      (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], fill=ink)
    for (x, y) in points:
        draw.ellipse([x - r, y - r, x + r, y + r], fill=ink)


# ------------------------------------------------------------------ figures

def glyph_section(draw, S, ink):
    """MechanicsOne: an I-section seen end on, with its neutral axis.

    This application is about one member at a time -- a section, and the axis
    every bending stress in it is measured from. The axis is two short heavy
    stubs rather than a dashed line: a dashed line dissolves into noise below
    32 points, and the small row is the row that decides.
    """
    web, flange_w, flange_t, depth = S * 0.125, S * 0.50, S * 0.115, S * 0.54
    cx = cy = S / 2
    draw.rectangle([cx - flange_w / 2, cy - depth / 2,
                    cx + flange_w / 2, cy - depth / 2 + flange_t], fill=ink)
    draw.rectangle([cx - flange_w / 2, cy + depth / 2 - flange_t,
                    cx + flange_w / 2, cy + depth / 2], fill=ink)
    draw.rectangle([cx - web / 2, cy - depth / 2, cx + web / 2, cy + depth / 2],
                   fill=ink)
    stub = S * 0.030
    for side in (-1, 1):
        near = cx + side * (flange_w / 2 + S * 0.045)
        far = cx + side * (flange_w / 2 + S * 0.155)
        draw.rectangle([min(near, far), cy - stub / 2,
                        max(near, far), cy + stub / 2], fill=ink)


def glyph_truss(draw, S, ink):
    """StructureMechOne: a Warren truss panel on two supports.

    A structure is members meeting at joints, which is exactly what this
    application takes as input and what the sibling application does not. Three
    bays keep the silhouette readable at 16 points; more become a texture.
    """
    left, right = S * 0.145, S * 0.855
    top_y, bottom_y = S * 0.335, S * 0.635
    t = S * 0.052
    span = right - left
    # top and bottom chords
    _stroke(draw, [(left, bottom_y), (right, bottom_y)], t, ink)
    _stroke(draw, [(left + span / 6, top_y), (right - span / 6, top_y)], t, ink)
    # web: the zigzag that makes it a truss and not a beam
    xs = [left, left + span / 6, left + span / 2, right - span / 6, right]
    ys = [bottom_y, top_y, bottom_y, top_y, bottom_y]
    _stroke(draw, list(zip(xs, ys)), t, ink)
    # joints
    r = t * 0.95
    for x, y in zip(xs, ys):
        draw.ellipse([x - r, y - r, x + r, y + r], fill=ink)
    # supports: pin and roller, the pair that makes it determinate
    s = S * 0.082
    draw.polygon([(left, bottom_y + t / 2),
                  (left - s * 0.85, bottom_y + t / 2 + s),
                  (left + s * 0.85, bottom_y + t / 2 + s)], fill=ink)
    rr = s * 0.46
    draw.ellipse([right - rr, bottom_y + t / 2 + s - 2 * rr,
                  right + rr, bottom_y + t / 2 + s], fill=ink)
    ground_y = bottom_y + t / 2 + s + S * 0.030
    draw.rectangle([left - s * 1.15, ground_y - t * 0.32,
                    right + s * 1.15, ground_y + t * 0.32], fill=ink)


def glyph_cycle(draw, S, ink):
    """ThermoOne: a closed cycle on a temperature-entropy plane.

    A cycle is a loop that returns to its own starting state, and the area it
    encloses is the work. Drawn as the Rankine shape -- two isobars joined by
    two near-vertical legs, with the dome's knee on the left -- rather than as
    a generic oval, because the knee is what makes it read as thermodynamics
    and not as a refresh symbol.
    """
    t = S * 0.050
    # axes: entropy across, temperature up
    ax_l, ax_b = S * 0.175, S * 0.795
    _stroke(draw, [(ax_l, S * 0.175), (ax_l, ax_b), (S * 0.845, ax_b)], t * 0.72, ink)
    # the loop
    loop = [
        (S * 0.285, S * 0.640),   # pump exit, compressed liquid
        (S * 0.285, S * 0.395),   # boiler, up the left leg
        (S * 0.420, S * 0.300),   # through the knee onto the top isobar
        (S * 0.700, S * 0.300),   # superheat, along the top
        (S * 0.700, S * 0.640),   # turbine, down the right leg
        (S * 0.285, S * 0.640),   # condenser, back along the bottom
    ]
    _stroke(draw, loop + [loop[0]], t, ink)
    # the state you are looking at
    dot = S * 0.055
    px, py = S * 0.700, S * 0.300
    draw.ellipse([px - dot, py - dot, px + dot, py + dot], fill=ink)


GLYPHS = {"section": glyph_section, "truss": glyph_truss, "cycle": glyph_cycle}

#: Which figure and hue each application uses, and what its .icns is called.
APPS = {
    "mechanicsone":     ("section", "steel", "MechanicsOne"),
    "structuremechone": ("truss",   "slate", "StructureMechOne"),
    "thermoone":        ("cycle",   "ember", "ThermoOne"),
}


def render(glyph: str, palette: str, size: int = 1024):
    """Returns (ios, mac). iOS is full bleed; macOS carries its own shape."""
    S = size * SUPERSAMPLE
    base = _ground(S, palette)
    GLYPHS[glyph](ImageDraw.Draw(base), S, INK)
    ios = base.resize((size, size), Image.LANCZOS)
    mac_full = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    mac_full.paste(base, (0, 0), _squircle(S, MAC_MARGIN))
    return ios, mac_full.resize((size, size), Image.LANCZOS)


#: macOS wants this ladder as an .iconset; `iconutil` turns it into an .icns.
MAC_LADDER = [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2),
              (256, 1), (256, 2), (512, 1), (512, 2)]
#: The distinct pixel sizes the asset catalogue references.
CATALOGUE_SIZES = (16, 32, 64, 128, 256, 512, 1024)


def write_all(out: pathlib.Path, app: str, catalogue: pathlib.Path | None = None):
    glyph, palette, _ = APPS[app]
    out.mkdir(parents=True, exist_ok=True)
    ios, mac = render(glyph, palette)

    ios.save(out / "icon-ios-1024.png")
    mac.save(out / "icon-mac-1024.png")

    iconset = out / "AppIcon.iconset"
    iconset.mkdir(exist_ok=True)
    for point, scale in MAC_LADDER:
        px = point * scale
        suffix = "" if scale == 1 else "@2x"
        mac.resize((px, px), Image.LANCZOS).save(
            iconset / f"icon_{point}x{point}{suffix}.png")

    if catalogue is not None:
        catalogue.mkdir(parents=True, exist_ok=True)
        ios.save(catalogue / "icon-ios-1024.png")
        for px in CATALOGUE_SIZES:
            mac.resize((px, px), Image.LANCZOS).save(
                catalogue / f"icon-mac-{px}.png")

    sheet = Image.new("RGB", (1024, 1024 + 200), (250, 250, 252))
    sheet.paste(ios, (0, 0))
    x = 40
    for px in (128, 64, 32, 16):
        sheet.paste(ios.resize((px, px), Image.LANCZOS),
                    (x, 1024 + 36 + (128 - px) // 2))
        x += px + 40
    sheet.save(out / "contact-sheet.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, choices=sorted(APPS))
    parser.add_argument("--out", default="build/icon", type=pathlib.Path)
    parser.add_argument("--catalogue", type=pathlib.Path, default=None,
                        help="AppIcon.appiconset directory to refresh as well")
    args = parser.parse_args()
    write_all(args.out, args.app, args.catalogue)
    print(f"{args.app} icon written to {args.out}")
