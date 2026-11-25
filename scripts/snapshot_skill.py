#!/usr/bin/env python3
"""在整改前创建不可变 Skill 基线，并拒绝覆盖。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

try:
    from .validate_skill import parse_frontmatter
except ImportError:
    from validate_skill import parse_frontmatter


EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__", "dist"}
EXCLUDED_FILES = {".DS_Store"}


def _skill_name(skill_path: Path) -> str:
    skill_md = skill_path / "SKILL.md"
    if not skill_md.is_file():
        raise ValueError("目标目录缺少 SKILL.md")
    frontmatter, _ = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    name = frontmatter.get("name", "").strip()
    if not name:
        raise ValueError("SKILL.md 缺少 name")
    return name


def _included_files(skill_path: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(skill_path.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(skill_path)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"快照不接受符号链接：{path}")
        if path.is_file() and path.name not in EXCLUDED_FILES:
            files.append(path)
    return files


def default_workspace(skill_path: Path, name: str) -> Path:
    """返回不会落入常见 Skill 扫描目录的默认 workspace。"""
    parent = skill_path.parent
    if parent.name.lower() == "skills":
        return parent.parent / "skill-workspaces" / f"{name}-workspace"
    return parent / f"{name}-workspace"


def _digest(skill_path: Path, files: list[Path]) -> str:
    checksum = hashlib.sha256()
    for path in files:
        relative = path.relative_to(skill_path).as_posix().encode("utf-8")
        checksum.update(len(relative).to_bytes(4, "big"))
        checksum.update(relative)
        content = path.read_bytes()
        checksum.update(len(content).to_bytes(8, "big"))
        checksum.update(content)
    return checksum.hexdigest()


def skill_digest(skill_path: str | Path) -> str:
    """只计算 Skill 内容摘要，不读取也不检查任何 workspace。"""
    source = Path(skill_path).expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Skill 目录不存在：{source}")
    return _digest(source, _included_files(source))


def verify_snapshot(workspace: str | Path) -> dict[str, object]:
    workspace_path = Path(workspace).expanduser().resolve()
    destination = workspace_path / "skill-snapshot"
    metadata_path = workspace_path / "snapshot.json"
    if not destination.is_dir() or not metadata_path.is_file():
        raise ValueError(f"快照或元数据不存在：{destination}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"快照元数据无效：{metadata_path}") from exc
    if not isinstance(metadata, dict):
        raise ValueError(f"快照元数据必须是对象：{metadata_path}")
    recorded_path = Path(str(metadata.get("snapshot", ""))).expanduser().resolve()
    if recorded_path != destination:
        raise ValueError("snapshot.json 指向的快照路径与当前 workspace 不一致")
    files = _included_files(destination)
    digest = _digest(destination, files)
    if metadata.get("files") != len(files) or metadata.get("sha256") != digest:
        raise ValueError("skill-snapshot 内容已变化，拒绝作为整改基线")
    return {
        "snapshot": str(destination),
        "files": len(files),
        "sha256": digest,
    }


def snapshot_skill(
    skill_path: str | Path,
    workspace: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    source = Path(skill_path).expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Skill 目录不存在：{source}")
    name = _skill_name(source)
    workspace_path = (
        Path(workspace).expanduser().resolve()
        if workspace is not None
        else default_workspace(source, name)
    )
    destination = workspace_path / "skill-snapshot"
    metadata = workspace_path / "snapshot.json"
    snapshot_exists = destination.exists() or metadata.exists()
    # dry-run 只用于预览和取摘要；整改期间快照必然已存在，不能因此报错。
    if snapshot_exists and not dry_run:
        raise FileExistsError(f"快照已存在，拒绝覆盖：{destination}")

    files = _included_files(source)
    payload: dict[str, object] = {
        "status": "dry-run" if dry_run else "created",
        "source": str(source),
        "snapshot": str(destination),
        "files": len(files),
        "sha256": _digest(source, files),
    }
    if dry_run:
        payload["snapshot_exists"] = snapshot_exists
        return payload

    workspace_path.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    for path in files:
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    metadata.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="整改前创建不再修改的旧版 Skill 快照")
    parser.add_argument("skill_path", help="已有 Skill 目录")
    parser.add_argument(
        "--workspace",
        help="工作目录；Skill 位于 skills 扫描目录时，默认使用其同级的 skill-workspaces",
    )
    parser.add_argument("--dry-run", action="store_true", help="只显示计划，不写入")
    parser.add_argument("--json", action="store_true", dest="as_json", help="输出 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = snapshot_skill(args.skill_path, args.workspace, args.dry_run)
    except (ValueError, FileExistsError, KeyError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        status = "仅预览" if payload["status"] == "dry-run" else "已创建"
        print(f"{status}：{payload['snapshot']}")
        print(f"文件数：{payload['files']}")
        print(f"SHA-256：{payload['sha256']}")
        if payload.get("snapshot_exists"):
            print("注意：快照已存在，正式运行会拒绝覆盖")
    return 0


if __name__ == "__main__":
    sys.exit(main())
