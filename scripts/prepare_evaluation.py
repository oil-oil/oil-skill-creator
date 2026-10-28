#!/usr/bin/env python3
"""根据 evals.json 创建结构固定、可以重复运行的评估目录。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from .evaluation_common import validate_eval_set
    from .snapshot_skill import default_workspace, snapshot_skill, verify_snapshot
    from .validate_skill import parse_frontmatter
except ImportError:
    from evaluation_common import validate_eval_set
    from snapshot_skill import default_workspace, snapshot_skill, verify_snapshot
    from validate_skill import parse_frontmatter


def _skill_name(skill_path: Path) -> str:
    skill_md = skill_path / "SKILL.md"
    if not skill_md.is_file():
        raise ValueError("目标目录缺少 SKILL.md")
    frontmatter, _ = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    name = frontmatter.get("name", "").strip()
    if not name:
        raise ValueError("SKILL.md 缺少 name")
    return name


def build_evaluation_plan(
    skill_path: str | Path,
    mode: str,
    iteration: int,
    workspace: str | Path | None = None,
    eval_set: str | Path | None = None,
    repetitions: int = 1,
    model: str | None = None,
    executor: str | None = None,
    allow_missing_skill: bool = False,
) -> tuple[Path, dict[str, object], list[tuple[Path, dict[str, object]]], list[Path]]:
    skill = Path(skill_path).expanduser().resolve()
    if not skill.is_dir():
        raise ValueError(f"Skill 目录不存在：{skill}")
    if mode not in {"create", "improve"}:
        raise ValueError("mode 必须是 create 或 improve")
    if iteration < 1:
        raise ValueError("iteration 必须大于等于 1")
    if not 1 <= repetitions <= 20:
        raise ValueError("repetitions 必须在 1 到 20 之间")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("必须提供非空 model，固定本轮评估使用的模型")
    if not isinstance(executor, str) or not executor.strip():
        raise ValueError("必须提供非空 executor，记录本轮隔离执行者")
    if allow_missing_skill and mode != "create":
        raise ValueError("allow_missing_skill 只适用于 create 模式")
    model = model.strip()
    executor = executor.strip()

    eval_path = (
        Path(eval_set).expanduser().resolve()
        if eval_set is not None
        else skill / "evals" / "evals.json"
    )
    eval_data = validate_eval_set(eval_path)
    if mode == "create" and len(eval_data["evals"]) < 3:
        raise ValueError("create 模式至少需要 3 条真实评估，先补充 evals/evals.json")

    skill_md = skill / "SKILL.md"
    if skill_md.is_file():
        name = _skill_name(skill)
        if eval_data["skill_name"] != name:
            raise ValueError(
                f"evals.skill_name 为 {eval_data['skill_name']!r}，与目标 Skill {name!r} 不一致"
            )
    elif allow_missing_skill:
        name = str(eval_data["skill_name"])
    else:
        raise ValueError("目标目录缺少 SKILL.md")

    workspace_path = (
        Path(workspace).expanduser().resolve()
        if workspace is not None
        else default_workspace(skill, name)
    )
    snapshot = workspace_path / "skill-snapshot"
    snapshot_hash: str | None = None
    if mode == "improve":
        try:
            snapshot_hash = str(verify_snapshot(workspace_path)["sha256"])
        except ValueError as exc:
            raise ValueError(
                f"整改评估需要完整的写入前快照；先运行 snapshot_skill.py。{exc}"
            ) from exc
    current_hash = (
        str(snapshot_skill(skill, dry_run=True)["sha256"]) if skill_md.is_file() else None
    )

    iteration_path = workspace_path / f"iteration-{iteration}"
    baseline = "without_skill" if mode == "create" else "old_skill"
    configurations = ["with_skill", baseline]
    metadata_files: list[tuple[Path, dict[str, object]]] = []
    output_dirs: list[Path] = []
    runs: list[dict[str, object]] = []

    for item in eval_data["evals"]:
        eval_dir = iteration_path / str(item["name"])
        resolved_files: list[str] = []
        for value in item["files"]:
            input_path = Path(value).expanduser()
            if not input_path.is_absolute():
                input_path = eval_path.parent / input_path
            input_path = input_path.resolve()
            if not input_path.exists():
                raise ValueError(f"评估输入文件不存在：{input_path}")
            resolved_files.append(str(input_path))
        metadata = {
            "eval_id": item["id"],
            "eval_name": item["name"],
            "prompt": item["prompt"],
            "expected_output": item["expected_output"],
            "files": resolved_files,
            "expectations": item["expectations"],
        }
        metadata_files.append((eval_dir / "eval_metadata.json", metadata))
        for configuration in configurations:
            configured_skill: str | None
            planned_hash: str | None
            if configuration == "with_skill":
                configured_skill = str(skill)
                planned_hash = current_hash
            elif configuration == "old_skill":
                configured_skill = str(snapshot)
                planned_hash = snapshot_hash
            else:
                configured_skill = None
                planned_hash = None
            for repetition in range(1, repetitions + 1):
                run_dir = eval_dir / configuration / f"run-{repetition}"
                outputs = run_dir / "outputs"
                output_dirs.append(outputs)
                runs.append(
                    {
                        "run_id": f"{item['name']}-{configuration}-run-{repetition}",
                        "eval_id": item["id"],
                        "eval_name": item["name"],
                        "configuration": configuration,
                        "repetition": repetition,
                        "model": model,
                        "executor": executor,
                        "skill_path": configured_skill,
                        "skill_hash": planned_hash,
                        "prompt": item["prompt"],
                        "input_files": resolved_files,
                        "expected_output": item["expected_output"],
                        "expectations": item["expectations"],
                        "run_dir": str(run_dir),
                        "outputs_dir": str(outputs),
                    }
                )

    plan: dict[str, object] = {
        "schema_version": 2,
        "skill_name": name,
        "skill_path": str(skill),
        "mode": mode,
        "iteration": iteration,
        "model": model,
        "executor": executor,
        "eval_set": str(eval_path),
        "configurations": configurations,
        "repetitions": repetitions,
        "runs": runs,
    }
    return iteration_path, plan, metadata_files, output_dirs


def prepare_evaluation(
    skill_path: str | Path,
    mode: str,
    iteration: int,
    workspace: str | Path | None = None,
    eval_set: str | Path | None = None,
    repetitions: int = 1,
    model: str | None = None,
    executor: str | None = None,
    allow_missing_skill: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    iteration_path, plan, metadata_files, output_dirs = build_evaluation_plan(
        skill_path,
        mode,
        iteration,
        workspace=workspace,
        eval_set=eval_set,
        repetitions=repetitions,
        model=model,
        executor=executor,
        allow_missing_skill=allow_missing_skill,
    )
    if iteration_path.exists():
        raise FileExistsError(f"iteration 已存在，拒绝覆盖：{iteration_path}")

    payload = {
        "status": "dry-run" if dry_run else "created",
        "iteration_path": str(iteration_path),
        "run_plan": str(iteration_path / "run_plan.json"),
        "runs": len(plan["runs"]),
        "model": model.strip() if isinstance(model, str) else None,
        "executor": executor.strip() if isinstance(executor, str) else None,
    }
    if dry_run:
        return payload

    iteration_path.mkdir(parents=True)
    for metadata_path, metadata in metadata_files:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    for output_dir in output_dirs:
        output_dir.mkdir(parents=True)
    (iteration_path / "run_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="创建结构固定的 Skill 评估目录")
    parser.add_argument("skill_path", help="目标 Skill 目录")
    parser.add_argument(
        "--mode",
        choices=("create", "improve"),
        required=True,
        help="create 与普通 Agent 比较；improve 与整改前快照比较",
    )
    parser.add_argument("--iteration", type=int, required=True, help="评估轮次，从 1 开始")
    parser.add_argument("--model", required=True, help="本轮所有运行固定使用的模型标识")
    parser.add_argument("--executor", required=True, help="实际隔离执行者或运行环境标识")
    parser.add_argument(
        "--workspace",
        help="评估工作目录；Skill 位于 skills 扫描目录时，默认使用其同级的 skill-workspaces",
    )
    parser.add_argument("--eval-set", help="evals.json 路径，默认读取目标 Skill")
    parser.add_argument("--repetitions", type=int, default=1, help="每种配置运行次数")
    parser.add_argument(
        "--allow-missing-skill",
        action="store_true",
        help="create 模式允许目录先只有 evals；实现后沿用同一计划运行候选",
    )
    parser.add_argument("--dry-run", action="store_true", help="只显示计划，不写入")
    parser.add_argument("--json", action="store_true", dest="as_json", help="输出 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = prepare_evaluation(
            args.skill_path,
            args.mode,
            args.iteration,
            workspace=args.workspace,
            eval_set=args.eval_set,
            repetitions=args.repetitions,
            model=args.model,
            executor=args.executor,
            allow_missing_skill=args.allow_missing_skill,
            dry_run=args.dry_run,
        )
    except (ValueError, FileExistsError, KeyError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        status = "仅预览" if payload["status"] == "dry-run" else "已创建"
        print(f"{status}：{payload['iteration_path']}")
        print(f"运行数：{payload['runs']}")
        print(f"运行计划：{payload['run_plan']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
