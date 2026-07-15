# Sandbox — Falling Sand Physics

A self-contained, dependency-free falling-sand simulator. Open `index.html` in any browser — no build step, no server.

## What it does

A 180×108 cellular-automaton grid where each cell is one of 12 materials, updated ~60 times/sec:

- **Sand** — falls, piles at its angle of repose, sinks through liquids
- **Water / Oil / Acid / Lava** — flow, spread, and layer by density (oil floats, sand sinks)
- **Stone / Wood / Ice / Plant** — static solids; wood and plant are flammable, ice melts near heat, plant grows near water
- **Fire** — ignites flammable neighbors, boils water to steam, melts ice, burns out into smoke
- **Smoke / Steam** — rise, drift, and dissipate (steam condenses back to water)
- **Acid** — dissolves sand/wood/plant/ice on contact (stone resists it, so it's safe to use as a container)

## Controls

- Left-click / drag to paint the selected material; right-click to erase
- Number keys `1`–`0`, `-`, `=` select materials; `E` selects the eraser
- `[` / `]` adjust brush size, `Space` pauses, `C` clears, `.` steps one frame
- Sidebar has Play/Pause, Step, Clear, "Add Walls" (border containment), and a speed multiplier

Try: build a stone basin, fill it with water, drop sand on top, then set oil alight next to it.
