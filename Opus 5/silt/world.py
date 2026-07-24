"""Assembling a world, in the order the world would have done it.

Rock, then water, then weather, then names -- each stage reading only what the
stages before it produced. The sequence matters:

* erosion needs somewhere for water to go, so hydrology runs *inside* it;
* the biomes need the drainage area, because a wet flat with a big catchment is
  a marsh and a wet flat without one is a meadow;
* the names come last, because what you call a place depends on what it is.

Everything hangs off one 64-bit seed. Same word in, same world out.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from . import erosion as erosion_mod
from . import terrain as terrain_mod
from .climate import Climate
from .features import Features, extract
from .field import D4, Field
from .hydro import Hydrology
from .names import Namer
from .rng import Rng

DEFAULT_LIMITS = {
    "rivers": 14,
    "lakes": 8,
    "ranges": 7,
    "summits": 4,
    "islands": 6,
    "bays": 5,
    "capes": 5,
    "regions": 7,
}


@dataclass
class World:
    """A finished world: fields, features, and the numbers that describe it."""

    seed: object
    rng: Rng
    width: int
    height_cells: int
    height: Field
    sea_level: float
    shape: str
    cell_km: float
    peak_altitude: float
    ocean_depth: float
    land_mask: list
    slope: Field
    hydro: Hydrology
    climate: Climate
    namer: Namer
    limits: dict = dc_field(default_factory=lambda: dict(DEFAULT_LIMITS))
    features: Features = dc_field(default_factory=Features)
    name: str = ""
    title: str = ""

    # -- unit conversions -------------------------------------------------

    @property
    def map_km(self) -> float:
        return self.width * self.cell_km

    def metres(self, i: int) -> float:
        """Elevation above sea level, in metres."""
        span = max(1e-6, 1.0 - self.sea_level)
        return max(0.0, (self.height.data[i] - self.sea_level) / span) * self.peak_altitude

    def depth_m(self, i: int) -> float:
        """Depth below sea level, in metres."""
        sea = self.sea_level
        if sea <= 0.0:
            return 0.0
        return max(0.0, (sea - self.height.data[i]) / sea) * self.ocean_depth

    def relative_elevation(self, i: int) -> float:
        """Elevation in [0, 1] over the land range; 0 at the shore."""
        span = max(1e-6, 1.0 - self.sea_level)
        return max(0.0, (self.height.data[i] - self.sea_level) / span)

    def relative_depth(self, i: int) -> float:
        """Depth in [0, 1] over the ocean range; 0 at the shore."""
        sea = self.sea_level
        if sea <= 0.0:
            return 0.0
        return max(0.0, min(1.0, (sea - self.height.data[i]) / sea))

    # -- summary ----------------------------------------------------------

    def land_cell_count(self) -> int:
        return sum(1 for v in self.land_mask if v)

    def land_fraction(self) -> float:
        return self.land_cell_count() / len(self.land_mask)

    def coast_km(self) -> float:
        """Approximate shoreline length.

        A stair-stepped digital coastline overestimates the smooth curve it
        approximates; the 0.79 is the usual correction for counting cell edges.
        """
        w, h = self.width, self.height_cells
        land = self.land_mask
        edges = 0
        for i, is_land in enumerate(land):
            if not is_land:
                continue
            x, y = i % w, i // w
            for dx, dy in D4:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h) or not land[ny * w + nx]:
                    edges += 1
        return edges * self.cell_km * 0.79

    def highest(self) -> int:
        return max(range(len(self.height.data)), key=self.height.data.__getitem__)

    def summary(self) -> dict:
        peak = self.highest()
        f = self.features
        return {
            "seed": str(self.seed),
            "name": self.name,
            "title": self.title,
            "shape": self.shape,
            "grid": [self.width, self.height_cells],
            "cell_km": round(self.cell_km, 3),
            "extent_km": [
                round(self.width * self.cell_km),
                round(self.height_cells * self.cell_km),
            ],
            "land_fraction": round(self.land_fraction(), 4),
            "land_area_km2": round(self.land_cell_count() * self.cell_km ** 2),
            "coastline_km": round(self.coast_km()),
            "latitude": [
                round(self.climate.latitude(self.height_cells - 1), 1),
                round(self.climate.latitude(0), 1),
            ],
            "prevailing_wind": self.climate.wind,
            "highest_point_m": round(self.metres(peak)),
            "deepest_point_m": round(max(self.depth_m(i) for i in range(len(self.height.data)))),
            "max_stream_order": self.hydro.max_order,
            "channel_cells": self.hydro.channel_cell_count(),
            "languages": [
                {"name": lang.name, "character": lang.blurb}
                for lang in self.namer.languages
            ],
            "biomes": [
                {"biome": key, "share": round(share, 4)}
                for key, share in self.climate.biome_fractions(self.land_mask)
            ],
            "features": {
                "rivers": len(f.rivers),
                "lakes": len(f.lakes),
                "ranges": len(f.ranges),
                "summits": len(f.summits),
                "islands": len(f.islands),
                "waters": len(f.waters),
                "capes": len(f.capes),
                "regions": len(f.regions),
            },
        }


def generate(
    seed: object = "silt",
    size: int = 224,
    height: int | None = None,
    erosion: int = 18,
    river_density: float = 0.5,
    limits: dict | None = None,
    progress=None,
) -> World:
    """Build a world from a seed.

    ``size`` is the grid width in cells; detail and runtime both scale with its
    square. ``erosion`` is how many stream-power steps to run -- more means
    deeper valleys and a more branched drainage network.
    """
    width = int(size)
    rows = int(height) if height else width
    if width < 24 or rows < 24:
        raise ValueError("a world needs at least 24 cells on a side")

    def say(stage: str, detail: str = "") -> None:
        if progress is not None:
            progress(stage, detail)

    rng = Rng(seed)

    say("terrain", "raising land")
    terrain = terrain_mod.build(width, rows, rng)

    say("erosion", f"{erosion} steps of stream power")
    erosion_mod.erode(terrain, iterations=erosion)

    scale = rng.derive("scale")
    cell_km = scale.between(420.0, 1150.0) / width
    peak_altitude = scale.between(2600.0, 5400.0) * (0.72 + 0.45 * terrain.relief)
    ocean_depth = scale.between(3200.0, 6800.0)

    say("water", "routing drainage")
    slope = erosion_mod.slope_field(terrain.height, cell_km)
    hydro = Hydrology(
        terrain.height,
        terrain.sea_level,
        cell_size=cell_km,
        river_density=river_density,
    )

    say("climate", "rain and warmth")
    climate = Climate(
        terrain.height,
        terrain.sea_level,
        rng,
        area=hydro.area,
        slope=slope,
        cell_km=cell_km,
    )

    land_mask = terrain.land_mask()
    namer = Namer(rng, width, rows)

    world = World(
        seed=seed,
        rng=rng,
        width=width,
        height_cells=rows,
        height=terrain.height,
        sea_level=terrain.sea_level,
        shape=terrain.shape,
        cell_km=cell_km,
        peak_altitude=peak_altitude,
        ocean_depth=ocean_depth,
        land_mask=land_mask,
        slope=slope,
        hydro=hydro,
        climate=climate,
        namer=namer,
        limits=dict(limits or DEFAULT_LIMITS),
    )

    say("names", "surveying and naming")
    world.name, world.title = namer.world_title(terrain.shape)
    world.features = extract(world)

    say("done", world.title)
    return world
