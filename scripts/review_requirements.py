#!/usr/bin/env python3
"""收集需要人工核对的需求证据，不把静态命中当作最终评审结论。"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

SKIP = {'.git', 'node_modules', '__pycache__', '.venv', 'tests', 'evals', 'credential-ui'}


def collect(root: Path) -> dict:
    root = root.resolve()
    if not (root / 'SKILL.md').is_file():
        raise ValueError('目标目录缺少 SKILL.md')
    signals = {'credentials': [], 'generation': []}
    patterns = {
        'credentials': re.compile(r'API[ _-]?KEY|api_key|密钥|Client Secret|credential_ref', re.I),
        'generation': re.compile(r'imagegen|image_gen|生图|图片生成', re.I),
    }
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.is_symlink() or any(part in SKIP for part in p.relative_to(root).parts):
            continue
        if p.suffix.lower() not in {'.md', '.py', '.ts', '.js', '.mjs', '.sh', '.ps1'}:
            continue
        if p.stat().st_size > 1_000_000:
            continue
        for number, line in enumerate(p.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            for name, pattern in patterns.items():
                if pattern.search(line):
                    # 不输出原文，避免凭据线索扫描反而泄露值。
                    signals[name].append({'file': p.relative_to(root).as_posix(), 'line': number})
    component = root / 'scripts/credential-ui'
    required = ['src/profile.ts', 'src/server.ts', 'src/run.ts', 'public/app.js', 'manifests/profiles.json', 'tests/profile.test.ts']
    text = (root / 'SKILL.md').read_text(encoding='utf-8')
    return {
        'skill': str(root), 'status': 'needs-review', 'signals': signals,
        'credential_component': {'present': component.is_dir(), 'missing': [f for f in required if not (component / f).is_file()]},
        'setup_navigation': 'api-key-setup.md' in text or 'credential-ui.md' in text,
        'required_decisions': ['凭据入口是否适用；若复用现成入口，给出真实入口', '页面保存、部分失败恢复与业务读取的证据', '默认内置能力与可选 API 的选择条件', 'description、README、仓库 About 是否先讲功能', '仓库测试入口、发布包和哈希清单是否同步'],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('skill_path', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(collect(args.skill_path), ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        parser.error(str(error))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
