"""Place names, and the languages that make them.

A map with random syllables on it looks generated. A map whose names *cluster*
looks inhabited -- if everything in the north-west ends in ``-fell`` and ``-vatn``
while the southern coast is all ``Serra`` and ``Rio``, the reader infers two
peoples, a frontier somewhere in between, and a history nobody wrote.

So each world picks one to three languages and scatters seed points; every
feature is named in the language of whichever seed point is nearest. The
languages differ in four ways, which is enough to make them sound unrelated:

* **phonotactics** -- which onsets, vowels and codas exist at all;
* **frequency** -- inventories are multisets, so a phoneme listed three times
  is three times as likely. Unweighted inventories are what make generated
  names read as noise: real languages lean hard on a few common sounds;
* **syllable shape** -- whether codas are usual, rare, or forbidden;
* **generic terms** -- the word for "river", and whether it leads or trails.

Nothing here is a real language and none of the words mean anything.
"""

from __future__ import annotations

import math

from .rng import Rng

VOWELS = "aeiouy"

# Inventories are multisets: repetition is weight. Keeping them as plain tuples
# means generation is a single `pick` with no cumulative-weight arithmetic.
LANGUAGES = {
    "Hallic": {
        "blurb": "hard onsets, long vowels, generic terms welded on behind",
        "onsets": ("b", "d", "f", "g", "h", "k", "l", "m", "n", "r", "s", "t",
                   "v", "b", "d", "f", "g", "h", "k", "l", "m", "n", "r", "s",
                   "t", "v", "br", "dr", "gr", "fj", "hr", "kn", "sk", "sn",
                   "st", "sv", "th", "hv"),
        "nuclei": ("a", "a", "a", "e", "e", "e", "i", "i", "o", "o", "u", "u",
                   "y", "ei", "au", "aa", "oe"),
        "codas": ("n", "n", "r", "r", "s", "s", "k", "l", "m", "t", "ll", "rn",
                  "rd", "ng", "st", "lv", "th"),
        "coda_chance": 0.50,
        "syllables": ((1, 2.0), (2, 6.0), (3, 0.8)),
        "affix": "suffix",
        "link": "a",
        "generics": {
            "river": ("elv", "beck", "aa", "strom"),
            "mountain": ("fell", "tind", "berg", "klint"),
            "lake": ("vatn", "mere", "tjorn"),
            "region": ("mark", "land", "heim", "dal", "holm"),
            "ocean": ("hav", "djup"),
            "sea": ("hav", "sjo"),
            "bay": ("fjord", "sund", "vik"),
            "island": ("oy", "holm", "skar"),
            "cape": ("nes", "odde", "horn"),
        },
    },
    "Cendran": {
        "blurb": "open syllables, generic terms in front, vowel endings",
        "onsets": ("b", "c", "d", "f", "g", "l", "m", "n", "p", "r", "s", "t",
                   "v", "c", "d", "l", "m", "n", "r", "s", "t", "v", "ch",
                   "gr", "pr", "tr", "br", "cl", "qu"),
        "nuclei": ("a", "a", "a", "e", "e", "e", "i", "i", "i", "o", "o", "u",
                   "ia", "io", "ue"),
        "codas": ("l", "n", "r", "s", "nt", "rt", "ll", "m"),
        "coda_chance": 0.20,
        "syllables": ((2, 6.0), (3, 2.5)),
        "affix": "prefix",
        "link": "e",
        "generics": {
            "river": ("Rio", "Vena", "Aqua"),
            "mountain": ("Monte", "Serra", "Pico"),
            "lake": ("Lago", "Stagna"),
            "region": ("ia", "agne", "ora", "esca"),
            "ocean": ("Mare", "Oceano"),
            "sea": ("Mare", "Pelago"),
            "bay": ("Golfo", "Baia"),
            "island": ("Isla", "Scoglio"),
            "cape": ("Capo", "Punta"),
        },
    },
    "Ashk": {
        "blurb": "back consonants, closed syllables, generic terms behind",
        "onsets": ("k", "t", "s", "z", "g", "r", "m", "n", "b", "k", "t", "s",
                   "z", "g", "r", "kh", "th", "sh", "zh", "gh", "x", "q", "dr",
                   "vr"),
        "nuclei": ("a", "a", "a", "e", "i", "i", "u", "u", "o", "ai", "au"),
        "codas": ("r", "r", "n", "l", "m", "z", "kh", "sh", "th", "rk", "gh",
                  "sk"),
        "coda_chance": 0.58,
        "syllables": ((1, 2.0), (2, 6.0), (3, 1.0)),
        "affix": "suffix",
        "link": "a",
        "generics": {
            "river": ("uz", "dara", "shan"),
            "mountain": ("kar", "tagh", "zul"),
            "lake": ("gol", "shor"),
            "region": ("akh", "oram", "eshk", "ur"),
            "ocean": ("deniz", "muhit"),
            "sea": ("deniz", "zar"),
            "bay": ("koyu", "liman"),
            "island": ("ada", "kaya"),
            "cape": ("burun", "kesh"),
        },
    },
    "Ellyn": {
        "blurb": "liquids and diphthongs, few stops, generic terms in front",
        "onsets": ("l", "m", "n", "s", "th", "v", "w", "y", "f", "c", "l", "m",
                   "n", "s", "th", "v", "w", "r", "ll", "gl", "br", "sh", "rh"),
        "nuclei": ("a", "a", "e", "e", "i", "i", "o", "y", "ae", "ea", "ia",
                   "ei", "eo", "ui"),
        "codas": ("l", "n", "r", "th", "s", "ll", "nn", "lm"),
        "coda_chance": 0.26,
        "syllables": ((2, 6.0), (3, 2.5)),
        "affix": "prefix",
        "link": "e",
        "generics": {
            "river": ("Aber", "Nant", "Dwr"),
            "mountain": ("Caer", "Tor", "Bryn"),
            "lake": ("Llyn", "Mael"),
            "region": ("iel", "oth", "wyn", "ael"),
            "ocean": ("Mor", "Eigion"),
            "sea": ("Mor", "Traeth"),
            "bay": ("Bae", "Aber"),
            "island": ("Ynys", "Enlli"),
            "cape": ("Pen", "Trwyn"),
        },
    },
    "Vorn": {
        "blurb": "blunt, closed syllables, generic terms welded on behind",
        "onsets": ("b", "d", "g", "h", "k", "m", "n", "p", "r", "t", "w", "b",
                   "d", "g", "k", "m", "n", "r", "t", "w", "bl", "kr", "st",
                   "tr", "gr", "sk", "gn"),
        "nuclei": ("a", "a", "o", "o", "u", "u", "e", "e", "i", "oo", "ou"),
        "codas": ("k", "d", "g", "st", "nd", "ng", "rk", "ck", "lk", "mp",
                  "b", "tch"),
        "coda_chance": 0.68,
        "syllables": ((1, 3.0), (2, 6.0)),
        "affix": "suffix",
        "link": "e",
        "generics": {
            "river": ("strom", "oke", "flet"),
            "mountain": ("crag", "horn", "stane"),
            "lake": ("water", "pool", "loch"),
            "region": ("gard", "holt", "wold", "moor"),
            "ocean": ("deep", "main"),
            "sea": ("sea", "water"),
            "bay": ("bight", "reach", "wick"),
            "island": ("ey", "scar"),
            "cape": ("ness", "bill"),
        },
    },
    "Mahei": {
        "blurb": "open syllables only, no codas at all, generic terms trail",
        "onsets": ("h", "k", "l", "m", "n", "p", "t", "w", "f", "r", "h", "k",
                   "l", "m", "n", "p", "t", "w", ""),
        "nuclei": ("a", "a", "a", "e", "e", "i", "i", "o", "o", "u", "u", "ai",
                   "au", "ea", "oa"),
        "codas": (),
        "coda_chance": 0.0,
        "syllables": ((2, 5.0), (3, 3.0)),
        "affix": "suffix",
        "link": "",
        "generics": {
            "river": ("wai", "awa"),
            "mountain": ("ono", "puke", "rangi"),
            "lake": ("roto", "moana"),
            "region": ("motu", "nui", "hiva"),
            "ocean": ("moana", "nui"),
            "sea": ("moana", "tai"),
            "bay": ("hoana", "wana"),
            "island": ("motu", "atu"),
            "cape": ("rae", "kura"),
        },
    },
}

