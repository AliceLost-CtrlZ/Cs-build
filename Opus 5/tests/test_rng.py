"""The determinism guarantee, and that the bits are not obviously bad."""

import unittest

from silt.rng import MASK64, Rng, mix64, text_hash, to_seed


class TestSeeding(unittest.TestCase):
    def test_text_hash_is_stable(self):
        # Hard-coded, because a change here does not break anything visibly --
        # it silently turns every previously generated world into a different
        # one. Better to fail a test than to lose a map someone liked.
        self.assertEqual(text_hash("silt"), 0x4E278B18E64C49A9)
        self.assertEqual(text_hash("elmwood"), 0x7B39D4CD8F058D0A)
        self.assertNotEqual(text_hash("silt"), text_hash("slit"))

    def test_seed_forms(self):
        self.assertEqual(to_seed(7), 7)
        self.assertEqual(to_seed("7"), 7)
        self.assertEqual(to_seed(" 7 "), 7)
        self.assertEqual(to_seed("Elmwood"), to_seed("elmwood"))
        self.assertNotEqual(to_seed("elmwood"), to_seed("kestrel"))

    def test_negative_seeds_wrap(self):
        self.assertEqual(to_seed(-1), MASK64)
        self.assertEqual(to_seed("-1"), MASK64)

    def test_mix_is_a_bijection_on_samples(self):
        seen = {mix64(i) for i in range(4000)}
        self.assertEqual(len(seen), 4000)


class TestStream(unittest.TestCase):
    def test_same_seed_same_stream(self):
        a = [Rng("elmwood").u64() for _ in range(3)]
        b = [Rng("elmwood").u64() for _ in range(3)]
        self.assertEqual(a, b)

    def test_stream_advances(self):
        rng = Rng("elmwood")
        values = [rng.u64() for _ in range(64)]
        self.assertEqual(len(set(values)), 64)

    def test_random_is_in_unit_interval(self):
        rng = Rng(11)
        values = [rng.random() for _ in range(5000)]
        self.assertTrue(all(0.0 <= v < 1.0 for v in values))
        self.assertAlmostEqual(sum(values) / len(values), 0.5, delta=0.02)

    def test_below_covers_its_range(self):
        rng = Rng("dice")
        counts = [0] * 6
        for _ in range(6000):
            counts[rng.below(6)] += 1
        self.assertTrue(all(800 < c < 1200 for c in counts), counts)

    def test_weighted_respects_weights(self):
        rng = Rng("weights")
        counts = {"a": 0, "b": 0}
        for _ in range(4000):
            counts[rng.weighted((("a", 3.0), ("b", 1.0)))] += 1
        self.assertAlmostEqual(counts["a"] / 4000, 0.75, delta=0.03)

    def test_shuffled_is_a_permutation(self):
        items = list(range(50))
        out = Rng("shuffle").shuffled(items)
        self.assertEqual(sorted(out), items)
        self.assertNotEqual(out, items)

    def test_pick_rejects_empty(self):
        with self.assertRaises(ValueError):
            Rng(0).pick([])


class TestDerive(unittest.TestCase):
    def test_named_streams_are_independent_of_consumption(self):
        """The whole point of derive: an unrelated draw must not move a world.

        If terrain read from a shared stream, adding one coin flip to the naming
        code would shift every mountain on every map.
        """
        parent = Rng("elmwood")
        before = [parent.derive("terrain").u64() for _ in range(3)]
        for _ in range(1000):
            parent.u64()
        after = [parent.derive("terrain").u64() for _ in range(3)]
        self.assertEqual(before, after)

    def test_different_labels_diverge(self):
        parent = Rng("elmwood")
        self.assertNotEqual(
            parent.derive("terrain").u64(), parent.derive("climate").u64()
        )

    def test_multi_label_derive(self):
        parent = Rng("elmwood")
        self.assertNotEqual(
            parent.derive("belt", 0).u64(), parent.derive("belt", 1).u64()
        )

    def test_derive_from_different_parents_diverge(self):
        self.assertNotEqual(
            Rng("elmwood").derive("terrain").u64(),
            Rng("kestrel").derive("terrain").u64(),
        )


if __name__ == "__main__":
    unittest.main()
