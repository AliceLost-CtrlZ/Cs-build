"""End to end: a whole world, its plate, and its gazetteer."""

import json
import os
import re
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
import zlib

from silt import png as png_mod
from silt.atlas import FORMATS, atlas_html, gazetteer, render_atlas
from silt.climate import BIOMES, classify, zonal_wetness
from silt.render import Placer, draw, raster
from silt.world import generate

SIZE = 64


def small_world(seed="elmwood"):
    return generate(seed, size=SIZE, erosion=6)


class TestGeneration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = small_world()

    def test_same_seed_same_world(self):
        again = small_world()
        self.assertEqual(self.world.height.data, again.height.data)
        self.assertEqual(self.world.summary(), again.summary())

    def test_different_seeds_differ(self):
        other = small_world("kestrel")
        self.assertNotEqual(self.world.height.data, other.height.data)
        self.assertNotEqual(self.world.name, other.name)

    def test_case_and_whitespace_in_seeds_are_ignored(self):
        self.assertEqual(small_world("  ELMWOOD ").name, self.world.name)

    def test_shape_is_one_of_the_known_forms(self):
        self.assertIn(self.world.shape, ("continent", "archipelago", "peninsulas",
                                         "inland sea"))

    def test_there_is_land_and_sea(self):
        fraction = self.world.land_fraction()
        self.assertGreater(fraction, 0.10)
        self.assertLess(fraction, 0.70)

    def test_heights_are_normalised(self):
        self.assertAlmostEqual(min(self.world.height.data), 0.0, places=9)
        self.assertAlmostEqual(max(self.world.height.data), 1.0, places=9)

    def test_elevations_are_sane(self):
        peak = self.world.highest()
        self.assertGreater(self.world.metres(peak), 800.0)
        self.assertLess(self.world.metres(peak), 9000.0)
        for i in range(len(self.world.height.data)):
            if self.world.land_mask[i]:
                self.assertGreaterEqual(self.world.metres(i), 0.0)
            else:
                self.assertGreaterEqual(self.world.depth_m(i), 0.0)

    def test_rejects_a_grid_too_small_to_mean_anything(self):
        with self.assertRaises(ValueError):
            generate("x", size=8)

    def test_non_square_grids(self):
        world = generate("elmwood", size=64, height=40, erosion=4)
        self.assertEqual(len(world.height.data), 64 * 40)
        self.assertEqual(world.height_cells, 40)


class TestFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = generate("kestrel", size=96, erosion=10)

    def test_something_got_named(self):
        self.assertGreater(self.world.features.count(), 5)

    def test_names_are_unique_across_the_map(self):
        names = []
        for group in ("rivers", "lakes", "ranges", "summits", "islands",
                      "waters", "capes", "regions"):
            names += [f.name for f in getattr(self.world.features, group)]
        self.assertEqual(len(names), len(set(names)))

    def test_rivers_end_at_water(self):
        for river in self.world.features.rivers:
            receiver = self.world.hydro.receivers[river.mouth]
            self.assertTrue(
                receiver < 0 or not self.world.hydro.channel[receiver],
                "a named river should run out at the sea or a lake",
            )

    def test_river_lengths_are_positive_and_ordered(self):
        for river in self.world.features.rivers:
            self.assertGreater(river.length_km, 0.0)
            self.assertGreaterEqual(river.order, 1)

    def test_ranges_contain_their_peak(self):
        for mountains in self.world.features.ranges:
            self.assertIn(mountains.peak, mountains.cells)
            self.assertGreater(mountains.peak_m, 0.0)

    def test_lakes_are_above_sea_level(self):
        for lake in self.world.features.lakes:
            for i in lake.cells:
                self.assertGreater(self.world.height.data[i], self.world.sea_level)

    def test_regions_partition_the_land(self):
        features = self.world.features
        if not features.regions:
            self.skipTest("no regions on this world")
        covered = sum(len(region.cells) for region in features.regions)
        self.assertEqual(covered, self.world.land_cell_count())

    def test_waters_sit_on_water(self):
        for water in self.world.features.waters:
            self.assertFalse(self.world.land_mask[water.index])

    def test_capes_sit_on_land(self):
        for cape in self.world.features.capes:
            self.assertTrue(self.world.land_mask[cape.index])


