"""The input line.

`input()` cannot edit a line that has wrapped past the screen width - the
terminal owns the wrapping and readline cannot see it. prompt_toolkit redraws
the line itself, so deleting, word jumps and history all keep working once the
text is longer than the screen.

Completion lives in `autocomplete.py`; this module is only the adapter that
feeds it to prompt_toolkit.
"""

from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, ThreadedCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.styles import Style

from . import autocomplete, file_drop

HISTORY = Path.home() / ".agents" / "history"

STYLE = Style.from_dict(
    {
        "prompt": "bold #9ece6a",
        "completion-menu.completion": "bg:#1c1f26 #8a8f9a",
        "completion-menu.completion.current": "bg:#6978a8 #f0f2f5",
    }
)


def _sources():
    """(commands, skills) for the engine, read at first use.

    Imported here rather than at module scope because `commands` imports `ui`,
    which imports this module - a top-level import would be a cycle. The
    command list is read on every keystroke rather than cached, so a command
    added to COMMANDS appears in the menu without a restart.
    """
    from .commands import COMMANDS
    from .skills import SKILLS

    # COMMANDS is keyed with the slash the user types; the engine wants the
    # bare name and puts the slash back on.
    return {name.removeprefix("/"): help for name, help in COMMANDS.items()}, SKILLS


bindings = KeyBindings()


# macOS sends option-arrow as escape then arrow. Terminals configured to send
# option as meta emit alt-b / alt-f instead, which prompt_toolkit binds itself.
@bindings.add("escape", "left")
def _word_left(event):
    document = event.current_buffer.document
    event.current_buffer.cursor_position += (
        document.find_previous_word_beginning(count=1) or 0
    )


@bindings.add("escape", "right")
def _word_right(event):
    document = event.current_buffer.document
    event.current_buffer.cursor_position += (
        document.find_next_word_ending(count=1) or 0
    )


@bindings.add("escape", "enter")
def _newline(event):
    """Option-enter starts a new line instead of sending the message."""
    event.current_buffer.insert_text("\n")


@bindings.add(Keys.BracketedPaste)
def _paste(event):
    """A dropped file arrives as a paste; anything else is a paste."""
    data = event.data

    # prompt_toolkit's own handler does this, and a terminal that pastes CRLF
    # would otherwise put a stray \r in the buffer. Done here too because this
    # binding replaces that one.
    data = data.replace("\r\n", "\n").replace("\r", "\n")

    event.current_buffer.insert_text(file_drop.normalize_dropped_paths(data) or data)


class Autocomplete(Completer):
    """Turns the engine's suggestions into prompt_toolkit completions.

    The span the engine returns is absolute, while prompt_toolkit wants an
    offset backwards from the cursor, so `start` is what is handed over and
    `replacement` is what gets inserted.
    """

    def __init__(self, cwd=None):
        self.cwd = Path.cwd() if cwd is None else Path(cwd)

    def get_completions(self, document, complete_event):
        commands, skills = _sources()
        state = autocomplete.build_completion_state(
            document.text,
            cursor=document.cursor_position,
            commands=commands,
            skills=skills,
            cwd=self.cwd,
        )
        for item in state.items:
            yield Completion(
                item.replacement,
                start_position=item.start - document.cursor_position,
                display=item.display,
                display_meta=item.description or "",
            )


SESSION = None


def read(prompt="> "):
    """Read one message. Raises EOFError on ctrl-d, like input() does."""
    global SESSION
    if SESSION is None:
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        SESSION = PromptSession(
            history=FileHistory(str(HISTORY)),
            key_bindings=bindings,
            style=STYLE,
            # The tree walk is a filesystem hit per keystroke, so it runs off
            # the UI thread and results appear when they are ready.
            completer=ThreadedCompleter(Autocomplete()),
            complete_while_typing=True,
        )
    return SESSION.prompt(HTML(f"<prompt>{prompt}</prompt>"))
