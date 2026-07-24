"""Deterministic pseudo-randomness.

Everything in Silt is reproducible: the same seed must always produce the same
world, on any machine, in any Python 3.x. That rules out :mod:`random` (whose
stream is an implementation detail) and :func:`hash` (salted per process).

So we carry our own: FNV-1a to turn text into a 64-bit seed, SplitMix64 to turn
that seed into a stream of bits.

The important design choice is :meth:`Rng.derive`. Streams are *named*, and a
named stream is a pure function of the world seed and the name -- never of how
many numbers some other part of the program happened to consume. That means
adding a coin flip to the naming code cannot move a mountain range.
"""

from __future__ import annotations

MASK64 = (1 << 64) - 1

_GOLDEN = 0x9E3779B97F4A7C15
_FNV_OFFSET = 0xCBF29CE484222325
_FNV_PRIME = 0x100000001B3


def mix64(z: int) -> int:
    """The SplitMix64 finalizer: a bijection on 64 bits with good avalanche."""
    z &= MASK64
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
    return z ^ (z >> 31)


def text_hash(text: str) -> int:
    """FNV-1a over UTF-8 bytes. Stable across processes and platforms."""
    h = _FNV_OFFSET
    for byte in text.encode("utf-8"):
        h = ((h ^ byte) * _FNV_PRIME) & MASK64
    return h


def to_seed(seed: object) -> int:
    """Coerce a user-supplied seed (word, number, anything) to 64 bits."""
    if isinstance(seed, Rng):
        return seed.base
    if isinstance(seed, bool):  # bool is an int subclass; be explicit
        return mix64(int(seed))
    if isinstance(seed, int):
        return seed & MASK64
    if isinstance(seed, str):
        stripped = seed.strip()
        if stripped.lstrip("-").isdigit():
            return int(stripped) & MASK64
        return text_hash(stripped.lower())
    return text_hash(repr(seed))


class Rng:
    """A SplitMix64 stream.

    ``base`` is the immutable identity of the stream; ``_state`` is how far
    along it we are. :meth:`derive` branches off ``base``, so sibling streams
    are independent of each other's consumption.
    """

    __slots__ = ("base", "_state")

    def __init__(self, seed: object = 0) -> None:
        self.base = to_seed(seed)
        self._state = self.base

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Rng(base=0x{self.base:016x})"

    # -- raw stream ---------------------------------------------------------

    def u64(self) -> int:
        self._state = (self._state + _GOLDEN) & MASK64
        return mix64(self._state)

    def random(self) -> float:
        """Uniform in [0, 1), using 53 bits like the stdlib does."""
        return (self.u64() >> 11) * (1.0 / (1 << 53))

    # -- conveniences ------------------------------------------------------

    def below(self, n: int) -> int:
        """Uniform integer in [0, n). Rejection-free; n is small in practice."""
        if n <= 0:
            raise ValueError("below() needs a positive bound")
        return self.u64() % n

    def between(self, lo: float, hi: float) -> float:
        return lo + (hi - lo) * self.random()

    def chance(self, p: float) -> bool:
        return self.random() < p

    def pick(self, items):
        items = items if isinstance(items, (list, tuple)) else list(items)
        if not items:
            raise ValueError("pick() from an empty sequence")
        return items[self.below(len(items))]

    def weighted(self, pairs):
        """Pick from ``[(item, weight), ...]`` proportionally to weight."""
        pairs = list(pairs)
        total = sum(w for _, w in pairs)
        if total <= 0:
            raise ValueError("weighted() needs at least one positive weight")
        roll = self.random() * total
        for item, weight in pairs:
            roll -= weight
            if roll < 0:
                return item
        return pairs[-1][0]

    def shuffled(self, items):
        out = list(items)
        for i in range(len(out) - 1, 0, -1):
            j = self.below(i + 1)
            out[i], out[j] = out[j], out[i]
        return out

    def gauss(self) -> float:
        """Standard normal via Box-Muller (one of the two values)."""
        import math

        u1 = self.random()
        while u1 <= 1e-12:
            u1 = self.random()
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(6.283185307179586 * self.random())

    # -- branching ---------------------------------------------------------

    def derive(self, *labels: object) -> "Rng":
        """A fresh stream identified by this stream's base plus ``labels``."""
        h = self.base
        for label in labels:
            h = mix64(h ^ to_seed(label))
        child = Rng.__new__(Rng)
        child.base = h
        child._state = h
        return child
