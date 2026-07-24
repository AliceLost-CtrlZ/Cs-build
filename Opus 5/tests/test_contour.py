"""Marching squares, chaining, smoothing and simplification."""

import math
import unittest

from silt.contour import chain, contours, segments, simplify, smooth


def disc(size=32, radius=10.0):
    """A field that is 1 inside a circle and falls off outside it."""
    centre = (size - 1) / 2.0
    values = []
    for y in range(size):
        for x in range(size):
            r = math.hypot(x - centre, y - centre)
            values.append(radius - r)
    return values, size


class TestSegments(unittest.TestCase):
    def test_uniform_field_has_no_contour(self):
        self.assertEqual(segments([0.5] * 100, 10, 10, 0.5 + 1e-6), [])
        self.assertEqual(segments([0.5] * 100, 10, 10, 0.9), [])

    def test_a_disc_yields_a_closed_ring(self):
        values, size = disc()
        chains = contours(values, size, size, 0.0)
        self.assertEqual(len(chains), 1)
        points, closed = chains[0]
        self.assertTrue(closed)
        self.assertGreater(len(points), 20)

    def test_contour_points_lie_on_the_level(self):
        values, size = disc(32, 10.0)
        centre = (size - 1) / 2.0
        points, _ = contours(values, size, size, 0.0)[0]
        for x, y in points:
            self.assertAlmostEqual(math.hypot(x - centre, y - centre), 10.0, delta=0.35)

    def test_ring_length_is_about_right(self):
        values, size = disc(40, 12.0)
        points, closed = contours(values, size, size, 0.0)[0]
        ring = points + [points[0]]
        length = sum(
            math.dist(a, b) for a, b in zip(ring, ring[1:])
        )
        self.assertAlmostEqual(length, 2 * math.pi * 12.0, delta=1.5)

    def test_segments_are_paired_endpoints(self):
        values, size = disc()
        for a, b in segments(values, size, size, 0.0):
            self.assertEqual(len(a), 2)
            self.assertEqual(len(b), 2)
            self.assertNotEqual(a, b)


class TestChaining(unittest.TestCase):
    def test_chain_of_nothing(self):
        self.assertEqual(chain([]), [])

    def test_two_rings_stay_separate(self):
        size = 40
        values = []
        for y in range(size):
            for x in range(size):
                a = 6.0 - math.hypot(x - 10, y - 10)
                b = 6.0 - math.hypot(x - 29, y - 29)
                values.append(max(a, b))
        chains = contours(values, size, size, 0.0)
        self.assertEqual(len(chains), 2)
        for points, closed in chains:
            self.assertTrue(closed)

    def test_samples_exactly_on_the_level_do_not_fragment_a_ring(self):
        """Regression: integer-radius cones put samples exactly on the level.

        Four corners of this cone sit at value 0.0 exactly, which used to place
        crossings precisely on lattice points and shatter one ring into six.
        """
        size = 30
        centre = 14
        values = [
            6.0 - math.hypot(x - centre, y - centre)
            for y in range(size) for x in range(size)
        ]
        self.assertIn(0.0, values, "the degenerate case must actually be present")
        chains = contours(values, size, size, 0.0)
        self.assertEqual(len(chains), 1)
        self.assertTrue(chains[0][1])

    def test_open_chain_when_the_contour_leaves_the_grid(self):
        size = 20
        # A ramp in x: the level crossing runs from one edge to the other.
        values = [float(x) for _ in range(size) for x in range(size)]
        chains = contours(values, size, size, 9.5)
        self.assertEqual(len(chains), 1)
        points, closed = chains[0]
        self.assertFalse(closed)
        # The sample grid is `size` wide, so there are size-1 cell rows and the
        # contour spans y = 0 to y = size - 1.
        self.assertAlmostEqual(points[0][1], 0.0, places=6)
        self.assertAlmostEqual(points[-1][1], size - 1.0, places=6)


class TestSmoothAndSimplify(unittest.TestCase):
    def test_smoothing_keeps_open_endpoints(self):
        points = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (2.0, 1.0)]
        out = smooth(points, closed=False, passes=2)
        self.assertEqual(out[0], points[0])
        self.assertEqual(out[-1], points[-1])
        self.assertGreater(len(out), len(points))

    def test_smoothing_shortens_a_corner(self):
        points = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
        before = math.dist(points[0], points[1]) + math.dist(points[1], points[2])
        out = smooth(points, closed=False, passes=2)
        after = sum(math.dist(a, b) for a, b in zip(out, out[1:]))
        self.assertLess(after, before)

    def test_simplify_keeps_the_ends(self):
        points = [(float(k), 0.0) for k in range(20)]
        out = simplify(points, 0.1)
        self.assertEqual(out[0], points[0])
        self.assertEqual(out[-1], points[-1])
        self.assertEqual(len(out), 2, "a straight run needs only its endpoints")

    def test_simplify_does_not_flatten_an_arc(self):
        """Regression: the naive collinearity filter turned arcs into chords.

        Every consecutive triple along a gentle curve is nearly collinear, so a
        one-pass filter deletes the whole interior and draws a straight line
        across the bay. Douglas-Peucker measures against the chord itself and so
        keeps enough of the curve to stay within tolerance of it.
        """
        points = [
            (math.cos(t * math.pi / 60.0) * 50.0, math.sin(t * math.pi / 60.0) * 50.0)
            for t in range(61)
        ]
        out = simplify(points, 0.35)
        self.assertGreater(len(out), 6, "the arc collapsed to a chord")
        for x, y in out:
            self.assertAlmostEqual(math.hypot(x, y), 50.0, delta=1e-9)
        # And every dropped point stays within tolerance of what remains.
        for point in points:
            best = min(
                _distance_to_segment(point, a, b) for a, b in zip(out, out[1:])
            )
            self.assertLessEqual(best, 0.36)

    def test_simplify_short_input(self):
        self.assertEqual(simplify([(0.0, 0.0)]), [(0.0, 0.0)])
        self.assertEqual(simplify([(0.0, 0.0), (1.0, 1.0)]), [(0.0, 0.0), (1.0, 1.0)])


def _distance_to_segment(point, start, end):
    px, py = point
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    if span == 0.0:
        return math.dist(point, start)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / span))
    return math.dist(point, (ax + t * dx, ay + t * dy))


if __name__ == "__main__":
    unittest.main()
