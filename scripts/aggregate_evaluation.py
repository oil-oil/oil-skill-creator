#!/usr/bin/env python3
"""检查评估运行数据，并生成 JSON 与 Markdown 对比报告。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from .evaluation_common import load_json, summarize
except ImportError:
    from evaluation_common import load_json, summarize


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} 必须是数字")
    if value < 0:
        raise ValueError(f"{label} 不能为负数")
    return float(value)


def _read_grading(path: Path, expectations: list[str]) -> tuple[float | None, list[dict[str, Any]]]:
    if not path.is_file():
        if expectations:
            raise ValueError(f"缺少 grading.json：{path}")
        return None, []
    data = load_json(path)
    items = data.get("expectations") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError(f"grading.expectations 必须是数组：{path}")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"grading expectation 必须是对象：{path}:{index}")
        text = item.get("text")
        passed = item.get("passed")
        evidence = item.get("evidence")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"grading.text 缺失：{path}:{index}")
        if not isinstance(passed, bool):
            raise ValueError(f"grading.passed 必须是布尔值：{path}:{index}")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError(f"grading.evidence 缺失：{path}:{index}")
        normalized.append(
            {"text": text.strip(), "passed": passed, "evidence": evidence.strip()}
        )
    expected_texts = set(expectations)
    actual_texts = {item["text"] for item in normalized}
    if expected_texts and actual_texts != expected_texts:
        raise ValueError(f"grading 与 eval_metadata 的 expectations 不一致：{path}")
    return (
        sum(1 for item in normalized if item["passed"]) / len(normalized)
        if normalized
        else None,
        normalized,
    )


def _read_timing(path: Path) -> tuple[float, float]:
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"timing.json 顶层必须是对象：{path}")
    tokens = _number(data.get("total_tokens"), f"{path}.total_tokens")
    if "duration_ms" in data:
        duration = _number(data["duration_ms"], f"{path}.duration_ms") / 1000
    else:
        duration = _number(
            data.get("total_duration_seconds"), f"{path}.total_duration_seconds"
        )
    return tokens, duration


def _read_execution(path: Path, run: dict[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"缺少 execution.json：{path}")
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"execution.json 顶层必须是对象：{path}")
    for field in ("model", "executor"):
        actual = data.get(field)
        if not isinstance(actual, str) or not actual.strip():
            raise ValueError(f"execution.{field} 必须是非空字符串：{path}")
        if actual.strip() != run.get(field):
            raise ValueError(
                f"execution.{field} 与 run_plan 不一致：{actual.strip()!r} != {run.get(field)!r}"
            )
    skill_hash = data.get("skill_hash")
    if skill_hash is not None and (
        not isinstance(skill_hash, str)
        or len(skill_hash) != 64
        or any(character not in "0123456789abcdef" for character in skill_hash)
    ):
        raise ValueError(f"execution.skill_hash 必须是 64 位小写 SHA-256 或 null：{path}")
    configuration = run.get("configuration")
    if configuration == "without_skill" and skill_hash is not None:
        raise ValueError("without_skill 的 execution.skill_hash 必须为 null")
    if configuration != "without_skill" and skill_hash is None:
        raise ValueError(f"{configuration} 必须记录实际加载的 execution.skill_hash")
    planned_hash = run.get("skill_hash")
    if planned_hash is not None and skill_hash != planned_hash:
        raise ValueError("execution.skill_hash 与 run_plan 不一致，Skill 内容可能在运行前后变化")
    return {
        "model": str(data["model"]).strip(),
        "executor": str(data["executor"]).strip(),
        "skill_hash": skill_hash,
    }


def aggregate_evaluation(
    iteration_path: str | Path,
    allow_incomplete: bool = False,
) -> dict[str, Any]:
    root = Path(iteration_path).expanduser().resolve()
    plan_path = root / "run_plan.json"
    plan = load_json(plan_path)
    if not isinstance(plan, dict) or not isinstance(plan.get("runs"), list):
        raise ValueError("run_plan.json 缺少 runs 数组")
    configurations = plan.get("configurations")
    if not isinstance(configurations, list) or len(configurations) != 2:
        raise ValueError("run_plan.json 必须包含两个 configurations")
    schema_version = plan.get("schema_version", 1)
    if schema_version not in {1, 2}:
        raise ValueError(f"不支持的 run_plan.schema_version：{schema_version}")
    model = plan.get("model") if schema_version == 2 else None
    executor = plan.get("executor") if schema_version == 2 else None
    if schema_version == 2 and (
        not isinstance(model, str)
        or not model.strip()
        or not isinstance(executor, str)
        or not executor.strip()
    ):
        raise ValueError("schema 2 的 run_plan 必须记录非空 model 和 executor")

    run_results: list[dict[str, Any]] = []
    incomplete: list[str] = []
    for run in plan["runs"]:
        if not isinstance(run, dict):
            raise ValueError("run_plan.runs 项必须是对象")
        if schema_version == 2 and (
            run.get("model") != model or run.get("executor") != executor
        ):
            raise ValueError("run 的 model 或 executor 与本轮 run_plan 不一致，拒绝混合聚合")
        run_dir = Path(str(run.get("run_dir", ""))).expanduser().resolve()
        try:
            run_dir.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"run_dir 越出 iteration：{run_dir}") from exc
        expectations = run.get("expectations", [])
        if not isinstance(expectations, list) or not all(
            isinstance(value, str) for value in expectations
        ):
            raise ValueError(f"run expectations 无效：{run.get('run_id')}")
        try:
            pass_rate, grading = _read_grading(run_dir / "grading.json", expectations)
            timing_path = run_dir / "timing.json"
            if not timing_path.is_file():
                raise ValueError(f"缺少 timing.json：{timing_path}")
            tokens, duration = _read_timing(timing_path)
            execution = _read_execution(run_dir / "execution.json", run) if schema_version == 2 else None
        except ValueError as exc:
            if not allow_incomplete:
                raise
            incomplete.append(str(exc))
            continue
        run_results.append(
            {
                "run_id": run.get("run_id"),
                "eval_id": run.get("eval_id"),
                "eval_name": run.get("eval_name"),
                "configuration": run.get("configuration"),
                "repetition": run.get("repetition"),
                "model": execution["model"] if execution else None,
                "executor": execution["executor"] if execution else None,
                "skill_hash": execution["skill_hash"] if execution else None,
                "pass_rate": pass_rate,
                "total_tokens": tokens,
                "duration_seconds": duration,
                "expectations": grading,
            }
        )

    summaries: dict[str, dict[str, Any]] = {}
    for configuration in configurations:
        selected = [
            item for item in run_results if item["configuration"] == configuration
        ]
        skill_hashes = {
            item["skill_hash"] for item in selected if item["skill_hash"] is not None
        }
        if len(skill_hashes) > 1:
            raise ValueError(f"{configuration} 在同一轮出现多个 Skill 内容摘要，拒绝混合聚合")
        summaries[str(configuration)] = {
            "runs": len(selected),
            "skill_hash": next(iter(skill_hashes)) if skill_hashes else None,
            "pass_rate": summarize(
                [item["pass_rate"] for item in selected if item["pass_rate"] is not None]
            ),
            "duration_seconds": summarize(
                [item["duration_seconds"] for item in selected]
            ),
            "total_tokens": summarize([item["total_tokens"] for item in selected]),
        }

    primary = summaries[str(configurations[0])]
    baseline = summaries[str(configurations[1])]
    delta: dict[str, float | None] = {}
    for metric in ("pass_rate", "duration_seconds", "total_tokens"):
        primary_mean = primary[metric]["mean"]
        baseline_mean = baseline[metric]["mean"]
        delta[metric] = (
            round(float(primary_mean) - float(baseline_mean), 4)
            if primary_mean is not None and baseline_mean is not None
            else None
        )

    return {
        "schema_version": schema_version,
        "skill_name": plan.get("skill_name"),
        "iteration": plan.get("iteration"),
        "model": model,
        "executor": executor,
        "configurations": summaries,
        "delta_primary_minus_baseline": delta,
        "runs": run_results,
        "incomplete": incomplete,
    }


def _format_metric(metric: dict[str, object], percent: bool = False) -> str:
    value = metric.get("mean")
    deviation = metric.get("stddev")
    if value is None:
        return "无数据"
    if percent:
        return f"{float(value) * 100:.1f}% ± {float(deviation or 0) * 100:.1f}%"
    return f"{float(value):.2f} ± {float(deviation or 0):.2f}"


def render_markdown(benchmark: dict[str, Any]) -> str:
    lines = [f"# {benchmark.get('skill_name', 'Skill')} 效果对比", ""]
    if benchmark.get("model"):
        lines.extend(
            [
                f"模型：{benchmark['model']}",
                f"执行者：{benchmark.get('executor') or '未记录'}",
                "",
            ]
        )
    lines.extend(
        [
            "| 配置 | 运行数 | 通过率 | 秒 | Token | Skill SHA-256 |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for name, summary in benchmark["configurations"].items():
        skill_hash = summary.get("skill_hash")
        lines.append(
            "| "
            + " | ".join(
                [
                    name,
                    str(summary["runs"]),
                    _format_metric(summary["pass_rate"], percent=True),
                    _format_metric(summary["duration_seconds"]),
                    _format_metric(summary["total_tokens"]),
                    str(skill_hash)[:12] if skill_hash else "未记录",
                ]
            )
            + " |"
        )
    lines.extend(["", "## 当前版本与基线的差值", ""])
    labels = {
        "pass_rate": "通过率",
        "duration_seconds": "耗时（秒）",
        "total_tokens": "Token",
    }
    for name, value in benchmark["delta_primary_minus_baseline"].items():
        lines.append(f"- {labels.get(name, name)}：{'无数据' if value is None else value}")
    if benchmark["incomplete"]:
        lines.extend(["", "## 未完成数据", ""])
        lines.extend(f"- {item}" for item in benchmark["incomplete"])
    return "\n".join(lines) + "\n"


def write_benchmark(
    iteration_path: str | Path,
    allow_incomplete: bool = False,
    replace: bool = False,
) -> tuple[Path, Path, dict[str, Any]]:
    root = Path(iteration_path).expanduser().resolve()
    json_path = root / "benchmark.json"
    markdown_path = root / "benchmark.md"
    if not replace and (json_path.exists() or markdown_path.exists()):
        raise FileExistsError("对比报告已存在；使用 --replace 明确覆盖")
    benchmark = aggregate_evaluation(root, allow_incomplete=allow_incomplete)
    json_path.write_text(
        json.dumps(benchmark, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    markdown_path.write_text(
        render_markdown(benchmark), encoding="utf-8", newline="\n"
    )
    return json_path, markdown_path, benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="汇总当前 Skill 与基线的效果数据")
    parser.add_argument("iteration_path", help="iteration-N 目录")
    parser.add_argument(
        "--allow-incomplete", action="store_true", help="跳过缺少数据的运行并标记"
    )
    parser.add_argument("--replace", action="store_true", help="明确覆盖已有对比报告")
    parser.add_argument("--json", action="store_true", dest="as_json", help="输出 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        json_path, markdown_path, benchmark = write_benchmark(
            args.iteration_path,
            allow_incomplete=args.allow_incomplete,
            replace=args.replace,
        )
    except (ValueError, FileExistsError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(benchmark, ensure_ascii=False, indent=2))
    else:
        print(f"已创建：{json_path}")
        print(f"已创建：{markdown_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
