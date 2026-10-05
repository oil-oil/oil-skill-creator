from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.scaffold_skill import create_skill


class ScaffoldSkillTests(unittest.TestCase):
    def test_creates_requested_components_without_extra_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target, _ = create_skill(
                temporary,
                "sample-skill",
                "处理稳定工作流。当用户要求创建固定产物时使用；普通问答不要触发。",
                components={"scripts", "evals"},
                public=True,
            )

            self.assertTrue((target / "SKILL.md").is_file())
            self.assertTrue((target / "README.md").is_file())
            self.assertTrue((target / "scripts").is_dir())
            self.assertTrue((target / "evals" / "evals.json").is_file())
            self.assertFalse((target / "references").exists())
            evals = json.loads((target / "evals" / "evals.json").read_text(encoding="utf-8"))
            self.assertEqual(evals, {"skill_name": "sample-skill", "evals": []})

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target, paths = create_skill(
                temporary,
                "dry-run-skill",
                "创建稳定结果。当用户需要该流程时使用；普通任务不要触发。",
                components={"tests"},
                dry_run=True,
            )
            self.assertFalse(target.exists())
            self.assertIn(target / "SKILL.md", paths)

    def test_optional_version_is_written_to_standard_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target, _ = create_skill(
                temporary,
                "versioned-skill",
                "创建稳定结果。当用户需要该流程时使用；普通问答不要触发。",
                version="0.1.0",
            )
            frontmatter = (target / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn('metadata:\n  version: "0.1.0"', frontmatter)

    def test_rejects_invalid_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                create_skill(
                    temporary,
                    "invalid-version-skill",
                    "创建稳定结果。当用户需要该流程时使用；普通问答不要触发。",
                    version="v1.0",
                )

    def test_refuses_to_overwrite_existing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            existing = Path(temporary) / "existing-skill"
            existing.mkdir()
            with self.assertRaises(FileExistsError):
                create_skill(
                    temporary,
                    "existing-skill",
                    "当用户需要时使用；普通任务不要触发。",
                )

    def test_rejects_invalid_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                create_skill(
                    temporary,
                    "Invalid_Name",
                    "当用户需要时使用；普通任务不要触发。",
                )


if __name__ == "__main__":
    unittest.main()
