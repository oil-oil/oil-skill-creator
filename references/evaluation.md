# Skill 评估规范

## 先确定评估类型

- **客观型**：输出能由格式、文件、数值、步骤或程序要求验证。
- **主观型**：核心价值取决于审美、语气、创意或整体体验。
- **混合型**：既有明确要求，也有人类偏好。

评估方法由任务类型决定。明确要求和主观结论要分开报告，不能合并成一个总分。

## 测试集

测试保存在目标 Skill 的 `evals/evals.json`，每条使用固定字段：

```json
{
  "id": 1,
  "name": "descriptive-name",
  "prompt": "真实用户请求",
  "expected_output": "期望结果说明",
  "files": [],
  "expectations": ["可验证要求"]
}
```

先准备 2–3 个真实请求，覆盖主流程、容易出错的分支和相似任务边界。能够明确检查的要求写入 `expectations`，不要改用其他字段。主观偏好写成人工评审问题，不要伪装成程序要求。

## 按需固定比较基线

- 创建新 Skill：基线是 `without_skill`，不加载任何 Skill。
- 整改现有 Skill：只有决定运行新版与旧版的效果对照时，才在第一次编辑前运行 `scripts/snapshot_skill.py`；基线是 `old_skill`，只加载 `skill-snapshot`。
- 当前版本统一命名为 `with_skill`。

快照不是普通整改的必做步骤。小范围、目标明确、可由 Git 恢复且不需要执行旧版对照的修改，可以只做静态校验和针对性回归。需要效果对照时，不允许用正在编辑的目录充当旧版本，也不允许完成修改后再补快照。

## 准备评估目录

在目标 Skill 目录中运行：

`<python>` 沿用 `SKILL.md` 中已经解析并确认版本的解释器。

```text
<python> <oil-skill-creator>/scripts/prepare_evaluation.py . --mode create --iteration 1
<python> <oil-skill-creator>/scripts/prepare_evaluation.py . --mode improve --iteration 1
```

`improve` 模式会检查外部 workspace 中的 `skill-snapshot`。Skill 位于名为 `skills` 的扫描目录时，默认 workspace 是该目录同级的 `skill-workspaces/<skill-name>-workspace/`，避免快照被识别成重复 Skill。每轮使用一个新的 `iteration-N` 目录，程序拒绝覆盖已有目录，并生成下面的结构：

```text
<workspace>/
├── skill-snapshot/               # 仅整改模式
└── iteration-N/
    ├── run_plan.json
    └── <eval-name>/
        ├── eval_metadata.json
        ├── with_skill/
        │   └── run-1/outputs/
        └── without_skill/         # 创建模式
            └── run-1/outputs/
```

整改模式将 `without_skill` 替换为 `old_skill`。需要测量波动时通过 `--repetitions` 创建多次运行，不要手工复制目录。

## 运行当前版本和基线

隔离执行者是不会继承作者工作上下文、只获得本次请求和指定 Skill 的 Agent 或运行环境。

读取 `run_plan.json`，在同一轮运行当前版本和基线。每个执行者获得相同的请求、输入文件、模型和环境，两边只能加载不同的 Skill。

- 明确提供 Skill 路径，让执行者真正加载 Skill。
- 不要把 Skill 正文复制进任务提示。
- 输出只写入计划指定的 `outputs/`。
- 作者不要提前告诉主观评审者哪个版本较新。

不能并发运行时可以依次执行，但必须保持计划和环境一致，并在结果中说明这一限制。

## 记录耗时、Token 和客观结果

每个 `run-N/` 保存 `timing.json`：

```json
{
  "total_tokens": 1200,
  "duration_ms": 8500,
  "total_duration_seconds": 8.5
}
```

客观型运行还要保存 `grading.json`：

```json
{
  "expectations": [
    {"text": "输出包含必需字段", "passed": true, "evidence": "result.json"}
  ]
}
```

凡是程序能检查的要求，都要运行对应脚本，不能让 Agent 目测。证据必须引用真实文件或命令结果，不能只引用执行者自己的说明。

## 生成对比报告并交给人评审

所有运行完成后执行：

```text
<python> <oil-skill-creator>/scripts/aggregate_evaluation.py <iteration-path>
<python> <oil-skill-creator>/scripts/generate_review.py <iteration-path>
```

