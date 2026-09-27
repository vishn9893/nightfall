"""Nightfall CLI's identity mark: the "nf" app icon, drawn in the terminal.

Same construction as nightfall/assets/nf-256.png (see tools/render_icon.py):
one flat plate, one flat ink, a modular skeleton where the stroke is exactly
one module and every counter is also one module.
"""

import sys

PLATE = "\033[48;5;234m"  # #1E1E2E
INK = "\033[38;5;252m"  # #C5C5C5
RESET = "\033[0m"

WORDMARK = "nf"

# 3 x 5 modules per letter; "#" is ink, "." is a module-sized gap.
GLYPHS = {
    "n": ("###", "#.#", "#.#", "#.#", "#.#"),
    "f": (".##", "#..", "##.", "#..", "#.."),
}

LETTER_COLS = 3
ROWS = 5
COLS = LETTER_COLS * len(WORDMARK) + len(WORDMARK) - 1  # 1 module between letters
SCALE = 2  # one module is SCALE columns wide and SCALE rows tall


def _mark():
    """The bare wordmark, one character per module corner."""
    grid = [[" "] * (COLS * SCALE) for _ in range(ROWS * SCALE)]
    for index, letter in enumerate(WORDMARK):
        glyph = GLYPHS[letter]
        for row, line in enumerate(glyph):
            for col, cell in enumerate(line):
                if cell != "#":
                    continue
                x = (index * (LETTER_COLS + 1) + col) * SCALE
                y = row * SCALE
                for dy in range(SCALE):
                    for dx in range(SCALE):
                        grid[y + dy][x + dx] = "█"
    return ["".join(line) for line in grid]


def _plate(lines):
    """Frame the mark on the plate and color it."""
    blank = f"{PLATE}{' ' * (COLS * SCALE + 2)}{RESET}"
    rows = [blank]
    for line in lines:
        cells = "".join(" " if char == " " else f"{INK}█" for char in line)
        rows.append(f"{PLATE} {cells} {RESET}")
    rows.append(blank)
    return rows


def render_agent_icon():
    """Return the mark as an ANSI-colored string."""
    return "\n".join([*_plate(_mark()), ""])


def print_agent_icon():
    """Print the icon for standalone use."""
    sys.stdout.write(render_agent_icon())


if __name__ == "__main__":
    print_agent_icon()
