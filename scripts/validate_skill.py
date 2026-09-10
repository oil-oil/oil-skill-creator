#!/usr/bin/env python3
"""Agent Skill 产品质量静态检查。

只使用 Python 标准库，确保同一套首次使用检查可以在 macOS、Windows
和 Linux 上运行。
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

try:
    from .evaluation_common import validate_eval_set
except ImportError:
    from evaluation_common import validate_eval_set


ALLOWED_FRONTMATTER_KEYS = {
    "name",
    "description",
    "license",
    "allowed-tools",
    "metadata",
    "compatibility",
}
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(?P<yaml>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL
)
TOP_LEVEL_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(?:[ \t]*(.*))?$")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
RESOURCE_CODE_RE = re.compile(
    r"`((?:scripts|references|assets|tests)/[^`\s]+)`"
)
HISTORY_HEADING_RE = re.compile(
    r"^\s{0,3}#{1,6}\s*(?:changelog|change\s+log|更新记录|修改记录|修复记录|版本历史)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
HISTORY_SENTENCE_RE = re.compile(
    r"(?:本次(?:修改|修复|更新)(?:了|内容|包括)|上一次任务|上个(?:案例|任务)|previous\s+task\s+fix)",
    re.IGNORECASE,
)
PERSONAL_PATH_PATTERNS = (
    re.compile(r"(?<![A-Za-z]:)/Users/(?!Shared(?:/|$))[A-Za-z0-9._-]+/"),
    re.compile(r"/home/[A-Za-z0-9._-]+/"),
    re.compile(r"/root(?:/|$)"),
    re.compile(
        r"[A-Za-z]:[\\/]+Users[\\/]+"
        r"(?!(?:Public|Default(?: User)?|All Users)(?:[\\/]+|$))"
        r"[A-Za-z0-9._ -]+[\\/]+",
        re.IGNORECASE,
    ),
)
SECRET_PATTERNS = (
    ("sk-prefixed API key", re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("GitLab token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("npm token", re.compile(r"\bnpm_[A-Za-z0-9]{30,}\b")),
    (
        "private key block",
        re.compile(
            r"-----BEGIN (?:(?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY|"
            r"PGP PRIVATE KEY BLOCK)-----"
        ),
    ),
)
SENSITIVE_KEY_NAME_PATTERN = (
    r"(?:[A-Za-z0-9]+[_-])*"
    r"(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"service[_-]?role[_-]?key|token|password|passwd|secret)"
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"""(?im)(?:^[ \t]*|[{,][ \t]*)(?:export[ \t]+)?[\"']?
    (?P<name>"""
    + SENSITIVE_KEY_NAME_PATTERN
    + r""")
    [\"']?[ \t]*[:=][ \t]*
    (?P<quote>[\"']?)(?P<value>[A-Za-z0-9_./+=:@-]{16,})(?P=quote)
    (?=[ \t]*[,};]?[ \t]*(?:$|\r?\n))
    """,
    re.VERBOSE,
)
SECRET_BLOCK_ASSIGNMENT_RE = re.compile(
    r"(?im)^(?P<indent>[ \t]*)[\"']?(?P<name>"
    + SENSITIVE_KEY_NAME_PATTERN
    + r")[\"']?[ \t]*:[ \t]*[>|][+-]?[ \t]*(?:#[^\r\n]*)?\r?\n"
    + r"(?P<value>(?:(?P=indent)[ \t]+[^\r\n]*(?:\r?\n|$))+)",
)
SECRET_PLACEHOLDER_MARKERS = (
    "example",
    "sample",
    "placeholder",
    "replace",
    "your_",
    "your-",
    "dummy",
    "fake",
    "xxxx",
)
SENSITIVE_FILENAMES = {
    ".git-credentials",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials.json",
    "secrets.json",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
}
HOST_BRAND_TEXT_PATTERNS = (
    re.compile(
        r"\b(?:codex|claude(?:\s+code)?|chatgpt|openai|anthropic|windsurf|gemini)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bCursor\b"),
)
HOST_BRAND_PATH_RE = re.compile(
    r"(?:^|[/._-])(?:codex|claude|cursor|chatgpt|openai|anthropic|windsurf|gemini)(?:[/._-]|$)",
    re.IGNORECASE,
)
TEXT_SUFFIXES = {
    ".asc",
    ".cfg",
    ".conf",
    ".csv",
    ".env",
    ".go",
    ".ini",
    ".java",
    ".md",
    ".py",
    ".json",
    ".key",
    ".kt",
    ".pem",
    ".properties",
    ".rb",
    ".rs",
    ".yaml",
    ".yml",
    ".toml",
    ".txt",
    ".sh",
    ".swift",
    ".ps1",
    ".js",
    ".ts",
    ".xml",
}
TEXT_FILENAMES = {"Dockerfile", "Makefile"}
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "dist"}


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    code: str
    message: str
    path: str | None = None
    line: int | None = None


@dataclass(frozen=True)
class MarkdownBlock:
    path: Path
    line: int
    text: str
    normalized: str


@dataclass
class AuditReport:
    skill_path: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    metrics: dict[str, int] = field(default_factory=dict)

    def add(
        self,
        severity: str,
        code: str,
        message: str,
        path: str | None = None,
        line: int | None = None,
    ) -> None:
        self.diagnostics.append(Diagnostic(severity, code, message, path, line))

    @property
    def errors(self) -> list[Diagnostic]:
        return [item for item in self.diagnostics if item.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [item for item in self.diagnostics if item.severity == "warning"]

    def passed(self, strict: bool = False) -> bool:
        return not self.errors and (not strict or not self.warnings)

    def to_dict(self, strict: bool = False) -> dict[str, object]:
        return {
            "skill_path": self.skill_path,
            "passed": self.passed(strict),
            "strict": strict,
            "summary": {
                "errors": len(self.errors),
                "warnings": len(self.warnings),
            },
            "metrics": self.metrics,
            "diagnostics": [asdict(item) for item in self.diagnostics],
        }


def _strip_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """解析 Skill frontmatter 使用的顶层标量字段。

    这里不实现通用 YAML，只支持校验所需的普通、引号、折叠和字面量顶层标量。
    """

    match = FRONTMATTER_RE.match(raw)
    if not match:
        raise ValueError("SKILL.md 缺少有效的 YAML frontmatter")

    lines = match.group("yaml").splitlines()
    result: dict[str, str] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line[:1].isspace():
            index += 1
            continue

        key_match = TOP_LEVEL_KEY_RE.match(line)
        if not key_match:
            index += 1
            continue

        key = key_match.group(1)
        value = (key_match.group(2) or "").strip()
        if value in {">", ">-", ">+", "|", "|-", "|+"}:
            folded = value.startswith(">")
            block: list[str] = []
            index += 1
            while index < len(lines):
                next_line = lines[index]
                if next_line and not next_line[:1].isspace() and TOP_LEVEL_KEY_RE.match(next_line):
                    break
                block.append(next_line.strip())
                index += 1
            if folded:
                result[key] = " ".join(part for part in block if part).strip()
            else:
                result[key] = "\n".join(block).strip()
            continue

        result[key] = _strip_scalar(value)
        index += 1

    return result, raw[match.end() :]


def _relative(skill_path: Path, path: Path) -> str:
    try:
        return path.relative_to(skill_path).as_posix()
    except ValueError:
        return str(path)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _iter_text_files(skill_path: Path) -> Iterable[Path]:
    for path in sorted(skill_path.rglob("*")):
        is_env_file = path.name.lower().startswith(".env")
        if not path.is_file() or (
            path.suffix.lower() not in TEXT_SUFFIXES
            and path.name not in TEXT_FILENAMES
            and not is_env_file
        ):
            continue
        try:
            relative_parts = path.relative_to(skill_path).parts
        except ValueError:
            continue
        if any(part in SKIP_DIRS for part in relative_parts):
            continue
        yield path


def _read_text(path: Path, report: AuditReport, skill_path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        report.add(
            "error",
            "text.encoding",
            "文本文件不是 UTF-8 编码",
            _relative(skill_path, path),
        )
    except OSError as exc:
        report.add(
            "error",
            "file.read",
            f"无法读取文件：{exc}",
            _relative(skill_path, path),
        )
    return None


def _normalize_block(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"[\W_]+", "", text.lower(), flags=re.UNICODE)


def _markdown_blocks(
    path: Path,
    text: str,
    min_normalized_chars: int = 0,
    split_list_items: bool = False,
) -> list[MarkdownBlock]:
    blocks: list[MarkdownBlock] = []
    current: list[str] = []
    start_line = 1
    in_fence = False

    def flush() -> None:
        nonlocal current
        if not current:
            return
        raw = "\n".join(current).strip()
        normalized = _normalize_block(raw)
        if len(normalized) >= min_normalized_chars:
            blocks.append(MarkdownBlock(path, start_line, raw, normalized))
        current = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        if re.match(r"^\s*(```|~~~)", line):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if re.match(r"^\s{0,3}#{1,6}\s+", line):
            flush()
            continue
        if not line.strip():
            flush()
            continue
        if split_list_items and re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line):
            flush()
        if not current:
            start_line = line_number
        current.append(line)
    flush()
    return blocks


def _check_readability(
    body: str, report: AuditReport, weak_model: bool
) -> None:
    lines = body.splitlines()
    heading_matches = [
        (index, len(match.group(1)))
        for index, line in enumerate(lines, start=1)
        if (match := re.match(r"^\s{0,3}(#{1,6})\s+", line))
    ]
    max_heading_depth = max((level for _, level in heading_matches), default=0)
    boundaries = [line for line, _ in heading_matches] + [len(lines) + 1]
    max_section_lines = max(
        (boundaries[index + 1] - boundaries[index] - 1 for index in range(len(boundaries) - 1)),
        default=len(lines),
    )
    blocks = _markdown_blocks(Path("SKILL.md"), body, split_list_items=True)
    max_paragraph_chars = max((len(block.normalized) for block in blocks), default=0)
    list_depths: list[int] = []
    for line in lines:
        match = re.match(r"^(\s*)(?:[-*+]|\d+[.)])\s+", line)
        if match:
            indent = len(match.group(1).expandtabs(4))
            list_depths.append(1 + indent // 2)
    max_list_depth = max(list_depths, default=0)

    report.metrics.update(
        {
            "max_heading_depth": max_heading_depth,
            "max_section_lines": max_section_lines,
            "max_paragraph_chars": max_paragraph_chars,
            "max_list_depth": max_list_depth,
            "weak_model_profile": int(weak_model),
        }
    )

    limits = {
        "lines": 300 if weak_model else 500,
        "section": 70 if weak_model else 120,
        "paragraph": 450 if weak_model else 900,
        "heading": 3 if weak_model else 4,
        "list": 3 if weak_model else 4,
    }
    profile = "弱模型门槛" if weak_model else "默认门槛"
    if len(lines) > limits["lines"]:
        report.add(
            "warning",
            "readability.skill-too-long",
            f"SKILL.md 正文为 {len(lines)} 行，超过{profile} {limits['lines']} 行；将只在特定阶段使用的细节移到 references",
            "SKILL.md",
        )
    if max_section_lines > limits["section"]:
        report.add(
            "warning",
            "readability.section-too-long",
            f"最长章节连续 {max_section_lines} 行，超过{profile} {limits['section']} 行；增加局部标题，或将阶段细节移到 references",
            "SKILL.md",
        )
    if max_paragraph_chars > limits["paragraph"]:
        report.add(
            "warning",
            "readability.long-paragraph",
            f"最长段落约 {max_paragraph_chars} 个有效字符，超过{profile} {limits['paragraph']}；拆成单动作指令",
            "SKILL.md",
        )
    if max_heading_depth > limits["heading"]:
        report.add(
            "warning",
            "readability.heading-depth",
            f"标题深度达到 {max_heading_depth}，超过{profile} {limits['heading']}；减少层级跳转",
            "SKILL.md",
        )
    if max_list_depth > limits["list"]:
        report.add(
            "warning",
            "readability.list-depth",
            f"列表嵌套达到 {max_list_depth} 层，超过{profile} {limits['list']}；改为顺序步骤或局部分支",
            "SKILL.md",
        )


def _local_markdown_targets(
    skill_path: Path, source: Path, text: str
) -> set[Path]:
    targets: set[Path] = set()
    raw_targets: list[tuple[str, bool]] = []
    for match in MARKDOWN_LINK_RE.finditer(text):
        raw_targets.append((match.group(1).strip().strip("<>"), False))
    for match in RESOURCE_CODE_RE.finditer(text):
        raw_targets.append((match.group(1).rstrip(".,;:，。；："), True))

    for target, root_relative in raw_targets:
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        clean = target.split("#", 1)[0].split("?", 1)[0]
        if not clean.lower().endswith(".md"):
            continue
        candidate = (skill_path / clean) if root_relative else (source.parent / clean)
        resolved = candidate.resolve()
        try:
            resolved.relative_to(skill_path.resolve())
        except ValueError:
            continue
        if resolved.is_file():
            targets.add(resolved)
    return targets


def _check_information_architecture(
    skill_path: Path,
    skill_md: Path,
    body: str,
    markdown_texts: dict[Path, str],
    report: AuditReport,
) -> None:
    references_root = skill_path / "references"
    reference_files = {
        path.resolve()
        for path in references_root.rglob("*.md")
        if path.is_file()
    } if references_root.is_dir() else set()

    reachable: set[Path] = {skill_md.resolve()}
    queue = [skill_md.resolve()]
    source_texts = dict(markdown_texts)
    source_texts[skill_md.resolve()] = body
    while queue:
        source = queue.pop(0)
        source_text = source_texts.get(source, "")
        for target in _local_markdown_targets(skill_path, source, source_text):
            if target not in reachable:
                reachable.add(target)
                queue.append(target)

    unreachable = sorted(reference_files - reachable, key=lambda item: item.as_posix())
    for item in unreachable:
        report.add(
            "warning",
            "layer.reference-unreachable",
            "参考资料无法从 SKILL.md 到达；补充读取时机或删除该文件",
            _relative(skill_path, item),
        )

    for item in sorted(skill_path.glob("*.md")):
        if item.name not in {"SKILL.md", "README.md"}:
            report.add(
                "warning",
                "layer.root-markdown",
                "根目录 Markdown 应移入 references，或说明其必须位于根目录的产品职责",
                item.name,
            )

    reference_chars = 0
    for item in reference_files:
        text = markdown_texts.get(item, "")
        reference_chars += len(text)
        if len(text.splitlines()) > 300 and not re.search(
            r"^#{1,3}\s+(?:目录|table of contents|contents)\s*$",
            text,
            re.IGNORECASE | re.MULTILINE,
        ):
            report.add(
                "warning",
                "layer.large-reference-no-toc",
                "参考资料超过 300 行但没有目录",
                _relative(skill_path, item),
            )

    report.metrics.update(
        {
            "reference_files": len(reference_files),
            "unreachable_reference_files": len(unreachable),
            "reference_chars": reference_chars,
            "estimated_reference_tokens": round(reference_chars / 3),
            "markdown_document_chars": sum(len(text) for text in markdown_texts.values()),
        }
    )


def _check_duplicate_markdown(
    skill_path: Path,
    skill_body: str,
    markdown_texts: dict[Path, str],
    report: AuditReport,
) -> None:
    blocks: list[MarkdownBlock] = []
    for path, text in markdown_texts.items():
        content = skill_body if path.name == "SKILL.md" else text
        blocks.extend(_markdown_blocks(path, content, min_normalized_chars=40))

    exact_seen: dict[str, MarkdownBlock] = {}
    duplicate_pairs: set[tuple[str, int, str, int]] = set()
    exact_count = 0
    near_count = 0
    for block in blocks:
        previous = exact_seen.get(block.normalized)
        if previous is None:
            exact_seen[block.normalized] = block
            continue
        key = (previous.path.as_posix(), previous.line, block.path.as_posix(), block.line)
        duplicate_pairs.add(key)
        exact_count += 1
        report.add(
            "warning",
            "content.duplicate-exact",
            f"与 {_relative(skill_path, previous.path)}:{previous.line} 重复；只保留一处完整规则，其余位置改为链接",
            _relative(skill_path, block.path),
            block.line,
        )

    near_reports = 0
    for index, left in enumerate(blocks):
        for right in blocks[index + 1 :]:
            if left.path == right.path or left.normalized == right.normalized:
                continue
            if min(len(left.normalized), len(right.normalized)) < 160:
                continue
            length_ratio = len(left.normalized) / len(right.normalized)
            if not 0.8 <= length_ratio <= 1.25:
                continue
            matcher = difflib.SequenceMatcher(
                None, left.normalized, right.normalized, autojunk=False
            )
            if matcher.quick_ratio() < 0.9 or matcher.ratio() < 0.9:
                continue
            pair_key = (left.path.as_posix(), left.line, right.path.as_posix(), right.line)
            if pair_key in duplicate_pairs:
                continue
            near_count += 1
            if near_reports < 10:
                report.add(
                    "warning",
                    "content.duplicate-near",
                    f"与 {_relative(skill_path, left.path)}:{left.line} 高度相似；合并内容，并从另一处链接过去",
                    _relative(skill_path, right.path),
                    right.line,
                )
                near_reports += 1

    report.metrics["duplicate_exact_blocks"] = exact_count
    report.metrics["duplicate_near_blocks"] = near_count


def _check_markdown_content(
    skill_path: Path,
    skill_body: str,
    markdown_texts: dict[Path, str],
    report: AuditReport,
) -> None:
    for path, raw_text in markdown_texts.items():
        text = skill_body if path.name == "SKILL.md" else raw_text
        relative = _relative(skill_path, path)
        history_lines = [
            line
            for line in text.splitlines()
            if HISTORY_SENTENCE_RE.search(line)
            and not re.search(
                r"不要|不得|禁止|避免|不能|do not|never", line, re.IGNORECASE
            )
        ]
        if HISTORY_HEADING_RE.search(text) or history_lines:
            report.add(
                "error",
                "content.history",
                "正式文档包含修改记录或单次修复叙述；只保留当前通用规则",
                relative,
            )


def _is_sensitive_filename(path: Path) -> bool:
    name = path.name.lower()
    if name in SENSITIVE_FILENAMES:
        return True
    if name.startswith(".env"):
        return not any(marker in name for marker in ("example", "sample", "template"))
    return False


def _check_sensitive_content(
    skill_path: Path,
    text_cache: dict[Path, str],
    report: AuditReport,
) -> None:
    personal_paths = 0
    embedded_secrets = 0

    for path in sorted(skill_path.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        relative = path.relative_to(skill_path)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if _is_sensitive_filename(path):
            embedded_secrets += 1
            report.add(
                "error",
                "security.sensitive-file",
                "Skill 包含高风险凭据文件；改为系统凭据存储、环境变量或不含密钥的模板",
                relative.as_posix(),
            )

    for path, text in text_cache.items():
        relative = _relative(skill_path, path)
        for pattern in PERSONAL_PATH_PATTERNS:
            match = pattern.search(text)
            if match:
                personal_paths += 1
                report.add(
                    "error",
                    "content.personal-path",
                    f"文件包含具体用户目录：{match.group(0)}；改为配置参数、环境变量或平台目录解析",
                    relative,
                    _line_number(text, match.start()),
                )
                break

        for label, pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                embedded_secrets += 1
                report.add(
                    "error",
                    "security.embedded-secret",
                    f"发现疑似硬编码的 {label}",
                    relative,
                    _line_number(text, match.start()),
                )

        for match in SECRET_ASSIGNMENT_RE.finditer(text):
            value = match.group("value").lower()
            if any(marker in value for marker in SECRET_PLACEHOLDER_MARKERS):
                continue
            embedded_secrets += 1
            report.add(
                "error",
                "security.plaintext-secret",
                f"发现疑似明文凭据赋值：{match.group('name')}",
                relative,
                _line_number(text, match.start()),
            )

        for match in SECRET_BLOCK_ASSIGNMENT_RE.finditer(text):
            value = "".join(line.strip() for line in match.group("value").splitlines())
            lowered = value.lower()
            if len(value) < 16 or any(
                marker in lowered for marker in SECRET_PLACEHOLDER_MARKERS
            ):
                continue
            embedded_secrets += 1
            report.add(
                "error",
                "security.plaintext-secret",
                f"发现疑似 YAML 多行明文凭据：{match.group('name')}",
                relative,
                _line_number(text, match.start()),
            )

    report.metrics["personal_paths"] = personal_paths
    report.metrics["embedded_secrets"] = embedded_secrets


def _check_host_neutral(
    skill_path: Path,
    skill_body: str,
    markdown_texts: dict[Path, str],
    report: AuditReport,
) -> None:
    mentions = 0
    for path, raw_text in markdown_texts.items():
        text = skill_body if path.name == "SKILL.md" else raw_text
        for pattern in HOST_BRAND_TEXT_PATTERNS:
            for match in pattern.finditer(text):
                mentions += 1
                line = text[text.rfind('\n', 0, match.start()) + 1:text.find('\n', match.end()) if '\n' in text[match.end():] else len(text)]
                # 品牌作为示例、模型或服务名，不足以证明宿主耦合。
                if not re.search(r'只在|仅在|必须.{0,30}(?:Codex|Claude|ChatGPT|Cursor|Windsurf)|(?:require|only in|must use).{0,30}(?:Codex|Claude|ChatGPT|Cursor|Windsurf)|[~$]/?\.(?:codex|claude|cursor)/', line, re.I):
                    continue
                report.add(
                    "error",
                    "compatibility.host-coupling",
                    "发现宿主专用执行要求；核对是否应改为能力描述或明确声明宿主依赖",
                    _relative(skill_path, path),
                    _line_number(text, match.start()),
                )
    for path in sorted(skill_path.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(skill_path)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if relative.as_posix() == 'agents/openai.yaml' or relative.parts[0] == 'adapters' or (relative.parts[0] == 'assets' and path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.svg', '.ico'}):
            continue
        if HOST_BRAND_PATH_RE.search(relative.as_posix()):
            mentions += 1
            report.add(
                "error",
                "compatibility.host-specific-path",
                "通用 Skill 包含宿主品牌路径；将适配器移出通用包或明确改为宿主专用 Skill",
                relative.as_posix(),
            )
    report.metrics["host_coupling_mentions"] = mentions


def _check_resource_links(
    skill_path: Path, skill_md: Path, body: str, report: AuditReport
) -> None:
    targets: list[tuple[str, int, bool]] = []
    for match in MARKDOWN_LINK_RE.finditer(body):
        target = match.group(1).strip().strip("<>")
        targets.append((target, match.start(1), True))
    for match in RESOURCE_CODE_RE.finditer(body):
        targets.append(
            (match.group(1).rstrip(".,;:，。；："), match.start(1), False)
        )

    seen: set[str] = set()
    for target, offset, explicit_link in targets:
        seen_key = f"{target}:{explicit_link}"
        if seen_key in seen:
            continue
        seen.add(seen_key)
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        clean_target = target.split("#", 1)[0].split("?", 1)[0]
        if not clean_target:
            continue
        candidate = Path(clean_target)
        if candidate.is_absolute():
            report.add(
                "warning",
                "resource.absolute-link",
                f"本地资源使用了绝对路径：{target}",
                _relative(skill_path, skill_md),
                _line_number(body, offset),
            )
            continue
        resolved = (skill_md.parent / candidate).resolve()
        try:
            resolved.relative_to(skill_path.resolve())
        except ValueError:
            report.add(
                "error",
                "resource.outside-skill",
                f"资源引用越出了 Skill 目录：{target}",
                _relative(skill_path, skill_md),
                _line_number(body, offset),
            )
            continue
        if not resolved.exists():
            report.add(
                "error" if explicit_link else "warning",
                "resource.missing",
                (
                    f"明确链接的资源不存在：{target}"
                    if explicit_link
                    else f"代码片段引用的资源不在当前 Skill 中，请确认是否属于外部 Skill：{target}"
                ),
                _relative(skill_path, skill_md),
                _line_number(body, offset),
            )


def _normalize_heading(text: str) -> str:
    return re.sub(r"[\s`*_—–-]+", "", text).lower()


def _markdown_section(text: str, markers: tuple[str, ...]) -> str:
    headings = list(re.finditer(r"^#{1,4}\s+(.+?)\s*$", text, re.MULTILINE))
    normalized_markers = tuple(_normalize_heading(marker) for marker in markers)
    for index, heading in enumerate(headings):
        normalized = _normalize_heading(heading.group(1))
        if not any(marker in normalized for marker in normalized_markers):
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        return text[heading.end() : end]
    return ""


def _public_readme_path(skill_path: Path) -> Path:
    readme = skill_path / "README.md"
    if readme.is_file():
        return readme
    # 只在可证明的当前 Git 仓库边界中寻找共享首页。
    for parent in (skill_path, *skill_path.parents):
        if (parent / '.git').exists():
            candidate = parent / 'README.md'
            if candidate.is_file():
                text = candidate.read_text(encoding='utf-8')
                relative = (skill_path / 'SKILL.md').relative_to(parent).as_posix()
                if relative in text or skill_path.name in text:
                    return candidate
            break
    return readme


def _check_public_readme(skill_path: Path, report: AuditReport) -> None:
    readme = _public_readme_path(skill_path)
    if not readme.is_file():
        report.add("error", "readme.missing", "公开 Skill 缺少 README.md", "README.md")
        return

    text = _read_text(readme, report, skill_path)
    if text is None:
        return
    headings = [
        _normalize_heading(match.group(1))
        for match in re.finditer(r"^#{1,4}\s+(.+?)\s*$", text, re.MULTILINE)
    ]
    normalized_text = _normalize_heading(text)
    first_section = re.split(r"^##\s+", text, maxsplit=1, flags=re.MULTILINE)[0]
    intro_text = re.sub(r"[#*_`<>\[\]()\s-]+", "", first_section)
    required_groups = {
        "安装": ("安装", "install", "快速开始", "quickstart"),
        "使用": ("使用", "usage", "快速开始", "quickstart"),
        "配置": ("配置", "config", "setup", "初始化", "apikey", "无需额外配置"),
        "兼容性或依赖": (
            "兼容",
            "依赖",
            "运行环境",
            "compat",
            "requirement",
            "support",
            "macos",
            "windows",
            "linux",
        ),
    }
    if len(intro_text) < 30 and not any(
        any(marker in heading for marker in ("作用", "有什么用", "简介", "为什么", "overview", "what"))
        for heading in headings
    ):
        report.add(
            "error",
            "readme.value-missing",
            "README 开头没有清楚说明 Skill 的价值或作用",
            "README.md",
        )
    for label, markers in required_groups.items():
        if not any(marker in normalized_text for marker in markers):
            report.add(
                "error",
                "readme.section-missing",
                f"README 没有讲清“{label}”相关内容",
                "README.md",
            )

    if not any(
        any(marker in heading for marker in ("边界", "隐私", "数据", "权限", "privacy", "security"))
        for heading in headings
    ):
        report.add(
            "warning",
            "readme.boundary-missing",
            "README 没有单独说明适用边界、数据或权限",
            "README.md",
        )

    install_section = _markdown_section(
        text, ("安装", "install", "快速开始", "quickstart")
    )
    github_repository = re.search(
        r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?",
        install_section,
        re.IGNORECASE,
    )
    if github_repository:
        if not re.search(r"\b(?:agent|ai)\b|智能体|助手", install_section, re.IGNORECASE):
            report.add(
                "warning",
                "readme.install-agent-missing",
                "GitHub 安装说明没有提供把仓库地址交给 Agent 的入口",
                "README.md",
            )
        if not re.search(r"\bnpx\s+skills\s+add\b", install_section, re.IGNORECASE):
            report.add(
                "warning",
                "readme.install-command-missing",
                "GitHub 安装说明没有提供 npx skills add 命令",
                "README.md",
            )


def _check_eval_schema(skill_path: Path, name: str, report: AuditReport) -> None:
    eval_path = skill_path / "evals" / "evals.json"
    if not eval_path.is_file():
        report.metrics["eval_cases"] = 0
        return
    try:
        data = validate_eval_set(eval_path, name, allow_empty=True)
    except ValueError as exc:
        report.add("error", "evals.schema", str(exc), "evals/evals.json")
        report.metrics["eval_cases"] = 0
        return
    count = len(data["evals"])
    report.metrics["eval_cases"] = count
    if count == 0:
        report.add(
            "warning",
            "evals.empty",
            "evals/evals.json 为空；补充真实测试，或者删除没有使用的 evals 目录",
            "evals/evals.json",
        )


def audit_skill(
    skill_path: str | Path,
    public: bool = False,
    weak_model: bool = False,
    universal: bool = False,
) -> AuditReport:
    path = Path(skill_path).expanduser().resolve()
    report = AuditReport(str(path))
    if not path.exists():
        report.add("error", "skill.missing", "Skill 目录不存在")
        return report
    if not path.is_dir():
        report.add("error", "skill.not-directory", "目标不是目录")
        return report

    skill_md = path / "SKILL.md"
    if not skill_md.is_file():
        report.add("error", "skill-md.missing", "缺少 SKILL.md", "SKILL.md")
        return report

    raw = _read_text(skill_md, report, path)
    if raw is None:
        return report
    try:
        frontmatter, body = parse_frontmatter(raw)
    except ValueError as exc:
        report.add("error", "frontmatter.invalid", str(exc), "SKILL.md", 1)
        return report

    report.metrics.update(
        {
            "skill_md_lines": len(raw.splitlines()),
            "skill_md_chars": len(raw),
            "body_chars": len(body),
            "description_chars": len(frontmatter.get("description", "")),
            "estimated_body_tokens": max(1, round(len(body) / 3)),
        }
    )
    _check_readability(body, report, weak_model)

    unexpected = sorted(set(frontmatter) - ALLOWED_FRONTMATTER_KEYS)
    if unexpected:
        report.add(
            "error",
            "frontmatter.unexpected-key",
            "frontmatter 包含不支持的字段：" + ", ".join(unexpected),
            "SKILL.md",
        )

    name = frontmatter.get("name", "").strip()
    description = frontmatter.get("description", "").strip()
    if not name:
        report.add("error", "frontmatter.name-missing", "缺少 name", "SKILL.md")
    elif not NAME_RE.fullmatch(name):
        report.add(
            "error",
            "frontmatter.name-invalid",
            "name 必须使用 kebab-case，且不能连续或首尾使用连字符",
            "SKILL.md",
        )
    elif len(name) > 64:
        report.add("error", "frontmatter.name-too-long", "name 超过 64 个字符", "SKILL.md")
    elif path.name != name:
        report.add(
            "warning",
            "skill.directory-name",
            f"目录名“{path.name}”与 name“{name}”不一致",
            "SKILL.md",
        )

    if not description:
        report.add("error", "frontmatter.description-missing", "缺少 description", "SKILL.md")
    else:
        if len(description) > 1024:
            report.add(
                "error",
                "frontmatter.description-too-long",
                "description 超过 1024 个字符",
                "SKILL.md",
            )
        if "<" in description or ">" in description:
            report.add(
                "error",
                "frontmatter.description-angle-bracket",
                "description 不能包含尖括号",
                "SKILL.md",
            )
        lowered = description.lower()
        if not any(marker in lowered for marker in ("使用", "触发", "当用户", "use when", "when the user", "whenever")):
            report.add(
                "warning",
                "trigger.positive-boundary",
                "description 没有清楚说明何时触发",
                "SKILL.md",
            )
        if not any(marker in lowered for marker in ("不要", "不用于", "仅在", "仅当", "do not", "not for", "only when")):
            report.add(
                "warning",
                "trigger.negative-boundary",
                "description 没有清楚说明相似场景何时不要触发",
                "SKILL.md",
            )

    if re.search(r"\bTODO\b|__SKILL_[A-Z_]+__", raw):
        report.add(
            "warning",
            "content.placeholder",
            "SKILL.md 仍包含待填写占位符",
            "SKILL.md",
        )
    _check_resource_links(path, skill_md, body, report)
    _check_eval_schema(path, name, report)

    text_files = list(_iter_text_files(path))
    report.metrics["text_files"] = len(text_files)
    text_cache: dict[Path, str] = {}
    for text_path in text_files:
        text = _read_text(text_path, report, path)
        if text is None:
            continue
        text_cache[text_path.resolve()] = text

    _check_sensitive_content(path, text_cache, report)

    markdown_texts = {
        file_path: text
        for file_path, text in text_cache.items()
        if file_path.suffix.lower() == ".md"
    }
    _check_information_architecture(path, skill_md, body, markdown_texts, report)
    _check_duplicate_markdown(path, body, markdown_texts, report)
    _check_markdown_content(path, body, markdown_texts, report)
    if universal:
        _check_host_neutral(path, body, markdown_texts, report)
    else:
        report.metrics["host_coupling_mentions"] = 0

    readme = _public_readme_path(path)
    readme_text = ""
    if readme.is_file():
        readme_text = _read_text(readme, report, path) or ""
        if re.search(r"__SKILL_[A-Z_]+__|\bTODO\b", readme_text):
            report.add(
                "warning",
                "readme.placeholder",
                "README 仍包含待填写占位符",
                "README.md",
            )

    platform_specific = [
        _relative(path, item)
        for item in path.rglob("*")
        if item.is_file() and item.suffix.lower() in {".sh", ".swift", ".applescript"}
    ]
    if platform_specific and readme_text and not re.search(
        r"macOS|Windows|Linux|兼容|运行环境|平台", readme_text, re.IGNORECASE
    ):
        report.add(
            "warning",
            "compatibility.undeclared",
            "存在平台相关脚本，但 README 没有说明支持平台",
            "README.md",
        )
    report.metrics["platform_specific_files"] = len(platform_specific)

    if public:
        _check_public_readme(path, report)

    return report


def _print_human(report: AuditReport, strict: bool) -> None:
    for item in report.diagnostics:
        location = ""
        if item.path:
            location = f" {item.path}"
            if item.line:
                location += f":{item.line}"
        print(f"[{item.severity.upper()}] {item.code}{location} - {item.message}")
    summary = report.to_dict(strict)["summary"]
    status = "PASS" if report.passed(strict) else "FAIL"
    print(
        f"{status}：{summary['errors']} 个错误，{summary['warnings']} 个警告；"
        f"SKILL.md 共 {report.metrics.get('skill_md_lines', 0)} 行"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查 Agent Skill 的结构与产品质量")
    parser.add_argument("skill_path", help="Skill 目录")
    parser.add_argument("--public", action="store_true", help="执行公开发布 README 检查")
    parser.add_argument(
        "--weak-model",
        action="store_true",
        help="使用面向较弱模型的严格结构门槛",
    )
    parser.add_argument("--strict", action="store_true", help="将警告也视为失败")
    parser.add_argument(
        "--universal",
        action="store_true",
        help="拒绝在通用文档和路径中写死具体宿主品牌",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="输出 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = audit_skill(
        args.skill_path,
        public=args.public,
        weak_model=args.weak_model,
        universal=args.universal,
    )
    if args.as_json:
        print(json.dumps(report.to_dict(args.strict), ensure_ascii=False, indent=2))
    else:
        _print_human(report, args.strict)
    return 0 if report.passed(args.strict) else 1


if __name__ == "__main__":
    sys.exit(main())
