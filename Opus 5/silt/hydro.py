"""Where the water goes.

No river in Silt is drawn. Rivers are what is left over after asking, for every
cell on the map, "which of my neighbours is downhill?" and then counting how
many cells drain through each one. Somewhere around thirty upstream cells, a
line on the map stops being a hillside and becomes a stream.

The pipeline:

``fill_depressions``  Priority flood (Barnes/Lehman/Mulla). Raises every closed
                      basin to its lowest outlet, plus a hair, so that a
                      downhill path to the sea exists from every land cell. The
                      hair matters: it makes "downhill" a strict order, which
                      makes the drainage graph a forest, which is what lets the
                      rest of this module be three linear passes.
``flow_directions``   D8 steepest descent on the filled surface.
``accumulate``        Sum upstream cells, walking the forest leaves-first.
``stream_order``      Strahler numbering, for line weights and for deciding
                      which watercourses are worth naming.
``channel_paths``     Decompose the network into polylines, longest first, so
                      each drawn stroke follows a whole watercourse.
"""

from __future__ import annotations

import heapq
import math

from .field import D8, D8_DIST, Field, flood_regions

FILL_EPSILON = 1e-7
LAKE_TOLERANCE = 1e-4


def fill_depressions(height: Field, sea_level: float, epsilon: float = FILL_EPSILON) -> Field:
    """Return a surface with no interior pits, draining to sea or map edge."""
    w, h = height.width, height.height
    src = height.data
    filled = list(src)
    closed = bytearray(len(src))
    heap = []

    for i, v in enumerate(src):
        if v <= sea_level or height.on_border(i):
            closed[i] = 1
            heap.append((v, i))
    heapq.heapify(heap)

    push = heapq.heappush
    pop = heapq.heappop
    while heap:
        level, i = pop(heap)
        x = i % w
        y = i // w
        for dx, dy in D8:
            nx = x + dx
            ny = y + dy
            if 0 <= nx < w and 0 <= ny < h:
                j = ny * w + nx
                if not closed[j]:
                    closed[j] = 1
                    nv = filled[j]
                    if nv <= level:
                        nv = level + epsilon
                        filled[j] = nv
                    push(heap, (nv, j))

    return Field(w, h, data=filled)


def flow_directions(filled: Field, height: Field, sea_level: float):
    """D8 receivers, plus cells sorted by descending filled height.

    A receiver of -1 means the cell is a sink: open water, or a border cell with
    nowhere lower to go. Land cells on the shore drain *into* the sea cell next
    to them, which is what puts river mouths on the coastline instead of one
    cell short of it.
    """
    w, h = filled.width, filled.height
    fdata = filled.data
    hdata = height.data
    receivers = [-1] * len(fdata)

    for i in range(len(fdata)):
        if hdata[i] <= sea_level:
            continue  # open water: a sink
        here = fdata[i]
        x = i % w
        y = i // w
        best = -1
        best_slope = 0.0
        for k in range(8):
            dx, dy = D8[k]
            nx = x + dx
            ny = y + dy
            if 0 <= nx < w and 0 <= ny < h:
                j = ny * w + nx
                drop = here - fdata[j]
                if drop > 0.0:
                    slope = drop / D8_DIST[k]
                    if slope > best_slope:
                        best_slope = slope
                        best = j
        receivers[i] = best

    order = sorted(range(len(fdata)), key=fdata.__getitem__, reverse=True)
    return receivers, order


def accumulate(receivers, order, weights=None):
    """Drainage area per cell, in cells (or in units of ``weights``)."""
    n = len(receivers)
    area = [1.0] * n if weights is None else list(weights)
    for i in order:
        r = receivers[i]
        if r >= 0:
            area[r] += area[i]
    return area


