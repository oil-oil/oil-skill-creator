#!/usr/bin/env python3
"""Preview or update a Skill's metadata.version using Semantic Versioning."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

try:
    from .skill_version import is_semver, read_skill_version, update_skill_version
except ImportError:
    from skill_version import is_semver, read_skill_version, update_skill_version


def bump_version(current: str, part: str) -> str:
    if not is_semver(current):
        raise ValueError("当前版本不是 MAJOR.MINOR.PATCH 格式")
    major, minor, patch = (int(item) for item in current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _atomic_write(path: Path, content: str) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="预览或更新 Skill 的 SemVer 版本")
    parser.add_argument("skill_path", help="包含 SKILL.md 的 Skill 目录")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--initial", help="设置尚未版本化的 Skill 初始版本，例如 1.0.0")
    action.add_argument("--bump", choices=("major", "minor", "patch"), help="递增已有版本")
    parser.add_argument("--write", action="store_true", help="写入文件；省略时只预览")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式结果")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    skill_path = Path(args.skill_path).expanduser().resolve()
    skill_file = skill_path / "SKILL.md"
    if not skill_file.is_file():
        print(f"ERROR: 找不到 Skill 文件：{skill_file}", file=sys.stderr)
        return 1

    try:
        with skill_file.open("r", encoding="utf-8", newline="") as stream:
            raw = stream.read()
        current = read_skill_version(raw)
        if args.initial is not None:
            if not is_semver(args.initial):
                raise ValueError("初始版本必须使用 MAJOR.MINOR.PATCH 格式，例如 1.0.0")
            if current is not None:
                raise ValueError(f"Skill 已有版本 {current}；不会覆盖已有版本")
            next_version = args.initial
            updated = update_skill_version(raw, next_version, require_absent=True)
        else:
            if current is None:
                raise ValueError("Skill 尚无 metadata.version；请先使用 --initial 设置初始版本")
            next_version = bump_version(current, args.bump)
            updated = update_skill_version(raw, next_version, require_absent=False)

        if args.write:
            _atomic_write(skill_file, updated)
        payload = {
            "status": "updated" if args.write else "preview",
            "skill": skill_path.name,
            "previous_version": current,
            "next_version": next_version,
            "path": str(skill_file),
        }
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        status = "已更新" if args.write else "预览"
        previous = payload["previous_version"] or "未设置"
        print(f"{status}：{payload['skill']} {previous} → {payload['next_version']}")
        if not args.write:
            print("确认后添加 --write 才会修改 SKILL.md。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
