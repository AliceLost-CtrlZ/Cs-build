# Flowfields — Generative Art Studio

A tiny, dependency-free generative art toy. Thousands of particles drift through a
living vector field built from seeded value-noise, tracing ink trails as they go.

## Run it

Just open **`index.html`** in any modern browser. No build step, no server, no dependencies.

## Controls

**Motion**
- **Particles** — how many agents flow at once
- **Field scale** — zoom of the underlying noise (small = tight swirls, large = broad sweeps)
- **Speed** — how fast particles travel
- **Curl / turbulence** — adds a second noise octave for chaos

**Ink**
- **Line weight** — stroke thickness
- **Opacity** — how strongly each stroke tints the canvas (low = soft, layered washes)
- **Fade / trail** — gently clears old ink so the piece keeps moving instead of filling in

**Palette / Background** — six curated color sets and three canvas tones.

## Interaction & shortcuts

- **Drag on the canvas** to push the flow around your cursor.
- `Space` pause · `R` new seed · `S` save PNG · `C` clear canvas

## How it works

The field angle at any point comes from 2D value-noise (a seeded Perlin-style function,
implemented from scratch — no libraries). Each particle reads the angle beneath it, steps
in that direction, and draws a short line from its previous position. Because neighboring
particles read nearly the same angle, they organize into smooth, braided streams —
the signature look of a flow field.

Everything lives in one `index.html` (~350 lines). Have fun, and hit **Save PNG** when you
catch something you like.
