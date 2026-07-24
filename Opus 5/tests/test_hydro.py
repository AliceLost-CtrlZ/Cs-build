"""Water routing: the invariants that make the rest of the pipeline valid.

Depression filling, flow direction and accumulation are each simple; what makes
them trustworthy is that together they guarantee a *forest* -- every land cell
has exactly one receiver, strictly lower than itself, and following receivers
always terminates at the sea. Every downstream algorithm assumes this, so it is
worth asserting directly rather than inferring from a map that looks fine.
"""

import unittest

from silt.field import D8, Field
from silt.hydro import (
    Hydrology,
    accumulate,
    channel_paths,
    fill_depressions,
    flow_directions,
    stream_order,
)
from silt.noise import Noise


def bowl_with_pit(size=24, sea=0.2):
    """A cone rising from the sea with a pit punched into its flank."""
    field = Field(size, size)
    centre = (size - 1) / 2.0
    for y in range(size):
        for x in range(size):
            r = ((x - centre) ** 2 + (y - centre) ** 2) ** 0.5 / centre
            field.put(x, y, max(0.0, 1.0 - r))
    for y in range(9, 12):
        for x in range(9, 12):
            field.put(x, y, 0.25)  # a closed hollow well above sea level
    return field, sea


def noisy_island(size=48, seed="hydro"):
    noise = Noise(seed)
    field = Field(size, size)
    centre = (size - 1) / 2.0
    for y in range(size):
        for x in range(size):
            r = ((x - centre) ** 2 + (y - centre) ** 2) ** 0.5 / centre
            base = 0.5 + 0.5 * noise.fbm(x / size * 3.0, y / size * 3.0, octaves=5)
            field.put(x, y, max(0.0, base * max(0.0, 1.15 - r ** 1.8)))
    return field, field.quantile(0.55)


class TestFilling(unittest.TestCase):
    def test_fill_never_lowers_the_ground(self):
        field, sea = bowl_with_pit()
        filled = fill_depressions(field, sea)
        for original, raised in zip(field.data, filled.data):
            self.assertGreaterEqual(raised, original - 1e-12)

    def test_the_pit_gets_filled(self):
        field, sea = bowl_with_pit()
        filled = fill_depressions(field, sea)
        i = field.index(10, 10)
        self.assertGreater(filled.data[i], field.data[i] + 1e-4)

    def test_no_interior_pit_survives(self):
        """After filling, every land cell has a strictly lower neighbour."""
        field, sea = noisy_island()
        filled = fill_depressions(field, sea)
        w, h = field.width, field.height
        for i in range(len(filled.data)):
            if field.data[i] <= sea or field.on_border(i):
                continue
            here = filled.data[i]
            lower = [j for j in filled.neighbours(i, D8) if filled.data[j] < here]
            self.assertTrue(lower, f"cell {field.xy(i)} has nowhere to drain")

    def test_open_water_is_untouched(self):
        field, sea = noisy_island()
        filled = fill_depressions(field, sea)
        for i, value in enumerate(field.data):
            if value <= sea:
                self.assertAlmostEqual(filled.data[i], value, places=12)


class TestRouting(unittest.TestCase):
    def setUp(self):
        self.field, self.sea = noisy_island()
        self.filled = fill_depressions(self.field, self.sea)
        self.receivers, self.order = flow_directions(self.filled, self.field, self.sea)

    def test_receivers_go_downhill(self):
        for i, r in enumerate(self.receivers):
            if r >= 0:
                self.assertLess(self.filled.data[r], self.filled.data[i])

    def test_water_cells_are_sinks(self):
        for i, value in enumerate(self.field.data):
            if value <= self.sea:
                self.assertEqual(self.receivers[i], -1)

    def test_every_land_cell_reaches_the_sea(self):
        for start in range(len(self.receivers)):
            if self.field.data[start] <= self.sea:
                continue
            i = start
            for _ in range(len(self.receivers) + 1):
                r = self.receivers[i]
                if r < 0:
                    break
                i = r
            else:
                self.fail(f"routing from {start} did not terminate")
            self.assertLessEqual(self.field.data[i], self.sea)

    def test_processing_order_puts_children_first(self):
        position = {cell: k for k, cell in enumerate(self.order)}
        for i, r in enumerate(self.receivers):
            if r >= 0:
                self.assertLess(position[i], position[r])


