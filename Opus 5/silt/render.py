"""Drawing the map.

The output is a hybrid, because the two halves of a map want opposite things.

The **ground** -- hypsometric colour, biome tint, hillshade, the sandy rim where
land meets sea -- is millions of independent samples. As vectors that is a
hundred megabytes of unusable SVG; as a raster it is a few hundred kilobytes.
So the ground is rendered to a PNG and embedded as a data URI.

The **linework** -- coast, contours, rivers, lakes, graticule, labels -- is a few
thousand carefully placed strokes that must stay crisp at any zoom, and that a
reader might want to restyle. So it stays vector, laid over the raster.

Everything in one self-contained SVG file with no external references.

Two things do most of the visual work:

* **Hillshade.** A Lambertian term from the height gradient, light from the
  north-west at 45 degrees. Without it, an eroded heightfield and a smooth one
  look nearly identical; with it, every valley the erosion cut becomes visible.
* **Coastal blending.** Water cells carry the *shore* colour in the land raster,
  so bilinear interpolation fades the land to sand as it approaches the sea
  instead of fading it to blue. The beach comes out of the interpolation for
  free, and follows the true coastline exactly.
"""

from __future__ import annotations

import math

from . import png as png_mod
from .climate import BIOMES, LEGEND_ORDER
from .contour import contours, simplify, smooth
from .features import elongation
from .util import clamp, lerp

# -- palette --------------------------------------------------------------

PAPER = (0xF4, 0xEF, 0xE2)
PAPER_EDGE = (0xE6, 0xDE, 0xCA)
INK = "#2f2c26"
INK_SOFT = "#6b6558"
WATER_INK = "#3c6d84"
RIVER_INK = "#2b657f"
CONTOUR_INK = "#6f5f42"
BATHY_INK = "#7ea8bd"
HALO = "#f6f2e6"

# Depth ramp, shore to abyss. The first stops are close together on purpose:
# spread them out and every coast wears a wide neon collar of shallows.
OCEAN_STOPS = (
    (0.00, (0x93, 0xBD, 0xC9)),
    (0.03, (0x77, 0xA8, 0xBD)),
    (0.09, (0x57, 0x8B, 0xA8)),
    (0.24, (0x3E, 0x71, 0x92)),
    (0.55, (0x2B, 0x55, 0x75)),
    (1.00, (0x1E, 0x3D, 0x59)),
)

# The sand the land fades to at the waterline.
SHORE = (0xE2, 0xD6, 0xB0)

# Hypsometric tint by relative elevation, blended over the biome colours.
# Biome alone reads as a thematic overlay; a little elevation tint underneath is
# what makes a sheet read as *terrain*, and it ties disparate biomes into one
# palette so the map looks composed rather than assembled.
HYPSOMETRIC = (
    (0.00, (0x9E, 0xB8, 0x86)),
    (0.14, (0xBD, 0xC6, 0x86)),
    (0.32, (0xD8, 0xC7, 0x8B)),
    (0.52, (0xD2, 0xAB, 0x74)),
    (0.72, (0xB6, 0x8A, 0x60)),
    (0.88, (0xA2, 0x86, 0x72)),
    (1.00, (0xEC, 0xEE, 0xEC)),
)
HYPSO_MIX = 0.30


def ramp(stops, t: float):
    """Piecewise-linear colour interpolation over ``(position, rgb)`` stops."""
    t = clamp(t)
    previous_pos, previous_rgb = stops[0]
    for pos, rgb in stops:
        if t <= pos:
            span = pos - previous_pos
            f = 0.0 if span <= 0.0 else (t - previous_pos) / span
            return (
                lerp(previous_rgb[0], rgb[0], f),
                lerp(previous_rgb[1], rgb[1], f),
                lerp(previous_rgb[2], rgb[2], f),
            )
        previous_pos, previous_rgb = pos, rgb
    return previous_rgb


