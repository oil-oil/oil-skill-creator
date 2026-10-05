#!/usr/bin/env python3
"""创建最小 Skill 目录，并拒绝覆盖已有文件。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from .skill_version import is_semver
    from .validate_skill import NAME_RE
except ImportError:  # 直接运行脚本时使用同目录导入。
    from skill_version import is_semver
    from validate_skill import NAME_RE


ALLOWED_COMPONENTS = {"scripts", "references", "assets", "tests", "evals"}
SKILL_TEMPLATE = """---
name: {name}
description: {description}
{version_metadata}---

# {name}

## 目标

TODO：说明这个 Skill 为谁解决什么重复问题，以及使用后能看到或测量到什么改善。

## 工作流

TODO：只保留必须作出的判断、关键分支和必须执行的步骤。结果固定并且需要重复运行的步骤放进 scripts。

## 输出

TODO：说明最终交付物、保存位置和完成后需要汇报的内容。

## 资源导航

TODO：只列出实际存在的按需资源及其读取时机。
"""

README_FALLBACK = """# __SKILL_NAME__

## 有什么用

__SUMMARY__

## 安装

给出完整 GitHub 仓库地址，让用户可以把地址交给 Agent 安装。

给出已经替换为真实仓库名的 `npx skills add <owner>/<repository>` 命令，并说明安装条件。

## 配置

说明首次配置；没有配置时明确写“无需额外配置”。

## 使用

说明如何用自然语言触发，不复制 SKILL.md 的内部流程。

## 兼容性与依赖

列出已验证平台、运行环境、系统命令和宿主必须提供的能力。

## 数据与适用边界

说明外部服务、权限、隐私、费用和不适用场景。

## 测试

说明如何运行程序测试和 Skill 效果评估。
"""


def _parse_components(value: str) -> set[str]:
    if not value.strip():
        return set()
    components = {item.strip() for item in value.split(",") if item.strip()}
    unknown = sorted(components - ALLOWED_COMPONENTS)
    if unknown:
        raise ValueError("不支持的组件：" + ", ".join(unknown))
    return components


def _read_readme_template() -> str:
    template = Path(__file__).resolve().parent.parent / "assets" / "README.template.md"
    if template.is_file():
        return template.read_text(encoding="utf-8")
    return README_FALLBACK


def _render_description(description: str) -> str:
    return json.dumps(description, ensure_ascii=False)


def planned_paths(
    output_root: Path, name: str, components: set[str], public: bool
) -> list[Path]:
    target = output_root / name
    paths = [target / "SKILL.md"]
    if public:
        paths.append(target / "README.md")
    for component in sorted(components):
        if component == "evals":
            paths.append(target / "evals" / "evals.json")
        else:
            paths.append(target / component)
    return paths


def create_skill(
    output_root: str | Path,
    name: str,
    description: str,
    components: set[str] | None = None,
    public: bool = False,
    dry_run: bool = False,
    version: str | None = None,
) -> tuple[Path, list[Path]]:
    if not NAME_RE.fullmatch(name) or len(name) > 64:
        raise ValueError("name 必须是 64 字符以内的 kebab-case")
    if not description.strip():
        raise ValueError("description 不能为空")
    if len(description) > 1024 or "<" in description or ">" in description:
        raise ValueError("description 不能超过 1024 字符或包含尖括号")
    if version is not None and not is_semver(version):
        raise ValueError("version 必须使用 MAJOR.MINOR.PATCH 格式，例如 0.1.0")

    component_set = set(components or set())
    unknown = sorted(component_set - ALLOWED_COMPONENTS)
    if unknown:
        raise ValueError("不支持的组件：" + ", ".join(unknown))

    root = Path(output_root).expanduser().resolve()
    target = root / name
    paths = planned_paths(root, name, component_set, public)
    if target.exists():
        raise FileExistsError(f"目标目录已存在，拒绝覆盖：{target}")
    if dry_run:
        return target, paths

    target.mkdir(parents=True)
    skill_text = SKILL_TEMPLATE.format(
        name=name,
        description=_render_description(description.strip()),
        version_metadata=(f'metadata:\n  version: "{version}"\n' if version else ""),
    )
    (target / "SKILL.md").write_text(skill_text, encoding="utf-8", newline="\n")

    if public:
        readme = _read_readme_template()
        readme = readme.replace("__SKILL_NAME__", name).replace(
            "__SUMMARY__", description.strip()
        )
        (target / "README.md").write_text(readme, encoding="utf-8", newline="\n")

    for component in sorted(component_set):
        component_dir = target / component
        component_dir.mkdir()
        if component == "evals":
            evals = {"skill_name": name, "evals": []}
            (component_dir / "evals.json").write_text(
                json.dumps(evals, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )

    return target, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="安全创建最小 Skill 骨架")
    parser.add_argument("name", help="kebab-case Skill 名称")
    parser.add_argument("--output-root", required=True, help="Skill 父目录")
    parser.add_argument(
        "--description",
        default="TODO：说明做什么、何时触发，以及哪些相似任务不要触发。",
        help="SKILL.md 顶部的触发说明",
    )
    parser.add_argument(
        "--components",
        default="",
        help="按需创建的逗号分隔组件：scripts,references,assets,tests,evals",
    )
    parser.add_argument("--public", action="store_true", help="同时生成 README.md")
    parser.add_argument(
        "--version",
        help="可选的初始 SemVer 版本；写入 metadata.version，例如 0.1.0",
    )
    parser.add_argument("--dry-run", action="store_true", help="只显示计划，不写入")
    parser.add_argument("--json", action="store_true", dest="as_json", help="输出 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        components = _parse_components(args.components)
        target, paths = create_skill(
            args.output_root,
            args.name,
            args.description,
            components=components,
            public=args.public,
            dry_run=args.dry_run,
            version=args.version,
        )
    except (ValueError, FileExistsError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    payload = {
        "status": "dry-run" if args.dry_run else "created",
        "target": str(target),
        "paths": [str(path) for path in paths],
    }
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        status = "仅预览" if payload["status"] == "dry-run" else "已创建"
        print(f"{status}：{target}")
        for path in paths:
            print(f"- {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
