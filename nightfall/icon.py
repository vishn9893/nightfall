"""Nightfall CLI's small ANSI pixel-art identity mark."""

import sys


GREEN = "\033[38;5;46m"
DARK_GREEN = "\033[38;5;28m"
RESET = "\033[0m"

ICON_MATRIX = (
    "█  █  ████",
    "██ █  █   ",
    "█ ██  ███ ",
    "█  █  █   ",
    "█  █  █   ",
)


def render_agent_icon():
    """Return the pixel icon as an ANSI-colored string."""
    width = max(len(row) for row in ICON_MATRIX) + 4
    border = f"{DARK_GREEN}┌{'─' * width}┐{RESET}"
    rows = [
        f"{DARK_GREEN}│  {GREEN}{row}{DARK_GREEN}  │{RESET}"
        for row in ICON_MATRIX
    ]
    footer = f" {GREEN}[Agent CLI System]{RESET}"
    return "\n".join([border, *rows, f"{DARK_GREEN}└{'─' * width}┘{RESET}", footer, ""])


def print_agent_icon():
    """Print the icon for standalone use."""
    sys.stdout.write(render_agent_icon())


if __name__ == "__main__":
    print_agent_icon()
