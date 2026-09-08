from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.install_credential_ui import install_credential_ui


class CredentialUiTests(unittest.TestCase):
    def root(self, temporary: str) -> Path:
        target = Path(temporary) / "sample-skill"
        target.mkdir()
        (target / "SKILL.md").write_text("# 测试 Skill\n", encoding="utf-8")
        return target

    def test_installs_self_contained_component_and_preserves_customized_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary)
            result = install_credential_ui(root, "sample-skill", "服务凭据", "sample/service/default")
            target = Path(result["directory"])
            self.assertEqual(result["status"], "installed")
            self.assertTrue((target / "public" / "app.js").is_file())
            self.assertFalse((target / "node_modules").exists())
            manifest = target / "manifests" / "default.json"
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["ui"]["title"] = "自定义标题"
            manifest.write_text(json.dumps(data), encoding="utf-8")
            again = install_credential_ui(root, "sample-skill", "服务凭据", "sample/service/default")
            self.assertEqual(again["status"], "unchanged")
            self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["ui"]["title"], "自定义标题")

    def test_refuses_identity_collision_and_modified_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary)
            result = install_credential_ui(root, "sample-skill", "服务凭据", "sample/service/default")
            with self.assertRaises(FileExistsError):
                install_credential_ui(root, "sample-skill", "另一个账号", "sample/other/default")
            source = Path(result["directory"]) / "public" / "style.css"
            source.write_text("用户已有修改", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                install_credential_ui(root, "sample-skill", "服务凭据", "sample/service/default")
            self.assertEqual(source.read_text(encoding="utf-8"), "用户已有修改")

    def test_real_cli_preview_is_read_only_and_install_does_not_change_skill(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary)
            before = (root / "SKILL.md").read_bytes()
            script = Path(__file__).resolve().parents[1] / "scripts" / "install_credential_ui.py"
            args = [sys.executable, str(script), str(root), "--id", "sample-skill", "--label", "服务凭据", "--credential", "sample/service/default"]
            preview = subprocess.run(args + ["--dry-run"], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(preview.stdout)["status"], "preview")
            self.assertFalse((root / "scripts").exists())
            installed = subprocess.run(args, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(installed.stdout)["status"], "installed")
            self.assertEqual((root / "SKILL.md").read_bytes(), before)

    def test_invalid_target_or_reference_does_not_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary)
            with self.assertRaises(ValueError):
                install_credential_ui(root, "sample-skill", "服务", "../wrong")
            self.assertFalse((root / "scripts").exists())

    def test_installed_component_runs_without_creator_workspace(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("没有 Node.js，跳过可选组件运行验证")
        version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout.strip().lstrip("v")
        if tuple(int(part) for part in version.split(".")[:2]) < (22, 18):
            self.skipTest("可选组件需要 Node.js 22.18+")
        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary)
            result = install_credential_ui(root, "sample-skill", "独立服务", "sample/service/default")
            execution = subprocess.run(
                [node, "--test", *sorted(str(item.relative_to(result["directory"])) for item in (Path(result["directory"]) / "tests").glob("*.test.ts"))],
                cwd=result["directory"], capture_output=True, text=True,
            )
            self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)


if __name__ == "__main__":
    unittest.main()
