"""The grid container and its sampling."""

import unittest

from silt.field import D4, D8, Field, flood_regions
from silt.noise import Noise


class TestConstruction(unittest.TestCase):
    def test_shape_and_fill(self):
        field = Field(4, 3, 1.5)
        self.assertEqual(len(field), 12)
        self.assertEqual(set(field.data), {1.5})

    def test_rejects_mismatched_data(self):
        with self.assertRaises(ValueError):
            Field(3, 3, data=[0.0] * 8)

    def test_generated_uses_xy(self):
        field = Field.generated(3, 2, lambda x, y: x + 10 * y)
        self.assertEqual(field.data, [0, 1, 2, 10, 11, 12])

    def test_index_and_xy_round_trip(self):
        field = Field(7, 5)
        for i in range(35):
            self.assertEqual(field.index(*field.xy(i)), i)

    def test_copy_is_independent(self):
        field = Field(3, 3, 1.0)
        clone = field.copy()
        clone[0] = 9.0
        self.assertEqual(field[0], 1.0)

    def test_border_detection(self):
        field = Field(4, 4)
        self.assertTrue(field.on_border(field.index(0, 2)))
        self.assertTrue(field.on_border(field.index(3, 3)))
        self.assertFalse(field.on_border(field.index(1, 1)))


class TestStatistics(unittest.TestCase):
    def test_quantile_endpoints(self):
        field = Field(10, 1, data=[float(v) for v in range(10)])
        self.assertEqual(field.quantile(0.0), 0.0)
        self.assertEqual(field.quantile(1.0), 9.0)
        self.assertAlmostEqual(field.quantile(0.5), 4.5)

    def test_quantile_is_monotone(self):
        noise = Noise("q")
        field = Field.generated(24, 24, lambda x, y: noise.fbm(x / 8, y / 8))
        values = [field.quantile(q / 20) for q in range(21)]
        self.assertEqual(values, sorted(values))

    def test_normalize_maps_to_range(self):
        field = Field(5, 1, data=[2.0, 4.0, 6.0, 8.0, 10.0])
        field.normalized(0.0, 1.0)
        self.assertAlmostEqual(field[0], 0.0)
        self.assertAlmostEqual(field[-1], 1.0)
        self.assertAlmostEqual(field[2], 0.5)

    def test_normalize_handles_a_constant_field(self):
        field = Field(3, 3, 7.0)
        field.normalized(0.0, 1.0)
        self.assertEqual(set(field.data), {0.0})

    def test_clamped(self):
        field = Field(4, 1, data=[-1.0, 0.5, 2.0, 0.25])
        field.clamped(0.0, 1.0)
        self.assertEqual(field.data, [0.0, 0.5, 1.0, 0.25])


class TestSampling(unittest.TestCase):
    def setUp(self):
        self.ramp = Field.generated(8, 8, lambda x, y: float(x))

    def test_bilinear_hits_sample_points(self):
        for x in range(8):
            self.assertAlmostEqual(self.ramp.bilinear(x, 3.0), float(x))

    def test_bilinear_interpolates(self):
        self.assertAlmostEqual(self.ramp.bilinear(2.5, 0.0), 2.5)
        self.assertAlmostEqual(self.ramp.bilinear(2.25, 4.0), 2.25)

    def test_bilinear_clamps_outside(self):
        self.assertAlmostEqual(self.ramp.bilinear(-5.0, 0.0), 0.0)
        self.assertAlmostEqual(self.ramp.bilinear(99.0, 0.0), 7.0)

    def test_bilinear_of_a_plane_is_exact(self):
        plane = Field.generated(6, 6, lambda x, y: 2.0 * x + 3.0 * y)
        self.assertAlmostEqual(plane.bilinear(1.5, 2.5), 2 * 1.5 + 3 * 2.5)

    def test_neighbours_stay_in_bounds(self):
        field = Field(4, 4)
        corner = list(field.neighbours(0, D8))
        self.assertEqual(sorted(corner), [1, 4, 5])
        middle = list(field.neighbours(field.index(1, 1), D8))
        self.assertEqual(len(middle), 8)
        self.assertEqual(len(list(field.neighbours(0, D4))), 2)


class TestBlur(unittest.TestCase):
    def test_blur_preserves_a_constant(self):
        field = Field(9, 9, 0.4)
        self.assertTrue(all(abs(v - 0.4) < 1e-12 for v in field.blurred(3).data))

    def test_blur_reduces_a_spike(self):
        field = Field(9, 9, 0.0)
        field.put(4, 4, 1.0)
        blurred = field.blurred(1)
        self.assertLess(blurred.at(4, 4), 1.0)
        self.assertGreater(blurred.at(4, 3), 0.0)

    def test_blur_leaves_the_source_alone(self):
        field = Field(5, 5, 0.0)
        field.put(2, 2, 1.0)
        field.blurred(2)
        self.assertEqual(field.at(2, 2), 1.0)


class TestFloodRegions(unittest.TestCase):
    def test_counts_and_labels(self):
        mask = [
            1, 1, 0, 0,
            1, 0, 0, 1,
            0, 0, 0, 1,
            0, 1, 0, 0,
        ]
        labels, regions = flood_regions(mask, 4, 4)
        self.assertEqual(len(regions), 3)
        self.assertEqual(sorted(len(r) for r in regions), [1, 2, 3])
        for rid, cells in enumerate(regions):
            for i in cells:
                self.assertEqual(labels[i], rid)
        self.assertEqual(labels[2], -1)

    def test_diagonals_join_under_d8(self):
        mask = [1, 0, 0, 1]
        _, four = flood_regions(mask, 2, 2, offsets=D4)
        _, eight = flood_regions(mask, 2, 2, offsets=D8)
        self.assertEqual(len(four), 2)
        self.assertEqual(len(eight), 1)

    def test_empty_mask(self):
        labels, regions = flood_regions([0] * 9, 3, 3)
        self.assertEqual(regions, [])
        self.assertEqual(set(labels), {-1})


if __name__ == "__main__":
    unittest.main()