def hexcolour(rgb) -> str:
    r, g, b = (int(clamp(v, 0, 255)) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


# -- the ground raster ----------------------------------------------------


def _land_base(world):
    """Per-cell land colour, with water cells holding the shore colour.

    That substitution is the whole trick behind the beaches: the interpolator
    walks a land pixel's colour toward sand as it nears the coast, because sand
    is what its seaward neighbours contain.
    """
    n = len(world.height.data)
    reds = [0.0] * n
    greens = [0.0] * n
    blues = [0.0] * n
    land = world.land_mask
    biomes = world.climate.biome
    moisture = world.climate.moisture.data

    for i in range(n):
        if not land[i]:
            reds[i], greens[i], blues[i] = SHORE
            continue
        r, g, b = BIOMES[biomes[i]][1]
        elevation = world.relative_elevation(i)

        tint = ramp(HYPSOMETRIC, elevation)
        r = lerp(r, tint[0], HYPSO_MIX)
        g = lerp(g, tint[1], HYPSO_MIX)
        b = lerp(b, tint[2], HYPSO_MIX)

        # Height desaturates and lightens: haze, thinner soil, more rock.
        pale = 0.11 * elevation ** 1.6
        r = lerp(r, 0xC8, pale)
        g = lerp(g, 0xC4, pale)
        b = lerp(b, 0xB4, pale)

        # Damp ground reads a little deeper and cooler.
        wet = (moisture[i] - 0.5) * 0.10
        r *= 1.0 - wet
        g *= 1.0 - wet * 0.35
        b *= 1.0 - wet * 0.15

        reds[i], greens[i], blues[i] = r, g, b
    return reds, greens, blues


def raster(world, scale: int = 4, shade: float = 0.90, grain: float = 0.7):
    """Render the ground to RGB bytes. Returns ``(width, height, pixels)``."""
    w, h = world.width, world.height_cells
    out_w, out_h = w * scale, h * scale
    sea = world.sea_level
    hd = world.height.data

    # Column and row sample weights, computed once.
    cols = []
    for px in range(out_w):
        fx = (px + 0.5) / scale - 0.5
        fx = clamp(fx, 0.0, w - 1.0)
        x0 = int(fx)
        x1 = x0 + 1 if x0 < w - 1 else x0
        cols.append((x0, x1, fx - x0))
    rows = []
    for py in range(out_h):
        fy = (py + 0.5) / scale - 0.5
        fy = clamp(fy, 0.0, h - 1.0)
        y0 = int(fy)
        y1 = y0 + 1 if y0 < h - 1 else y0
        rows.append((y0 * w, y1 * w, fy - y0))

    # Pass one: the heightfield at output resolution, for shading.
    big = [0.0] * (out_w * out_h)
    p = 0
    for r0, r1, ty in rows:
        for x0, x1, tx in cols:
            top = hd[r0 + x0] * (1.0 - tx) + hd[r0 + x1] * tx
            bottom = hd[r1 + x0] * (1.0 - tx) + hd[r1 + x1] * tx
            big[p] = top + (bottom - top) * ty
            p += 1

    reds, greens, blues = _land_base(world)

    # Light from the north-west, 45 degrees up. Flat ground returns 0.703, which
    # is the divisor that normalises the response to 1.0 on the level.
    lx, ly, lz = -1.0, -1.0, 1.4
    light_len = math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / light_len, ly / light_len, lz / light_len
    flat_response = lz

    exaggeration = 26.0 * scale * 0.5  # per-pixel gradient -> per-cell slope
    water_exaggeration = exaggeration * 0.55

    pixels = bytearray(3 * out_w * out_h)
    index = 0
    for py in range(out_h):
        r0, r1, ty = rows[py]
        row_start = py * out_w
        up = row_start - out_w if py > 0 else row_start
        down = row_start + out_w if py < out_h - 1 else row_start
        for px in range(out_w):
            x0, x1, tx = cols[px]
            p = row_start + px
            elevation = big[p]

            left = big[p - 1] if px > 0 else elevation
            right = big[p + 1] if px < out_w - 1 else elevation
            above = big[up + px]
            below = big[down + px]

            submerged = elevation <= sea
            k = water_exaggeration if submerged else exaggeration
            gx = (right - left) * k
            gy = (below - above) * k
            length = math.sqrt(gx * gx + gy * gy + 1.0)
            response = (-gx * lx - gy * ly + lz) / length
            # The floor matters more than the ceiling. Let shadows run to a
            # third of full brightness and forested slopes go to mud; a floor
            # near 0.6 keeps the biome colour legible in shadow, which is the
            # difference between a relief model and a map.
            factor = 1.0 + (clamp(response / flat_response, 0.58, 1.42) - 1.0) * shade

            if submerged:
                depth = (sea - elevation) / sea if sea > 0.0 else 0.0
                r, g, b = ramp(OCEAN_STOPS, depth)
            else:
                # Interpolate the land colours, not the biome labels: hard
                # category edges look like a choropleth, soft ones like ground.
                w00 = (1.0 - tx) * (1.0 - ty)
                w10 = tx * (1.0 - ty)
                w01 = (1.0 - tx) * ty
                w11 = tx * ty
                i00, i10 = r0 + x0, r0 + x1
                i01, i11 = r1 + x0, r1 + x1
                r = reds[i00] * w00 + reds[i10] * w10 + reds[i01] * w01 + reds[i11] * w11
                g = greens[i00] * w00 + greens[i10] * w10 + greens[i01] * w01 + greens[i11] * w11
                b = blues[i00] * w00 + blues[i10] * w10 + blues[i01] * w01 + blues[i11] * w11

            r *= factor
            g *= factor
            b *= factor

            if grain:
                # Deterministic per-pixel tooth, so the flats are not dead flat.
                noise = ((px * 73856093) ^ (py * 19349663)) & 0xFF
                jitter = (noise / 255.0 - 0.5) * 5.0 * grain
                r += jitter
                g += jitter
                b += jitter

            pixels[index] = 0 if r < 0 else (255 if r > 255 else int(r))
            pixels[index + 1] = 0 if g < 0 else (255 if g > 255 else int(g))
            pixels[index + 2] = 0 if b < 0 else (255 if b > 255 else int(b))
            index += 3

    return out_w, out_h, bytes(pixels)


# -- label placement ------------------------------------------------------


class Placer:
    """Greedy label placement with rectangle rejection.

    Cartographic label placement is NP-hard in general and gorgeous when done
    properly. This is the cheap version that still avoids the thing readers
    actually notice: two names printed on top of each other. Labels are offered
    in priority order and the first fit wins.
    """

    def __init__(self, width: float, height: float, margin: float = 4.0):
        self.width = width
        self.height = height
        self.margin = margin
        self.boxes = []

    @staticmethod
    def measure(text: str, size: float, tracking: float = 0.0):
        """Rough advance width for a serif face at ``size`` pixels."""
        return len(text) * (size * 0.505 + tracking)

    def place(self, x, y, text, size, tracking=0.0, offsets=((0.0, 0.0),), pad=1.6):
        """Try each offset in turn; return the accepted centre, or None."""
        half_w = self.measure(text, size, tracking) / 2.0 + pad
        half_h = size * 0.62 + pad
        for dx, dy in offsets:
            cx, cy = x + dx, y + dy
            if not (
                self.margin + half_w <= cx <= self.width - self.margin - half_w
                and self.margin + half_h <= cy <= self.height - self.margin - half_h
            ):
                continue
            box = (cx - half_w, cy - half_h, cx + half_w, cy + half_h)
            if any(
                box[0] < other[2] and other[0] < box[2]
                and box[1] < other[3] and other[1] < box[3]
                for other in self.boxes
            ):
                continue
            self.boxes.append(box)
            return cx, cy
        return None

    def fits(self, x0, y0, x1, y1) -> bool:
        if not (
            self.margin <= x0 and x1 <= self.width - self.margin
            and self.margin <= y0 and y1 <= self.height - self.margin
        ):
            return False
        return not any(
            x0 < other[2] and other[0] < x1 and y0 < other[3] and other[1] < y1
            for other in self.boxes
        )

    def reserve(self, x0, y0, x1, y1):
        self.boxes.append((x0, y0, x1, y1))

    def place_flexible(self, x, y, text, size, tracking=0.0, offsets=((0.0, 0.0),),
                       shrink=(1.0, 0.80, 0.64)):
        """Try the label at successively smaller sizes before giving up.

        An ocean's name is the largest thing on the sheet and therefore the most
        likely to find no rectangle it fits in -- and an unnamed ocean is far
        worse than a slightly small one.
        """
        for factor in shrink:
            scaled = size * factor
            spot = self.place(x, y, text, scaled, tracking * factor, offsets=offsets)
            if spot:
                return spot, scaled, tracking * factor
        return None, size, tracking


# -- SVG helpers ----------------------------------------------------------


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _path(points, closed: bool = False, precision: int = 2) -> str:
    if not points:
        return ""
    fmt = f"{{:.{precision}f}}"
    parts = ["M" + fmt.format(points[0][0]) + "," + fmt.format(points[0][1])]
    for x, y in points[1:]:
        parts.append("L" + fmt.format(x) + "," + fmt.format(y))
    if closed:
        parts.append("Z")
    return "".join(parts)


def _label(
    x, y, text, size, *, fill=INK, angle=0.0, tracking=0.0, italic=False,
    weight="normal", family="serif", halo=2.6, opacity=1.0, anchor="middle",
):
    style = [f'font-size="{size:.1f}"', f'fill="{fill}"', f'text-anchor="{anchor}"']
    if tracking:
        style.append(f'letter-spacing="{tracking:.2f}"')
    if italic:
        style.append('font-style="italic"')
    if weight != "normal":
        style.append(f'font-weight="{weight}"')
    if family != "serif":
        style.append(f'font-family="{family}"')
    if opacity < 1.0:
        style.append(f'opacity="{opacity:.2f}"')
    if halo:
        style.append(f'stroke="{HALO}" stroke-width="{halo:.2f}" stroke-linejoin="round"')
        style.append('paint-order="stroke fill"')
    transform = ""
    if abs(angle) > 0.5:
        transform = f' transform="rotate({angle:.2f} {x:.2f} {y:.2f})"'
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" {" ".join(style)}'
        f' dominant-baseline="middle"{transform}>{_escape(text)}</text>'
    )


