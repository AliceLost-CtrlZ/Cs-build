"""Does the erosion model actually produce a fluvial landscape?

"It looks better" is not testable. This is: stream power drives a landscape
towards a state where channel slope scales as a power of drainage area,

    S ~ A^(-m/n)

so a log-log regression of slope against area over the channel network should
recover an exponent near -0.5 for the default m=0.5, n=1. Raw fractal noise has
no such relationship and sits far from it. That single number is the difference
between terrain that has been eroded and terrain that has merely been blurred.
"""

import math
import unittest

from silt.erosion import erode, slope_field
from silt.hydro import Hydrology
from silt.rng import Rng
from silt.terrain import build

SIZE = 72
SEEDS = ("elmwood", "kestrel", "tamarind")


def slope_area_exponent(terrain):
    """Regress log(slope) on log(area) across the channel network."""
    hydro = Hydrology(terrain.height, terrain.sea_level, 1.0, 0.75)
    w = terrain.height.width
    hd = terrain.height.data
    xs, ys = [], []
    for i in range(len(hd)):
        if not hydro.channel[i]:
            continue
        r = hydro.receivers[i]
        if r < 0:
            continue
        drop = hd[i] - hd[r]
        if drop <= 1e-9:
            continue
        dx = abs((i % w) - (r % w))
        dy = abs((i // w) - (r // w))
        distance = 1.4142135623730951 if dx and dy else 1.0
        xs.append(math.log(hydro.area[i]))
        ys.append(math.log(drop / distance))
    if len(xs) < 25:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    numerator = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    denominator = sum((a - mx) ** 2 for a in xs)
    return numerator / denominator if denominator else None


def spread(values):
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5


class TestStreamPower(unittest.TestCase):
    def test_the_exponent_lands_near_the_theoretical_value(self):
        """Averaged over seeds, the defaults should recover -m/n = -0.5."""
        exponents = []
        for seed in SEEDS + ("vaerholm", "17"):
            terrain = build(SIZE, SIZE, Rng(seed))
            erode(terrain, iterations=24)
            exponent = slope_area_exponent(terrain)
            self.assertIsNotNone(exponent, f"no channels found for {seed}")
            exponents.append(exponent)
        mean = sum(exponents) / len(exponents)
        self.assertAlmostEqual(mean, -0.5, delta=0.12)
        for exponent in exponents:
            self.assertLess(exponent, -0.30, "barely eroded")
            self.assertGreater(exponent, -0.80, "over-eroded, sanded flat")

    def test_erosion_pulls_different_worlds_towards_one_state(self):
        """The signature of a physical process rather than a filter.

        Five fractal fields start with quite different slope-area behaviour.
        Stream power drives each towards the same attractor, so the *spread*
        across seeds should contract even where individual values move little.
        """
        before, after = [], []
        for seed in SEEDS + ("vaerholm", "17"):
            raw = build(SIZE, SIZE, Rng(seed))
            before.append(slope_area_exponent(raw))
            eroded = build(SIZE, SIZE, Rng(seed))
            erode(eroded, iterations=24)
            after.append(slope_area_exponent(eroded))
        self.assertLess(spread(after), spread(before))

    def test_excessive_strength_flattens_rather_than_explodes(self):
        """The per-step clamp is what keeps forward Euler from diverging.

        A cell may never erode below its own receiver, so however large K gets,
        the worst outcome is a landscape ground smooth -- never oscillation, and
        never a NaN.
        """
        terrain = build(SIZE, SIZE, Rng("elmwood"))
        relief_before = max(terrain.height.data) - min(terrain.height.data)
        erode(terrain, iterations=30, strength=60.0)
        for value in terrain.height.data:
            self.assertEqual(value, value, "NaN in the heightfield")
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)
        rough = slope_area_exponent(terrain)
        self.assertIsNotNone(rough)
        self.assertGreater(rough, -0.9)
        self.assertLessEqual(max(terrain.height.data) - min(terrain.height.data),
                             relief_before + 1e-9)

    def test_eroded_terrain_still_drains(self):
        """Whatever erosion does, hydrology must still be able to route it."""
        terrain = build(SIZE, SIZE, Rng("kestrel"))
        erode(terrain, iterations=24)
        hydro = Hydrology(terrain.height, terrain.sea_level, 1.0, 0.6)
        for start in range(len(terrain.height.data)):
            if terrain.height.data[start] <= terrain.sea_level:
                continue
            i = start
            for _ in range(len(hydro.receivers) + 1):
                r = hydro.receivers[i]
                if r < 0:
                    break
                i = r
            else:
                self.fail("routing did not terminate after erosion")


class TestInvariants(unittest.TestCase):
    def test_heights_stay_in_range(self):
        terrain = build(SIZE, SIZE, Rng("kestrel"))
        erode(terrain, iterations=12)
        self.assertGreaterEqual(min(terrain.height.data), 0.0)
        self.assertLessEqual(max(terrain.height.data), 1.0)

    def test_land_fraction_is_preserved(self):
        terrain = build(SIZE, SIZE, Rng("kestrel"))
        before = terrain.land_fraction()
        erode(terrain, iterations=20)
        self.assertAlmostEqual(terrain.land_fraction(), before, delta=0.02)

    def test_erosion_is_deterministic(self):
        a = build(SIZE, SIZE, Rng("tamarind"))
        erode(a, iterations=8)
        b = build(SIZE, SIZE, Rng("tamarind"))
        erode(b, iterations=8)
        self.assertEqual(a.height.data, b.height.data)

    def test_zero_iterations_changes_nothing(self):
        terrain = build(SIZE, SIZE, Rng("elmwood"))
        before = list(terrain.height.data)
        erode(terrain, iterations=0)
        # Only the final renormalisation runs, and the field is already [0, 1].
        for a, b in zip(before, terrain.height.data):
            self.assertAlmostEqual(a, b, places=9)

    def test_progress_callback_fires_once_per_step(self):
        seen = []
        terrain = build(SIZE, SIZE, Rng("elmwood"))
        erode(terrain, iterations=4, progress=lambda k, n: seen.append((k, n)))
        self.assertEqual(seen, [(1, 4), (2, 4), (3, 4), (4, 4)])


class TestSlopeField(unittest.TestCase):
    def test_flat_ground_has_no_slope(self):
        from silt.field import Field

        flat = Field(10, 10, 0.5)
        self.assertEqual(set(slope_field(flat).data), {0.0})

    def test_a_ramp_has_constant_slope(self):
        from silt.field import Field

        ramp = Field.generated(10, 10, lambda x, y: x * 0.1)
        values = slope_field(ramp, cell_size=1.0).data
        interior = [values[y * 10 + x] for y in range(1, 9) for x in range(1, 9)]
        for value in interior:
            self.assertAlmostEqual(value, 0.1, places=9)


if __name__ == "__main__":
    unittest.main()
