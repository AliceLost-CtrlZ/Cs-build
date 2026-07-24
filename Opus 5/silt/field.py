"""A 2D scalar grid stored as one flat list.

Nested lists are pleasant to read and slow to walk. Every hot loop in Silt --
erosion, priority flood, the rain sweep, the renderer -- touches its field's
``data`` list directly by index. The methods here are the cold paths: setup,
statistics, sampling.

Coordinate convention: ``x`` runs east (column), ``y`` runs south (row), origin
at the north-west corner, index ``y * width + x``. Same as the image we will
eventually write, which saves a flip later.
"""

from __future__ import annotations

# East, then clockwise. Diagonal steps cost sqrt(2) in flow routing.
D8 = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))
D8_DIST = (1.0, 1.4142135623730951) * 4
D4 = ((1, 0), (0, 1), (-1, 0), (0, -1))


class Field:
    __slots__ = ("width", "height", "data")

    def __init__(self, width: int, height: int, fill: float = 0.0, data=None) -> None:
        self.width = width
        self.height = height
        if data is None:
            self.data = [fill] * (width * height)
        else:
            if len(data) != width * height:
                raise ValueError(
                    f"data has {len(data)} cells, expected {width * height}"
                )
            self.data = data

    # -- basics ------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def __getitem__(self, i: int) -> float:
        return self.data[i]

    def __setitem__(self, i: int, v: float) -> None:
        self.data[i] = v

    def index(self, x: int, y: int) -> int:
        return y * self.width + x

    def xy(self, i: int):
        return i % self.width, i // self.width

    def at(self, x: int, y: int) -> float:
        return self.data[y * self.width + x]

    def put(self, x: int, y: int, v: float) -> None:
        self.data[y * self.width + x] = v

    def on_border(self, i: int) -> bool:
        x, y = i % self.width, i // self.width
        return x == 0 or y == 0 or x == self.width - 1 or y == self.height - 1

    def copy(self) -> "Field":
        return Field(self.width, self.height, data=list(self.data))

    @classmethod
    def generated(cls, width: int, height: int, fn) -> "Field":
        """Build from ``fn(x, y)``."""
        data = [0.0] * (width * height)
        i = 0
        for y in range(height):
            for x in range(width):
                data[i] = fn(x, y)
                i += 1
        return cls(width, height, data=data)

    # -- statistics --------------------------------------------------------

    def min(self) -> float:
        return min(self.data)

    def max(self) -> float:
        return max(self.data)

    def quantile(self, q: float) -> float:
        """Value at fraction ``q`` of the sorted cells (0 -> min, 1 -> max)."""
        if not self.data:
            return 0.0
        ordered = sorted(self.data)
        pos = q * (len(ordered) - 1)
        lo = int(pos)
        hi = min(lo + 1, len(ordered) - 1)
        frac = pos - lo
        return ordered[lo] * (1.0 - frac) + ordered[hi] * frac

    # -- whole-field operations -------------------------------------------

    def normalized(self, lo: float = 0.0, hi: float = 1.0) -> "Field":
        """Rescale in place so the extremes land on ``lo`` and ``hi``."""
        cur_lo = min(self.data)
        cur_hi = max(self.data)
        span = cur_hi - cur_lo
        if span <= 1e-12:
            self.data = [lo] * len(self.data)
        else:
            scale = (hi - lo) / span
            self.data = [lo + (v - cur_lo) * scale for v in self.data]
        return self

    def clamped(self, lo: float = 0.0, hi: float = 1.0) -> "Field":
        self.data = [lo if v < lo else (hi if v > hi else v) for v in self.data]
        return self

    def blurred(self, passes: int = 1) -> "Field":
        """Separable 1-2-1 blur, edges clamped. Returns a new field."""
        w, h = self.width, self.height
        src = list(self.data)
        tmp = [0.0] * len(src)
        for _ in range(max(0, passes)):
            for y in range(h):
                row = y * w
                for x in range(w):
                    i = row + x
                    left = src[i - 1] if x > 0 else src[i]
                    right = src[i + 1] if x < w - 1 else src[i]
                    tmp[i] = (left + 2.0 * src[i] + right) * 0.25
            for y in range(h):
                row = y * w
                up = row - w
                down = row + w
                for x in range(w):
                    i = row + x
                    above = tmp[up + x] if y > 0 else tmp[i]
                    below = tmp[down + x] if y < h - 1 else tmp[i]
                    src[i] = (above + 2.0 * tmp[i] + below) * 0.25
        return Field(w, h, data=src)

    # -- sampling ----------------------------------------------------------

    def bilinear(self, fx: float, fy: float) -> float:
        """Sample at fractional cell coordinates, clamped at the edges."""
        w, h = self.width, self.height
        if fx < 0.0:
            fx = 0.0
        elif fx > w - 1:
            fx = w - 1.0
        if fy < 0.0:
            fy = 0.0
        elif fy > h - 1:
            fy = h - 1.0
        x0 = int(fx)
        y0 = int(fy)
        x1 = x0 + 1 if x0 < w - 1 else x0
        y1 = y0 + 1 if y0 < h - 1 else y0
        tx = fx - x0
        ty = fy - y0
        d = self.data
        r0 = y0 * w
        r1 = y1 * w
        top = d[r0 + x0] * (1.0 - tx) + d[r0 + x1] * tx
        bottom = d[r1 + x0] * (1.0 - tx) + d[r1 + x1] * tx
        return top * (1.0 - ty) + bottom * ty

    def neighbours(self, i: int, offsets=D8):
        """Indices of in-bounds neighbours of cell ``i``."""
        w = self.width
        x, y = i % w, i // w
        for dx, dy in offsets:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < self.height:
                yield ny * w + nx


def flood_regions(mask, width: int, height: int, offsets=D4):
    """Label connected runs of truthy cells in ``mask``.

    Returns ``(labels, regions)`` where ``labels[i]`` is -1 outside the mask and
    a region id inside, and ``regions`` is a list of index lists.
    """
    labels = [-1] * (width * height)
    regions = []
    for start in range(width * height):
        if not mask[start] or labels[start] != -1:
            continue
        rid = len(regions)
        cells = [start]
        labels[start] = rid
        head = 0
        while head < len(cells):
            i = cells[head]
            head += 1
            x, y = i % width, i // width
            for dx, dy in offsets:
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    j = ny * width + nx
                    if mask[j] and labels[j] == -1:
                        labels[j] = rid
                        cells.append(j)
        regions.append(cells)
    return labels, regions
