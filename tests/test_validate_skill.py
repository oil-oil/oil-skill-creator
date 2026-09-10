from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.validate_skill import audit_skill, parse_frontmatter


VALID_SKILL = """---
name: sample-skill
description: 生成稳定产物。当用户要求执行固定流程时使用；普通问答不要触发。
compatibility: Python 3，支持 macOS、Windows 和 Linux。
---

# sample-skill

读取 [规则](references/rules.md)，运行 `scripts/run.py`，交付结果。
"""

VALID_README = """# sample-skill

## 有什么用
说明价值。

## 安装
把仓库地址交给 Agent 安装：

https://github.com/example/sample-skill

也可以使用 `npx skills add example/sample-skill`。

## 配置
无需额外配置。

## 使用
说明使用。

## 兼容性与依赖
支持 macOS、Windows 和 Linux。

## 数据与适用边界
只处理本地数据。
"""


def make_valid_skill(root: Path) -> Path:
    skill = root / "sample-skill"
    (skill / "references").mkdir(parents=True)
    (skill / "scripts").mkdir()
    (skill / "SKILL.md").write_text(VALID_SKILL, encoding="utf-8")
    (skill / "README.md").write_text(VALID_README, encoding="utf-8")
    (skill / "references" / "rules.md").write_text("# 规则\n", encoding="utf-8")
    (skill / "scripts" / "run.py").write_text("print('ok')\n", encoding="utf-8")
    return skill


