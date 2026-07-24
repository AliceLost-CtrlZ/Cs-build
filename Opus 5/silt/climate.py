"""Rain, warmth, and what grows.

Temperature is the easy half: cold towards the poles, cold with altitude. The
world picks a latitude band, so one seed gives you a tropical archipelago and
the next a subarctic coast.

Rain is the interesting half, and it is done as a *sweep*. Air enters one edge
of the map carrying humidity, gains it over water, and loses it as rain wherever
the ground rises beneath it. Downwind of a range the air has nothing left to
give, which produces a rain shadow -- a desert immediately behind mountains,
with forest on the windward slope. That asymmetry is the single most convincing
thing on a climate map, and it falls out of the sweep for free.

Prevailing wind follows the latitude band: trade winds out of the east in the
tropics, westerlies in the temperate belt. So which flank of a range is wet
depends on where in the world you are.
"""

from __future__ import annotations

import math

from .field import Field
from .rng import Rng
from .util import clamp, lerp, smoothstep

# key -> (label, base RGB). Colours are muted on purpose: an atlas sheet, not a
# satellite composite. Hillshade and elevation tint are layered over these.
BIOMES = {
    "ice": ("Permanent ice", (0xE6, 0xEC, 0xEF)),
    "snowfield": ("Snowfield", (0xF1, 0xF4, 0xF5)),
    "bare": ("Bare rock", (0xAE, 0xA4, 0x93)),
    "tundra": ("Tundra", (0xAC, 0xB1, 0x9C)),
    "taiga": ("Boreal forest", (0x5C, 0x78, 0x64)),
    "cold steppe": ("Cold steppe", (0xAB, 0xAE, 0x85)),
    "temperate forest": ("Temperate forest", (0x73, 0x91, 0x61)),
    "temperate rainforest": ("Temperate rainforest", (0x5D, 0x84, 0x5D)),
    "grassland": ("Grassland", (0xB3, 0xBB, 0x79)),
    "steppe": ("Dry steppe", (0xC6, 0xC0, 0x84)),
    "desert": ("Desert", (0xDE, 0xCD, 0xA0)),
    "savanna": ("Savanna", (0xC8, 0xBA, 0x70)),
    "dry forest": ("Monsoon forest", (0x92, 0x9F, 0x5D)),
    "jungle": ("Tropical forest", (0x4D, 0x80, 0x51)),
    "marsh": ("Marsh", (0x7A, 0x91, 0x75)),
}

# Order for the map legend: cold and high at the top, hot and wet at the bottom.
LEGEND_ORDER = (
    "snowfield", "ice", "bare", "tundra", "cold steppe", "taiga",
    "temperate rainforest", "temperate forest", "grassland", "steppe",
    "desert", "savanna", "dry forest", "jungle", "marsh",
)


def zonal_wetness(lat: float) -> float:
    """Latitudinal rainfall envelope, in [0, 1].

    Wet at the equator, dry at the horse latitudes, wet again in the storm belt,
    dry at the poles. Three Gaussians and a ramp -- crude, but it puts the
    world's deserts where an atlas would put them.
    """
    a = abs(lat)
    itcz = math.exp(-((a / 13.0) ** 2))
    horse = math.exp(-(((a - 26.0) / 11.0) ** 2))
    storm = math.exp(-(((a - 52.0) / 15.0) ** 2))
    polar = smoothstep(62.0, 90.0, a)
    return clamp(0.50 + 0.46 * itcz - 0.34 * horse + 0.26 * storm - 0.34 * polar)


def classify(elev: float, temp: float, moist: float, wet_flat: bool) -> str:
    """Pick a biome from normalised elevation, temperature and moisture."""
    if elev > 0.88 and temp < 0.40:
        return "snowfield"
    if elev > 0.82:
        return "bare"
    if temp < 0.10:
        return "ice"
    if wet_flat and temp > 0.22:
        return "marsh"
    if temp < 0.24:
        return "tundra"
    if temp < 0.44:
        return "cold steppe" if moist < 0.26 else "taiga"
    if temp < 0.70:
        if moist < 0.17:
            return "desert"
        if moist < 0.34:
            return "steppe"
        if moist < 0.52:
            return "grassland"
        if moist < 0.74:
            return "temperate forest"
        return "temperate rainforest"
    if moist < 0.15:
        return "desert"
    if moist < 0.33:
        return "savanna"
    if moist < 0.58:
        return "dry forest"
    return "jungle"