聚合程序生成 `benchmark.json` 和 `benchmark.md`。这两份文件记录通过率、耗时、Token 的平均值、波动和基线差异。程序还会生成本地 `review.html` 评审页，但不会自动打开浏览器；页面可以导出 `feedback.json`。

先向用户展示候选结果、证据和对比报告，再停止等待反馈。没有图形界面时，在对话中按同一顺序展示，并把用户意见整理成 `feedback.json`。收到反馈前不要继续修改 Skill。

## 主观与混合型

主观型评估按以下顺序：

1. 独立执行者生成候选；
2. 程序检查尺寸、格式、数量、路径和可打开性；
3. 隐去版本身份后并排展示；
4. 用户判断是否更清楚、更符合偏好、更愿意使用；
5. 将反馈抽象成通用规则，不复制候选内容。

另一个模型可以整理差异，不能用自己的分数替代用户。混合型分别报告客观门槛、人类偏好、时间、Token 和未验证风险。

## 触发评估

description 优化必须区分静态检查和真实测量。准备 8–10 条应触发请求，以及 8–10 条容易混淆但不应触发的请求。交给用户确认后固定测试集，后续版本不能换题。

评分程序按 ID 将测试分为两组：60% 是训练集（`train`），用于修改 description；40% 是保留集（`holdout`），只在最终选择版本时使用。

### 准备触发数据

评测集：

```json
{
  "skill_name": "example-skill",
  "cases": [
    {"id": "case-1", "query": "真实请求", "should_trigger": true}
  ]
}
```

独立执行后保存结果：

```json
{
  "skill_name": "example-skill",
  "description": "本轮真实加载的 description",
  "cases": [
    {"id": "case-1", "trials": [true, true, false]}
  ]
}
```

严格模式要求每条请求至少运行三次，并且运行次数必须是奇数。触发测试和保留集文件交给独立子 Agent 或其他隔离执行者；Skill 作者只能看到训练报告：

```text
<python> <oil-skill-creator>/scripts/score_triggers.py <eval-set> <candidate-results> --skill-path <current-skill> --phase train --strict --output <workspace>/trigger-train.json
```

`train` 输出只包含训练集的汇总和用例，不包含保留集的 ID、结果或分组。程序同时检查结果中的 description 是否与对应的 `SKILL.md` 一致，并保存测试集和 description 的摘要。

### 最终选择版本

隔离执行者保存基线的 `select` 报告，在改写阶段不交给作者。候选版本定稿后，再运行最终选择：

```text
<python> <oil-skill-creator>/scripts/score_triggers.py <eval-set> <baseline-results> --skill-path <baseline-skill> --phase select --strict --output <workspace>/trigger-baseline-select.json
<python> <oil-skill-creator>/scripts/score_triggers.py <eval-set> <candidate-results> --skill-path <current-skill> --phase select --strict --baseline-report <workspace>/trigger-baseline-select.json --output <workspace>/trigger-candidate-select.json
```

报告只有同时满足以下条件，才标记 `recommended: true`：

- 保留集准确率上升；
- 应触发请求的命中率没有下降；
- 不应触发请求的排除率没有下降。

出现取舍时交给用户决定。不能用训练集的改善掩盖保留集的退步，也不能只凭关键词或作者直觉声称触发更准确。

程序能够避免在训练报告中意外显示保留集，但无法阻止拥有全部文件权限的作者主动读取。

没有隔离执行者时，必须标记“保留集未独立”，不能宣称新 description 在未见请求上也有改善。

## 迭代与停止

每轮写入新的 `iteration-N`，并使用同一个固定基线。只有测试请求本身改变时，才更新该轮的评估信息；不要覆盖上一轮结果。

结果不理想时不要立即向 Skill 追加禁令或特例。先比较基线与带 Skill 运行，再结合输入完整性、执行偏差、工具限制、环境波动和用户反馈，确认 Skill 是否造成或放大了问题。

若问题来自 Skill，优先修正阶段目标、判断依据、工具接口或验证节点。只有条件客观且处理稳定时才增加程序分支；修改后用原失败类型和正常主流程共同回归。

满足以下任一条件时停止：

- 用户确认真实结果满足使用；
- 客观指标达到事先约定门槛且没有明显回归；
- 新修改不再产生能够看到或测量的改善；
- 继续优化的时间或 Token 成本高于收益。

没有子 Agent 或其他隔离执行能力时，只能由作者试跑并交给人查看。明确写“尚未完成独立验证”，不能把静态校验或作者自测当作完整效果证据。
