"""Renders the Nightfall "nf" app icon.

Design language lifted from the reference mark:

  * one flat plate, one flat ink - no gradients, no strokes, no shadows
  * a rounded-square plate (corner radius ~7% of the canvas)
  * a modular skeleton where the stroke is exactly one module and every
    counter is also one module
  * square terminals, optically centred, generous margins

Usage: python tools/render_icon.py [outdir]
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

PLATE = (30, 30, 46, 255)  # #1E1E2E - dusk navy
INK = (197, 197, 197, 255)  # #C5C5C5 - neutral light grey

SIZES = (16, 32, 48, 64, 128, 256)
CORNER = 0.07  # corner radius as a fraction of the canvas
MODULE = 0.11  # one module as a fraction of the canvas

# 3 x 5 modules per letter; "#" is ink, "." is a module-sized gap.
GLYPHS = {
    "n": ("###", "#.#", "#.#", "#.#", "#.#"),
    "f": (".##", "#..", "##.", "#..", "#.."),
}

WORDMARK = "nf"
LETTER_COLS = 3
ROWS = 5
COLS = LETTER_COLS * len(WORDMARK) + len(WORDMARK) - 1  # 1 module between letters


def _cells(size):
    """Yield (x, y, w, h) ink rectangles for the wordmark, in canvas coords."""
    module = size * MODULE
    left = (size - COLS * module) / 2
    top = (size - ROWS * module) / 2

    for index, letter in enumerate(WORDMARK):
        glyph = GLYPHS[letter]
        offset = left + index * (LETTER_COLS + 1) * module
        for row, line in enumerate(glyph):
            for col, cell in enumerate(line):
                if cell == "#":
                    x = offset + col * module
                    y = top + row * module
                    yield x, y, module, module


def render(size):
    """Return the icon at `size`."""
    image = Image.new("RGBA", (size, size), PLATE)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, size - 1, size - 1),
        radius=round(size * CORNER),
        fill=PLATE,
    )
    for x, y, w, h in _cells(size):
        draw.rectangle((x, y, x + w, y + h), fill=INK)
    return image


def main():
    outdir = Path(sys.argv[1] if len(sys.argv) > 1 else "nightfall/assets")
    outdir.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        path = outdir / f"nf-{size}.png"
        render(size).save(path)
        print(path)


if __name__ == "__main__":
    main()