class ValidateSkillTests(unittest.TestCase):
    def test_public_nested_skill_uses_referenced_repository_readme(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / '.git').mkdir()
            skill = make_valid_skill(root / 'skills')
            (skill / 'README.md').unlink()
            (root / 'README.md').write_text(VALID_README + '\n入口：skills/sample-skill/SKILL.md\n')
            report = audit_skill(skill, public=True)
            self.assertNotIn('readme.missing', {item.code for item in report.errors})

    def test_parent_readme_outside_repository_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = make_valid_skill(root)
            (skill / 'README.md').unlink()
            (root / 'README.md').write_text(VALID_README)
            self.assertIn('readme.missing', {item.code for item in audit_skill(skill, public=True).errors})

    def test_provider_name_and_optional_metadata_do_not_prove_host_dependency(self):
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / 'agents').mkdir()
            (skill / 'assets').mkdir()
            (skill / 'assets/openai.svg').write_text('<svg/>')
            (skill / 'agents/openai.yaml').write_text('interface: {}\n')
            with (skill / 'SKILL.md').open('a') as handle:
                handle.write('\n可选服务为 OpenAI API，示例产品名为 Claude Code。\n')
            report = audit_skill(skill, universal=True)
            self.assertFalse([item for item in report.errors if item.code.startswith('compatibility.host')])

    def test_valid_public_skill_passes_strict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            report = audit_skill(skill, public=True, weak_model=True)
            self.assertTrue(report.passed(strict=True), report.to_dict(strict=True))

    def test_folded_description_is_parsed(self) -> None:
        raw = """---
name: folded-skill
description: >
  第一行。
  当用户需要时使用；普通任务不要触发。
---
body
"""
        frontmatter, body = parse_frontmatter(raw)
        self.assertEqual(frontmatter["name"], "folded-skill")
        self.assertIn("当用户需要时使用", frontmatter["description"])
        self.assertEqual(body, "body\n")

    def test_broken_resource_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / "SKILL.md").write_text(
                VALID_SKILL.replace("references/rules.md", "references/missing.md"),
                encoding="utf-8",
            )
            report = audit_skill(skill)
            self.assertIn("resource.missing", {item.code for item in report.errors})

    def test_history_heading_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            with (skill / "SKILL.md").open("a", encoding="utf-8") as handle:
                handle.write("\n## 修改记录\n\n- 调整流程。\n")
            report = audit_skill(skill)
            self.assertIn("content.history", {item.code for item in report.errors})

    def test_rule_forbidding_previous_task_reuse_is_not_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            with (skill / "SKILL.md").open("a", encoding="utf-8") as handle:
                handle.write("\n不要复用上一次任务里的具体内容。\n")
            report = audit_skill(skill)
            self.assertNotIn("content.history", {item.code for item in report.errors})

    def test_history_in_reference_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / "references" / "rules.md").write_text(
                "# 修改记录\n\n- 调整流程。\n", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertIn("content.history", {item.code for item in report.errors})

    def test_personal_path_in_readme_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            personal_path = "/Users/" + "example/private/config.json"
            with (skill / "README.md").open("a", encoding="utf-8") as handle:
                handle.write(f"\n配置位于 {personal_path}。\n")
            report = audit_skill(skill)
            self.assertIn("content.personal-path", {item.code for item in report.errors})

    def test_personal_path_in_script_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            personal_path = "/home/" + "alice/.config/sample-skill"
            (skill / "scripts" / "run.py").write_text(
                f'CONFIG = "{personal_path}"\n', encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertIn("content.personal-path", {item.code for item in report.errors})

    def test_configurable_user_path_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / "scripts" / "run.py").write_text(
                """from pathlib import Path
import os

CONFIG = Path(os.environ.get("SAMPLE_SKILL_CONFIG", Path.home() / ".sample-skill"))
""",
                encoding="utf-8",
            )
            report = audit_skill(skill)
            self.assertNotIn("content.personal-path", {item.code for item in report.errors})

    def test_public_readme_sections_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / "README.md").write_text("# sample-skill\n", encoding="utf-8")
            report = audit_skill(skill, public=True)
            self.assertIn("readme.section-missing", {item.code for item in report.errors})

    def test_github_readme_requires_agent_install_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            readme = (skill / "README.md").read_text(encoding="utf-8")
            (skill / "README.md").write_text(
                readme.replace("把仓库地址交给 Agent 安装：\n\n", ""),
                encoding="utf-8",
            )
            report = audit_skill(skill, public=True)
            self.assertIn(
                "readme.install-agent-missing",
                {item.code for item in report.warnings},
            )

    def test_github_readme_requires_npx_install_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            readme = (skill / "README.md").read_text(encoding="utf-8")
            (skill / "README.md").write_text(
                readme.replace(
                    "\n也可以使用 `npx skills add example/sample-skill`。\n", "\n"
                ),
                encoding="utf-8",
            )
            report = audit_skill(skill, public=True)
            self.assertIn(
                "readme.install-command-missing",
                {item.code for item in report.warnings},
            )

    def test_embedded_secret_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            fake_secret = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
            (skill / "references" / "secret.md").write_text(
                f"token: {fake_secret}", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertIn("security.embedded-secret", {item.code for item in report.errors})

    def test_plaintext_secret_assignment_in_json_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            secret_value = "m8Lq7xP2vN4cR9tY6wK3zB5d"
            (skill / "config.json").write_text(
                f'{{"api_key": "{secret_value}"}}\n', encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertIn("security.plaintext-secret", {item.code for item in report.errors})

    def test_credential_reference_in_json_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / "config.json").write_text(
                '{"credential_ref": "sample-skill/default"}\n', encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertNotIn("security.plaintext-secret", {item.code for item in report.errors})

    def test_private_key_block_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            private_key_header = "-----BEGIN " + "PRIVATE KEY-----"
            (skill / "references" / "secret.txt").write_text(
                private_key_header + "\nabc123\n", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertIn("security.embedded-secret", {item.code for item in report.errors})

    def test_private_key_block_in_pem_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            private_key_header = "-----BEGIN " + "PRIVATE KEY-----"
            (skill / "key.pem").write_text(
                private_key_header + "\nabc123\n", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertIn("security.embedded-secret", {item.code for item in report.errors})

    def test_private_key_block_in_key_file_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            private_key_header = "-----BEGIN " + "ENCRYPTED PRIVATE KEY-----"
            (skill / "server.key").write_text(
                private_key_header + "\nabc123\n", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertIn("security.embedded-secret", {item.code for item in report.errors})

    def test_pgp_private_key_block_in_asc_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            private_key_header = "-----BEGIN " + "PGP PRIVATE KEY BLOCK-----"
            (skill / "key.asc").write_text(
                private_key_header + "\nabc123\n", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertIn("security.embedded-secret", {item.code for item in report.errors})

    def test_prefixed_secret_assignment_in_env_template_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            secret_value = "m8Lq7xP2vN4cR9tY6wK3zB5d"
            (skill / ".env.example").write_text(
                "OPENAI_" + f"API_KEY={secret_value}\n", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertIn("security.plaintext-secret", {item.code for item in report.errors})

    def test_prefixed_secret_assignments_in_structured_config_are_errors(self) -> None:
        cases = {
            "config.json": ('{\n  "SUPABASE_' + 'SERVICE_ROLE_KEY": "m8Lq7xP2vN4cR9tY6wK3zB5d"\n}\n'),
            "config.yaml": ("service:\n  GITHUB_" + "TOKEN: m8Lq7xP2vN4cR9tY6wK3zB5d\n"),
        }
        for filename, content in cases.items():
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temporary:
                skill = make_valid_skill(Path(temporary))
                (skill / filename).write_text(content, encoding="utf-8")
                report = audit_skill(skill)
                self.assertIn(
                    "security.plaintext-secret", {item.code for item in report.errors}
                )

    def test_prefixed_secret_placeholder_in_env_template_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / ".env.example").write_text(
                "OPENAI_API_KEY=your_api_key_here\n", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertNotIn("security.plaintext-secret", {item.code for item in report.errors})

    def test_folded_yaml_secret_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            secret_value = "m8Lq7xP2vN4cR9tY6wK3zB5d"
            (skill / "config.yaml").write_text(
                "api_" + f"key: >-\n  {secret_value}\n", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertIn("security.plaintext-secret", {item.code for item in report.errors})

    def test_folded_yaml_secret_placeholder_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / "config.yaml").write_text(
                "api_" + "key: >-\n  your_api_key_here\n", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertNotIn("security.plaintext-secret", {item.code for item in report.errors})

    def test_windows_shared_profile_paths_are_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / "references" / "rules.md").write_text(
                "C:\\Users\\Public\\sample and C:/Users/Default/sample\n",
                encoding="utf-8",
            )
            report = audit_skill(skill)
            self.assertNotIn("content.personal-path", {item.code for item in report.errors})

    def test_windows_personal_path_with_forward_slashes_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / "references" / "rules.md").write_text(
                "C:/Users/" + "alice/private/config.json\n", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertIn("content.personal-path", {item.code for item in report.errors})

    def test_root_home_path_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / "references" / "rules.md").write_text(
                "/" + "root/.config/sample-skill/config.json\n", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertIn("content.personal-path", {item.code for item in report.errors})

    def test_sensitive_credential_file_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / ".env").write_text("SAFE_PLACEHOLDER=1\n", encoding="utf-8")
            report = audit_skill(skill)
            self.assertIn("security.sensitive-file", {item.code for item in report.errors})

    def test_env_template_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / ".env.example").write_text(
                "API_KEY=your_api_key_here\n", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertNotIn("security.sensitive-file", {item.code for item in report.errors})
            self.assertNotIn("security.plaintext-secret", {item.code for item in report.errors})

    def test_unreachable_reference_is_a_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / "references" / "orphan.md").write_text(
                "# 孤立规则\n\n这份规则没有入口。\n", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertIn(
                "layer.reference-unreachable", {item.code for item in report.warnings}
            )

    def test_duplicate_markdown_block_is_a_warning(self) -> None:
        duplicate = (
            "所有确定、重复并且能够通过程序验证的步骤都应写进脚本，"
            "执行 Agent 只负责选择策略和处理无法穷举的例外情况。"
        )
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            with (skill / "SKILL.md").open("a", encoding="utf-8") as handle:
                handle.write(f"\n{duplicate}\n")
            (skill / "references" / "rules.md").write_text(
                f"# 规则\n\n{duplicate}\n", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertIn(
                "content.duplicate-exact", {item.code for item in report.warnings}
            )

    def test_near_duplicate_markdown_block_is_a_warning(self) -> None:
        original = (
            "面向能力较弱的模型时，每条指令都要明确动作主体、输入、输出和停止条件，"
            "分支必须紧邻对应步骤，并保持术语前后一致。"
        ) * 5
        similar = original.replace("都要明确", "需要明确", 1)
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            with (skill / "SKILL.md").open("a", encoding="utf-8") as handle:
                handle.write(f"\n{original}\n")
            (skill / "references" / "rules.md").write_text(
                f"# 规则\n\n{similar}\n", encoding="utf-8"
            )
            report = audit_skill(skill)
            self.assertIn(
                "content.duplicate-near", {item.code for item in report.warnings}
            )

    def test_weak_model_profile_rejects_long_paragraph(self) -> None:
        long_paragraph = "这个步骤必须保持单一动作并明确输入输出。" * 30
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            with (skill / "SKILL.md").open("a", encoding="utf-8") as handle:
                handle.write(f"\n{long_paragraph}\n")
            report = audit_skill(skill, weak_model=True)
            self.assertIn(
                "readability.long-paragraph", {item.code for item in report.warnings}
            )

    def test_invalid_eval_schema_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / "evals").mkdir()
            (skill / "evals" / "evals.json").write_text(
                """{
  "skill_name": "sample-skill",
  "evals": [{"id": 1, "prompt": "测试", "assertions": []}]
}
""",
                encoding="utf-8",
            )
            report = audit_skill(skill)
            self.assertIn("evals.schema", {item.code for item in report.errors})

    def test_universal_mode_rejects_host_brand(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            with (skill / "SKILL.md").open("a", encoding="utf-8") as handle:
                handle.write("\n只在 Codex 中执行这个流程。\n")
            report = audit_skill(skill, universal=True)
            self.assertIn(
                "compatibility.host-coupling", {item.code for item in report.errors}
            )
            self.assertNotIn(
                "compatibility.host-coupling",
                {item.code for item in audit_skill(skill).errors},
            )

    def test_universal_mode_rejects_host_specific_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = make_valid_skill(Path(temporary))
            (skill / "references" / "claude-adapter.md").write_text(
                "# Adapter\n", encoding="utf-8"
            )
            report = audit_skill(skill, universal=True)
            self.assertIn(
                "compatibility.host-specific-path",
                {item.code for item in report.errors},
            )


if __name__ == "__main__":
    unittest.main()