def _nice_scale_length(km: float) -> float:
    """A round number of kilometres, at most ``km``."""
    for candidate in (2000, 1000, 500, 400, 300, 250, 200, 150, 100, 50, 25, 10, 5):
        if candidate <= km:
            return float(candidate)
    return max(1.0, km)


# -- the map --------------------------------------------------------------

# Plate furniture, expressed at the reference scale of 4 pixels per cell.
# Everything is multiplied by `scale / 4` so that a plate drawn at --scale 6 is
# the same design enlarged, rather than the same map with undersized type
# rattling around inside a hairline frame.
MARGIN_AT_4 = 58.0
FOOTER_AT_4 = 152.0


def draw(
    world,
    scale: int = 4,
    contour_interval: float = 0.10,
    graticule: bool = True,
    labels: bool = True,
    shade: float = 0.90,
    embed_raster: bool = True,
) -> str:
    """Render a finished world as a standalone SVG document."""
    w, h = world.width, world.height_cells
    map_w, map_h = w * scale, h * scale
    unit = scale / 4.0
    margin = MARGIN_AT_4 * unit
    footer = FOOTER_AT_4 * unit
    total_w = map_w + 2 * margin
    total_h = map_h + margin + footer
    sea = world.sea_level
    hd = world.height.data

    def to_px(cx, cy):
        return (cx + 0.5) * scale, (cy + 0.5) * scale

    parts = []
    add = parts.append

    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {total_w:.0f} {total_h:.0f}" width="{total_w:.0f}" '
        f'height="{total_h:.0f}" font-family="Georgia, \'Times New Roman\', serif">'
    )
    add(f"<title>{_escape(world.title)}</title>")
    add(
        f'<desc>Procedurally generated atlas plate. Seed: {_escape(world.seed)}. '
        f'Generated by Silt.</desc>'
    )

    # Paper.
    add(
        f'<defs><linearGradient id="paper" x1="0" y1="0" x2="0.6" y2="1">'
        f'<stop offset="0" stop-color="{hexcolour(PAPER)}"/>'
        f'<stop offset="1" stop-color="{hexcolour(PAPER_EDGE)}"/>'
        f"</linearGradient></defs>"
    )
    add(f'<rect width="{total_w:.0f}" height="{total_h:.0f}" fill="url(#paper)"/>')

    # -- the map body ----------------------------------------------------
    add(f'<g transform="translate({margin:.2f},{margin:.2f})">')

    if embed_raster:
        rw, rh, pixels = raster(world, scale, shade=shade)
        uri = png_mod.data_uri(png_mod.encode(rw, rh, pixels))
        add(
            f'<image x="0" y="0" width="{map_w:.0f}" height="{map_h:.0f}" '
            f'preserveAspectRatio="none" xlink:href="{uri}"/>'
        )
    else:
        add(f'<rect width="{map_w:.0f}" height="{map_h:.0f}" fill="#cfd9d2"/>')

    add(
        f'<defs><clipPath id="mapclip"><rect width="{map_w:.0f}" '
        f'height="{map_h:.0f}"/></clipPath></defs>'
    )
    add('<g clip-path="url(#mapclip)">')

    # Bathymetric bands.
    bathy = []
    step = max(0.05, contour_interval * 1.6)
    depth_level = sea - step
    while depth_level > 0.02:
        for points, closed in contours(hd, w, h, depth_level):
            curve = simplify(smooth(points, closed, 2), 0.30)
            if len(curve) > 3:
                bathy.append(_path([to_px(*p) for p in curve], closed))
        depth_level -= step
    if bathy:
        add(
            f'<g fill="none" stroke="{BATHY_INK}" stroke-width="{0.5 * scale / 4:.2f}" '
            f'opacity="0.30">'
        )
        for d in bathy:
            add(f'<path d="{d}"/>')
        add("</g>")

    # Land contours. Every third is an index contour, drawn heavier.
    land_lines = []
    index_lines = []
    span = 1.0 - sea
    count = 0
    level = sea + contour_interval * span
    while level < 1.0:
        count += 1
        target = index_lines if count % 3 == 0 else land_lines
        for points, closed in contours(hd, w, h, level):
            curve = simplify(smooth(points, closed, 2), 0.30)
            if len(curve) > 3:
                target.append(_path([to_px(*p) for p in curve], closed))
        level += contour_interval * span
    if land_lines:
        add(
            f'<g fill="none" stroke="{CONTOUR_INK}" '
            f'stroke-width="{0.42 * scale / 4:.2f}" opacity="0.40">'
        )
        for d in land_lines:
            add(f'<path d="{d}"/>')
        add("</g>")
    if index_lines:
        add(
            f'<g fill="none" stroke="{CONTOUR_INK}" '
            f'stroke-width="{0.80 * scale / 4:.2f}" opacity="0.58">'
        )
        for d in index_lines:
            add(f'<path d="{d}"/>')
        add("</g>")

    # Graticule.
    ticks = _graticule_ticks(world)
    if graticule and ticks:
        add(
            f'<g stroke="{INK}" stroke-width="{0.4 * scale / 4:.2f}" opacity="0.16" '
            f'stroke-dasharray="{2.5 * scale / 4:.1f} {3.5 * scale / 4:.1f}">'
        )
        for _, py in ticks["parallels"]:
            y = py * scale
            add(f'<line x1="0" y1="{y:.2f}" x2="{map_w:.0f}" y2="{y:.2f}"/>')
        for _, px in ticks["meridians"]:
            x = px * scale
            add(f'<line x1="{x:.2f}" y1="0" x2="{x:.2f}" y2="{map_h:.0f}"/>')
        add("</g>")

    # Rivers, thickest last so confluences read correctly. Each is drawn twice:
    # a pale casing, then the line. Casing is standard practice for linear
    # features crossing dark ground -- without it a one-pixel blue thread
    # disappears into a shaded forest slope.
    river_runs = _river_runs(world, scale)
    if river_runs:
        add(
            f'<g fill="none" stroke="{HALO}" stroke-linecap="round" '
            f'stroke-linejoin="round" opacity="0.42">'
        )
        for width_px, points in river_runs:
            add(f'<path d="{_path(points)}" stroke-width="{width_px + 1.5 * scale / 4:.2f}"/>')
        add("</g>")
        add(
            f'<g fill="none" stroke="{RIVER_INK}" stroke-linecap="round" '
            f'stroke-linejoin="round">'
        )
        for width_px, points in river_runs:
            add(f'<path d="{_path(points)}" stroke-width="{width_px:.2f}"/>')
        add("</g>")

    # Lakes.
    lake_mask = [1.0 if v else 0.0 for v in world.hydro.lake_mask]
    lake_paths = []
    for points, closed in contours(lake_mask, w, h, 0.5):
        if not closed or len(points) < 4:
            continue
        curve = smooth(points, True, 2)
        lake_paths.append(_path([to_px(*p) for p in curve], True))
    if lake_paths:
        shallow = hexcolour(ramp(OCEAN_STOPS, 0.10))
        add(f'<g fill="{shallow}" stroke="{WATER_INK}" stroke-width="{0.55 * scale / 4:.2f}">')
        for d in lake_paths:
            add(f'<path d="{d}"/>')
        add("</g>")

    # Coastline.
    coast_paths = []
    for points, closed in contours(hd, w, h, sea):
        curve = simplify(smooth(points, closed, 2), 0.22)
        if len(curve) > 2:
            coast_paths.append(_path([to_px(*p) for p in curve], closed))
    if coast_paths:
        add(
            f'<g fill="none" stroke="{INK}" stroke-width="{0.95 * scale / 4:.2f}" '
            f'stroke-linejoin="round" opacity="0.78">'
        )
        for d in coast_paths:
            add(f'<path d="{d}"/>')
        add("</g>")

    add("</g>")  # end clip

    # Labels and the compass sit above everything.
    placer = Placer(map_w, map_h, margin=3.0)
    if labels:
        # Names first, then the rose fits itself around them. An ocean's name and
        # a compass both want the largest patch of empty water, and of the two
        # the name is the one that cannot move somewhere else.
        for chunk in _labels(world, scale, placer, ticks):
            add(chunk)
        add(_compass(world, scale, map_w, map_h, placer))

    add("</g>")  # end map translate

    # -- frame -----------------------------------------------------------
    inner, mid, outer = 1.0 * unit, 6.0 * unit, 9.0 * unit
    add(
        f'<g fill="none" stroke="{INK}">'
        f'<rect x="{margin - inner:.2f}" y="{margin - inner:.2f}" '
        f'width="{map_w + 2 * inner:.2f}" height="{map_h + 2 * inner:.2f}" '
        f'stroke-width="{1.1 * unit:.2f}"/>'
        f'<rect x="{margin - mid:.2f}" y="{margin - mid:.2f}" '
        f'width="{map_w + 2 * mid:.2f}" height="{map_h + 2 * mid:.2f}" '
        f'stroke-width="{2.2 * unit:.2f}"/>'
        f'<rect x="{margin - outer:.2f}" y="{margin - outer:.2f}" '
        f'width="{map_w + 2 * outer:.2f}" height="{map_h + 2 * outer:.2f}" '
        f'stroke-width="{0.6 * unit:.2f}"/>'
        f"</g>"
    )
    add(_frame_ticks(world, scale, ticks, margin))
    add(_footer(world, scale, total_w, map_h, margin))

    add("</svg>")
    return "\n".join(parts)


