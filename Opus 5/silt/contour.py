"""Marching squares: turning a scalar field into lines.

Used three times over, for three different jobs:

* the **coastline** is the contour at sea level;
* the **contour lines** and the bathymetric bands are contours at intervals;
* the **lake outlines** are contours of the lake mask at 0.5.

The algorithm walks every 2x2 block of samples, classifies its four corners as
above or below the level to get one of sixteen cases, and emits the line
segments crossing that block. Corner values that straddle the level are
interpolated, which is what makes the result smooth rather than staircased.

Segments come out unordered, so :func:`chain` stitches them into polylines by
matching endpoints -- exact float matches, because adjacent blocks compute their
shared edge from the same two corner values by the same expression.
"""

from __future__ import annotations

# Corner bits: top-left 1, top-right 2, bottom-right 4, bottom-left 8.
# Edges are named T, R, B, L and each spans two corners.
_CORNER_BITS = (1, 2, 4, 8)
_EDGE_CORNERS = {"T": (1, 2), "R": (2, 4), "B": (8, 4), "L": (1, 8)}
# The two edges that meet at each corner.
_CORNER_EDGES = {1: ("T", "L"), 2: ("T", "R"), 4: ("R", "B"), 8: ("B", "L")}


def _straddled(case: int, edge: str) -> bool:
    """Does the level cross this edge? Only if its two corners disagree."""
    a, b = _EDGE_CORNERS[edge]
    return bool(case & a) != bool(case & b)


def _build_cases():
    """Derive the sixteen-case table rather than typing it out.

    Hand-written marching-squares tables are notorious: two entries swapped is
    invisible in the source and produces interpolation parameters far outside
    [0, 1], which draw as wild spurs shooting off the contour. Deriving each
    case from "an edge is crossed exactly when its corners disagree" makes that
    class of mistake impossible.
    """
    table = {}
    for case in range(1, 15):
        edges = [edge for edge in ("T", "R", "B", "L") if _straddled(case, edge)]
        if len(edges) == 2:
            table[case] = ((edges[0], edges[1]),)
    return table


_CASES = _build_cases()


def _saddle(case: int, centre_above: bool):
    """Resolve an ambiguous saddle using the value at the block's centre.

    Cases 5 and 10 have two opposite corners above the level and two below, so
    all four edges are crossed and there are two ways to join them. The centre
    decides: whichever pair of corners disagrees with it is the pair that gets
    cut off into its own little island.
    """
    isolate = [bit for bit in _CORNER_BITS if bool(case & bit) != centre_above]
    return tuple(_CORNER_EDGES[bit] for bit in isolate)


_QUANTUM = 1e-7


def _fraction(low: float, high: float, level: float) -> float:
    denominator = high - low
    if denominator == 0.0:
        return 0.5
    t = (level - low) / denominator
    # A crossing lies on its edge by definition; clamping costs nothing and
    # contains any damage from a near-zero denominator.
    return 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)


def _crossing(edge: str, x: int, y: int, tl: float, tr: float, br: float, bl: float,
              level: float):
    """Where the level crosses one edge of the block at (x, y)."""
    if edge == "T":
        return (x + _fraction(tl, tr, level), float(y))
    if edge == "R":
        return (float(x + 1), y + _fraction(tr, br, level))
    if edge == "B":
        return (x + _fraction(bl, br, level), float(y + 1))
    return (float(x), y + _fraction(tl, bl, level))


def segments(values, width: int, height: int, level: float):
    """Line segments of the ``level`` contour, in cell coordinates.

    The level is nudged by a hair before use. A sample lying *exactly* on the
    contour puts the crossing exactly on a lattice corner, where up to four
    edges meet at one point and the chaining step can no longer tell which
    segment continues which -- rings fragment or splice into each other. It is
    not a hypothetical: sea level is chosen as a quantile of the heightfield, so
    it is frequently equal to a cell's height on the nose. Shifting the level
    instead of special-casing the geometry keeps every cell consistent with its
    neighbours, which is the only property the chaining actually needs.
    """
    level += 1e-9 * (abs(level) + 1.0)
    out = []
    for y in range(height - 1):
        row = y * width
        next_row = row + width
        for x in range(width - 1):
            tl = values[row + x]
            tr = values[row + x + 1]
            br = values[next_row + x + 1]
            bl = values[next_row + x]

            case = 0
            if tl >= level:
                case |= 1
            if tr >= level:
                case |= 2
            if br >= level:
                case |= 4
            if bl >= level:
                case |= 8
            if case == 0 or case == 15:
                continue

            if case in (5, 10):
                mean = (tl + tr + br + bl) * 0.25
                pairs = _saddle(case, mean >= level)
            else:
                pairs = _CASES[case]

            for a, b in pairs:
                out.append(
                    (
                        _crossing(a, x, y, tl, tr, br, bl, level),
                        _crossing(b, x, y, tl, tr, br, bl, level),
                    )
                )
    return out


