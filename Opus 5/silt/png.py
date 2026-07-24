"""A minimal PNG writer.

The map is a hybrid: a raster for the ground (hypsometric colour, biome tint,
hillshade -- millions of samples, hopeless as vectors) with vector linework over
it (coast, contours, rivers, labels). That means Silt needs to emit a PNG, and
with no third-party libraries it needs to do so itself.

Which turns out to be about forty lines, because PNG is a kind format: length,
tag, payload, CRC32, repeat. Filter type 0 on every scanline and let zlib --
which is in the standard library, and is the same DEFLATE that every PNG
encoder uses -- do the compression.
"""

from __future__ import annotations

import base64
import struct
import zlib

_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + tag
        + payload
        + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


def encode(width: int, height: int, pixels: bytes, level: int = 6) -> bytes:
    """Encode 8-bit RGB pixel data (``3 * width * height`` bytes) as a PNG.

    ``level`` 6 rather than 9: on a smooth hypsometric raster the last two
    compression levels buy a couple of percent for several times the time.
    """
    expected = 3 * width * height
    if len(pixels) != expected:
        raise ValueError(f"expected {expected} bytes of RGB, got {len(pixels)}")

    stride = 3 * width
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0: store the scanline as-is
        start = y * stride
        raw += pixels[start:start + stride]

    ihdr = struct.pack(
        ">IIBBBBB",
        width,
        height,
        8,  # bit depth
        2,  # colour type 2: truecolour RGB
        0,  # deflate
        0,  # adaptive filtering
        0,  # no interlace
    )
    return (
        _SIGNATURE
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), level))
        + _chunk(b"IEND", b"")
    )


def data_uri(png: bytes) -> str:
    """Wrap encoded PNG bytes for embedding in an ``<image href>``."""
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def write(path, width: int, height: int, pixels: bytes, level: int = 6) -> int:
    """Write a PNG to disk; returns the byte count."""
    data = encode(width, height, pixels, level)
    with open(path, "wb") as handle:
        handle.write(data)
    return len(data)
