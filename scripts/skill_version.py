#!/usr/bin/env python3
"""Read and update the optional metadata.version field in a Skill frontmatter."""

from __future__ import annotations

import re
from pathlib import Path


SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(?P<yaml>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL
)
TOP_LEVEL_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(?:[ \t]*(.*))?$")
VERSION_KEY_RE = re.compile(r"^(?P<indent> +)version:[ \t]*(?P<value>.*)$")
# 按行读取版本的发版和更新脚本用的就是这两条规则；能被它们读到的写法才算有效。
LINE_NAME_RE = re.compile(r'^name:\s*"?([\w-]+)"?\s*$', re.MULTILINE)
LINE_VERSION_RE = re.compile(r'^\s+version:\s*"?(\d+\.\d+\.\d+)"?\s*$', re.MULTILINE)
STANDARD_FORM = '请写成多行映射：metadata 下一行 version: "1.2.3"，用双引号或不加引号，行尾不加注释'


def is_semver(value: str) -> bool:
    return bool(SEMVER_RE.fullmatch(value))


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _top_level_key(line: str) -> tuple[str, str] | None:
    match = TOP_LEVEL_KEY_RE.match(line)
    if not match:
        return None
    return match.group(1), (match.group(2) or "").strip()


def _metadata_version_line(
    lines: list[str],
) -> tuple[int | None, int | None, int | None, str]:
    metadata_indices = [
        index
        for index, line in enumerate(lines)
        if (parsed := _top_level_key(line)) is not None and parsed[0] == "metadata"
    ]
    if len(metadata_indices) > 1:
        raise ValueError("frontmatter 中出现了多个 metadata 字段")
    if not metadata_indices:
        return None, None, None, "  "

    metadata_index = metadata_indices[0]
    _, inline_value = _top_level_key(lines[metadata_index]) or ("metadata", "")
    if inline_value and not inline_value.startswith("#"):
        if inline_value == "{}":
            return metadata_index, metadata_index + 1, None, "  "
        if re.search(r"(?:\{|,)\s*version\s*:", inline_value):
            raise ValueError(f"metadata.version 不能写在单行映射里；{STANDARD_FORM}")
        # 其他单行映射是合法 YAML，但安全改写需要完整解析器，不猜它的结构。
        return metadata_index, metadata_index + 1, None, "  "

    end_index = len(lines)
    for index in range(metadata_index + 1, len(lines)):
        if _top_level_key(lines[index]) is not None:
            end_index = index
            break

    # metadata 的直接子项沿用第一个子项的缩进，更深的缩进属于嵌套字段。
    child_indent = None
    version_indices = []
    for index in range(metadata_index + 1, end_index):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = line[: len(line) - len(line.lstrip(" "))]
        if child_indent is None:
            child_indent = indent
        match = VERSION_KEY_RE.match(line)
        if match and match.group("indent") == child_indent:
            version_indices.append(index)
    if len(version_indices) > 1:
        raise ValueError("metadata 中出现了多个 version 字段")
    return (
        metadata_index,
        end_index,
        version_indices[0] if version_indices else None,
        child_indent or "  ",
    )


def _decode_version_scalar(line: str) -> str:
    match = VERSION_KEY_RE.match(line)
    if not match:
        raise ValueError("metadata.version 必须是字符串")

    value = match.group("value").strip()
    if value.startswith("'"):
        raise ValueError(f"metadata.version 不能用单引号；{STANDARD_FORM}")
    if re.search(r"[ \t]#", value):
        raise ValueError(f"metadata.version 行尾不能加注释；{STANDARD_FORM}")
    if value.startswith('"'):
        quoted = re.fullmatch(r'"([^"\\]*)"', value)
        if not quoted:
            raise ValueError(f"metadata.version 必须是简单的字符串；{STANDARD_FORM}")
        return quoted.group(1)
    return value


def read_skill_version(raw: str) -> str | None:
    match = FRONTMATTER_RE.match(raw)
    if not match:
        raise ValueError("SKILL.md 缺少有效的 YAML frontmatter")

    lines = _lines(match.group("yaml"))
    _, _, version_index, _ = _metadata_version_line(lines)
    if version_index is None:
        return None
    value = _decode_version_scalar(lines[version_index])
    if not is_semver(value):
        raise ValueError("metadata.version 必须使用 MAJOR.MINOR.PATCH 格式，例如 1.2.3")
    return value


def line_reader_problem(raw: str, name: str, version: str) -> str | None:
    """检查按行读取的发版和更新脚本能否读到与 frontmatter 一致的名称和版本。"""
    name_match = LINE_NAME_RE.search(raw)
    if not name_match or name_match.group(1) != name:
        return "按行读取的发版和更新脚本读不到 name；请写成 name: skill-name，用双引号或不加引号"
    version_match = LINE_VERSION_RE.search(raw)
    if not version_match:
        return f"按行读取的发版和更新脚本读不到 metadata.version；{STANDARD_FORM}"
    if version_match.group(1) != version:
        return (
            f"按行读取的发版和更新脚本会读到 {version_match.group(1)}，而不是 metadata.version 的 {version}；"
            "把 metadata.version 放在 frontmatter 中第一个缩进的 version 字段"
        )
    return None


def update_skill_version(raw: str, version: str, *, require_absent: bool) -> str:
    if not is_semver(version):
        raise ValueError("版本号必须使用 MAJOR.MINOR.PATCH 格式，例如 1.2.3")

    match = FRONTMATTER_RE.match(raw)
    if not match:
        raise ValueError("SKILL.md 缺少有效的 YAML frontmatter")

    current = read_skill_version(raw)
    if require_absent and current is not None:
        raise ValueError(f"Skill 已有版本 {current}；首次设置操作不会覆盖已有版本")
    if not require_absent and current is None:
        raise ValueError("Skill 尚无 metadata.version；请先使用 --initial 设置初始版本")

    yaml_text = match.group("yaml")
    lines = _lines(yaml_text)
    metadata_index, metadata_end, version_index, child_indent = _metadata_version_line(lines)

    newline = "\r\n" if "\r\n" in raw else "\n"
    if metadata_index is None:
        lines.extend(["metadata:", f'  version: "{version}"'])
    elif version_index is not None:
        lines[version_index] = f'{child_indent}version: "{version}"'
    else:
        _, inline_value = _top_level_key(lines[metadata_index]) or ("metadata", "")
        if inline_value == "{}":
            lines[metadata_index] = "metadata:"
        elif inline_value and not inline_value.startswith("#"):
            raise ValueError("无法安全扩展 metadata 内联值；请先改成多行 YAML 映射")
        insert_at = metadata_end if metadata_end is not None else len(lines)
        lines[insert_at:insert_at] = [f'{child_indent}version: "{version}"']

    updated_yaml = newline.join(lines)
    return raw[: match.start("yaml")] + updated_yaml + raw[match.end("yaml") :]
