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
VERSION_KEY_RE = re.compile(r"^  version:[ \t]*(.*)$")


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
) -> tuple[int | None, int | None, int | None]:
    metadata_indices = [
        index
        for index, line in enumerate(lines)
        if (parsed := _top_level_key(line)) is not None and parsed[0] == "metadata"
    ]
    if len(metadata_indices) > 1:
        raise ValueError("frontmatter 中出现了多个 metadata 字段")
    if not metadata_indices:
        return None, None, None

    metadata_index = metadata_indices[0]
    _, inline_value = _top_level_key(lines[metadata_index]) or ("metadata", "")
    if inline_value and not inline_value.startswith("#"):
        if inline_value == "{}":
            return metadata_index, metadata_index + 1, None
        # Inline YAML is valid, but changing it safely needs a YAML parser. Do not
        # guess its structure or rewrite unrelated metadata.
        if inline_value.startswith("{") and re.search(
            r"(?:\{|,)\s*version\s*:", inline_value
        ):
            version_match = re.search(
                r"(?:\{|,)\s*version\s*:\s*(['\"]?)([^,}\s'\"]+)\1\s*(?=[,}])",
                inline_value,
            )
            if not version_match:
                raise ValueError("metadata.version 不是有效的 SemVer 字符串")
            return metadata_index, metadata_index + 1, -1
        return metadata_index, metadata_index + 1, None

    end_index = len(lines)
    for index in range(metadata_index + 1, len(lines)):
        if _top_level_key(lines[index]) is not None:
            end_index = index
            break

    version_indices = [
        index
        for index in range(metadata_index + 1, end_index)
        if VERSION_KEY_RE.match(lines[index])
    ]
    if len(version_indices) > 1:
        raise ValueError("metadata 中出现了多个 version 字段")
    return metadata_index, end_index, version_indices[0] if version_indices else None


def _decode_version_scalar(line: str) -> str:
    match = VERSION_KEY_RE.match(line)
    if not match:
        raise ValueError("metadata.version 必须是字符串")

    value = match.group(1).strip()
    if value.startswith('"'):
        quoted = re.fullmatch(r'"([^"\\]*)"(?:[ \t]+#.*)?', value)
        if not quoted:
            raise ValueError("metadata.version 必须是简单的 YAML 字符串")
        return quoted.group(1)
    if value.startswith("'"):
        quoted = re.fullmatch(r"'([^']*)'(?:[ \t]+#.*)?", value)
        if not quoted:
            raise ValueError("metadata.version 必须是简单的 YAML 字符串")
        return quoted.group(1)

    return re.sub(r"[ \t]+#.*$", "", value).strip()


def read_skill_version(raw: str) -> str | None:
    match = FRONTMATTER_RE.match(raw)
    if not match:
        raise ValueError("SKILL.md 缺少有效的 YAML frontmatter")

    lines = _lines(match.group("yaml"))
    metadata_index, _, version_index = _metadata_version_line(lines)
    if version_index is None:
        return None
    if version_index == -1:
        if metadata_index is None:
            raise ValueError("metadata.version 无法解析")
        inline = _top_level_key(lines[metadata_index])[1]
        inline_match = re.search(
            r"(?:\{|,)\s*version\s*:\s*(['\"]?)([^,}\s'\"]+)\1\s*(?=[,}])",
            inline,
        )
        value = inline_match.group(2) if inline_match else ""
    else:
        value = _decode_version_scalar(lines[version_index])

    if not is_semver(value):
        raise ValueError("metadata.version 必须使用 MAJOR.MINOR.PATCH 格式，例如 1.2.3")
    return value


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
    metadata_index, metadata_end, version_index = _metadata_version_line(lines)

    newline = "\r\n" if "\r\n" in raw else "\n"
    if metadata_index is None:
        lines.extend(["metadata:", f'  version: "{version}"'])
    elif version_index == -1:
        raise ValueError("无法安全修改 metadata 内联映射；请先改成多行 YAML 映射")
    elif version_index is not None:
        old_line = lines[version_index]
        comment_match = re.search(r"[ \t]+(#.*)$", old_line)
        comment = f" {comment_match.group(1)}" if comment_match else ""
        lines[version_index] = f'  version: "{version}"{comment}'
    else:
        _, inline_value = _top_level_key(lines[metadata_index]) or ("metadata", "")
        if inline_value == "{}":
            lines[metadata_index] = "metadata:"
        elif inline_value and not inline_value.startswith("#"):
            raise ValueError("无法安全扩展 metadata 内联值；请先改成多行 YAML 映射")
        insert_at = metadata_end if metadata_end is not None else len(lines)
        lines[insert_at:insert_at] = [f'  version: "{version}"']

    updated_yaml = newline.join(lines)
    return raw[: match.start("yaml")] + updated_yaml + raw[match.end("yaml") :]
