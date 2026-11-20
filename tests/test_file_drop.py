import os
import tempfile
import unittest
from pathlib import Path

from nightfall import file_drop

WINDOWS = os.name == "nt"


def quoted(path):
    """How a path with a space comes back from the normalizer on this platform."""
    return f'"{path}"'


def file_uri(path, escape_spaces=False):
    """A file:// URI for a path. Windows needs the third slash before the drive."""
    text = str(path).replace("\\", "/")
    if escape_spaces:
        text = text.replace(" ", "%20")
    return "file://" + (text if text.startswith("/") else "/" + text)


class DropTests(unittest.TestCase):
    """Terminals disagree about what a drop looks like; all of them land here."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.plain = self._make("notes.txt")
        self.spaced = self._make("my file.txt")
        # Windows file names cannot contain a double quote, so the quote case
        # only exists on POSIX.
        self.quote = self._make("say hi.txt" if WINDOWS else 'say "hi".txt')

    def tearDown(self):
        self._tmp.cleanup()

    def _make(self, name):
        path = self.root / name
        path.write_text("x")
        return path

    def drop(self, text):
        return file_drop.normalize_dropped_paths(text)

    def test_a_single_path_comes_back_as_typed(self):
        self.assertEqual(self.drop(str(self.plain)), str(self.plain))

    @unittest.skipIf(WINDOWS, "backslash-escaping is a POSIX shell convention")
    def test_a_shell_escaped_path_is_unquoted(self):
        # What most POSIX terminals send: backslash-escaped, no quotes.
        self.assertEqual(
            self.drop(f"{self.root}/my\\ file.txt"), quoted(self.spaced)
        )

    def test_a_quoted_path_is_unquoted(self):
        self.assertEqual(self.drop(f'"{self.spaced}"'), quoted(self.spaced))

    def test_a_bare_path_with_spaces_survives_intact(self):
        # The case splitting would otherwise break apart into two paths.
        self.assertEqual(self.drop(str(self.spaced)), quoted(self.spaced))

    def test_a_file_uri_is_decoded(self):
        self.assertEqual(self.drop(file_uri(self.spaced)), quoted(self.spaced))

    def test_a_percent_encoded_uri_is_decoded(self):
        spaced = self.root / "a b.txt"
        spaced.write_text("x")
        self.assertEqual(
            self.drop(file_uri(spaced, escape_spaces=True)), quoted(spaced)
        )

    def test_a_path_too_long_to_stat_is_not_fatal(self):
        # stat(2) answers ENAMETOOLONG with an OSError, not a False. If the
        # normalizer let that through it would take the whole prompt down on a
        # long paste.
        self.assertIsNone(self.drop("/" + "x" * (file_drop.MAX_PATH_CHARS + 10)))
        self.assertIsNone(self.drop("/tmp/" + "y" * (file_drop.MAX_PATH_CHARS * 2)))

    @unittest.skipIf(WINDOWS, "POSIX shell-escaped input")
    def test_several_files_are_space_separated(self):
        self.assertEqual(
            self.drop(f"{self.plain} {self.root}/my\\ file.txt"),
            f"{self.plain} {quoted(self.spaced)}",
        )

    @unittest.skipIf(WINDOWS, "Windows file names cannot contain a double quote")
    def test_a_quote_in_the_name_is_escaped(self):
        self.assertEqual(
            self.drop(str(self.quote)), f'"{self.root}/say \\"hi\\".txt"'
        )

    def test_surrounding_whitespace_is_ignored(self):
        self.assertEqual(self.drop(f"  {self.plain}\n"), str(self.plain))

    def test_a_directory_counts_as_a_path(self):
        self.assertEqual(self.drop(str(self.root)), str(self.root))

    def test_two_paths_one_with_spaces_are_a_drop(self):
        # Terminals quote a spaced path when it is one of several dropped.
        self.assertEqual(
            self.drop(f'"{self.spaced}" {self.plain}'),
            f"{quoted(self.spaced)} {self.plain}",
        )

    def test_a_directory_of_files_is_still_a_drop(self):
        paths = [self.root / f"f{i}.txt" for i in range(3)]
        for path in paths:
            path.write_text("x")
        self.assertEqual(
            self.drop(" ".join(str(p) for p in paths)),
            " ".join(str(p) for p in paths),
        )

    @unittest.skipUnless(WINDOWS, "Windows path rules")
    def test_windows_backslashes_are_not_treated_as_escapes(self):
        self.assertEqual(self.drop(str(self.plain)), str(self.plain))
        self.assertIn("\\", self.drop(str(self.plain)))
        self.assertEqual(
            self.drop(f'"{self.spaced}" {self.plain}'),
            f"{quoted(self.spaced)} {self.plain}",
        )

    @unittest.skipUnless(WINDOWS, "Windows path rules")
    def test_windows_file_uri_with_drive_letter_is_decoded(self):
        uri = file_uri(self.spaced, escape_spaces=True)
        self.assertIn("file:///C:/", uri)
        self.assertEqual(self.drop(uri), quoted(self.spaced))

    @unittest.skipUnless(WINDOWS, "Windows path rules")
    def test_windows_spaced_path_is_not_doubled_backslashes(self):
        result = self.drop(str(self.spaced))
        self.assertNotIn("\\\\", result)


class NotADropTests(unittest.TestCase):
    """The failure that matters: a paste that merely contains a path is a paste."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.plain = self.root / "notes.txt"
        self.plain.write_text("x")

    def tearDown(self):
        self._tmp.cleanup()

    def drop(self, text):
        return file_drop.normalize_dropped_paths(text)

    def test_prose_with_a_path_in_it_is_left_alone(self):
        self.assertIsNone(self.drop(f"please read {self.plain} and tell me"))

    def test_a_path_that_does_not_exist_is_left_alone(self):
        self.assertIsNone(self.drop("/nope/does/not/exist.txt"))

    def test_a_relative_path_is_left_alone(self):
        # A drop did not come from this process, so a relative path is junk.
        self.assertIsNone(self.drop("notes.txt"))

    def test_empty_text_is_not_a_drop(self):
        self.assertIsNone(self.drop("   "))

    def test_one_bad_token_poisons_the_whole_drop(self):
        self.assertIsNone(self.drop(f"{self.plain} /nope/missing.txt"))

    def test_unbalanced_quotes_are_left_alone(self):
        self.assertIsNone(self.drop(f'{self.plain} "unclosed'))

    def test_a_remote_file_uri_is_not_local(self):
        self.assertIsNone(self.drop("file://otherhost/tmp/a.txt"))

    def test_an_enormous_drop_is_refused(self):
        # A paste of hundreds of paths is a paste, not a drop anyone meant.
        made = []
        for index in range(file_drop.MAX_DROPPED_FILES + 1):
            path = self.root / f"f{index}.txt"
            path.write_text("x")
            made.append(path)
        self.assertIsNone(self.drop(" ".join(str(p) for p in made)))


if __name__ == "__main__":
    unittest.main()
