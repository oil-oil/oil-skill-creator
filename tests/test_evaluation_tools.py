from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.aggregate_evaluation import write_benchmark
from scripts.generate_review import generate_review
from scripts.prepare_evaluation import prepare_evaluation
from scripts.score_triggers import score_triggers
from scripts.snapshot_skill import snapshot_skill
from tests.test_validate_skill import make_valid_skill
from scripts.validate_skill import parse_frontmatter


def write_eval_set(skill: Path, count: int = 3) -> Path:
    eval_dir = skill / "evals"
    eval_dir.mkdir(parents=True, exist_ok=True)
    names = ["main-flow", "error-branch", "similar-boundary"]
    path = eval_dir / "evals.json"
    path.write_text(
        json.dumps(
            {
                "skill_name": "sample-skill",
                "evals": [
                    {
                        "id": index,
                        "name": names[index - 1],
                        "prompt": "执行主流程",
                        "expected_output": "生成结果文件",
                        "files": [],
                        "expectations": ["结果可用"],
                    }
                    for index in range(1, count + 1)
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def fill_runs(iteration: Path) -> None:
    plan = json.loads((iteration / "run_plan.json").read_text(encoding="utf-8"))
    for run in plan["runs"]:
        run_dir = Path(run["run_dir"])
        passed = run["configuration"] == "with_skill"
        (run_dir / "grading.json").write_text(
            json.dumps(
                {
                    "expectations": [
                        {"text": "结果可用", "passed": passed, "evidence": "result.txt"}
                    ]
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (run_dir / "timing.json").write_text(
            json.dumps(
                {
                    "total_tokens": 100 if passed else 120,
                    "duration_ms": 1000 if passed else 1500,
                    "total_duration_seconds": 1.0 if passed else 1.5,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        if plan.get("schema_version") == 2:
            skill_hash = run["skill_hash"]
            if run["configuration"] == "with_skill" and skill_hash is None:
                skill_hash = snapshot_skill(run["skill_path"], dry_run=True)["sha256"]
            (run_dir / "execution.json").write_text(
                json.dumps(
                    {
                        "model": run["model"],
                        "executor": run["executor"],
                        "skill_hash": skill_hash,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        (run_dir / "outputs" / "result.txt").write_text(
            "可用结果\n" if passed else "基线结果\n", encoding="utf-8"
        )
        (run_dir / "outputs" / "preview.png").write_bytes(
            b"\x89PNG\r\n\x1a\n"
        )


class EvaluationToolsTests(unittest.TestCase):
    def test_snapshot_refuses_overwrite_and_preserves_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = make_valid_skill(root)
            payload = snapshot_skill(skill)
            snapshot = Path(str(payload["snapshot"]))
            self.assertTrue((snapshot / "SKILL.md").is_file())
            self.assertEqual(payload["files"], 4)
            with self.assertRaises(FileExistsError):
                snapshot_skill(skill)

    def test_snapshot_avoids_named_skills_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = make_valid_skill(root / "skills")
            payload = snapshot_skill(skill)
            self.assertEqual(
                Path(str(payload["snapshot"])).resolve(),
                (root / "skill-workspaces" / "sample-skill-workspace" / "skill-snapshot").resolve(),
            )

    def test_prepare_uses_canonical_configuration_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = make_valid_skill(root)
            write_eval_set(skill)
            created = prepare_evaluation(
                skill, "create", 1, model="model-a", executor="isolated-a"
            )
            iteration = Path(str(created["iteration_path"]))
            self.assertTrue((iteration / "main-flow" / "with_skill").is_dir())
            self.assertTrue((iteration / "main-flow" / "without_skill").is_dir())
            plan = json.loads((iteration / "run_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["schema_version"], 2)
            self.assertEqual(plan["model"], "model-a")
            self.assertEqual(plan["executor"], "isolated-a")
            current_run = next(
                run for run in plan["runs"] if run["configuration"] == "with_skill"
            )
            self.assertEqual(
                current_run["skill_hash"], snapshot_skill(skill, dry_run=True)["sha256"]
            )

            workspace = root / "custom-workspace"
            snapshot_skill(skill, workspace=workspace)
            improved = prepare_evaluation(
                skill,
                "improve",
                1,
                workspace=workspace,
                model="model-a",
                executor="isolated-a",
            )
            improved_iteration = Path(str(improved["iteration_path"]))
            plan = json.loads(
                (improved_iteration / "run_plan.json").read_text(encoding="utf-8")
            )
            self.assertEqual(plan["configurations"], ["with_skill", "old_skill"])
            old_run = next(
                run for run in plan["runs"] if run["configuration"] == "old_skill"
            )
            self.assertEqual(
                Path(old_run["skill_path"]).resolve(),
                (workspace / "skill-snapshot").resolve(),
            )

    def test_create_allows_evals_only_and_preserves_plan_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "sample-skill"
            skill.mkdir()
            write_eval_set(skill)
            created = prepare_evaluation(
                skill,
                "create",
                1,
                model="model-a",
                executor="isolated-a",
                allow_missing_skill=True,
            )
            iteration = Path(str(created["iteration_path"]))
            plan = json.loads((iteration / "run_plan.json").read_text(encoding="utf-8"))
            current_run = next(
                run for run in plan["runs"] if run["configuration"] == "with_skill"
            )
            self.assertIsNone(current_run["skill_hash"])
            baseline_run = next(
                run for run in plan["runs"] if run["configuration"] == "without_skill"
            )
            baseline_execution = Path(baseline_run["run_dir"]) / "execution.json"
            baseline_execution.write_text(
                json.dumps(
                    {"model": "model-a", "executor": "isolated-a", "skill_hash": None}
                ),
                encoding="utf-8",
            )
            self.assertTrue(baseline_execution.is_file())
            self.assertFalse((skill / "SKILL.md").exists())

            make_valid_skill(root)
            fill_runs(iteration)
            _, _, benchmark = write_benchmark(iteration)
            self.assertEqual(benchmark["model"], "model-a")
            self.assertIsNotNone(benchmark["configurations"]["with_skill"]["skill_hash"])

    def test_create_requires_three_evals_and_missing_skill_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "sample-skill"
            skill.mkdir()
            write_eval_set(skill, count=2)
            with self.assertRaises(ValueError):
                prepare_evaluation(
                    skill,
                    "create",
                    1,
                    model="model-a",
                    executor="isolated-a",
                    allow_missing_skill=True,
                )
            write_eval_set(skill)
            with self.assertRaises(ValueError):
                prepare_evaluation(
                    skill, "create", 1, model="model-a", executor="isolated-a"
                )
            with self.assertRaises(ValueError):
                prepare_evaluation(
                    skill,
                    "improve",
                    1,
                    model="model-a",
                    executor="isolated-a",
                    allow_missing_skill=True,
                )

    def test_execution_metadata_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = make_valid_skill(root)
            write_eval_set(skill)
            created = prepare_evaluation(
                skill, "create", 1, model="model-a", executor="isolated-a"
            )
            iteration = Path(str(created["iteration_path"]))
            for field in ("model", "executor"):
                with self.subTest(field=field):
                    fill_runs(iteration)
                    plan = json.loads((iteration / "run_plan.json").read_text(encoding="utf-8"))
                    run = next(
                        item for item in plan["runs"] if item["configuration"] == "with_skill"
                    )
                    execution_path = Path(run["run_dir"]) / "execution.json"
                    execution = json.loads(execution_path.read_text(encoding="utf-8"))
                    execution[field] = "unexpected"
                    execution_path.write_text(json.dumps(execution), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        write_benchmark(iteration)
            fill_runs(iteration)
            plan_path = iteration / "run_plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            current_run = next(
                run for run in plan["runs"] if run["configuration"] == "with_skill"
            )
            execution_path = Path(current_run["run_dir"]) / "execution.json"
            execution = json.loads(execution_path.read_text(encoding="utf-8"))
            execution["skill_hash"] = "0" * 64
            execution_path.write_text(json.dumps(execution), encoding="utf-8")
            with self.assertRaises(ValueError):
                write_benchmark(iteration)

            fill_runs(iteration)
            plan["runs"][0]["model"] = "model-b"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaises(ValueError):
                write_benchmark(iteration)

            plan["runs"][0]["model"] = "model-a"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            fill_runs(iteration)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            execution_path = Path(plan["runs"][0]["run_dir"]) / "execution.json"
            execution_path.unlink()
            with self.assertRaises(ValueError):
                write_benchmark(iteration)

    def test_models_stay_in_separate_iterations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = make_valid_skill(root)
            write_eval_set(skill)
            benchmarks = []
            for iteration_number, model in ((1, "model-a"), (2, "model-b")):
                created = prepare_evaluation(
                    skill,
                    "create",
                    iteration_number,
                    model=model,
                    executor="isolated-a",
                )
                iteration = Path(str(created["iteration_path"]))
                fill_runs(iteration)
                _, _, benchmark = write_benchmark(iteration)
                benchmarks.append(benchmark)
                self.assertEqual(benchmark["model"], model)
                self.assertEqual(
                    {run["model"] for run in benchmark["runs"]}, {model}
                )
            self.assertEqual(
                [benchmark["model"] for benchmark in benchmarks], ["model-a", "model-b"]
            )

    def test_schema_one_remains_aggregateable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = make_valid_skill(root)
            write_eval_set(skill)
            created = prepare_evaluation(
                skill, "create", 1, model="model-a", executor="isolated-a"
            )
            iteration = Path(str(created["iteration_path"]))
            plan_path = iteration / "run_plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["schema_version"] = 1
            for run in plan["runs"]:
                run.pop("model")
                run.pop("executor")
                run.pop("skill_hash")
            plan.pop("model")
            plan.pop("executor")
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            fill_runs(iteration)
            _, _, benchmark = write_benchmark(iteration)
            self.assertEqual(benchmark["schema_version"], 1)
            self.assertIsNone(benchmark["model"])

    def test_improve_rejects_changed_snapshot(self) -> None:
        operations = {
            "modify": lambda snapshot: (snapshot / "SKILL.md").write_text(
                "changed\n", encoding="utf-8"
            ),
            "add": lambda snapshot: (snapshot / "extra.txt").write_text(
                "new\n", encoding="utf-8"
            ),
            "delete": lambda snapshot: (snapshot / "README.md").unlink(),
        }
        for label, mutate in operations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                skill = make_valid_skill(root)
                write_eval_set(skill)
                workspace = root / "workspace"
                payload = snapshot_skill(skill, workspace=workspace)
                mutate(Path(str(payload["snapshot"])))
                with self.assertRaises(ValueError):
                    prepare_evaluation(
                        skill,
                        "improve",
                        1,
                        workspace=workspace,
                        model="model-a",
                        executor="isolated-a",
                    )

    def test_aggregate_and_blind_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = make_valid_skill(root)
            write_eval_set(skill)
            created = prepare_evaluation(
                skill, "create", 1, model="model-a", executor="isolated-a"
            )
            iteration = Path(str(created["iteration_path"]))
            fill_runs(iteration)
            _, _, benchmark = write_benchmark(iteration)
            self.assertEqual(
                benchmark["delta_primary_minus_baseline"]["pass_rate"], 1.0
            )
            review, manifest = generate_review(iteration)
            html = review.read_text(encoding="utf-8")
            self.assertIn("候选 A", html)
            self.assertIn("model-a", html)
            self.assertNotIn("with_skill", html)
            self.assertIn("+'\\n'", html)
            self.assertIn("localStorage", html)
            self.assertIn("label.htmlFor", html)
            self.assertIn("data:image/png;base64", html)
            mapping = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertTrue(mapping["blind"])
            self.assertEqual(mapping["model"], "model-a")
            self.assertEqual(set(mapping["candidates"]), {"with_skill", "without_skill"})

    def test_trigger_score_reports_false_positive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = make_valid_skill(root)
            frontmatter, _ = parse_frontmatter(
                (skill / "SKILL.md").read_text(encoding="utf-8")
            )
            eval_set = root / "trigger-evals.json"
            results = root / "trigger-results.json"
            eval_set.write_text(
                json.dumps(
                    {
                        "skill_name": "sample-skill",
                        "description": "处理固定流程",
                        "cases": [
                            {"id": "yes", "query": "执行固定流程", "should_trigger": True},
                            {"id": "no", "query": "普通问答", "should_trigger": False},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            results.write_text(
                json.dumps(
                    {
                        "cases": [
                            {"id": "yes", "trials": [True, True, False]},
                            {"id": "no", "triggered": True},
                        ],
                        "description": frontmatter["description"],
                    }
                ),
                encoding="utf-8",
            )
            report = score_triggers(eval_set, results, skill, phase="select")
            self.assertEqual(report["summary"]["holdout"]["accuracy"], 0.5)
            self.assertEqual(report["summary"]["holdout"]["fp"], 1)
            with self.assertRaises(ValueError):
                score_triggers(eval_set, results, skill, strict=True, phase="select")

            bad_results = json.loads(results.read_text(encoding="utf-8"))
            bad_results["description"] = "不是目标 description"
            results.write_text(json.dumps(bad_results), encoding="utf-8")
            with self.assertRaises(ValueError):
                score_triggers(eval_set, results, skill, phase="select")

    def test_trigger_selection_rejects_train_only_improvement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = make_valid_skill(root)
            frontmatter, _ = parse_frontmatter(
                (skill / "SKILL.md").read_text(encoding="utf-8")
            )
            cases = [
                {
                    "id": f"positive-{index}",
                    "query": f"应触发请求 {index}",
                    "should_trigger": True,
                }
                for index in range(8)
            ] + [
                {
                    "id": f"negative-{index}",
                    "query": f"不应触发请求 {index}",
                    "should_trigger": False,
                }
                for index in range(8)
            ]
            eval_set = root / "trigger-evals.json"
            baseline_results = root / "baseline-results.json"
            eval_set.write_text(
                json.dumps({"skill_name": "sample-skill", "cases": cases}),
                encoding="utf-8",
            )
            baseline_results.write_text(
                json.dumps(
                    {
                        "description": frontmatter["description"],
                        "cases": [
                            {"id": item["id"], "triggered": False} for item in cases
                        ],
                    }
                ),
                encoding="utf-8",
            )
            baseline_train = score_triggers(
                eval_set, baseline_results, skill, phase="train"
            )
            baseline = score_triggers(
                eval_set, baseline_results, skill, phase="select"
            )
            baseline_report = root / "baseline-report.json"
            baseline_report.write_text(json.dumps(baseline), encoding="utf-8")

            candidate_description = "处理稳定流程。当用户要求固定产物时使用；普通问答不要触发。"
            skill_md = skill / "SKILL.md"
            skill_md.write_text(
                skill_md.read_text(encoding="utf-8").replace(
                    frontmatter["description"], candidate_description
                ),
                encoding="utf-8",
            )
            train_ids = {item["id"] for item in baseline_train["cases"]}
            candidate_results = root / "candidate-results.json"
            candidate_results.write_text(
                json.dumps(
                    {
                        "description": candidate_description,
                        "cases": [
                            {
                                "id": item["id"],
                                "triggered": (
                                    item["should_trigger"]
                                    if item["id"] in train_ids
                                    else not item["should_trigger"]
                                ),
                            }
                            for item in cases
                        ],
                    }
                ),
                encoding="utf-8",
            )
            candidate_train = score_triggers(
                eval_set,
                candidate_results,
                skill,
                phase="train",
            )
            candidate = score_triggers(
                eval_set,
                candidate_results,
                skill,
                baseline_report=baseline_report,
                phase="select",
            )
            self.assertGreater(
                candidate_train["summary"]["train"]["accuracy"],
                baseline_train["summary"]["train"]["accuracy"],
            )
            self.assertLess(
                candidate["summary"]["holdout"]["accuracy"],
                baseline["summary"]["holdout"]["accuracy"],
            )
            self.assertFalse(candidate["selection"]["recommended"])
            self.assertNotIn("holdout", json.dumps(candidate_train))
            self.assertTrue(
                {item["id"] for item in candidate_train["cases"]}.isdisjoint(
                    {item["id"] for item in candidate["cases"]}
                )
            )


if __name__ == "__main__":
    unittest.main()
