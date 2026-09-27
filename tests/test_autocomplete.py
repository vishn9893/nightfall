import tempfile
import unittest
from pathlib import Path

from nightfall import autocomplete as ac

COMMANDS = {
    "compact": "summarise the history",
    "rewind": "jump back",
    "sessions": "open a past chat",
}
SKILLS = {
    "grill-me": {"description": "interview a plan"},
    "find-skills": {"description": "discover skills"},
}


def build(text, cursor=None, cwd=None):
    return ac.build_completion_state(
        text,
        cursor=cursor,
        commands=COMMANDS,
        skills=SKILLS,
        cwd=cwd,
    )


class CommandTests(unittest.TestCase):
    def test_slash_lists_every_command(self):
        self.assertEqual(
            [item.display for item in build("/").items],
            ["/compact", "/rewind", "/sessions"],
        )

    def test_prefix_narrows_and_ranks_alphabetically(self):
        self.assertEqual([i.display for i in build("/s").items], ["/sessions"])
        self.assertEqual([i.display for i in build("/r").items], ["/rewind"])

    def test_command_carries_its_help_text(self):
        self.assertEqual(build("/c").items[0].description, "summarise the history")

    def test_command_replaces_the_whole_first_token(self):
        item = build("/co").items[0]
        self.assertEqual((item.start, item.end), (0, 3))
        self.assertEqual(item.apply("/co"), "/compact")
        self.assertEqual(item.cursor_after_apply(), len("/compact"))

    def test_a_command_with_no_match_offers_nothing(self):
        self.assertEqual(build("/zzz").items, ())

    def test_double_slash_is_not_a_command(self):
        self.assertEqual(build("//c").items, ())

    def test_typing_after_a_command_offers_no_arguments(self):
        # There is no argument completion, so a settled command stays quiet
        # rather than suggesting a second word that means nothing.
        self.assertEqual(build("/compact ").items, ())
        self.assertEqual(build("/compact and then").items, ())


class SkillTests(unittest.TestCase):
    def test_skill_prefix_lists_skills(self):
        self.assertEqual(
            [i.display for i in build("/skill:").items],
            ["/skill:find-skills", "/skill:grill-me"],
        )

    def test_skill_prefix_narrows(self):
        self.assertEqual(
            [i.display for i in build("/skill:g").items], ["/skill:grill-me"]
        )

    def test_skill_carries_its_description(self):
        self.assertEqual(build("/skill:g").items[0].description, "interview a plan")

    def test_skill_replaces_the_whole_token(self):
        item = build("/skill:g").items[0]
        self.assertEqual(item.apply("/skill:g"), "/skill:grill-me")

    def test_text_after_a_skill_name_is_not_completed(self):
        # The skill is already named, so the rest is prompt text.
        self.assertEqual(build("/skill:grill-me now").items, ())


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "src").mkdir()
        (self.root / "src" / "llm.py").write_text("x")
        (self.root / "README.md").write_text("x")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "big.js").write_text("x")

    def tearDown(self):
        self._tmp.cleanup()

    def test_at_completes_paths_in_the_tree(self):
        displays = [i.display for i in build("@s", cwd=self.root).items]
        # A substring, not a prefix: "@llm" should still find src/llm.py.
        self.assertIn("@src/", displays)
        self.assertIn("@src/llm.py", displays)

    def test_a_longer_prefix_finds_the_file(self):
        displays = [i.display for i in build("@src/l", cwd=self.root).items]
        self.assertEqual(displays, ["@src/llm.py"])

    def test_directories_get_a_trailing_slash(self):
        self.assertIn("@src/", [i.display for i in build("@s", cwd=self.root).items])
        self.assertNotIn("@src", [i.display for i in build("@s", cwd=self.root).items])

    def test_ignored_directories_are_not_offered(self):
        displays = [i.display for i in build("@", cwd=self.root).items]
        self.assertNotIn("@node_modules/", displays)
        self.assertNotIn("@node_modules/big.js", displays)

    def test_reference_replaces_the_at_token_only(self):
        item = build("look at @READ x", cursor=10, cwd=self.root).items[0]
        self.assertEqual(item.apply("look at @READ x"), "look at @README.md x")

    def test_at_inside_a_word_is_not_a_reference(self):
        # user@example.com must not be read as a path.
        self.assertEqual(build("mail me at user@exa", cwd=self.root).items, ())

    def test_no_at_no_completions(self):
        self.assertEqual(build("just typing", cwd=self.root).items, ())

    def test_parent_directory_is_offered(self):
        displays = [i.display for i in build("@..", cwd=self.root).items]
        self.assertEqual(displays, ["@../"])

    def test_a_missing_cwd_yields_nothing(self):
        self.assertEqual(build("@s", cwd=self.root / "nope").items, ())

    def test_no_cwd_at_all_yields_nothing(self):
        self.assertEqual(build("@s").items, ())

    def test_results_are_capped(self):
        for index in range(ac.MAX_FILE_COMPLETIONS + 10):
            (self.root / f"f{index:03d}.txt").write_text("x")
        self.assertEqual(len(build("@f", cwd=self.root).items), ac.MAX_FILE_COMPLETIONS)


class StateTests(unittest.TestCase):
    def test_apply_and_cursor_land_where_the_replacement_ends(self):
        state = build("/c")
        applied = state.selected.apply("/c")
        self.assertEqual(applied[: state.selected.cursor_after_apply()], "/compact")

    def test_selection_wraps_in_both_directions(self):
        state = build("/")
        self.assertEqual(state.select_next().selected_index, 1)
        self.assertEqual(state.select_previous().selected_index, 2)

    def test_an_empty_state_has_nothing_selected(self):
        self.assertIsNone(build("/zzz").selected)
        self.assertEqual(build("/zzz").select_next().items, ())

    def test_a_cursor_outside_the_text_is_clamped_not_fatal(self):
        # A stale cursor must not make the engine read out of range, and a
        # command is completed from the first token wherever the cursor is.
        self.assertEqual(len(build("/c", cursor=99).items), 1)
        self.assertEqual(len(build("/c", cursor=-5).items), 1)


if __name__ == "__main__":
    unittest.main()
