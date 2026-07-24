"""Cutting the land back down.

Noise alone gives hills that are smooth in every direction. Real terrain is not
isotropic: it has *drainage*. Valleys join at acute angles, ridges are sharp
where two catchments meet, and slope shallows as the river below gets bigger.
None of that comes from noise -- it comes from water having somewhere to be.

So: the stream-power law, run on the drainage network that :mod:`silt.hydro`
extracts, a handful of times.

    dz/dt = U - K * A^m * S^n

``U`` uplift, ``A`` upstream area, ``S`` local slope. Erosion is proportional to
how much water passes and how steeply it falls, which means big rivers grind
their valleys flat and headwaters stay steep. That single term is most of what
makes a heightfield look like somewhere.

Two guards keep an explicit forward-Euler step honest:

* A cell never erodes below its own receiver. That preserves the drainage
  order, so the network stays a forest and cannot oscillate.
* Erosion is computed from the *raw* surface, not the depression-filled one, so
  the flat water of a lake does no cutting.
"""

from __future__ import annotations

from .field import D8, D8_DIST, Field
from .hydro import accumulate, fill_depressions, flow_directions
from .terrain import Terrain


def _creep(height: Field, sea_level: float, rate: float) -> None:
    """Hillslope diffusion: soil sliding downhill, independent of rivers.

    Softens the interfluves that stream power leaves knife-edged, and is the
    reason gentle country looks gentle instead of merely lower.
    """
    if rate <= 0.0:
        return
    w, h = height.width, height.height
    d = height.data
    out = list(d)
    for y in range(1, h - 1):
        row = y * w
        for x in range(1, w - 1):
            i = row + x
            here = d[i]
            if here <= sea_level:
                continue
            total = (
                d[i - 1] + d[i + 1] + d[i - w] + d[i + w]
                + 0.5 * (d[i - w - 1] + d[i - w + 1] + d[i + w - 1] + d[i + w + 1])
            )
            average = total / 6.0
            out[i] = here + (average - here) * rate
    height.data = out


def erode(
    terrain: Terrain,
    iterations: int = 24,
    strength: float = 1.0,
    uplift: float = 0.0015,
    creep: float = 0.05,
    m: float = 0.5,
    n_exp: float = 1.0,
    progress=None,
) -> Terrain:
    """Run stream-power erosion in place; returns the same Terrain.

    ``strength`` is ``K``, ``uplift`` is peak ``U`` per step (scaled by the
    original elevation, so ranges keep rising while plains do not).

    The two are not free parameters. There is a diagnostic that says whether
    they are set sensibly: regress log channel slope against log drainage area
    and you should recover an exponent near ``-m/n``, because that is what
    stream power drives a landscape towards. Averaged over seeds these defaults
    land within a hundredth of the theoretical -0.5; raising ``strength`` drives
    it well past -0.6, which reads as a landscape sanded flat. ``tests/
    test_erosion.py`` measures it, so retuning by eye is not necessary.
    """
    height = terrain.height
    w, h = height.width, height.height
    cells = w * h
    sea = terrain.sea_level
    land_target = terrain.land_fraction()

    # Uplift is keyed to the *original* elevation: where the belts put rock,
    # rock keeps arriving. Otherwise 18 steps of erosion flatten the world.
    original = list(height.data)
    span = max(1e-6, 1.0 - sea)
    uplift_rate = [
        uplift * ((v - sea) / span) ** 1.2 if v > sea else 0.0 for v in original
    ]

    for step in range(iterations):
        filled = fill_depressions(height, sea)
        receivers, order = flow_directions(filled, height, sea)
        area = accumulate(receivers, order)

        d = height.data
        for i in range(cells):
            r = receivers[i]
            if r < 0:
                continue
            drop = d[i] - d[r]
            if drop <= 0.0:
                continue  # standing water: no cutting here
            dx = abs((i % w) - (r % w))
            dy = abs((i // w) - (r // w))
            dist = 1.4142135623730951 if dx and dy else 1.0
            slope = drop / dist
            a = area[i] / cells
            cut = strength * (a ** m) * (slope ** n_exp)
            limit = 0.45 * drop  # stay above the receiver
            d[i] = d[i] - (cut if cut < limit else limit) + uplift_rate[i]

        _creep(height, sea, creep)
        if progress is not None:
            progress(step + 1, iterations)

    height.normalized(0.0, 1.0)
    # Erosion and uplift do not balance exactly, so re-cut sea level at the same
    # land fraction we started with rather than trusting the old absolute value.
    terrain.sea_level = height.quantile(1.0 - land_target)
    return terrain


def slope_field(height: Field, cell_size: float = 1.0) -> Field:
    """Steepest downhill gradient at each cell. Used for shading and biomes."""
    w, h = height.width, height.height
    d = height.data
    out = [0.0] * (w * h)
    for y in range(h):
        row = y * w
        for x in range(w):
            i = row + x
            here = d[i]
            worst = 0.0
            for k in range(8):
                dx, dy = D8[k]
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    drop = here - d[ny * w + nx]
                    if drop > 0.0:
                        s = drop / (D8_DIST[k] * cell_size)
                        if s > worst:
                            worst = s
            out[i] = worst
    return Field(w, h, data=out)