# -- map furniture --------------------------------------------------------


def _graticule_ticks(world):
    """Positions and labels for whole-degree parallels and meridians."""
    w, h = world.width, world.height_cells
    scale_rows = world.climate
    top = scale_rows.latitude(0)
    bottom = scale_rows.latitude(h - 1)
    lat_lo, lat_hi = min(top, bottom), max(top, bottom)
    span = lat_hi - lat_lo
    interval = 1.0
    for candidate in (20.0, 10.0, 5.0, 2.0, 1.0):
        if span / candidate >= 2.5:
            interval = candidate
            break

    parallels = []
    first = math.ceil(lat_lo / interval) * interval
    value = first
    while value <= lat_hi + 1e-9:
        # Invert Climate.latitude, which is linear in the row index.
        t = (value - bottom) / (top - bottom) if top != bottom else 0.0
        py = (1.0 - t) * (h - 1)
        parallels.append((value, (py + 0.5) * 1.0))
        value += interval

    mean_lat = (lat_lo + lat_hi) / 2.0
    km_per_degree = 111.32 * max(0.18, math.cos(math.radians(mean_lat)))
    lon_span = world.width * world.cell_km / km_per_degree
    lon_origin = (world.rng.derive("meridian").below(340) - 170) * 1.0
    lon_interval = interval
    for candidate in (20.0, 10.0, 5.0, 2.0, 1.0):
        if lon_span / candidate >= 2.5:
            lon_interval = candidate
            break

    meridians = []
    first = math.ceil(lon_origin / lon_interval) * lon_interval
    value = first
    while value <= lon_origin + lon_span + 1e-9:
        t = (value - lon_origin) / lon_span if lon_span else 0.0
        meridians.append((value, t * (w - 1) + 0.5))
        value += lon_interval

    return {
        "parallels": parallels,
        "meridians": meridians,
        "lat_range": (lat_lo, lat_hi),
        "lon_range": (lon_origin, lon_origin + lon_span),
    }


