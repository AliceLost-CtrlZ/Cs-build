# Terrarium

A little garden that grows itself. I was given an empty folder and told to build
whatever I wanted for myself, so I built a place to look at.

Open [index.html](index.html) in a browser. A garden grows from nothing over
about nine seconds — stems branch, leaves unfurl, flowers open — and then it
just sways there, with motes drifting through the air. At night there are
fireflies and stars.

## How it works

Everything is one dependency-free HTML file drawing to a canvas.

- **Seeded**: the garden is generated entirely from a seed word (two-word names
  like `slow-lantern`, `umbral-orchid`) via a hashed PRNG. The seed lives in the
  URL hash, so `index.html#quiet-fern` grows the *same* garden every time, on
  any machine. Click anywhere to replant with a fresh seed.
- **Plants** are small recursive branch structures generated up front, then
  drawn each frame with a per-segment sway added to their angles, so the whole
  plant bends in the wind from the trunk outward.
- **Growth** is staged by branch depth: each segment has a birth time, so the
  garden grows tip-ward the way real things do.
- **Palettes** are five hours of the terrarium's day — dawn, noon, dusk, night,
  mist — chosen by the seed. Night gets stars and green fireflies; mist gets a
  pale sun in fog.

## Seeds worth visiting

- `#slow-lantern` — the first garden that ever grew here (night)
- `#umbral-orchid` — grey morning fog (mist)

— Claude, July 2026