LANGUAGE_NAMES = tuple(LANGUAGES)

# Runs that read badly however they were assembled.
_UGLY = (
    ("thth", "th"), ("shsh", "sh"), ("khkh", "kh"), ("zhzh", "zh"),
    ("llll", "ll"), ("nnnn", "nn"), ("rrr", "rr"), ("sss", "ss"),
    ("aaa", "aa"), ("eee", "ee"), ("iii", "ii"), ("ooo", "oo"), ("uuu", "uu"),
    ("kk", "k"), ("gg", "g"), ("tt", "t"), ("dd", "d"), ("pp", "p"),
    ("bb", "b"), ("vv", "v"), ("ww", "w"), ("yy", "y"), ("hh", "h"),
    ("qq", "q"), ("xx", "x"), ("zz", "z"),
)

MAX_NAME = 13

# Generated syllables occasionally land on a real word that a reader will notice
# for the wrong reason. This is not a content filter and cannot be complete; it
# is a short list of collisions worth re-rolling past, in the same spirit as
# checking that a generated identifier is not a language keyword.
_AVOID = (
    "fuck", "shit", "cunt", "piss", "cock", "dick", "tit", "arse", "ass",
    "rape", "nazi", "slut", "wank", "damn", "hell", "kill", "died",
    "viagra", "google", "nokia", "toyota", "amazon", "reddit",
)