def _frame_ticks(world, scale, ticks, margin) -> str:
    """Degree marks and labels around the outside of the frame."""
    if not ticks:
        return ""
    w, h = world.width, world.height_cells
    map_w, map_h = w * scale, h * scale
    unit = scale / 4.0
    MARGIN = margin
    tick_in, tick_out = 1.0 * unit, 6.0 * unit
    parts = [f'<g stroke="{INK}" stroke-width="{0.9 * unit:.2f}">']
    for _, py in ticks["parallels"]:
        y = MARGIN + py * scale
        parts.append(
            f'<line x1="{MARGIN - tick_out:.2f}" y1="{y:.2f}" '
            f'x2="{MARGIN - tick_in:.2f}" y2="{y:.2f}"/>'
        )
        parts.append(
            f'<line x1="{MARGIN + map_w + tick_in:.2f}" y1="{y:.2f}" '
            f'x2="{MARGIN + map_w + tick_out:.2f}" y2="{y:.2f}"/>'
        )
    for _, px in ticks["meridians"]:
        x = MARGIN + px * scale
        parts.append(
            f'<line x1="{x:.2f}" y1="{MARGIN - tick_out:.2f}" x2="{x:.2f}" '
            f'y2="{MARGIN - tick_in:.2f}"/>'
        )
        parts.append(
            f'<line x1="{x:.2f}" y1="{MARGIN + map_h + tick_in:.2f}" x2="{x:.2f}" '
            f'y2="{MARGIN + map_h + tick_out:.2f}"/>'
        )
    parts.append("</g>")

    for value, py in ticks["parallels"]:
        y = MARGIN + py * scale
        hemisphere = "N" if value >= 0 else "S"
        text = f"{abs(value):g}°{hemisphere}"
        parts.append(
            _label(MARGIN - 17 * unit, y, text, 8.5 * unit, fill=INK_SOFT, halo=0)
        )
    for value, px in ticks["meridians"]:
        x = MARGIN + px * scale
        wrapped = (value + 180.0) % 360.0 - 180.0
        hemisphere = "E" if wrapped >= 0 else "W"
        text = f"{abs(wrapped):g}°{hemisphere}"
        parts.append(
            _label(x, MARGIN + map_h + 16 * unit, text, 8.5 * unit,
                   fill=INK_SOFT, halo=0)
        )
    return "".join(parts)


