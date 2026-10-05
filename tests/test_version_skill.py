from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.skill_version import read_skill_version, update_skill_version
from scripts.version_skill import bump_version, main


class VersionSkillTests(unittest.TestCase):
    def test_initial_version_adds_metadata_without_changing_body(self) -> None:
        source = "---\nname: example\ndescription: Example.\n---\n\n# Body\n"
        result = update_skill_version(source, "1.0.0", require_absent=True)
        self.assertIn('metadata:\n  version: "1.0.0"', result)
        self.assertTrue(result.endswith("\n\n# Body\n"))

    def test_existing_metadata_is_preserved(self) -> None:
        source = (
            "---\nname: example\ndescription: Example.\nmetadata:\n"
            "  author: oil\n  requires:\n    bins: [git]\n---\nbody\n"
        )
        result = update_skill_version(source, "2.3.4", require_absent=True)
        self.assertIn('  version: "2.3.4"', result)
        self.assertIn("  author: oil\n  requires:\n    bins: [git]", result)
        self.assertEqual(read_skill_version(result), "2.3.4")

    def test_bump_changes_only_version(self) -> None:
        source = (
            '---\nname: example\ndescription: Example.\nmetadata:\n'
            '  author: oil\n  version: "1.2.3"\n---\nbody\n'
        )
        result = update_skill_version(source, "1.2.4", require_absent=False)
        self.assertIn('  author: oil\n  version: "1.2.4"\n---\nbody\n', result)

    def test_forms_line_readers_cannot_read_are_rejected(self) -> None:
        forms = {
            "单引号": "metadata:\n  version: '1.2.3'",
            "行尾不能加注释": 'metadata:\n  version: "1.2.3" # current',
            "单行映射": 'metadata: {version: "1.2.3"}',
        }
        for reason, metadata in forms.items():
            with self.subTest(reason=reason):
                source = f"---\nname: example\ndescription: Example.\n{metadata}\n---\n"
                with self.assertRaisesRegex(ValueError, reason):
                    read_skill_version(source)
                with self.assertRaises(ValueError):
                    update_skill_version(source, "1.2.4", require_absent=False)

    def test_existing_child_indent_is_kept(self) -> None:
        source = (
            '---\nname: example\ndescription: Example.\nmetadata:\n'
            '    requires:\n      version: ">=2"\n    version: "1.0.0"\n---\n'
        )
        self.assertEqual(read_skill_version(source), "1.0.0")
        result = update_skill_version(source, "1.1.0", require_absent=False)
        self.assertIn('      version: ">=2"\n    version: "1.1.0"\n', result)

        added = update_skill_version(
            "---\nname: example\ndescription: Example.\nmetadata:\n    author: oil\n---\n",
            "0.1.0",
            require_absent=True,
        )
        self.assertIn('    author: oil\n    version: "0.1.0"\n', added)

    def test_initial_version_refuses_to_replace_existing_version(self) -> None:
        source = '---\nname: example\ndescription: Example.\nmetadata:\n  version: "1.0.0"\n---\n'
        with self.assertRaisesRegex(ValueError, "不会覆盖"):
            update_skill_version(source, "2.0.0", require_absent=True)

    def test_inline_nonempty_metadata_is_not_rewritten(self) -> None:
        source = '---\nname: example\ndescription: Example.\nmetadata: {author: oil}\n---\n'
        with self.assertRaisesRegex(ValueError, "无法安全扩展"):
            update_skill_version(source, "1.0.0", require_absent=True)

    def test_semver_bumps(self) -> None:
        self.assertEqual(bump_version("1.2.3", "patch"), "1.2.4")
        self.assertEqual(bump_version("1.2.3", "minor"), "1.3.0")
        self.assertEqual(bump_version("1.2.3", "major"), "2.0.0")

    def test_cli_preview_does_not_write_and_write_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "example"
            skill.mkdir()
            skill_file = skill / "SKILL.md"
            original = "---\nname: example\ndescription: Example.\n---\nbody\n"
            skill_file.write_text(original, encoding="utf-8")

            self.assertEqual(main([str(skill), "--initial", "1.0.0"]), 0)
            self.assertEqual(skill_file.read_text(encoding="utf-8"), original)
            self.assertEqual(main([str(skill), "--initial", "1.0.0", "--write"]), 0)
            self.assertEqual(read_skill_version(skill_file.read_text(encoding="utf-8")), "1.0.0")


if __name__ == "__main__":
    unittest.main()
