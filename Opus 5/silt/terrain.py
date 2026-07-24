"""Raising the land.

Three ingredients, in order of how much they matter to the eye:

1. **Belts.** A smooth noise field's zero-contour is a wandering curve across
   the map. Widen that curve into a ribbon and you have something that behaves
   like a plate boundary: mountains that run in *lines*, with a near side and a
   far side. Scattered ridged noise never looks like a range; this does.
2. **Basement.** Warped fractal noise, low amplitude. Rolling ground.
3. **A coastal mask.** Decides sea from land at the largest scale, and gives
   each world its overall figure -- one continent, an archipelago, a ragged
   peninsular coast, or a ring of land around an inland sea.

Sea level is not a constant. It is chosen afterwards as a quantile of the
finished heightfield, so every seed yields a map with a usable amount of land.
"""

from __future__ import annotations

import math

from .field import Field
from .noise import Noise
from .rng import Rng
from .util import band, clamp, smoothstep

# Each shape sets the coastal mask and how much land to keep.
SHAPES = {
    "continent": {"land": 0.42, "warp": 0.10, "belts": 2},
    "archipelago": {"land": 0.24, "warp": 0.18, "belts": 2},
    "peninsulas": {"land": 0.36, "warp": 0.34, "belts": 2},
    "inland sea": {"land": 0.40, "warp": 0.14, "belts": 3},
}

SHAPE_WEIGHTS = (
    ("continent", 4.0),
    ("peninsulas", 3.0),
    ("archipelago", 2.0),
    ("inland sea", 2.0),
)


class Terrain:
    """The heightfield and the parameters that produced it."""

    def __init__(self, height: Field, sea_level: float, shape: str, relief: float):
        self.height = height
        self.sea_level = sea_level
        self.shape = shape
        self.relief = relief

    @property
    def width(self) -> int:
        return self.height.width

    def land_mask(self):
        sea = self.sea_level
        return [v > sea for v in self.height.data]

    def land_fraction(self) -> float:
        sea = self.sea_level
        return sum(1 for v in self.height.data if v > sea) / len(self.height.data)


def _coast_mask(shape: str, r: float, nx: float, ny: float, edge: Noise) -> float:
    """How much land is permitted at this point, in [0, 1]."""
    ragged = edge.fbm(nx * 2.4 + 3.1, ny * 2.4 - 5.7, octaves=4)

    if shape == "archipelago":
        frame = smoothstep(0.0, 0.55, 1.30 - r ** 1.6)
        blobs = edge.fbm(nx * 3.4 - 8.2, ny * 3.4 + 2.6, octaves=5)
        return frame * smoothstep(-0.06, 0.34, blobs + 0.25 * ragged)

    if shape == "inland sea":
        frame = smoothstep(0.0, 0.48, 1.18 - r ** 2.0 + 0.34 * ragged)
        inner = edge.fbm(nx * 2.9 + 14.0, ny * 2.9 - 11.0, octaves=3)
        hole = smoothstep(0.0, 0.30, r - 0.20 + 0.16 * inner)
        return frame * hole

    if shape == "peninsulas":
        # Same falloff, much louder coastline noise: inlets and headlands.
        return smoothstep(0.0, 0.46, 1.16 - r ** 1.9 + 0.62 * ragged)

    return smoothstep(0.0, 0.50, 1.14 - r ** 2.0 + 0.40 * ragged)


def build(width: int, height: int, rng: Rng) -> Terrain:
    """Generate a heightfield in [0, 1] with a sea level chosen to fit."""
    shape = rng.derive("shape").weighted(SHAPE_WEIGHTS)
    params = SHAPES[shape]

    basement = Noise(rng.derive("basement"))
    warper = Noise(rng.derive("warp"))
    edge = Noise(rng.derive("coast"))
    crest = Noise(rng.derive("crest"))
    belt_noise = [Noise(rng.derive("belt", k)) for k in range(params["belts"])]

    # Belt geometry: each belt gets its own frequency, thickness and height, so
    # one world can hold a broad old massif and a narrow young cordillera.
    belt_rng = rng.derive("belt-shape")
    belts = []
    for k in range(params["belts"]):
        belts.append(
            {
                "noise": belt_noise[k],
                "freq": belt_rng.between(0.9, 1.7),
                "thickness": belt_rng.between(0.10, 0.30),
                "gain": belt_rng.between(0.55, 1.0),
                "phase": belt_rng.between(-0.35, 0.35),
            }
        )
    belts.sort(key=lambda b: -b["gain"])
    relief = sum(b["gain"] for b in belts) / len(belts)

    warp_strength = params["warp"]
    half = max(width, height) / 2.0
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0

    data = [0.0] * (width * height)
    i = 0
    for y in range(height):
        for x in range(width):
            nx = x / width
            ny = y / height

            dx = (x - cx) / half
            dy = (y - cy) / half
            r = math.sqrt(dx * dx + dy * dy)

            # Warp before sampling: features bend and hook instead of knitting.
            # The low base frequency is deliberate -- mid-frequency power in the
            # basement chops the flanks into hundreds of tiny catchments, and
            # then no river on the map is longer than a thumbnail.
            wx, wy = warper.warp(nx * 1.8, ny * 1.8, strength=warp_strength, freq=1.1)

            base = 0.5 + 0.5 * basement.fbm(wx, wy, octaves=7, gain=0.50)

            orogeny = 0.0
            for belt in belts:
                f = belt["freq"]
                signal = belt["noise"].fbm(nx * f + 5.0, ny * f - 3.0, octaves=3)
                ribbon = band(signal + belt["phase"], belt["thickness"])
                if ribbon > 0.0:
                    crests = crest.ridged(
                        wx * 2.9 + 17.0, wy * 2.9 - 9.0, octaves=6, sharpness=2.2
                    )
                    orogeny = max(orogeny, ribbon * crests * belt["gain"])

            mask = _coast_mask(shape, r, nx, ny, edge)
            h = (base * 0.58 + orogeny * 0.90) * mask

            # Trench the deep ocean so the bathymetry has somewhere to shade.
            if mask < 0.04:
                h -= 0.06 * (1.0 - mask / 0.04)

            data[i] = h
            i += 1

    field = Field(width, height, data=data)
    field.normalized(0.0, 1.0)

    sea_level = max(0.05, min(0.85, field.quantile(1.0 - params["land"])))
    _shape_hypsometry(field, sea_level)

    return Terrain(field, sea_level, shape, clamp(relief))


def _shape_hypsometry(field: Field, sea_level: float, land_gamma: float = 1.55,
                      sea_gamma: float = 0.78) -> None:
    """Bend the elevation histogram towards a planet's rather than noise's.

    Fractal noise is symmetric: as much land sits high as low. Real continents
    are nothing like that -- most land is close to sea level and the high ground
    is a thin tail. Without this correction the whole interior of every map
    renders as mid-elevation brown, and mountains have nothing to stand out
    against.

    The ocean gets the opposite treatment: a shorter shelf and a deeper abyssal
    plain, so coasts do not sit inside a wide band of pale shallows.
    """
    span = 1.0 - sea_level
    data = field.data
    for i, v in enumerate(data):
        if v > sea_level:
            if span > 1e-9:
                data[i] = sea_level + span * ((v - sea_level) / span) ** land_gamma
        elif sea_level > 1e-9:
            depth = (sea_level - v) / sea_level
            data[i] = sea_level - sea_level * depth ** sea_gamma
