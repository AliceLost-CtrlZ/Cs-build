"""Gradient noise, and the fractal sums built from it.

Value noise is cheaper but looks blocky along the lattice axes, which reads as
"computer" the moment you put it under a hillshade. So: Perlin gradient noise
with a quintic fade, hashed gradients from a 16-direction table.

Three shapes get used downstream:

``fbm``     -- ordinary fractal sum. Rolling, cloud-like. Continents, moisture.
``ridged``  -- ``1 - |n|`` per octave, weighted by the octave above it. Creases
               and crests. Mountain ranges.
``billow``  -- ``|n|`` per octave. Lumpy. Hills, island clusters.
"""

from __future__ import annotations

import math

from .rng import MASK64, mix64, to_seed

# 16 unit vectors: enough directions that the lattice stops being visible,
# few enough that the table stays in cache.
_GRADIENTS = tuple(
    (math.cos(2.0 * math.pi * i / 16.0), math.sin(2.0 * math.pi * i / 16.0))
    for i in range(16)
)

# Odd multipliers, so the product is a bijection mod 2**64 and coordinate
# collisions do not fold onto each other.
_XP = 0x2545F4914F6CDD1D
_YP = 0x9E3779B97F4A7C15


class Noise:
    """Perlin noise over the infinite plane, keyed by a 64-bit seed."""

    __slots__ = ("seed",)

    def __init__(self, seed: object = 0) -> None:
        self.seed = to_seed(seed)

    def _gradient(self, xi: int, yi: int):
        h = ((xi * _XP) ^ (yi * _YP) ^ self.seed) & MASK64
        return _GRADIENTS[mix64(h) & 15]

    def at(self, x: float, y: float) -> float:
        """Gradient noise at a point, in roughly [-1, 1]."""
        xi = math.floor(x)
        yi = math.floor(y)
        fx = x - xi
        fy = y - yi

        # Quintic fade: zero first and second derivatives at the lattice, so
        # neither the value nor the shading creases on cell boundaries.
        u = fx * fx * fx * (fx * (fx * 6.0 - 15.0) + 10.0)
        v = fy * fy * fy * (fy * (fy * 6.0 - 15.0) + 10.0)

        g = self._gradient(xi, yi)
        n00 = g[0] * fx + g[1] * fy
        g = self._gradient(xi + 1, yi)
        n10 = g[0] * (fx - 1.0) + g[1] * fy
        g = self._gradient(xi, yi + 1)
        n01 = g[0] * fx + g[1] * (fy - 1.0)
        g = self._gradient(xi + 1, yi + 1)
        n11 = g[0] * (fx - 1.0) + g[1] * (fy - 1.0)

        low = n00 + u * (n10 - n00)
        high = n01 + u * (n11 - n01)
        # 1/sqrt(0.5) restores the theoretical range; Perlin's raw output peaks
        # near 0.707 for 2D unit gradients.
        return (low + v * (high - low)) * 1.4142135623730951

    # -- fractal sums ------------------------------------------------------

    def fbm(
        self,
        x: float,
        y: float,
        octaves: int = 6,
        lacunarity: float = 2.0,
        gain: float = 0.5,
    ) -> float:
        """Fractal Brownian motion, normalised to about [-1, 1]."""
        total = 0.0
        amplitude = 1.0
        norm = 0.0
        freq = 1.0
        for _ in range(octaves):
            total += amplitude * self.at(x * freq, y * freq)
            norm += amplitude
            amplitude *= gain
            freq *= lacunarity
        return total / norm if norm else 0.0

    def billow(self, x: float, y: float, octaves: int = 5, lacunarity: float = 2.0,
               gain: float = 0.5) -> float:
        """Absolute-value sum, in [0, 1]. Rounded, cumulus-like lumps."""
        total = 0.0
        amplitude = 1.0
        norm = 0.0
        freq = 1.0
        for _ in range(octaves):
            total += amplitude * abs(self.at(x * freq, y * freq))
            norm += amplitude
            amplitude *= gain
            freq *= lacunarity
        return min(1.0, total / norm) if norm else 0.0

    def ridged(
        self,
        x: float,
        y: float,
        octaves: int = 6,
        lacunarity: float = 2.0,
        gain: float = 0.5,
        sharpness: float = 2.0,
    ) -> float:
        """Ridged multifractal, in [0, 1].

        Each octave is weighted by the one above it, so fine detail only
        survives where the coarse structure is already high. That is what turns
        a field of creases into a range with foothills.
        """
        total = 0.0
        amplitude = 1.0
        norm = 0.0
        freq = 1.0
        weight = 1.0
        for _ in range(octaves):
            signal = 1.0 - abs(self.at(x * freq, y * freq))
            signal *= signal
            signal *= weight
            weight = min(1.0, signal * sharpness)
            total += amplitude * signal
            norm += amplitude
            amplitude *= gain
            freq *= lacunarity
        return min(1.0, max(0.0, total / norm)) if norm else 0.0

    def warp(self, x: float, y: float, strength: float = 1.0, freq: float = 1.0):
        """Displace a coordinate by a vector read from two noise channels.

        Feeding warped coordinates into ``fbm`` bends its features into curves
        and hooks. Straight noise looks knitted; warped noise looks weathered.
        """
        wx = self.at(x * freq + 11.3, y * freq - 4.7)
        wy = self.at(x * freq - 7.1, y * freq + 19.9)
        return x + wx * strength, y + wy * strength