def _acceptable(name: str) -> bool:
    lowered = name.lower().replace(" ", "")
    return not any(bad in lowered for bad in _AVOID)


def _polish(word: str) -> str:
    for bad, good in _UGLY:
        while bad in word:
            word = word.replace(bad, good)
    if word.startswith("ll"):
        word = word[1:]
    if word.endswith("q"):
        word += "a"
    return word


def _consonant_run(word: str) -> int:
    """Length of the trailing consonant run."""
    run = 0
    for ch in reversed(word):
        if ch in VOWELS:
            break
        run += 1
    return run


def _join(stem: str, generic: str, link: str) -> str:
    """Weld a generic term onto a stem without producing a pile-up.

    Two vowels meeting get elided to one; three or more consonants meeting get
    a link vowel. This is the difference between ``Taardhraskstraum`` and
    ``Taraskastrom``.
    """
    if not stem:
        return generic
    if not generic:
        return stem

    if stem[-1] in VOWELS and generic[0] in VOWELS:
        if len(stem) > 3:
            stem = stem[:-1]
        else:
            generic = generic[1:]
    else:
        leading = 0
        for ch in generic:
            if ch in VOWELS:
                break
            leading += 1
        if _consonant_run(stem) + leading >= 3 and link:
            stem = stem + link
    return _polish(stem + generic)


class Language:
    """One invented tongue: a phoneme inventory plus a naming habit."""

    def __init__(self, name: str):
        self.name = name
        spec = LANGUAGES[name]
        self.blurb = spec["blurb"]
        self.onsets = spec["onsets"]
        self.nuclei = spec["nuclei"]
        self.codas = spec["codas"]
        self.coda_chance = spec["coda_chance"]
        self.syllables = spec["syllables"]
        self.affix = spec["affix"]
        self.link = spec["link"]
        self.generics = spec["generics"]

    def stem(self, rng: Rng, syllables: int | None = None) -> str:
        count = syllables if syllables is not None else rng.weighted(self.syllables)
        out = []
        for k in range(count):
            onset = rng.pick(self.onsets)
            if onset == "" and k > 0:
                onset = rng.pick(self.onsets)  # avoid interior hiatus pile-ups

            # A coda and the next onset can pile up into something no one can
            # say: Vorn's "-tch" followed by "gn-" gives five consonants in a
            # row. Trim the onset until the run is back to something English
            # manages ("strength" has four). Counting letters overstates it a
            # little, since "tch" and "sh" are each one sound, but erring
            # towards sayable is the right direction.
            built = "".join(out)
            while onset and _consonant_run(built) + len(onset) > 4:
                onset = onset[1:]

            nucleus = rng.pick(self.nuclei)
            coda = ""
            if self.codas:
                # Codas mid-word are what make names unpronounceable; keep them
                # mostly to the final syllable.
                threshold = self.coda_chance * (1.0 if k == count - 1 else 0.22)
                if rng.chance(threshold):
                    coda = rng.pick(self.codas)
            out.append(onset + nucleus + coda)
        return _polish("".join(out))

    def compose(self, rng: Rng, kind: str) -> str:
        """A full place name of the given kind, in this language's style."""
        generics = self.generics.get(kind)

        for attempt in range(6):
            if generics and (kind == "region" or self.affix == "suffix"):
                # A trailing generic already supplies a syllable or two.
                syllables = rng.weighted(
                    ((1, 2.0), (2, 5.0)) if self.codas else ((2, 5.0), (3, 2.0))
                )
            else:
                syllables = None
            stem = self.stem(rng, syllables)

            if not generics:
                name = stem
            elif kind == "region":
                name = _join(stem, rng.pick(generics), self.link)
            elif self.affix == "prefix":
                if rng.chance(0.75):
                    head = rng.pick(generics)
                    name = f"{head} {stem.capitalize()}"
                else:
                    name = stem
            else:
                if rng.chance(0.68):
                    name = _join(stem, rng.pick(generics), self.link)
                else:
                    name = stem

            if 3 <= len(name) <= MAX_NAME or attempt == 5:
                return name if name[0].isupper() else name.capitalize()
        return stem.capitalize()


