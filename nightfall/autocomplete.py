"""Prompt autocomplete.

Turns the text on the input line into a ranked list of suggestions. The engine
is deliberately dumb about everything except the text: it does not know what a
terminal is, and importing prompt_toolkit here would mean the only interesting
part could be tested with one. `prompt.py` owns the UI side.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Walking a tree on every keystroke is only affordable if most of it is skipped.
IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
    }
)
MAX_FILE_COMPLETIONS = 50

SKILL_PREFIX = "/skill:"


class CompletionKind(str, Enum):
    """Where a suggestion came from.

    A str mixin rather than `enum.StrEnum`, which is 3.11+ - this project
    supports 3.10.
    """

    COMMAND = "command"
    SKILL = "skill"
    FILE_REFERENCE = "file_reference"


@dataclass(frozen=True, slots=True)
class CompletionItem:
    """One suggestion, with the span of the line it would replace."""

    display: str
    replacement: str
    start: int
    end: int
    kind: CompletionKind
    description: str | None = None

    def apply(self, text: str) -> str:
        """The line with this suggestion in it."""
        return f"{text[: self.start]}{self.replacement}{text[self.end :]}"

    def cursor_after_apply(self) -> int:
        """Where the cursor belongs once the suggestion is in."""
        return self.start + len(self.replacement)


@dataclass(frozen=True, slots=True)
class CompletionState:
    """The suggestions for the line as it stands, and which one is picked."""

    items: tuple[CompletionItem, ...] = ()
    selected_index: int = 0

    @property
    def selected(self) -> CompletionItem | None:
        if not self.items:
            return None
        return self.items[self.selected_index]

    def select_next(self) -> CompletionState:
        return self._moved(1)

    def select_previous(self) -> CompletionState:
        return self._moved(-1)

    def _moved(self, step: int) -> CompletionState:
        if not self.items:
            return self
        return CompletionState(
            items=self.items,
            selected_index=(self.selected_index + step) % len(self.items),
        )


def build_completion_state(
    text: str,
    *,
    cursor: int | None = None,
    commands: dict[str, str] | None = None,
    skills: dict[str, dict] | None = None,
    cwd: Path | None = None,
) -> CompletionState:
    """What to offer for `text`, with the cursor `cursor` characters in.

    `commands` is name -> help and `skills` is name -> {"description": ...},
    both handed in so this module never imports the modules that own them and
    so a new command shows up in the menu without a change here. Command names
    are bare: the leading slash is added here, and `commands.COMMANDS` carries
    one of its own.
    """
    cursor = len(text) if cursor is None else max(0, min(cursor, len(text)))
    commands = commands or {}
    skills = skills or {}

    if not text.startswith("/") or text.startswith("//"):
        if cwd is None:
            return CompletionState()
        return CompletionState(_file_reference_completions(text, cursor, cwd))

    token_end = _first_token_end(text)
    token = text[:token_end]

    if token.startswith(SKILL_PREFIX):
        if token_end < len(text) and _is_skill_command(token, skills):
            # Past the skill name the rest is ordinary prompt text, so the user
            # can still point at a file while naming a skill.
            return CompletionState(_file_reference_completions(text, cursor, cwd))
        return CompletionState(
            _skill_completions(token, token_end, skills),
        )

    if token_end < len(text) and token.removeprefix("/") in commands:
        # The command is already complete and the user has moved on to its
        # argument. Re-offering the name it just finished would fight the
        # next word.
        return CompletionState()

    return CompletionState(_command_completions(token, token_end, commands))


# --------------------------------------------------------------------- commands


def _command_completions(
    token: str, token_end: int, commands: dict[str, str]
) -> tuple[CompletionItem, ...]:
    prefix = token.removeprefix("/").lower()
    return tuple(
        CompletionItem(
            display=f"/{name}",
            replacement=f"/{name}",
            start=0,
            end=token_end,
            kind=CompletionKind.COMMAND,
            description=help_text,
        )
        for name, help_text in _ranked(commands.items(), prefix)
    )


def _skill_completions(
    token: str, token_end: int, skills: dict[str, dict]
) -> tuple[CompletionItem, ...]:
    prefix = token.removeprefix(SKILL_PREFIX).lower()
    return tuple(
        CompletionItem(
            display=f"{SKILL_PREFIX}{name}",
            replacement=f"{SKILL_PREFIX}{name}",
            start=0,
            end=token_end,
            kind=CompletionKind.SKILL,
            description=skill.get("description"),
        )
        for name, skill in _ranked(skills.items(), prefix)
    )


def _ranked(items, prefix: str) -> list:
    """The entries whose name starts with `prefix`, alphabetically.

    Filtering before sorting keeps the order tied to what the user typed: the
    command they started typing is the one they meant.
    """
    return sorted(
        (item for item in items if item[0].lower().startswith(prefix)),
        key=lambda item: item[0].lower(),
    )


def _is_skill_command(token: str, skills: dict[str, dict]) -> bool:
    name = token.removeprefix(SKILL_PREFIX).lower()
    return any(skill.lower() == name for skill in skills)


def _first_token_end(text: str) -> int:
    space = text.find(" ")
    return len(text) if space == -1 else space


# ----------------------------------------------------------------- file paths


def _file_reference_completions(
    text: str, cursor: int, cwd: Path
) -> tuple[CompletionItem, ...]:
    token = _active_reference_token(text, cursor)
    if token is None:
        return ()

    start, end = token
    typed = text[start + 1 : cursor]
    walked = _walk_reference(text, start, end, typed, cwd)
    if walked is not None:
        return walked

    suggestions = []
    for path in _iter_paths(cwd):
        relative = path.relative_to(cwd).as_posix()
        if typed.lower() not in relative.lower():
            continue
        display = _display_path(relative, path)
        if display == text[start:end]:
            continue  # already typed in full
        suggestions.append(_reference_item(display, start, end))
        if len(suggestions) >= MAX_FILE_COMPLETIONS:
            break
    return tuple(suggestions)


def _walk_reference(
    text: str, start: int, end: int, typed: str, cwd: Path
) -> tuple[CompletionItem, ...] | None:
    """Completions for a path that leaves the working tree, or None if it does not.

    The tree walk below cannot see outside `cwd`, so `../` has to be resolved
    separately or `@../` would offer nothing at all.
    """
    if typed == "..":
        display = "@../"
        if display == text[start:end]:
            return ()
        return (_reference_item(display, start, end),)

    if not typed.startswith("../"):
        return None

    parent_text, _, name_prefix = typed.rpartition("/")
    if any(part in IGNORED_DIRECTORIES for part in parent_text.split("/")):
        return ()
    parent = cwd / parent_text
    if not parent.is_dir():
        return ()

    try:
        children = sorted(parent.iterdir(), key=lambda path: path.name.lower())
    except OSError:
        return ()

    suggestions = []
    for child in children:
        if child.name in IGNORED_DIRECTORIES:
            continue
        if not child.name.lower().startswith(name_prefix.lower()):
            continue
        display = f"@{parent_text}/{child.name}{'/' if child.is_dir() else ''}"
        if display == text[start:end]:
            continue
        suggestions.append(_reference_item(display, start, end))
        if len(suggestions) >= MAX_FILE_COMPLETIONS:
            break
    return tuple(suggestions)


def _reference_item(display: str, start: int, end: int) -> CompletionItem:
    return CompletionItem(
        display=display,
        replacement=display,
        start=start,
        end=end,
        kind=CompletionKind.FILE_REFERENCE,
        description="File reference",
    )


def _display_path(relative: str, path: Path) -> str:
    return f"@{relative}{'/' if path.is_dir() else ''}"


def _active_reference_token(text: str, cursor: int) -> tuple[int, int] | None:
    """The span of the @-token the cursor sits in, if there is one."""
    line_start = max(text.rfind(" ", 0, cursor), text.rfind("\n", 0, cursor)) + 1
    start = text.rfind("@", line_start, cursor)
    if start == -1:
        return None

    end = cursor
    while end < len(text) and not text[end].isspace():
        end += 1
    return start, end


def _iter_paths(cwd: Path) -> tuple[Path, ...]:
    if not cwd.is_dir():
        return ()

    paths = []
    stack = [cwd]
    while stack:
        try:
            children = sorted(stack.pop().iterdir(), key=lambda path: path.name.lower())
        except OSError:
            continue  # a directory we cannot read is not a reason to fail
        for child in children:
            if _is_ignored(child, cwd):
                continue
            paths.append(child)
            if child.is_dir():
                stack.append(child)
    return tuple(paths)


def _is_ignored(path: Path, cwd: Path) -> bool:
    try:
        parts = path.relative_to(cwd).parts
    except ValueError:
        return True
    return any(part in IGNORED_DIRECTORIES for part in parts)
