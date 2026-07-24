"""Silt -- a procedural atlas generator.

Give it a word. It raises a continent, runs water over it until the water has
carved somewhere to live, works out where the rain falls and what grows there,
names the results, and draws you a map.

    from silt import generate, render_atlas
    world = generate("elmwood")
    render_atlas(world, "out")

Pure standard library. Every world is a deterministic function of its seed.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["generate", "World", "render_atlas", "__version__"]


def __getattr__(name):  # lazy, so `import silt` stays cheap
    if name in ("generate", "World"):
        from . import world as _world

        return getattr(_world, name)
    if name == "render_atlas":
        from .atlas import render_atlas

        return render_atlas
    raise AttributeError(name)
