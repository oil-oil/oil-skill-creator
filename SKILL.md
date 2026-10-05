---
name: oil-skill-creator
description: 创建、评审、整改和发布 Skill。用户想从零创建 Skill、评审现有 Skill、检查它是否真正有用、修复触发或执行流程，或者改善首次使用、稳定性、Token 开销、文件分层、弱模型可读性与跨平台兼容性时使用。不要用于执行目标 Skill 负责的实际任务，也不要因为普通的编码、设计或写作请求触发。
license: MIT
compatibility: 核心脚本只使用 Python 3 标准库；可选凭据输入页需要 Node.js 22.18+ 和系统凭据服务，已验证 macOS，Windows 与 Linux 待实机验证；独立效果评估需要隔离执行能力。
metadata:
  version: "1.0.1"
---

# oil-skill-creator

把 Skill 当作需要长期维护的工具。先确认它解决了重复问题，再让它容易开始、稳定执行、能够验证，并如实说明兼容范围。不要把一次任务的提示词包装成 Skill。

## 先选择模式

| 模式 | 适用情况 | 路径 | 默认停止点 |
| --- | --- | --- | --- |
| 创建 | 还没有 Skill | 产品定义 → 实现 → 校验 → 评估 → 按需发布 | 交付可用 Skill |
| Review | 用户只要求评审、审计或找问题 | 读取 → 需求适用表 → 静态检查 → 流程检查 → 报告 | 交付报告后停止 |
| 整改 | 已有 Skill，用户要求修复或优化 | 读取 → 需求适用表 → 静态检查 → 按需保存快照 → 局部修改 → 复验 | 问题修复且无回归 |

Review 只读：不修改文件、不创建快照、不打包。用户看完报告再授权整改时，从整改路径重新开始。整改不用脚手架重建已有目录，只在用户要求交付发布包时打包。

## 开始前

已有 Skill 时，先完整读取 `SKILL.md`，再只读取当前模式和问题需要的资源：相关目录、脚本、测试、评估用例、README 和平台假设。已有信息不要再问。

只有目标或交付物不清楚、需要新增权限或服务、可能覆盖内容，或者主观方向会改变结果时才询问，并把问题一次问完。

分工如下：

- Agent 判断价值、边界、架构、例外和主观质量。
- 程序执行确定、重复、可验证、失败敏感的步骤。
- 隔离执行者运行触发测试和效果对照。它不继承作者的工作上下文，只拿到本次请求和指定 Skill，通常是子 Agent。
- 人判断审美、文案和整体体验。

下文的 `<python>` 指已确认版本不低于 3.10 的 Python 解释器：macOS 和 Linux 通常是 `python3`，Windows 通常是 `py -3`。不要假设 `python` 命令一定存在。

## 创建路径

先读 [产品设计](references/product-design.md)，确认问题值得做，并明确用户、当前做法、预期改善、输入、输出、边界、风险和任务类型。一次性需求、普通 Agent 已能稳定完成，或者说不清使用后会改善什么时，不要强行创建。

需要目录时先预览最小骨架，确认后去掉 `--dry-run` 再运行一次：

```text
<python> <oil-skill-creator>/scripts/scaffold_skill.py <skill-name> --output-root <目录> --description <描述> --public --dry-run
```

只用 `--components` 添加当前确实需要的目录，例如 `--components scripts,tests`，不为示例完整而创建空资源。需要版本号时加 `--version 0.1.0`。

然后按“设计和编写”写内容，再运行程序校验。

## Review 与整改路径

先读 [Review 与整改规范](references/review-and-remediation.md)，按其中的检查顺序执行。三个节点不能跳过：

- 运行校验器之前先建需求适用表，批量评审时逐个 Skill 登记。需要用户输入 Key 的 Skill，第一次 Review 就核对凭据入口，这一项最容易漏。
- 校验器只确认结构问题。Skill 是否有用、流程是否合理、兼容性是否属实，要另外检查。
- 按 P0、P1、P2 报告。Review 交付报告后停止。

整改按规范中的整改步骤执行。第一次编辑前，判断是否需要旧版快照：

| 情况 | 做法 |
| --- | --- |
| 要让隔离执行者运行旧版做前后效果对照；用户要求保留独立基线；旧版无法从 Git 等可靠来源恢复 | 运行 `<python> <oil-skill-creator>/scripts/snapshot_skill.py <skill-path>` |
| 其他整改 | 不建快照，直接局部修改并复验 |

## 设计和编写

### 触发

目标 Skill 的触发信息只放在 frontmatter `description`：写清它做什么、什么时候用、哪些相似请求不该触发、与其他 Skill 怎么分工。正文不再重复一套触发规则。

description 先讲用户能完成的任务、得到的产物和适用边界，不用模型、服务商或宿主的名字代替功能介绍。只有决定触发对象或真实兼容范围的专用产品名才保留。

准备真实的正向请求和容易混淆的反向请求。需要测量触发准确性时，按 [评估规范](references/evaluation.md) 的触发评估执行；关键词静态检查证明不了触发可靠。

### 宿主中立

默认写成不依赖特定宿主的 Skill。正式指令、参考资料、README、目录名和示例使用“Agent、宿主、能力、隔离执行者”等通用名称，不写当前宿主的品牌、专属目录、专属命令或私有 API。

