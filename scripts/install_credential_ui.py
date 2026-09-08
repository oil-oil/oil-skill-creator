#!/usr/bin/env python3
"""将固定凭据组件装入目标 Skill，只生成非敏感声明。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "credential-ui"
IGNORED = {"node_modules", "__pycache__", ".git", ".DS_Store"}


def component_files() -> dict[str, bytes]:
    files = {}
    for item in sorted(TEMPLATE.rglob("*")):
        relative = item.relative_to(TEMPLATE)
        if any(part in IGNORED for part in relative.parts):
            continue
        if item.is_symlink():
            raise ValueError("组件模板不接受符号链接")
        if item.is_file():
            files[relative.as_posix()] = item.read_bytes()
    if "src/server.ts" not in files or "public/app.js" not in files:
        raise ValueError("组件模板不完整")
    return files


def install_credential_ui(
    skill_path: str | Path,
    skill_id: str,
    label: str,
    credential: str,
    title: str = "输入密钥",
    placeholder: str = "粘贴 API Key",
    dry_run: bool = False,
) -> dict:
    if not re.fullmatch(r"[a-z0-9-]{1,80}", skill_id):
        raise ValueError("Skill 标识不合法")
    if not re.fullmatch(r"[a-z0-9][a-z0-9/_.-]{0,150}", credential):
        raise ValueError("凭据引用不合法")
    for value, limit in ((label, 120), (title, 80), (placeholder, 80)):
        if not value.strip() or len(value) > limit:
            raise ValueError("页面文案为空或过长")
    # 先规范化用户指定的根路径，兼容系统临时目录等合法路径别名；
    # 随后拒绝组件安装位置中的链接，避免写入被重定向。
    root = Path(skill_path).expanduser().resolve()
    if not (root / "SKILL.md").is_file():
        raise ValueError("目标必须是已有 Skill 目录")
    target = root / "scripts" / "credential-ui"
    for item in (target, *target.parents):
        if item.is_symlink():
            raise ValueError("目标路径不接受符号链接")
    files = component_files()
    manifest = {
        "version": 1, "id": skill_id, "label": label, "credential": credential,
        "ui": {"title": title, "placeholder": placeholder},
    }
    manifest_name = "manifests/default.json"
    files[manifest_name] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items() if name != manifest_name}
    record = {"version": 1, "files": hashes}
    if target.exists():
        try:
            existing = json.loads((target / manifest_name).read_text(encoding="utf-8"))
            saved = json.loads((target / "component.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise FileExistsError("已有目录不是可识别的凭据组件，未覆盖") from exc
        if existing.get("id") != skill_id or existing.get("credential") != credential or saved != record:
            raise FileExistsError("已有组件的身份或版本不同，未覆盖；请检查后使用独立目录")
        for name, digest in hashes.items():
            item = target / name
            if item.is_symlink() or not item.is_file() or hashlib.sha256(item.read_bytes()).hexdigest() != digest:
                raise FileExistsError("已有组件源码发生变化，未覆盖")
        return {"status": "unchanged", "directory": str(target), "manifest": str(target / manifest_name)}
    result = {"status": "preview" if dry_run else "installed", "directory": str(target), "manifest": str(target / manifest_name)}
    if dry_run:
        return result
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".credential-ui-", dir=target.parent))
    try:
        for name, data in files.items():
            output = temporary / name
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
        (temporary / "component.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        if target.exists():
            raise FileExistsError("目标目录刚被创建，未覆盖")
        temporary.rename(target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return result


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        print("需要 Python 3.10 或更新版本", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description="向现有 Skill 接入可复用的凭据输入页；不读取或写入密钥")
    parser.add_argument("skill_path", help="已存在且包含 SKILL.md 的目标目录")
    parser.add_argument("--id", required=True, dest="skill_id")
    parser.add_argument("--label", required=True, help="页面显示的服务用途")
    parser.add_argument("--credential", required=True, help="不含密钥的稳定引用")
    parser.add_argument("--title", default="输入密钥")
    parser.add_argument("--placeholder", default="粘贴 API Key")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = install_credential_ui(**vars(args))
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
