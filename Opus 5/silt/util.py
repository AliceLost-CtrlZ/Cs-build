"""Small numeric helpers used across modules."""

from __future__ import annotations


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else (hi if v > hi else v)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def smoothstep(edge0: float, edge1: float, v: float) -> float:
    """Hermite ramp from 0 to 1 between the two edges."""
    if edge1 == edge0:
        return 0.0 if v < edge0 else 1.0
    t = clamp((v - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def band(v: float, width: float) -> float:
    """1 where ``v`` is 0, falling to 0 at +/-``width``.

    Used to turn the zero-contour of a smooth noise field into a ribbon --
    which is how Silt gets mountain ranges that run in lines instead of
    scattering in clumps.
    """
    if width <= 0.0:
        return 0.0
    t = clamp(1.0 - abs(v) / width)
    return t * t * (3.0 - 2.0 * t)


def plural(n: int, singular: str, many: str | None = None) -> str:
    return singular if n == 1 else (many or singular + "s")