核心能力确实依赖某个宿主时，把专用适配器与通用流程分开，在兼容性中写明限制和替代方案，不宣称支持所有宿主。细则见 [兼容性](references/compatibility.md)。

### 首次使用和恢复

按 [产品设计](references/product-design.md) 的决策表处理首次使用、配置、需要确认的操作和失败恢复。登录、密钥、系统安装、覆盖、删除和外部写入先获得授权。

需要持久化配置或凭据时，按 [兼容性](references/compatibility.md) 分开设计普通配置、凭据引用和密钥存储。密钥值不进 JSON、Skill 文件、日志或 Agent 上下文。

本机桌面需要用户输入 API Key 等单行凭据、又没有现成安全入口时，按 [凭据输入页](references/credential-ui.md) 用安装脚本接入随附组件，不为每个 Skill 重新生成页面。

重复运行初始化或迁移不能破坏已有配置，也不能产生重复结果。失败时保留可用的中间产物，说明停在哪一步、怎么恢复、还有哪些必做步骤没执行。

### 信息架构

拆分文件前读 [信息架构](references/information-architecture.md)。主流程放 `SKILL.md`，阶段细节放 `references/`，结果固定的步骤放 `scripts/`，运行结果和 Review 记录放 Skill 外部。长参考资料需排查互斥分支并配置目录导航（TOC）。

目标 Skill 会生成难以一次完成或局部修改的大型产物，或者需要复杂配置、反复预览和人工调整时，按 [产品设计](references/product-design.md) 设计分段产出或可复用操作页面。

正文写目标、判断原则、主流程、必要分支和停止条件，不穷举具体情境。有限、稳定、可验证的分支交给程序；依赖语义的选择留给 Agent。一步只表达一个主要动作，分支紧邻对应步骤，术语保持一致。

只写能用于同类任务的规则、程序和回归测试。具体任务、个人目录、单次候选、Review 记录和修改历史不进 Skill。

Skill 不得包含与 description 不一致的隐藏行为、误导能力、越权访问或数据外传。兼容性只声明实际实现或真实验证过的范围。

## 程序校验

开发过程中运行：

```text
<python> <oil-skill-creator>/scripts/validate_skill.py <skill-path>
```

公开发布或整改完成前加上严格选项。`--weak-model` 使用更严格的结构限制，`--universal` 检查是否写死了宿主品牌或专属路径；只有产品明确依赖某个宿主时才省略 `--universal`，并在兼容性中说明原因。

```text
<python> <oil-skill-creator>/scripts/validate_skill.py <skill-path> --public --strict --weak-model --universal
```

校验通过只说明程序能确认的问题没有出现，不说明 Skill 有用。流程含义和真实效果要单独检查。

## 效果评估

用户要求证明效果、整改带来静态检查确认不了的重大行为变化，或者正式发布需要效果证据时，先读 [评估规范](references/evaluation.md)。创建模式与普通 Agent 对照，整改模式与写入前的快照对照。目标明确的小范围修正，用静态校验和针对性回归即可。

程序准备固定目录和运行计划，Agent 按计划运行，不自行增加目录或字段。整改对照把 `create` 换成 `improve`：

```text
<python> <oil-skill-creator>/scripts/prepare_evaluation.py <skill-path> --mode create --iteration 1
```

运行完成后，聚合数据并生成静态评审页：

```text
<python> <oil-skill-creator>/scripts/aggregate_evaluation.py <iteration-path>
<python> <oil-skill-creator>/scripts/generate_review.py <iteration-path>
```

把候选结果、证据和对比报告交给用户，收到反馈前不再修改 Skill。主观结果由人判断，AI 只检查明确要求或整理差异。没有隔离执行能力时，说明评估受限，不宣称已完成独立对照。

效果不好时，先按评估规范查明原因，不直接追加规则。

## 兼容与发布

发布前读 [兼容性](references/compatibility.md) 和 [GitHub 发布](references/publishing.md)。README 面向使用者，说明价值、安装、配置、兼容范围、数据边界和输出，不复制 Agent 的执行步骤。

需要版本号时，只记在源 Skill 的 `metadata.version`，用 [版本管理](references/versioning.md) 中的脚本设置和升版。

严格校验通过后打包：

```text
<python> <oil-skill-creator>/scripts/package_skill.py <skill-path> --public --strict --weak-model --universal
```

同样内容每次打出的包完全一致，默认排除 Git、虚拟环境、缓存、evals 和运行 workspace。

## 完成标准

- 创建：价值成立，主流程可执行，静态校验通过，已说明效果证据与未验证项。
- Review：结论有证据，缺陷与取舍分开，给出按优先级排列的最小整改方案，没有修改文件或外部状态。
- 整改：需求适用表逐项有实现和验证证据，凭据项覆盖页面、保存、恢复和实际业务读取；P0、P1 已处理或由用户明确接受；相关回归测试通过，没有覆盖无关内容；做了前后效果对照的，快照和对照证据完整。

交付时只报告文件路径、主要能力、程序与测试结果、已确认的兼容范围、效果证据和剩余风险。不复述整个 Skill，也不把执行过程写回正式文件。
