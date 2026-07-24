"""Command line: a word in, an atlas out."""

from __future__ import annotations

import argparse
import sys
import time

from . import __version__
from .atlas import FORMATS, render_atlas
from .rng import Rng
from .world import generate

EPILOG = """\
examples:
  silt                          a world from the default seed
  silt kestrel                  a world named by the word "kestrel"
  silt kestrel --size 320       the same world, at higher resolution
  silt --count 6 --out plates   six worlds, seeds derived from the first
  silt tamarind --erosion 40    let the rivers work for longer

Seeds may be any word or number. The same seed always produces the same world;
--size changes only how finely it is resolved, not which world it is.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="silt",
        description="Generate a procedural atlas: terrain, rivers, climate, names.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("seed", nargs="?", default="silt", help="any word or number")
    parser.add_argument(
        "--size", type=int, default=224,
        help="grid width in cells (default 224; cost grows with the square)",
    )
    parser.add_argument(
        "--rows", type=int, default=None, help="grid height, if not square",
    )
    parser.add_argument(
        "--scale", type=int, default=4, help="output pixels per cell (default 4)",
    )
    parser.add_argument(
        "--erosion", type=int, default=24,
        help="stream-power steps; more means deeper valleys (default 24)",
    )
    parser.add_argument(
        "--rivers", type=float, default=0.5, metavar="DENSITY",
        help="drainage density from 0 (few trunk rivers) to 1 (dense) [0.5]",
    )
    parser.add_argument(
        "--contours", type=float, default=0.10, metavar="INTERVAL",
        help="contour spacing as a fraction of relief (default 0.10)",
    )
    parser.add_argument(
        "--shade", type=float, default=0.90,
        help="hillshade strength, 0 to flatten (default 0.90)",
    )
    parser.add_argument("--no-labels", action="store_true", help="draw no place names")
    parser.add_argument("--no-graticule", action="store_true", help="draw no lat/long grid")
    parser.add_argument("--out", default="out", metavar="DIR", help="output directory")
    parser.add_argument(
        "--formats", default="svg,md,json",
        help=f"comma separated, any of: {','.join(FORMATS)} (default svg,md,json)",
    )
    parser.add_argument(
        "--count", type=int, default=1,
        help="generate several worlds, with seeds derived from the given one",
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="print nothing but paths")
    parser.add_argument("--version", action="version", version=f"silt {__version__}")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.size < 24:
        parser.error("--size must be at least 24")
    if args.scale < 1:
        parser.error("--scale must be at least 1")
    if args.count < 1:
        parser.error("--count must be at least 1")

    try:
        formats = tuple(f.strip() for f in args.formats.split(",") if f.strip())
        unknown = set(formats) - set(FORMATS)
        if unknown:
            parser.error(
                f"unknown format(s) {', '.join(sorted(unknown))}; "
                f"choose from {', '.join(FORMATS)}"
            )
    except AttributeError:  # pragma: no cover - argparse guarantees a string
        parser.error("--formats needs a comma separated list")

    seeds = [args.seed]
    if args.count > 1:
        stream = Rng(args.seed).derive("plates")
        seeds = [f"{args.seed}-{stream.u64() % 100000:05d}" for _ in range(args.count)]

    for number, seed in enumerate(seeds, start=1):
        started = time.time()

        def report(stage: str, detail: str = "") -> None:
            if not args.quiet:
                print(f"  {stage:<9} {detail}", file=sys.stderr)

        if not args.quiet and len(seeds) > 1:
            print(f"[{number}/{len(seeds)}] {seed}", file=sys.stderr)

        world = generate(
            seed,
            size=args.size,
            height=args.rows,
            erosion=args.erosion,
            river_density=args.rivers,
            progress=report,
        )
        written = render_atlas(
            world,
            directory=args.out,
            scale=args.scale,
            formats=formats,
            contour_interval=args.contours,
            shade=args.shade,
            labels=not args.no_labels,
            graticule=not args.no_graticule,
        )

        if not args.quiet:
            elapsed = time.time() - started
            print(
                f"{world.title} — {world.shape}, "
                f"{world.width * world.cell_km:,.0f} km across, "
                f"{len(world.features.rivers)} named rivers, "
                f"{elapsed:.1f}s",
                file=sys.stderr,
            )
        for key in FORMATS:
            if key in written:
                print(written[key])

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