class TestClimate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = small_world("tamarind")

    def test_fields_are_in_range(self):
        for value in self.world.climate.temperature.data:
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)
        for value in self.world.climate.moisture.data:
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_every_land_cell_has_a_known_biome(self):
        for i, is_land in enumerate(self.world.land_mask):
            if is_land:
                self.assertIn(self.world.climate.biome[i], BIOMES)

    def test_altitude_cools(self):
        """Two cells at the same latitude: the higher one must be colder."""
        climate = self.world.climate
        width = self.world.width
        for y in range(self.world.height_cells):
            row = [
                i for i in range(y * width, (y + 1) * width)
                if self.world.land_mask[i]
            ]
            if len(row) < 4:
                continue
            low = min(row, key=lambda i: self.world.height.data[i])
            high = max(row, key=lambda i: self.world.height.data[i])
            if self.world.height.data[high] - self.world.height.data[low] > 0.1:
                self.assertLess(
                    climate.temperature.data[high], climate.temperature.data[low]
                )

    def test_latitude_decreases_southward(self):
        climate = self.world.climate
        self.assertGreater(climate.latitude(0), climate.latitude(self.world.height_cells - 1))

    def test_zonal_wetness_puts_deserts_in_the_horse_latitudes(self):
        self.assertGreater(zonal_wetness(0.0), zonal_wetness(26.0))
        self.assertGreater(zonal_wetness(52.0), zonal_wetness(26.0))
        self.assertGreater(zonal_wetness(52.0), zonal_wetness(85.0))

    def test_biomes_span_the_range(self):
        shares = self.world.climate.biome_fractions(self.world.land_mask)
        self.assertGreaterEqual(len(shares), 3, "a world of one biome is a bug")
        self.assertLess(shares[0][1], 0.85, "one biome should not swallow the map")
        self.assertAlmostEqual(sum(share for _, share in shares), 1.0, places=6)

    def test_classify_extremes(self):
        self.assertEqual(classify(0.95, 0.1, 0.5, False), "snowfield")
        self.assertEqual(classify(0.2, 0.9, 0.02, False), "desert")
        self.assertEqual(classify(0.2, 0.9, 0.95, False), "jungle")
        self.assertEqual(classify(0.2, 0.05, 0.5, False), "ice")


class TestPng(unittest.TestCase):
    def test_structure_and_checksums(self):
        pixels = bytes(range(3 * 4 * 2))
        data = png_mod.encode(4, 2, pixels)
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))

        offset = 8
        tags = []
        while offset < len(data):
            length = struct.unpack(">I", data[offset:offset + 4])[0]
            tag = data[offset + 4:offset + 8]
            payload = data[offset + 8:offset + 8 + length]
            checksum = struct.unpack(
                ">I", data[offset + 8 + length:offset + 12 + length]
            )[0]
            self.assertEqual(checksum, zlib.crc32(tag + payload) & 0xFFFFFFFF)
            tags.append(tag)
            offset += 12 + length
        self.assertEqual(tags, [b"IHDR", b"IDAT", b"IEND"])

    def test_header_records_the_size(self):
        data = png_mod.encode(7, 3, bytes(3 * 7 * 3))
        width, height, depth, colour = struct.unpack(">IIBB", data[16:26])
        self.assertEqual((width, height, depth, colour), (7, 3, 8, 2))

    def test_pixels_survive_the_round_trip(self):
        pixels = bytes((i * 7) % 256 for i in range(3 * 5 * 4))
        data = png_mod.encode(5, 4, pixels)
        start = data.index(b"IDAT") + 4
        length = struct.unpack(">I", data[start - 8:start - 4])[0]
        raw = zlib.decompress(data[start:start + length])
        recovered = bytearray()
        stride = 3 * 5
        for y in range(4):
            row = raw[y * (stride + 1):(y + 1) * (stride + 1)]
            self.assertEqual(row[0], 0, "filter type should be 0")
            recovered += row[1:]
        self.assertEqual(bytes(recovered), pixels)

    def test_rejects_wrong_length(self):
        with self.assertRaises(ValueError):
            png_mod.encode(4, 4, b"\x00" * 10)

    def test_data_uri(self):
        uri = png_mod.data_uri(png_mod.encode(1, 1, b"\xff\x00\x00"))
        self.assertTrue(uri.startswith("data:image/png;base64,"))