class TestAccumulation(unittest.TestCase):
    def setUp(self):
        self.field, self.sea = noisy_island()
        filled = fill_depressions(self.field, self.sea)
        self.receivers, self.order = flow_directions(filled, self.field, self.sea)
        self.area = accumulate(self.receivers, self.order)

    def test_area_is_conserved(self):
        """Every cell's unit of rain ends up in exactly one sink."""
        outlets = sum(
            self.area[i] for i, r in enumerate(self.receivers) if r < 0
        )
        self.assertAlmostEqual(outlets, float(len(self.receivers)), places=6)

    def test_area_grows_downstream(self):
        for i, r in enumerate(self.receivers):
            if r >= 0:
                self.assertGreater(self.area[r], self.area[i])

    def test_headwaters_carry_one_cell(self):
        contributed = set(r for r in self.receivers if r >= 0)
        heads = [
            i for i in range(len(self.receivers))
            if self.receivers[i] >= 0 and i not in contributed
        ]
        self.assertTrue(heads)
        for i in heads:
            self.assertEqual(self.area[i], 1.0)


class TestStreamOrder(unittest.TestCase):
    def test_strahler_rules(self):
        field, sea = noisy_island(56)
        hydro = Hydrology(field, sea, cell_size=1.0, river_density=0.7)
        orders = hydro.stream_order

        children = {}
        for i, r in enumerate(hydro.receivers):
            if hydro.channel[i] and r >= 0 and hydro.channel[r]:
                children.setdefault(r, []).append(orders[i])

        for i in range(len(orders)):
            if not hydro.channel[i]:
                self.assertEqual(orders[i], 0)
                continue
            kids = children.get(i, [])
            if not kids:
                self.assertEqual(orders[i], 1, "a source is first order")
            else:
                top = max(kids)
                expected = top + 1 if kids.count(top) >= 2 else top
                self.assertEqual(orders[i], expected)

    def test_order_never_decreases_downstream(self):
        field, sea = noisy_island(56)
        hydro = Hydrology(field, sea, cell_size=1.0, river_density=0.7)
        for i, r in enumerate(hydro.receivers):
            if hydro.channel[i] and r >= 0 and hydro.channel[r]:
                self.assertGreaterEqual(hydro.stream_order[r], hydro.stream_order[i])


class TestPaths(unittest.TestCase):
    def setUp(self):
        self.field, self.sea = noisy_island(56)
        self.hydro = Hydrology(self.field, self.sea, 1.0, 0.7)

    def test_paths_are_contiguous(self):
        """Consecutive cells in a drawn path must be neighbours.

        A path that jumps draws as a straight line ruled across the map.
        """
        w = self.field.width
        for path in self.hydro.paths:
            for a, b in zip(path, path[1:]):
                dx = abs((a % w) - (b % w))
                dy = abs((a // w) - (b // w))
                self.assertLessEqual(max(dx, dy), 1, f"jump from {a} to {b}")

    def test_paths_follow_receivers(self):
        for path in self.hydro.paths:
            for a, b in zip(path, path[1:]):
                self.assertEqual(self.hydro.receivers[a], b)

    def test_every_channel_cell_is_drawn(self):
        drawn = set()
        for path in self.hydro.paths:
            drawn.update(path)
        for i, is_channel in enumerate(self.hydro.channel):
            if is_channel:
                self.assertIn(i, drawn)

    def test_main_stems_start_at_a_mouth(self):
        for stem in self.hydro.stems:
            mouth = stem[0]
            receiver = self.hydro.receivers[mouth]
            self.assertTrue(receiver < 0 or not self.hydro.channel[receiver])


if __name__ == "__main__":
    unittest.main()