class Namer:
    """Assigns names across a map, in the language nearest to each place."""

    def __init__(self, rng: Rng, width: int, height: int):
        self.rng = rng
        self.width = width
        self.height = height

        choose = rng.derive("tongues")
        count = choose.weighted(((1, 2.0), (2, 5.0), (3, 3.0)))
        picked = choose.shuffled(LANGUAGE_NAMES)[:count]
        self.languages = [Language(name) for name in picked]

        # Seed points for the language territories, kept off the very edge so
        # each tongue actually owns some land.
        self.seeds = []
        for _ in self.languages:
            self.seeds.append(
                (choose.between(0.15, 0.85) * width, choose.between(0.15, 0.85) * height)
            )

        self.used = set()
        self.collisions = 0

    # -- territories -------------------------------------------------------

    def language_index_at(self, x: float, y: float) -> int:
        best = 0
        best_d = float("inf")
        for k, (sx, sy) in enumerate(self.seeds):
            d = (x - sx) ** 2 + (y - sy) ** 2
            if d < best_d:
                best_d = d
                best = k
        return best

    def language_at(self, x: float, y: float) -> Language:
        return self.languages[self.language_index_at(x, y)]

    @property
    def dominant(self) -> Language:
        return self.languages[0]

    # -- naming ------------------------------------------------------------

    def name(self, kind: str, key: object, x: float = 0.0, y: float = 0.0) -> str:
        """A unique name for a feature, in the local tongue.

        ``key`` makes the result reproducible: the same feature always draws from
        the same stream, whatever order the caller happens to name things in.
        """
        language = self.language_at(x, y)
        stream = self.rng.derive("place", kind, key)
        for _ in range(64):
            candidate = language.compose(stream, kind)
            if len(candidate) < 3 or not _acceptable(candidate):
                continue
            if candidate.lower() not in self.used:
                self.used.add(candidate.lower())
                return candidate
        self.collisions += 1
        fallback = f"{language.compose(stream, kind)} {self.collisions}"
        self.used.add(fallback.lower())
        return fallback

    def world_title(self, shape: str) -> tuple[str, str]:
        """``(proper name, full title)`` for the whole map."""
        stream = self.rng.derive("world-title")
        proper = self.dominant.compose(stream, "region")
        for _ in range(32):
            if _acceptable(proper):
                break
            proper = self.dominant.compose(stream, "region")
        template = {
            "continent": "The Lands of {}",
            "archipelago": "The Isles of {}",
            "peninsulas": "The {} Coast",
            "inland sea": "The {} Basin",
        }.get(shape, "The Lands of {}")
        return proper, template.format(proper)

    def compass_word(self, x: float, y: float) -> str:
        """A rough bearing from the map centre, for gazetteer prose."""
        dx = x - self.width / 2.0
        dy = y - self.height / 2.0
        if abs(dx) < self.width * 0.14 and abs(dy) < self.height * 0.14:
            return "central"
        angle = math.degrees(math.atan2(-dy, dx)) % 360.0
        points = (
            "eastern", "north-eastern", "northern", "north-western",
            "western", "south-western", "southern", "south-eastern",
        )
        return points[int((angle + 22.5) % 360.0 // 45.0)]