def _compass(world, scale, map_w, map_h, placer) -> str:
    """An eight-point rose, in the emptiest corner that nothing else has taken."""
    w, h = world.width, world.height_cells
    land = world.land_mask
    probe = max(6, int(0.22 * min(w, h)))

    corners = []
    for cx, cy in ((0, 0), (w - probe, 0), (0, h - probe), (w - probe, h - probe)):
        total = 0
        occupied = 0
        for y in range(cy, min(h, cy + probe)):
            for x in range(cx, min(w, cx + probe)):
                total += 1
                if land[y * w + x]:
                    occupied += 1
        corners.append((occupied / max(1, total), (cx, cy)))
    corners.sort(key=lambda item: item[0])

    radius = max(13.0, probe * scale * 0.30)
    chosen = None
    for _, (corner_x, corner_y) in corners:
        cx = clamp((corner_x + probe / 2) * scale, radius + 12, map_w - radius - 12)
        cy = clamp((corner_y + probe / 2) * scale, radius + 20, map_h - radius - 12)
        box = (cx - radius - 6, cy - radius - 14, cx + radius + 6, cy + radius + 6)
        if placer.fits(*box):
            chosen = (cx, cy, box)
            break
    if chosen is None:
        return ""  # nowhere to put it without printing over a name

    cx, cy, box = chosen
    placer.reserve(*box)

    parts = [f'<g transform="translate({cx:.1f},{cy:.1f})" opacity="0.80">']
    parts.append(
        f'<circle r="{radius:.1f}" fill="{HALO}" fill-opacity="0.42" '
        f'stroke="{INK}" stroke-width="0.7"/>'
    )
    parts.append(f'<circle r="{radius * 0.62:.1f}" fill="none" stroke="{INK}" stroke-width="0.4"/>')
    for k in range(8):
        angle = math.radians(k * 45.0)
        long_arm = k % 2 == 0
        tip = radius * (0.98 if long_arm else 0.60)
        wide = radius * (0.16 if long_arm else 0.10)
        sin_a, cos_a = math.sin(angle), math.cos(angle)
        # Points of a kite: tip outward, two shoulders, centre.
        px, py = sin_a * tip, -cos_a * tip
        lx, ly = cos_a * wide, sin_a * wide
        fill = INK if k % 2 == 0 else INK_SOFT
        parts.append(
            f'<path d="M0,0 L{lx:.2f},{ly:.2f} L{px:.2f},{py:.2f} '
            f'L{-lx:.2f},{-ly:.2f} Z" fill="{fill}" opacity="0.85"/>'
        )
    parts.append(
        _label(0, -radius - 8, "N", radius * 0.42, fill=INK, halo=2.0, weight="bold")
    )
    parts.append("</g>")
    return "".join(parts)