class TestPlacer(unittest.TestCase):
    def test_rejects_overlap(self):
        placer = Placer(200, 200)
        self.assertIsNotNone(placer.place(100, 100, "Alpha", 12))
        self.assertIsNone(placer.place(100, 100, "Beta", 12))

    def test_offsets_are_tried_in_order(self):
        placer = Placer(200, 200)
        placer.place(100, 100, "Alpha", 12)
        spot = placer.place(100, 100, "Beta", 12, offsets=((0, 0), (0, 40)))
        self.assertEqual(spot, (100, 140))

    def test_rejects_labels_that_run_off_the_sheet(self):
        placer = Placer(60, 60)
        self.assertIsNone(placer.place(30, 30, "A very long name indeed", 20))

    def test_shrinking_finds_room(self):
        placer = Placer(160, 60)
        wide = placer.measure("Rokiromoana", 22.0, 5.0)
        self.assertGreater(wide, 160 - 8, "the label must not fit at full size")
        spot, size, _ = placer.place_flexible(80, 30, "Rokiromoana", 22.0, 5.0)
        self.assertIsNotNone(spot)
        self.assertLess(size, 22.0)

    def test_fits_matches_place(self):
        placer = Placer(200, 200)
        self.assertTrue(placer.fits(10, 10, 40, 40))
        placer.reserve(10, 10, 40, 40)
        self.assertFalse(placer.fits(20, 20, 50, 50))


class TestRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = small_world("vaerholm")
        cls.svg = draw(cls.world, scale=3)

    def test_svg_parses(self):
        root = ElementTree.fromstring(self.svg)
        self.assertTrue(root.tag.endswith("svg"))

    def test_no_broken_numbers_reach_the_output(self):
        """Every numeric attribute must be a finite number.

        Substring-matching for "nan" does not work here: place names contain it
        (Faununui, Nanoa), and so does base64. Parse the numbers instead.
        """
        vectors = re.sub(r'xlink:href="data:[^"]*"', "", self.svg)
        numeric = (
            "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "width", "height",
            "stroke-width", "font-size", "letter-spacing", "opacity", "offset",
        )
        checked = 0
        for name in numeric:
            for value in re.findall(rf'(?<![-\w]){name}="([^"]*)"', vectors):
                if value.endswith("%") or value.startswith("url("):
                    continue
                number = float(value)
                self.assertEqual(number, number, f"{name}={value!r}")
                self.assertNotEqual(abs(number), float("inf"), f"{name}={value!r}")
                checked += 1
        self.assertGreater(checked, 50, "the scan found almost no attributes")

        for path in re.findall(r'\sd="([^"]*)"', vectors):
            self.assertNotRegex(path, r"(?i)nan|inf")
            for token in re.findall(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?", path):
                float(token)

        self.assertNotIn(">None<", vectors)

    def test_the_plate_carries_its_furniture(self):
        for expected in (self.world.title, str(self.world.seed), "km"):
            self.assertIn(expected, self.svg)
        self.assertIn("data:image/png;base64,", self.svg)

    def test_names_reach_the_sheet(self):
        drawn = set(re.findall(r"<text[^>]*>([^<]*)</text>", self.svg))
        placed = 0
        for group in ("rivers", "ranges", "regions", "waters"):
            for feature in getattr(self.world.features, group):
                if feature.name in drawn:
                    placed += 1
        self.assertGreater(placed, 3, "almost nothing got labelled")

    def test_the_ocean_gets_named(self):
        oceans = [w for w in self.world.features.waters if w.kind == "ocean"]
        if not oceans:
            self.skipTest("no open ocean on this world")
        self.assertIn(oceans[0].name, self.svg)

    def test_labels_do_not_overlap(self):
        """The placer's whole job, checked on real output."""
        placer = Placer(1e9, 1e9)  # measurement only
        boxes = []
        for match in re.finditer(
            r'<text x="([\d.-]+)" y="([\d.-]+)" font-size="([\d.]+)"[^>]*>([^<]*)</text>',
            self.svg,
        ):
            x, y, size = (float(match.group(k)) for k in (1, 2, 3))
            text = match.group(4)
            if not text or "°" in text:
                continue
            half_w = placer.measure(text, size) / 2.0
            boxes.append((x - half_w, y - size * 0.6, x + half_w, y + size * 0.6, text))
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                overlap = (
                    a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
                )
                self.assertFalse(overlap, f"{a[4]!r} overlaps {b[4]!r}")

    def test_rendering_without_decoration(self):
        bare = draw(self.world, scale=2, labels=False, graticule=False,
                    embed_raster=False)
        ElementTree.fromstring(bare)
        self.assertNotIn("data:image/png", bare)

    def test_raster_size_and_determinism(self):
        w, h, pixels = raster(self.world, 2)
        self.assertEqual((w, h), (SIZE * 2, SIZE * 2))
        self.assertEqual(len(pixels), 3 * w * h)
        self.assertEqual(raster(self.world, 2)[2], pixels)

    def test_land_and_sea_look_different(self):
        scale = 2
        _, _, pixels = raster(self.world, scale)
        width = self.world.width
        land_blue = sea_blue = 0
        land_n = sea_n = 0
        for i in range(len(self.world.height.data)):
            x, y = (i % width) * scale, (i // width) * scale
            offset = 3 * (y * width * scale + x)
            blue = pixels[offset + 2]
            red = pixels[offset]
            if self.world.land_mask[i]:
                land_blue += blue - red
                land_n += 1
            else:
                sea_blue += blue - red
                sea_n += 1
        self.assertGreater(sea_blue / max(1, sea_n), land_blue / max(1, land_n) + 20)


class TestAtlas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = small_world("tamarind")

    def test_gazetteer_mentions_the_features(self):
        text = gazetteer(self.world)
        self.assertIn(self.world.title, text)
        self.assertIn(str(self.world.seed), text)
        for river in self.world.features.rivers[:3]:
            self.assertIn(river.name, text)
        for language in self.world.namer.languages:
            self.assertIn(language.name, text)

    def test_summary_is_json_serialisable(self):
        payload = json.dumps(self.world.summary())
        restored = json.loads(payload)
        self.assertEqual(restored["name"], self.world.name)
        self.assertEqual(restored["grid"], [SIZE, SIZE])
        self.assertAlmostEqual(
            sum(entry["share"] for entry in restored["biomes"]), 1.0, places=3
        )

    def test_html_is_self_contained(self):
        html = atlas_html(self.world, draw(self.world, scale=2), gazetteer(self.world))
        self.assertIn("<svg", html)
        self.assertNotIn("http://", html.replace("http://www.w3.org", ""))
        self.assertNotIn("https://", html)
        self.assertIn("prefers-color-scheme", html)

    def test_render_atlas_writes_every_format(self):
        with tempfile.TemporaryDirectory() as directory:
            written = render_atlas(self.world, directory, scale=2, formats=FORMATS)
            self.assertEqual(set(written), set(FORMATS))
            for path in written.values():
                self.assertTrue(os.path.exists(path))
                self.assertGreater(os.path.getsize(path), 200)
            with open(written["json"], encoding="utf-8") as handle:
                json.load(handle)

    def test_render_atlas_rejects_unknown_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                render_atlas(self.world, directory, formats=("svg", "tiff"))


class TestCli(unittest.TestCase):
    def test_generates_files(self):
        from silt.cli import main

        with tempfile.TemporaryDirectory() as directory:
            code = main([
                "elmwood", "--size", "48", "--scale", "2", "--erosion", "3",
                "--formats", "svg,json", "--out", directory, "--quiet",
            ])
            self.assertEqual(code, 0)
            produced = os.listdir(directory)
            self.assertEqual(len(produced), 2)

    def test_rejects_a_bad_format(self):
        from silt.cli import main

        with self.assertRaises(SystemExit):
            main(["x", "--formats", "jpeg"])

    def test_count_produces_distinct_worlds(self):
        from silt.cli import main

        with tempfile.TemporaryDirectory() as directory:
            main([
                "elmwood", "--count", "2", "--size", "48", "--scale", "1",
                "--erosion", "2", "--formats", "json", "--out", directory, "--quiet",
            ])
            files = sorted(os.listdir(directory))
            self.assertEqual(len(files), 2)
            payloads = []
            for name in files:
                with open(os.path.join(directory, name), encoding="utf-8") as handle:
                    payloads.append(json.load(handle)["name"])
            self.assertNotEqual(payloads[0], payloads[1])


if __name__ == "__main__":
    unittest.main()