def _step_distance(i: int, j: int, width: int, cell_size: float) -> float:
    dx = abs((i % width) - (j % width))
    dy = abs((i // width) - (j // width))
    return cell_size * (1.4142135623730951 if dx and dy else 1.0)


def downstream_length(receivers, order, width: int, cell_size: float = 1.0):
    """Flow distance from each cell to the water it eventually reaches."""
    length = [0.0] * len(receivers)
    for i in reversed(order):  # ascending height: receivers resolved first
        r = receivers[i]
        if r >= 0:
            length[i] = length[r] + _step_distance(i, r, width, cell_size)
    return length


def stream_order(receivers, order, channel):
    """Strahler order for channel cells; 0 elsewhere.

    Two tributaries of equal order make a stream one greater; a tributary
    joining a larger stream leaves it unchanged. Because ``order`` runs downhill
    and every receiver is strictly lower, all of a cell's children are numbered
    before the cell itself.
    """
    n = len(receivers)
    result = [0] * n
    best = [0] * n
    ties = [0] * n

    for i in order:
        if not channel[i]:
            continue
        own = 1 if best[i] == 0 else best[i] + (1 if ties[i] >= 2 else 0)
        result[i] = own
        r = receivers[i]
        if r >= 0 and channel[r]:
            if own > best[r]:
                best[r] = own
                ties[r] = 1
            elif own == best[r]:
                ties[r] += 1
    return result


def channel_paths(receivers, channel, length, width: int):
    """Split the channel network into polylines of cell indices.

    Each path starts at a source and runs downstream until it meets a path
    already traced, which it joins by one cell so the drawn strokes connect.
    Longest watercourses are traced first, so trunks come out whole rather than
    as a chain of stubs.
    """
    n = len(receivers)
    children = [0] * n
    for i in range(n):
        if channel[i]:
            r = receivers[i]
            if r >= 0 and channel[r]:
                children[r] += 1

    heads = [i for i in range(n) if channel[i] and children[i] == 0]
    heads.sort(key=lambda i: (-length[i], i))

    claimed = bytearray(n)
    paths = []
    for head in heads:
        if claimed[head]:
            continue
        path = [head]
        claimed[head] = 1
        cur = head
        while True:
            r = receivers[cur]
            if r < 0:
                break
            path.append(r)
            if not channel[r] or claimed[r]:
                break  # reached open water, or joined an existing stroke
            claimed[r] = 1
            cur = r
        if len(path) > 1:
            paths.append(path)
    return paths


def main_stems(receivers, channel, area):
    """Trace each river from its mouth upstream along the largest tributary.

    This is the watercourse a cartographer would name: the single continuous
    line from the sea to the remotest source, chosen at every fork by taking the
    branch with more water in it.
    """
    n = len(receivers)
    kids = {}
    mouths = []
    for i in range(n):
        if not channel[i]:
            continue
        r = receivers[i]
        if r >= 0 and channel[r]:
            kids.setdefault(r, []).append(i)
        else:
            mouths.append(i)

    stems = []
    for mouth in mouths:
        stem = [mouth]
        cur = mouth
        while True:
            branch = kids.get(cur)
            if not branch:
                break
            cur = max(branch, key=lambda j: (area[j], j))
            stem.append(cur)
        stems.append(stem)
    stems.sort(key=lambda s: (-area[s[0]], s[0]))
    return stems, mouths


class Hydrology:
    """Everything derived from routing water over a heightfield."""

    def __init__(
        self,
        height: Field,
        sea_level: float,
        cell_size: float = 1.0,
        river_density: float = 0.5,
    ):
        self.height = height
        self.sea_level = sea_level
        self.cell_size = cell_size
        w, h = height.width, height.height
        n = w * h

        self.filled = fill_depressions(height, sea_level)
        self.receivers, self.order = flow_directions(self.filled, height, sea_level)
        self.area = accumulate(self.receivers, self.order)
        self.length = downstream_length(self.receivers, self.order, w, cell_size)

        # Lakes: anywhere the fill had to raise the surface above the rock.
        self.lake_mask = [
            (self.filled.data[i] - height.data[i]) > LAKE_TOLERANCE
            and height.data[i] > sea_level
            for i in range(n)
        ]
        _, self.lake_regions = flood_regions(self.lake_mask, w, h)

        # Channel threshold as a fraction of the map, so the drainage density
        # of a 128-cell map matches that of a 512-cell one.
        density = max(0.0, min(1.0, river_density))
        frac = 0.0021 * math.exp(-2.6 * density)
        self.channel_area = max(6.0, frac * n)
        land = height.data
        self.channel = [
            land[i] > sea_level and self.area[i] >= self.channel_area
            for i in range(n)
        ]

        self.stream_order = stream_order(self.receivers, self.order, self.channel)
        self.paths = channel_paths(self.receivers, self.channel, self.length, w)
        self.stems, self.mouths = main_stems(self.receivers, self.channel, self.area)

    @property
    def max_order(self) -> int:
        return max(self.stream_order) if self.stream_order else 0

    def channel_cell_count(self) -> int:
        return sum(1 for c in self.channel if c)