def _river_runs(world, scale):
    """River polylines split into runs of constant stream order.

    SVG strokes cannot taper, so a river is drawn as a handful of constant-width
    pieces that share endpoints. Each piece's width comes from its Strahler
    order, which is exactly the quantity a cartographer would use.
    """
    w = world.width
    hydro = world.hydro
    orders = hydro.stream_order
    unit = scale / 4.0
    runs = []
    for path in hydro.paths:
        if len(path) < 2:
            continue
        points = [((i % w + 0.5) * scale, (i // w + 0.5) * scale) for i in path]
        smoothed = smooth(points, False, 2)
        # Order along the path, resampled to the smoothed point count.
        path_orders = [max(1, orders[i]) for i in path]
        pieces = []
        current = path_orders[0]
        start = 0
        for k in range(1, len(path_orders)):
            if path_orders[k] != current:
                pieces.append((current, start, k))
                current = path_orders[k]
                start = k
        pieces.append((current, start, len(path_orders)))

        ratio = (len(smoothed) - 1) / max(1, len(points) - 1)
        for order, a, b in pieces:
            i0 = int(a * ratio)
            i1 = min(len(smoothed) - 1, int(b * ratio) + 1)
            if i1 - i0 < 1:
                continue
            width_px = (0.85 + 0.62 * (order ** 0.92)) * unit
            runs.append((width_px, smoothed[i0:i1 + 1]))
    runs.sort(key=lambda item: item[0])
    return runs


def _labels(world, scale, placer: Placer, ticks):
    """Every place name on the sheet, offered in priority order."""
    w = world.width
    features = world.features
    out = []

    def px(index):
        return ((index % w) + 0.5) * scale, ((index // w) + 0.5) * scale

    def centre_px(point):
        return (point[0] + 0.5) * scale, (point[1] + 0.5) * scale

    # Oceans and seas first: they own the largest empty areas.
    unit = scale / 4.0
    ring = [(0.0, 0.0)]
    for radius in (16.0, 34.0, 56.0):
        for k in range(8):
            angle = math.radians(k * 45.0)
            ring.append((math.cos(angle) * radius * unit, math.sin(angle) * radius * unit))

    for water in features.waters:
        x, y = px(water.index)
        if water.kind == "ocean":
            size, tracking = 17.0 * unit, 5.0
        elif water.kind == "sea":
            size, tracking = 12.5 * unit, 3.0
        elif water.kind == "gulf":
            size, tracking = 9.5 * unit, 1.2
        else:
            size, tracking = 8.5 * unit, 0.8
        spot, size, tracking = placer.place_flexible(
            x, y, water.name, size, tracking, offsets=ring,
        )
        if spot:
            out.append(
                _label(
                    spot[0], spot[1], water.name, size, fill=WATER_INK,
                    tracking=tracking, italic=True, halo=2.2 * unit,
                )
            )

    # Regions.
    for region in features.regions:
        x, y = centre_px(region.centroid)
        size = 12.0 * scale / 4.0
        text = region.name.upper()
        spot = placer.place(
            x, y, text, size, 2.6,
            offsets=((0, 0), (0, -18 * scale / 4), (0, 18 * scale / 4)),
        )
        if spot:
            out.append(
                _label(
                    spot[0], spot[1], text, size, fill=INK, tracking=2.6,
                    opacity=0.80, halo=2.8 * scale / 4,
                )
            )

    # Ranges, rotated along their principal axis -- but only when there is an
    # axis worth following. A roughly circular massif has a meaningless
    # principal angle, and setting its name at 43 degrees just looks careless.
    for mountains in features.ranges:
        x, y = centre_px(mountains.centroid)
        size = 10.5 * scale / 4.0
        angle = mountains.angle if elongation(mountains.cells, w) >= 1.5 else 0.0
        if angle > 78.0:
            angle -= 180.0
        elif angle < -78.0:
            angle += 180.0
        spot = placer.place(
            x, y, mountains.name, size, 1.6,
            offsets=((0, 0), (0, -13 * scale / 4), (0, 13 * scale / 4)),
        )
        if spot:
            out.append(
                _label(
                    spot[0], spot[1], mountains.name, size, fill="#5b4a35",
                    tracking=1.6, italic=True, angle=angle, halo=2.4 * scale / 4,
                )
            )

    # Summits: a small triangle and a height.
    for summit in features.summits:
        x, y = px(summit.index)
        size = 8.0 * scale / 4.0
        arm = 2.2 * scale / 4.0
        text = f"{summit.name} {summit.elevation_m:.0f}m"
        spot = placer.place(
            x, y + 7 * scale / 4, text, size, 0.0,
            offsets=((0, 0), (0, -14 * scale / 4), (12 * scale / 4, 0)),
        )
        if spot:
            out.append(
                f'<path d="M{x:.1f},{y - arm:.1f} L{x + arm:.1f},{y + arm * 0.7:.1f} '
                f'L{x - arm:.1f},{y + arm * 0.7:.1f} Z" fill="{INK}" opacity="0.85"/>'
            )
            out.append(
                _label(spot[0], spot[1], text, size, fill=INK, halo=2.2 * scale / 4)
            )

    # Rivers, rotated to follow the channel.
    for river in features.rivers:
        cells = river.cells
        if len(cells) < 6:
            continue
        anchor = int(len(cells) * 0.42)
        ax, ay = px(cells[anchor])
        span = max(2, len(cells) // 8)
        bx, by = px(cells[max(0, anchor - span)])
        ex, ey = px(cells[min(len(cells) - 1, anchor + span)])
        angle = math.degrees(math.atan2(ey - by, ex - bx))
        if angle > 90.0:
            angle -= 180.0
        elif angle < -90.0:
            angle += 180.0
        size = 8.5 * scale / 4.0
        # Offset perpendicular to the channel so the name sits beside the line.
        radians = math.radians(angle)
        nudge = 5.0 * scale / 4.0
        offsets = (
            (-math.sin(radians) * nudge, -math.cos(radians) * nudge),
            (math.sin(radians) * nudge, math.cos(radians) * nudge),
        )
        spot = placer.place(ax, ay, river.name, size, 0.4, offsets=offsets)
        if spot:
            out.append(
                _label(
                    spot[0], spot[1], river.name, size, fill=RIVER_INK, tracking=0.4,
                    italic=True, angle=angle, halo=2.2 * scale / 4,
                )
            )

    # Lakes.
    for lake in features.lakes:
        x, y = centre_px(lake.centroid)
        size = 8.5 * scale / 4.0
        offset = max(4.0, math.sqrt(len(lake.cells)) * 0.6) * scale / 4.0
        spot = placer.place(
            x, y, lake.name, size, 0.4,
            offsets=((0, -offset - 5 * scale / 4), (0, offset + 5 * scale / 4), (0, 0)),
        )
        if spot:
            out.append(
                _label(
                    spot[0], spot[1], lake.name, size, fill=WATER_INK, tracking=0.4,
                    italic=True, halo=2.2 * scale / 4,
                )
            )

    # Islands.
    for island in features.islands:
        x, y = centre_px(island.centroid)
        size = 9.0 * scale / 4.0
        spot = placer.place(x, y, island.name, size, 1.0, offsets=((0, 0), (0, -11 * scale / 4)))
        if spot:
            out.append(
                _label(
                    spot[0], spot[1], island.name, size, fill=INK, tracking=1.0,
                    opacity=0.85, halo=2.2 * scale / 4,
                )
            )

    # Capes, with a locating dot.
    for cape in features.capes:
        x, y = px(cape.index)
        size = 7.5 * scale / 4.0
        spot = placer.place(
            x, y, cape.name, size, 0.3,
            offsets=(
                (0, -8 * scale / 4), (0, 8 * scale / 4),
                (11 * scale / 4, 0), (-11 * scale / 4, 0),
            ),
        )
        if spot:
            out.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{0.9 * scale / 4:.2f}" '
                f'fill="{INK}" opacity="0.75"/>'
            )
            out.append(
                _label(
                    spot[0], spot[1], cape.name, size, fill=INK_SOFT, tracking=0.3,
                    halo=2.0 * scale / 4,
                )
            )
    return out


def _footer(world, scale, total_w, map_h, margin) -> str:
    """Title, credits, biome legend and scale bar."""
    unit = scale / 4.0
    MARGIN = margin
    top = MARGIN + map_h + 26 * unit
    parts = []
    left = MARGIN

    parts.append(
        _label(
            left, top + 6, world.title, 25.0, fill=INK, tracking=1.6, halo=0,
            anchor="start",
        )
    )
    climate = world.climate
    lat_lo = climate.latitude(world.height_cells - 1)
    lat_hi = climate.latitude(0)
    tongues = ", ".join(lang.name for lang in world.namer.languages)
    subtitle = (
        f"seed “{world.seed}” · {world.shape} · "
        f"{world.width * world.cell_km:,.0f} × "
        f"{world.height_cells * world.cell_km:,.0f} km · "
        f"lat {min(lat_lo, lat_hi):.0f}° to {max(lat_lo, lat_hi):.0f}° · "
        f"prevailing wind from the {climate.wind}"
    )
    parts.append(
        _label(left, top + 27, subtitle, 10.0, fill=INK_SOFT, halo=0, anchor="start")
    )
    detail = (
        f"{world.land_cell_count() * world.cell_km ** 2:,.0f} km² of land · "
        f"{world.coast_km():,.0f} km of coast · "
        f"{len(world.features.rivers)} named rivers · "
        f"highest point {world.metres(world.highest()):,.0f} m · "
        f"tongues: {tongues}"
    )
    parts.append(
        _label(left, top + 43, detail, 10.0, fill=INK_SOFT, halo=0, anchor="start")
    )

    # Scale bar geometry first, because the legend gets whatever is left over.
    bar_right = total_w - MARGIN
    km = _nice_scale_length(world.width * world.cell_km / 3.0)
    bar_px = min(km / world.cell_km * scale, 210.0, (total_w - 2 * MARGIN) * 0.42)
    km = _nice_scale_length(bar_px / scale * world.cell_km)
    bar_px = km / world.cell_km * scale
    bar_left = bar_right - bar_px
    bar_y = top + 88

    # Legend: the biomes that actually cover ground, in a natural cold-to-hot
    # order. Column count follows the width available beside the scale bar --
    # a fixed grid overruns the sheet on a small plate and prints the legend
    # straight through the scale bar.
    shares = world.climate.biome_fractions(world.land_mask)
    present = [key for key, share in shares if share >= 0.012][:12]
    present.sort(key=lambda key: LEGEND_ORDER.index(key) if key in LEGEND_ORDER else 99)

    column_width = 126.0
    available = bar_left - left - 26.0
    if present and available >= column_width * 0.75:
        columns = max(1, int(available // column_width))
        per_column = max(1, -(-len(present) // columns))
        if per_column > 4:
            per_column = 4
        present = present[: columns * per_column]
        swatch = 9.0
        for k, key in enumerate(present):
            cx = left + (k // per_column) * column_width
            cy = top + 64 + (k % per_column) * 15
            parts.append(
                f'<rect x="{cx:.1f}" y="{cy - swatch / 2:.1f}" width="{swatch:.1f}" '
                f'height="{swatch:.1f}" fill="{hexcolour(BIOMES[key][1])}" '
                f'stroke="{INK}" stroke-width="0.35" stroke-opacity="0.5"/>'
            )
            parts.append(
                _label(
                    cx + swatch + 5, cy, BIOMES[key][0], 9.0, fill=INK_SOFT, halo=0,
                    anchor="start",
                )
            )
    segments = 4
    for k in range(segments):
        seg_w = bar_px / segments
        fill = INK if k % 2 == 0 else HALO
        parts.append(
            f'<rect x="{bar_left + k * seg_w:.2f}" y="{bar_y:.1f}" '
            f'width="{seg_w:.2f}" height="5" fill="{fill}" stroke="{INK}" '
            f'stroke-width="0.5"/>'
        )
    parts.append(
        _label(bar_left, bar_y - 7, "0", 8.5, fill=INK_SOFT, halo=0)
    )
    parts.append(
        _label(bar_right, bar_y - 7, f"{km:,.0f} km", 8.5, fill=INK_SOFT, halo=0)
    )
    parts.append(
        _label(
            bar_right, bar_y + 17, "Silt · procedural atlas", 8.5,
            fill=INK_SOFT, halo=0, anchor="end", italic=True,
        )
    )
    return "".join(parts)
