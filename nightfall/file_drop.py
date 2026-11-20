"""Recognise files dropped onto the terminal.

A terminal has no drag-and-drop event. When a file is dropped on the window,
the emulator types the path into the running program instead, and - because
prompt_toolkit turns on bracketed paste - the whole path arrives as a single
`Keys.BracketedPaste` rather than a burst of keystrokes.

Terminals disagree about what that text looks like:

- most shell-escape the path and separate several dropped files with spaces;
- some wrap a path with spaces in quotes;
- VTE-based terminals send a `file://` URI;
- a few send the bare path, spaces and all.

So this normalizes the pasted text, but only when it is *exclusively* one or
more absolute paths that exist on disk. Anything else returns None, and the
paste is inserted as typed - a paste that happens to contain a path is a paste,
not a drop, and must not be rewritten.

On Windows the separator is a backslash, which POSIX shell rules would read as
an escape character. So the splitting and quoting follow Windows rules there:
backslashes are kept exactly as typed, and quotes are plain double quotes.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from urllib.parse import unquote, urlparse

# A drop of a lot of files is more likely to be a mistake than an intention,
# and every one of them is a filesystem path going into the prompt.
MAX_DROPPED_FILES = 20

# Linux caps a path at 4096 bytes, so anything longer cannot be one path. The
# check is what keeps a huge paste away from stat(2), which answers ENAMETOOLONG
# with an OSError rather than a False.
MAX_PATH_CHARS = 4096

_WINDOWS = os.name == "nt"

# "/C:/Users/..." is what a file:// URI path looks like for a drive letter.
_URI_DRIVE_PREFIX = re.compile(r"^/[A-Za-z]:")


def normalize_dropped_paths(text: str) -> str | None:
    """The prompt text for a dropped file, or None if this is not a drop.

    Paths containing whitespace come back quoted, so the model can tell where
    one path ends and the next begins.
    """
    stripped = text.strip()
    if not stripped:
        return None

    # Checked before any filesystem work: a paste of hundreds of paths is a
    # paste, and splitting a very long string is not free.
    if len(stripped) > MAX_DROPPED_FILES * MAX_PATH_CHARS:
        return None

    # A single dropped file can arrive bare, with its spaces unescaped, which
    # splitting would otherwise break into several non-existent paths.
    whole = _token_to_path(stripped)
    if whole is not None:
        return _quote_path(whole)

    try:
        tokens = _split(stripped)
    except ValueError:
        return None  # unbalanced quotes: not something a terminal emitted

    if not tokens or len(tokens) > MAX_DROPPED_FILES:
        return None

    paths = []
    for token in tokens:
        path = _token_to_path(token)
        if path is None:
            return None  # one bad token means the whole thing is not a drop
        paths.append(path)
    return " ".join(_quote_path(path) for path in paths)


def _split(text: str) -> list[str]:
    """Split a drop into its tokens, using the rules of the platform's shells."""
    if _WINDOWS:
        return _split_windows(text)
    return shlex.split(text, posix=True)


def _split_windows(text: str) -> list[str]:
    """Split on whitespace outside double quotes.

    Backslashes are path separators here, not escapes, so they are kept as
    typed. Windows file names cannot contain a double quote, so quotes are only
    ever delimiters.
    """
    tokens: list[str] = []
    current: list[str] = []
    in_quotes = False
    in_token = False
    for char in text:
        if char == '"':
            in_quotes = not in_quotes
            in_token = True
        elif char.isspace() and not in_quotes:
            if in_token:
                tokens.append("".join(current))
                current = []
                in_token = False
        else:
            current.append(char)
            in_token = True
    if in_quotes:
        raise ValueError("unbalanced quotes")
    if in_token:
        tokens.append("".join(current))
    return tokens


def _token_to_path(token: str) -> str | None:
    """The existing absolute path a token names, if it names one."""
    candidate = token
    if candidate.startswith("file://"):
        parsed = urlparse(candidate)
        if parsed.netloc not in ("", "localhost"):
            return None
        candidate = unquote(parsed.path)
        if _WINDOWS:
            if _URI_DRIVE_PREFIX.match(candidate):
                candidate = candidate[1:]
            # URIs always use forward slashes; hand back a Windows spelling.
            candidate = str(Path(candidate))

    path = Path(candidate)
    try:
        # Relative paths are rejected on purpose: the drop did not come from
        # this process, so it cannot have meant anything relative to the
        # working directory, and resolving it would paper over a terminal
        # sending junk. is_absolute() is also the portable spelling of "starts
        # with a separator", which is wrong on Windows.
        if not path.is_absolute() or not path.exists():
            return None
    except OSError:
        # A path the kernel will not even stat - too long, or a loop - is not a
        # file, and must not take the prompt down with it.
        return None
    return candidate


def _quote_path(path: str) -> str:
    if not any(char.isspace() for char in path):
        return path
    if _WINDOWS:
        # No escaping: a Windows path has no escape character, and it cannot
        # contain a double quote to escape.
        return f'"{path}"'
    escaped = path.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