def _key(point):
    return (round(point[0] / _QUANTUM), round(point[1] / _QUANTUM))


def chain(segs):
    """Stitch segments into polylines. Returns ``[(points, closed), ...]``."""
    if not segs:
        return []

    # Endpoint -> indices of segments touching it.
    touching = {}
    for index, (a, b) in enumerate(segs):
        touching.setdefault(_key(a), []).append(index)
        touching.setdefault(_key(b), []).append(index)

    used = bytearray(len(segs))
    chains = []

    def walk(start_index, from_point):
        """Follow connected segments away from ``from_point``."""
        points = [from_point]
        index = start_index
        current = from_point
        while True:
            used[index] = 1
            a, b = segs[index]
            nxt = b if _key(a) == _key(current) else a
            points.append(nxt)
            current = nxt
            candidates = touching.get(_key(current), ())
            following = -1
            for candidate in candidates:
                if not used[candidate]:
                    following = candidate
                    break
            if following < 0:
                return points
            index = following

    # Open chains first, starting from loose ends, so that a line running off
    # the edge of the map is not entered halfway and split into two.
    for index, (a, b) in enumerate(segs):
        if used[index]:
            continue
        for endpoint in (a, b):
            if len(touching.get(_key(endpoint), ())) == 1:
                points = walk(index, endpoint)
                if len(points) > 1:
                    chains.append((points, False))
                break

    # Whatever is left is closed loops.
    for index, (a, b) in enumerate(segs):
        if used[index]:
            continue
        points = walk(index, a)
        if len(points) > 2:
            closed = _key(points[0]) == _key(points[-1])
            chains.append((points[:-1] if closed else points, closed))
    return chains


def contours(values, width: int, height: int, level: float):
    """Marching squares plus stitching, in one call."""
    return chain(segments(values, width, height, level))


def smooth(points, closed: bool = False, passes: int = 2):
    """Chaikin corner cutting.

    Marching squares output is faceted at cell scale; two passes of this turn a
    coastline from a run of tiny straight hops into a curve.
    """
    result = list(points)
    for _ in range(max(0, passes)):
        if len(result) < 3:
            return result
        out = []
        if closed:
            pairs = list(zip(result, result[1:] + result[:1]))
        else:
            out.append(result[0])
            pairs = list(zip(result, result[1:]))
        for (x0, y0), (x1, y1) in pairs:
            out.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            out.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        if not closed:
            out.append(result[-1])
        result = out
    return result


def _perpendicular(point, start, end) -> float:
    """Distance from ``point`` to the segment ``start``-``end``."""
    px, py = point
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    if span < 1e-18:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / span
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    ox, oy = ax + t * dx, ay + t * dy
    return ((px - ox) ** 2 + (py - oy) ** 2) ** 0.5


def simplify(points, tolerance: float = 0.35):
    """Douglas-Peucker: drop points that no reader would miss.

    Chaikin quadruples the point count and this puts most of it back, which
    matters when one sheet holds a few hundred coastlines.

    It has to be Douglas-Peucker rather than the obvious one-pass "is this point
    nearly collinear with its two neighbours?" filter. On a long shallow arc,
    *every* consecutive triple is nearly collinear, so the cheap filter deletes
    the entire interior and replaces the arc with its chord -- which draws as an
    inexplicable straight line ruled across a headland. Recursing on the point
    of maximum deviation from the current chord cannot make that mistake,
    because the chord is exactly what it measures against.
    """
    if len(points) < 3:
        return list(points)

    keep = bytearray(len(points))
    keep[0] = 1
    keep[-1] = 1
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        worst = 0.0
        split = -1
        start, end = points[first], points[last]
        for k in range(first + 1, last):
            deviation = _perpendicular(points[k], start, end)
            if deviation > worst:
                worst = deviation
                split = k
        if split > 0 and worst >= tolerance:
            keep[split] = 1
            stack.append((first, split))
            stack.append((split, last))
    return [p for p, flag in zip(points, keep) if flag]