class Climate:
    """Temperature, moisture and biome for every cell."""

    def __init__(
        self,
        height: Field,
        sea_level: float,
        rng: Rng,
        area=None,
        slope: Field | None = None,
        cell_km: float = 2.0,
    ):
        w, h = height.width, height.height
        n = w * h
        self.width, self.height_cells = w, h
        self.sea_level = sea_level

        band = rng.derive("latitude")
        # Where on its planet this map sits, and how much of it the map spans.
        self.lat_span = band.between(16.0, 42.0)
        self.lat_centre = band.between(-38.0, 56.0)
        # Easterly trades in the tropics, westerlies in the temperate belt.
        self.wind_from_east = abs(self.lat_centre) < 24.0
        self.wind = "east" if self.wind_from_east else "west"

        self.temperature = Field(w, h)
        self.moisture = Field(w, h)
        self.biome = ["ice"] * n

        self._temperatures(height)
        self._rainfall(height)
        self._biomes(height, area, slope)

    # -- latitude ----------------------------------------------------------

    def latitude(self, y: float) -> float:
        """Degrees at row ``y``; north is up, so latitude falls southward."""
        frac = 0.5 - (y / max(1, self.height_cells - 1) - 0.5)
        return self.lat_centre + (frac - 0.5) * self.lat_span

    def celsius(self, i: int) -> float:
        """A readable temperature for the gazetteer."""
        return -18.0 + 46.0 * self.temperature.data[i]

    # -- fields ------------------------------------------------------------

    def _temperatures(self, height: Field) -> None:
        w, h = self.width, self.height_cells
        sea = self.sea_level
        span = max(1e-6, 1.0 - sea)
        out = self.temperature.data
        hd = height.data
        for y in range(h):
            lat = self.latitude(y)
            # Insolation by latitude, then an environmental lapse rate.
            base = clamp(1.02 - (abs(lat) / 90.0) ** 1.25 * 1.15, 0.0, 1.0)
            row = y * w
            for x in range(w):
                i = row + x
                elev = hd[i]
                if elev <= sea:
                    out[i] = clamp(base * 0.94 + 0.03)  # water evens out extremes
                else:
                    out[i] = clamp(base - 0.62 * ((elev - sea) / span) ** 1.05)

    def _sweep(self, height: Field, from_east: bool):
        """One pass of moist air across the map, raining as the ground rises."""
        w, h = self.width, self.height_cells
        sea = self.sea_level
        hd = height.data
        rain = [0.0] * (w * h)
        xs = list(range(w - 1, -1, -1) if from_east else range(w))

        for y in range(h):
            row = y * w
            zonal = zonal_wetness(self.latitude(y))
            humidity = 0.55 * zonal + 0.18
            previous = hd[row + xs[0]]
            for x in xs:
                i = row + x
                elev = hd[i]
                if elev <= sea:
                    # Over water: evaporation tops the air back up.
                    humidity += (1.0 - humidity) * 0.30 * (0.45 + 0.55 * zonal)
                    rain[i] = 0.85 * zonal
                else:
                    rise = elev - previous
                    orographic = 22.0 * rise if rise > 0.0 else 3.0 * rise
                    fall = humidity * clamp(0.045 + orographic, 0.006, 0.80)
                    rain[i] = fall
                    humidity = max(0.0, humidity - fall)
                    # Evapotranspiration. Without it the air arrives at the far
                    # coast bone dry and every continental interior is Sahara.
                    humidity += (1.0 - humidity) * 0.035 * zonal
                previous = elev
        return rain

    def _rainfall(self, height: Field) -> None:
        w, h = self.width, self.height_cells
        n = w * h
        sea = self.sea_level
        hd = height.data

        # Prevailing wind does most of the work, but weather also arrives from
        # the other quarter. Modelling only one direction gives absolute rain
        # shadows -- a hard line with forest on one side and dune on the other.
        main = self._sweep(height, self.wind_from_east)
        counter = self._sweep(height, not self.wind_from_east)
        blended = [0.74 * main[i] + 0.26 * counter[i] for i in range(n)]

        field = Field(w, h, data=blended).blurred(2)

        land_indices = [i for i in range(n) if hd[i] > sea]
        out = self.moisture.data
        for i in range(n):
            out[i] = 1.0

        if not land_indices:
            return

        # Two normalisations, blended. Absolute rescaling keeps a genuinely arid
        # world arid; rank transform guarantees that *some* of every world is
        # wet and some is dry, so no seed comes out as an unreadable monotone.
        values = sorted((field.data[i], i) for i in land_indices)
        count = len(values)
        lo = values[int(0.04 * (count - 1))][0]
        hi = values[int(0.96 * (count - 1))][0]
        span = max(1e-9, hi - lo)

        rank_of = {}
        for position, (_, i) in enumerate(values):
            rank_of[i] = position / max(1, count - 1)

        for i in land_indices:
            absolute = clamp((field.data[i] - lo) / span)
            out[i] = clamp(0.55 * rank_of[i] + 0.45 * absolute)

    def _biomes(self, height: Field, area, slope: Field | None) -> None:
        w, h = self.width, self.height_cells
        n = w * h
        sea = self.sea_level
        span = max(1e-6, 1.0 - sea)
        hd = height.data
        td = self.temperature.data
        md = self.moisture.data
        wet_threshold = 0.0016 * n
        out = self.biome
        for i in range(n):
            if hd[i] <= sea:
                out[i] = "ice" if td[i] < 0.07 else "marsh"  # unused for water
                continue
            elev = (hd[i] - sea) / span
            flat = slope is None or slope.data[i] < 0.010
            wet_flat = (
                flat
                and md[i] > 0.45
                and area is not None
                and area[i] > wet_threshold
            )
            out[i] = classify(elev, td[i], md[i], wet_flat)

    # -- summary -----------------------------------------------------------

    def biome_fractions(self, land_mask):
        counts = {}
        total = 0
        for i, is_land in enumerate(land_mask):
            if is_land:
                counts[self.biome[i]] = counts.get(self.biome[i], 0) + 1
                total += 1
        if not total:
            return []
        return sorted(
            ((k, v / total) for k, v in counts.items()), key=lambda kv: -kv[1]
        )
