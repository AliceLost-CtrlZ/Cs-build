"""Invented languages: are the names pronounceable, unique, and reproducible?"""

import unittest

from silt.names import (
    LANGUAGE_NAMES,
    LANGUAGES,
    MAX_NAME,
    VOWELS,
    Language,
    Namer,
    _acceptable,
    _join,
)
from silt.rng import Rng

KINDS = ("river", "mountain", "lake", "region", "ocean", "sea", "bay", "island", "cape")


class TestInventories(unittest.TestCase):
    def test_every_language_covers_every_kind(self):
        for name in LANGUAGE_NAMES:
            generics = LANGUAGES[name]["generics"]
            for kind in KINDS:
                self.assertIn(kind, generics, f"{name} has no term for {kind}")
                self.assertTrue(generics[kind])

    def test_every_nucleus_is_vocalic(self):
        for name in LANGUAGE_NAMES:
            for nucleus in LANGUAGES[name]["nuclei"]:
                self.assertTrue(
                    all(ch in VOWELS for ch in nucleus), f"{name}: {nucleus!r}"
                )

    def test_open_syllable_language_has_no_codas(self):
        self.assertEqual(LANGUAGES["Mahei"]["codas"], ())


class TestGeneration(unittest.TestCase):
    def test_names_are_reasonable_words(self):
        for name in LANGUAGE_NAMES:
            language = Language(name)
            rng = Rng(name)
            for kind in KINDS:
                for _ in range(60):
                    word = language.compose(rng, kind)
                    self.assertGreaterEqual(len(word), 3, f"{name}/{kind}: {word!r}")
                    self.assertTrue(word[0].isupper(), word)
                    self.assertTrue(
                        all(ch.isalpha() or ch == " " for ch in word), repr(word)
                    )

    def test_names_stay_short_enough_to_print(self):
        """Long names are the failure mode: a label must fit on the sheet."""
        overlong = []
        for name in LANGUAGE_NAMES:
            language = Language(name)
            rng = Rng(name + "-length")
            for _ in range(400):
                word = language.compose(rng, "river")
                if len(word.replace(" ", "")) > MAX_NAME + 4:
                    overlong.append((name, word))
        self.assertEqual(overlong, [], f"unwieldy names: {overlong[:5]}")

    def test_no_run_of_four_consonants(self):
        """The thing that makes generated names unsayable."""
        worst = []
        for name in LANGUAGE_NAMES:
            language = Language(name)
            rng = Rng(name + "-clusters")
            for _ in range(400):
                word = language.compose(rng, "mountain").lower().replace(" ", "")
                run = 0
                for ch in word:
                    run = 0 if ch in VOWELS else run + 1
                    if run >= 5:
                        worst.append((name, word))
                        break
        self.assertEqual(worst, [], f"unpronounceable: {worst[:5]}")

    def test_generation_is_deterministic(self):
        first = [Language("Hallic").compose(Rng("x"), "river") for _ in range(5)]
        second = [Language("Hallic").compose(Rng("x"), "river") for _ in range(5)]
        self.assertEqual(first, second)

    def test_languages_sound_different(self):
        """Two tongues drawing from the same stream should not agree."""
        a = [Language("Mahei").compose(Rng("s"), "river") for _ in range(20)]
        b = [Language("Ashk").compose(Rng("s"), "river") for _ in range(20)]
        self.assertEqual(len(set(a) & set(b)), 0)


class TestJoining(unittest.TestCase):
    def test_vowel_collision_elides(self):
        # 'mora' + 'aa' would give three vowels running; the stem gives one up.
        self.assertEqual(_join("mora", "aa", "a"), "moraa")
        self.assertEqual(_join("mo", "aa", "a"), "moa")  # short stems keep theirs

    def test_consonant_pile_up_gets_a_link_vowel(self):
        joined = _join("taskr", "strom", "e")
        self.assertIn("e", joined)
        self.assertTrue(joined.startswith("taskr"))

    def test_empty_parts(self):
        self.assertEqual(_join("", "elv", "a"), "elv")
        self.assertEqual(_join("mora", "", "a"), "mora")


class TestBlocklist(unittest.TestCase):
    def test_unfortunate_collisions_are_rejected(self):
        self.assertFalse(_acceptable("Damnfell"))
        self.assertFalse(_acceptable("Aqua Viagra"))
        self.assertTrue(_acceptable("Tarkecrag"))

    def test_namer_never_emits_a_blocked_name(self):
        namer = Namer(Rng("blocklist"), 100, 100)
        for k in range(200):
            name = namer.name("river", k, k % 100, (k * 7) % 100)
            self.assertTrue(_acceptable(name), name)


class TestNamer(unittest.TestCase):
    def setUp(self):
        self.namer = Namer(Rng("elmwood"), 200, 200)

    def test_picks_one_to_three_tongues(self):
        for seed in range(40):
            namer = Namer(Rng(seed), 120, 120)
            self.assertIn(len(namer.languages), (1, 2, 3))
            self.assertEqual(len(namer.seeds), len(namer.languages))

    def test_names_are_unique(self):
        names = [self.namer.name("river", k, k, k) for k in range(150)]
        self.assertEqual(len(set(names)), len(names))

    def test_the_same_feature_gets_the_same_name(self):
        a = Namer(Rng("elmwood"), 200, 200).name("river", ("river", 42), 30, 40)
        b = Namer(Rng("elmwood"), 200, 200).name("river", ("river", 42), 30, 40)
        self.assertEqual(a, b)

    def test_naming_order_does_not_matter(self):
        """Feature keys, not call order, decide a name.

        Otherwise adding one lake would rename every river on the map.
        """
        first = Namer(Rng("elmwood"), 200, 200)
        first.name("lake", ("lake", 1), 10, 10)
        with_lake = first.name("river", ("river", 7), 90, 90)

        second = Namer(Rng("elmwood"), 200, 200)
        without_lake = second.name("river", ("river", 7), 90, 90)
        self.assertEqual(with_lake, without_lake)

    def test_territory_is_geographic(self):
        namer = Namer(Rng("territory"), 200, 200)
        if len(namer.languages) < 2:
            self.skipTest("this seed drew a single tongue")
        for sx, sy in namer.seeds:
            self.assertEqual(
                namer.language_at(sx, sy).name,
                namer.languages[namer.language_index_at(sx, sy)].name,
            )
        # A point on top of a seed belongs to that seed's language.
        for k, (sx, sy) in enumerate(namer.seeds):
            self.assertEqual(namer.language_index_at(sx, sy), k)

    def test_world_title_shapes(self):
        for shape, expected in (
            ("continent", "The Lands of"),
            ("archipelago", "The Isles of"),
            ("inland sea", "Basin"),
        ):
            proper, title = Namer(Rng("t"), 100, 100).world_title(shape)
            self.assertIn(expected, title)
            self.assertIn(proper, title)

    def test_compass_words(self):
        namer = Namer(Rng("c"), 100, 100)
        self.assertEqual(namer.compass_word(50, 50), "central")
        self.assertEqual(namer.compass_word(95, 50), "eastern")
        self.assertEqual(namer.compass_word(50, 5), "northern")
        self.assertEqual(namer.compass_word(50, 95), "southern")
        self.assertEqual(namer.compass_word(5, 50), "western")


if __name__ == "__main__":
    unittest.main()
