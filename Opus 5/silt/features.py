"""Finding the things a map would label.

The simulation produces fields of numbers. A map needs *features*: this river,
that range, the bay between them. Each one is found by a small piece of
geometry over the fields, then handed to :mod:`silt.names` to be named in
whatever language holds that part of the world.

The two nicest tricks here:

* **Enclosure.** A summed-area table over the land mask makes "what fraction of
  the neighbourhood around this cell is land?" an O(1) query. High enclosure on
  a water cell means a bay; high *water* enclosure on a land cell means a cape.
  One integral image finds both.
* **Principal axis.** A range's label should run along the range. The major
  eigenvector of a component's coordinate covariance gives the angle, which is
  a two-by-two eigenproblem and therefore one ``atan2``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field as dc_field

from .field import D4, D8, Field, flood_regions
from .names import Namer


# -- geometry helpers -----------------------------------------------------


def centroid(cells, width: int):
    sx = sy = 0.0
    for i in cells:
        sx += i % width
        sy += i // width
    n = len(cells)
    return (sx / n, sy / n) if n else (0.0, 0.0)


def principal_angle(cells, width: int) -> float:
    """Degrees of the major axis of a cell cluster, in SVG's sense (y down)."""
    n = len(cells)
    if n < 3:
        return 0.0
    cx, cy = centroid(cells, width)
    cxx = cyy = cxy = 0.0
    for i in cells:
        dx = (i % width) - cx
        dy = (i // width) - cy
        cxx += dx * dx
        cyy += dy * dy
        cxy += dx * dy
    cxx /= n
    cyy /= n
    cxy /= n
    if abs(cxy) < 1e-9 and abs(cxx - cyy) < 1e-9:
        return 0.0
    angle = 0.5 * math.atan2(2.0 * cxy, cxx - cyy)
    return math.degrees(angle)


def elongation(cells, width: int) -> float:
    """Ratio of principal axis lengths; 1 is a blob, large is a ridge."""
    n = len(cells)
    if n < 3:
        return 1.0
    cx, cy = centroid(cells, width)
    cxx = cyy = cxy = 0.0
    for i in cells:
        dx = (i % width) - cx
        dy = (i // width) - cy
        cxx += dx * dx
        cyy += dy * dy
        cxy += dx * dy
    cxx /= n
    cyy /= n
    cxy /= n
    trace = cxx + cyy
    det = cxx * cyy - cxy * cxy
    disc = max(0.0, trace * trace / 4.0 - det)
    root = math.sqrt(disc)
    major = trace / 2.0 + root
    minor = max(1e-9, trace / 2.0 - root)
    return math.sqrt(major / minor)


class Enclosure:
    """Summed-area table over a boolean mask, for box queries in constant time."""

    def __init__(self, mask, width: int, height: int):
        self.width = width
        self.height = height
        stride = width + 1
        table = [0] * (stride * (height + 1))
        for y in range(height):
            row_sum = 0
            base = y * width
            cur = (y + 1) * stride
            prev = y * stride
            for x in range(width):
                row_sum += 1 if mask[base + x] else 0
                table[cur + x + 1] = table[prev + x + 1] + row_sum
        self.table = table
        self.stride = stride

    def fraction(self, x: int, y: int, radius: int) -> float:
        """Share of the (clipped) box around (x, y) that is inside the mask."""
        x0 = max(0, x - radius)
        y0 = max(0, y - radius)
        x1 = min(self.width, x + radius + 1)
        y1 = min(self.height, y + radius + 1)
        s = self.stride
        total = (
            self.table[y1 * s + x1]
            - self.table[y0 * s + x1]
            - self.table[y1 * s + x0]
            + self.table[y0 * s + x0]
        )
        area = (x1 - x0) * (y1 - y0)
        return total / area if area else 0.0


def chamfer_distance(mask, width: int, height: int):
    """Distance of every cell from the nearest cell where ``mask`` is set.

    Two passes of 3x4 chamfer, straight steps 1 and diagonals sqrt(2). Used to
    find the point *furthest* from land in a body of water, which is where an
    ocean's name belongs -- put it at the centroid instead and a horseshoe-shaped
    sea prints its name across the continent it wraps around.
    """
    far = float(width + height) * 2.0
    d = [0.0 if mask[i] else far for i in range(width * height)]
    root2 = 1.4142135623730951

    for y in range(height):
        row = y * width
        for x in range(width):
            i = row + x
            best = d[i]
            if best == 0.0:
                continue
            if x > 0 and d[i - 1] + 1.0 < best:
                best = d[i - 1] + 1.0
            if y > 0:
                up = i - width
                if d[up] + 1.0 < best:
                    best = d[up] + 1.0
                if x > 0 and d[up - 1] + root2 < best:
                    best = d[up - 1] + root2
                if x < width - 1 and d[up + 1] + root2 < best:
                    best = d[up + 1] + root2
            d[i] = best

    for y in range(height - 1, -1, -1):
        row = y * width
        for x in range(width - 1, -1, -1):
            i = row + x
            best = d[i]
            if best == 0.0:
                continue
            if x < width - 1 and d[i + 1] + 1.0 < best:
                best = d[i + 1] + 1.0
            if y < height - 1:
                down = i + width
                if d[down] + 1.0 < best:
                    best = d[down] + 1.0
                if x > 0 and d[down - 1] + root2 < best:
                    best = d[down - 1] + root2
                if x < width - 1 and d[down + 1] + root2 < best:
                    best = d[down + 1] + root2
            d[i] = best
    return d


def _spread_picks(candidates, width: int, limit: int, separation: float):
    """Greedily take the strongest candidates, no two within ``separation``."""
    chosen = []
    for score, i in candidates:
        x, y = i % width, i // width
        if all(
            (x - (j % width)) ** 2 + (y - (j // width)) ** 2 >= separation * separation
            for _, j in chosen
        ):
            chosen.append((score, i))
            if len(chosen) >= limit:
                break
    return chosen


# -- feature records ------------------------------------------------------


@dataclass
class River:
    name: str
    cells: list
    length_km: float
    mouth: int
    discharge: float
    order: int


@dataclass
class Lake:
    name: str
    cells: list
    centroid: tuple
    area_km2: float


@dataclass
class Range:
    name: str
    cells: list
    centroid: tuple
    angle: float
    peak: int
    peak_m: float
    area_km2: float


@dataclass
class Summit:
    name: str
    index: int
    elevation_m: float


@dataclass
class Island:
    name: str
    cells: list
    centroid: tuple
    area_km2: float


@dataclass
class Waters:
    name: str
    kind: str  # ocean | sea | gulf | bay
    index: int
    centroid: tuple
    area_km2: float = 0.0


@dataclass
class Cape:
    name: str
    index: int


@dataclass
class Region:
    name: str
    cells: list
    centroid: tuple
    biome: str
    area_km2: float
    seed: int


@dataclass
class Features:
    rivers: list = dc_field(default_factory=list)
    lakes: list = dc_field(default_factory=list)
    ranges: list = dc_field(default_factory=list)
    summits: list = dc_field(default_factory=list)
    islands: list = dc_field(default_factory=list)
    waters: list = dc_field(default_factory=list)
    capes: list = dc_field(default_factory=list)
    regions: list = dc_field(default_factory=list)
    region_of: list = dc_field(default_factory=list)

    def count(self) -> int:
        return (
            len(self.rivers) + len(self.lakes) + len(self.ranges) + len(self.summits)
            + len(self.islands) + len(self.waters) + len(self.capes) + len(self.regions)
        )


# -- extraction -----------------------------------------------------------


def _elevation_metres(h: float, sea: float, peak_altitude: float) -> float:
    span = max(1e-6, 1.0 - sea)
    return max(0.0, (h - sea) / span) * peak_altitude


def extract(world) -> Features:
    """Find and name every labelled feature of a finished world."""
    height = world.height
    w, h = height.width, height.height
    n = w * h
    sea = world.sea_level
    hd = height.data
    namer: Namer = world.namer
    cell_km = world.cell_km
    cell_area = cell_km * cell_km
    land = world.land_mask
    out = Features()

    # -- rivers ----------------------------------------------------------
    hydro = world.hydro
    # Threshold in cells, not kilometres: the map scale varies between worlds,
    # and what makes a watercourse worth naming is how far it runs across *this*
    # sheet, not what its length converts to.
    min_cells = max(8, int(0.09 * max(w, h)))
    candidates = []
    for stem in hydro.stems:
        if len(stem) < min_cells:
            continue
        km = 0.0
        for a, b in zip(stem, stem[1:]):
            dx = abs((a % w) - (b % w))
            dy = abs((a // w) - (b // w))
            km += cell_km * (1.4142135623730951 if dx and dy else 1.0)
        candidates.append((km, stem))
    candidates.sort(key=lambda kv: (-kv[0], kv[1][0]))

    for km, stem in candidates[: world.limits["rivers"]]:
        mouth = stem[0]
        mid = stem[len(stem) // 2]
        out.rivers.append(
            River(
                name=namer.name("river", ("river", mouth), mid % w, mid // w),
                cells=stem,
                length_km=km,
                mouth=mouth,
                discharge=hydro.area[mouth] * cell_area,
                order=hydro.stream_order[mouth],
            )
        )

    # -- lakes -----------------------------------------------------------
    min_lake = max(4, int(0.00035 * n))
    lakes = [cells for cells in hydro.lake_regions if len(cells) >= min_lake]
    lakes.sort(key=lambda cells: (-len(cells), cells[0]))
    for cells in lakes[: world.limits["lakes"]]:
        cx, cy = centroid(cells, w)
        out.lakes.append(
            Lake(
                name=namer.name("lake", ("lake", cells[0]), cx, cy),
                cells=cells,
                centroid=(cx, cy),
                area_km2=len(cells) * cell_area,
            )
        )

    # -- mountain ranges -------------------------------------------------
    land_heights = sorted(hd[i] for i in range(n) if land[i])
    if land_heights:
        crest_level = land_heights[int(0.88 * (len(land_heights) - 1))]
        upland_level = land_heights[int(0.74 * (len(land_heights) - 1))]
    else:
        crest_level = upland_level = 1.0
    upland = [land[i] and hd[i] >= upland_level for i in range(n)]
    _, upland_regions = flood_regions(upland, w, h, offsets=D8)
    min_range = max(10, int(0.0018 * n))
    ranges = [cells for cells in upland_regions if len(cells) >= min_range]
    ranges.sort(key=lambda cells: (-len(cells), cells[0]))

    for cells in ranges[: world.limits["ranges"]]:
        peak = max(cells, key=lambda i: (hd[i], -i))
        if hd[peak] < crest_level:
            continue  # high ground, but nothing that deserves the word "range"
        cx, cy = centroid(cells, w)
        out.ranges.append(
            Range(
                name=namer.name("mountain", ("range", cells[0]), cx, cy),
                cells=cells,
                centroid=(cx, cy),
                angle=principal_angle(cells, w),
                peak=peak,
                peak_m=_elevation_metres(hd[peak], sea, world.peak_altitude),
                area_km2=len(cells) * cell_area,
            )
        )

    # The highest points in the tallest few ranges get their own names.
    for rng_feature in sorted(out.ranges, key=lambda r: -r.peak_m)[
        : world.limits["summits"]
    ]:
        i = rng_feature.peak
        out.summits.append(
            Summit(
                name=namer.name("mountain", ("summit", i), i % w, i // w),
                index=i,
                elevation_m=rng_feature.peak_m,
            )
        )

    # -- islands ---------------------------------------------------------
    _, land_regions = flood_regions(land, w, h, offsets=D8)
    land_regions.sort(key=lambda cells: (-len(cells), cells[0]))
    min_island = max(3, int(0.0008 * n))
    for cells in land_regions[1 : world.limits["islands"] + 1]:
        if len(cells) < min_island:
            break
        cx, cy = centroid(cells, w)
        out.islands.append(
            Island(
                name=namer.name("island", ("island", cells[0]), cx, cy),
                cells=cells,
                centroid=(cx, cy),
                area_km2=len(cells) * cell_area,
            )
        )

    # -- seas, gulfs, bays, capes ---------------------------------------
    water = [not land[i] for i in range(n)]
    _, water_regions = flood_regions(water, w, h, offsets=D4)
    water_regions.sort(key=lambda cells: (-len(cells), cells[0]))

    enclosure = Enclosure(land, w, h)
    radius = max(3, int(0.055 * max(w, h)))
    offshore = chamfer_distance(land, w, h)

    for rank, cells in enumerate(water_regions):
        if len(cells) < max(12, int(0.002 * n)):
            continue
        touches_edge = any(height.on_border(i) for i in cells)
        if rank == 0 and touches_edge:
            kind = "ocean"
        elif touches_edge:
            continue  # a lobe of the same ocean; its bays get named below
        else:
            kind = "sea"
        cx, cy = centroid(cells, w)

        # Where does an ocean's name go? Not the centroid -- a sea that wraps
        # around a continent would print its name across the land. Not the point
        # furthest from land either, which on any map with open sea is a corner.
        # The pole of inaccessibility *clipped to the sheet*: furthest from land
        # and from the edge at once, which is the middle of the largest expanse
        # of open water the reader can actually see.
        def openness(i):
            x, y = i % w, i // w
            from_edge = min(x, y, w - 1 - x, h - 1 - y)
            return (min(offshore[i], from_edge * 1.35), -i)

        anchor = max(cells, key=openness)
        label = namer.name(kind, (kind, cells[0]), cx, cy)
        out.waters.append(
            Waters(
                name=label,
                kind=kind,
                index=anchor,
                centroid=(cx, cy),
                area_km2=len(cells) * cell_area,
            )
        )

    # Bays: water cells hemmed in by land on most sides.
    bay_candidates = []
    for i in range(n):
        if land[i]:
            continue
        x, y = i % w, i // w
        if not any(land[j] for j in height.neighbours(i, D4)):
            continue
        score = enclosure.fraction(x, y, radius)
        if score > 0.46:
            bay_candidates.append((score, i))
    bay_candidates.sort(key=lambda kv: (-kv[0], kv[1]))
    for score, i in _spread_picks(
        bay_candidates, w, world.limits["bays"], max(6.0, 0.13 * max(w, h))
    ):
        out.waters.append(
            Waters(
                name=namer.name("bay", ("bay", i), i % w, i // w),
                kind="gulf" if score > 0.60 else "bay",
                index=i,
                centroid=(i % w, i // w),
            )
        )

    # Capes: the same test, inverted.
    cape_candidates = []
    for i in range(n):
        if not land[i]:
            continue
        x, y = i % w, i // w
        if not any(not land[j] for j in height.neighbours(i, D4)):
            continue
        score = 1.0 - enclosure.fraction(x, y, radius)
        if score > 0.62:
            cape_candidates.append((score, i))
    cape_candidates.sort(key=lambda kv: (-kv[0], kv[1]))
    for _, i in _spread_picks(
        cape_candidates, w, world.limits["capes"], max(7.0, 0.16 * max(w, h))
    ):
        out.capes.append(
            Cape(name=namer.name("cape", ("cape", i), i % w, i // w), index=i)
        )

    # -- regions ---------------------------------------------------------
    land_cells = [i for i in range(n) if land[i]]
    if land_cells:
        wanted = min(
            world.limits["regions"], max(2, int(math.sqrt(len(land_cells)) / 5.0))
        )
        seeds = _farthest_point_seeds(land_cells, w, wanted, world.rng.derive("regions"))
        assignment = [-1] * n
        for i in land_cells:
            x, y = i % w, i // w
            best = 0
            best_d = float("inf")
            for k, s in enumerate(seeds):
                d = (x - s % w) ** 2 + (y - s // w) ** 2
                if d < best_d:
                    best_d = d
                    best = k
            assignment[i] = best
        out.region_of = assignment

        buckets = [[] for _ in seeds]
        for i in land_cells:
            buckets[assignment[i]].append(i)
        for k, cells in enumerate(buckets):
            if not cells:
                continue
            counts = {}
            for i in cells:
                b = world.climate.biome[i]
                counts[b] = counts.get(b, 0) + 1
            dominant = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
            cx, cy = centroid(cells, w)
            out.regions.append(
                Region(
                    name=namer.name("region", ("region", seeds[k]), cx, cy),
                    cells=cells,
                    centroid=(cx, cy),
                    biome=dominant,
                    area_km2=len(cells) * cell_area,
                    seed=seeds[k],
                )
            )

    return out


def _farthest_point_seeds(land_cells, width: int, count: int, rng):
    """Farthest-point sampling: evenly spread seeds without rejection loops."""
    if not land_cells:
        return []
    first = land_cells[rng.below(len(land_cells))]
    seeds = [first]
    best = [
        (i % width - first % width) ** 2 + (i // width - first // width) ** 2
        for i in land_cells
    ]
    while len(seeds) < count:
        pick = max(range(len(land_cells)), key=lambda k: (best[k], -land_cells[k]))
        if best[pick] <= 0:
            break
        chosen = land_cells[pick]
        seeds.append(chosen)
        sx, sy = chosen % width, chosen // width
        for k, i in enumerate(land_cells):
            d = (i % width - sx) ** 2 + (i // width - sy) ** 2
            if d < best[k]:
                best[k] = d
    return seeds
