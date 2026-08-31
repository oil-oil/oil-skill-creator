<p align="center">
  <img src="./assets/readme/hero.png" width="100%" alt="oil-skill-creator：像做产品一样写 Skill">
</p>

`oil-skill-creator` 用来创建、Review、整改和发布 Agent Skill。它关心的不只是说明有没有写完，而是这个 Skill 是否值得安装、能否稳定执行、是否适合能力较弱的模型，以及效果不好时能不能找到真正的设计原因。

> 静态校验通过，只能证明已知结构没有问题，不能证明一个 Skill 真的有用。

## 你会得到什么

- 最小且清楚的 Skill 文件结构，不为了完整感创建空目录；
- 明确的触发与反向边界，减少误触发和漏触发；
- 静默、可恢复的首次使用流程；
- 用程序固定确定、重复、失败敏感的步骤；
- 需要前后效果对照时使用的不可变快照与固定基线；
- 触发测试、效果聚合、本地评审页和可重复发布包；
- 对 Token、弱模型可读性、宿主中立和跨平台范围的检查。

## 三种使用模式

| 模式 | 什么时候使用 | 默认结果 |
| --- | --- | --- |
| 创建 | 从零设计一个可重复使用的 Skill | 可执行、可验证的 Skill |
| Review | 只想知道现有 Skill 哪里有问题 | 按 P0、P1、P2 排列的只读报告 |
| 整改 | 已经确认需要修复或优化 | 按需保留基线、局部修改并完成复验 |

Review 默认不修改文件。只有明确要求整改时才开始写入；仅在需要前后效果对照时保存快照。

## 安装

### 让 Agent 安装

复制下面的仓库地址，告诉你正在使用的 Agent：“请帮我安装这个 Skill。”

```text
https://github.com/oil-oil/oil-skill-creator
```

### 使用命令安装

```shell
npx skills add oil-oil/oil-skill-creator
```

该安装方式需要本机能够运行 `npx`，但 Node.js 不是 Skill 的运行依赖。

核心脚本要求 Python 3.10 或更高版本，只使用标准库，无需安装额外依赖，也不需要密钥或初始化配置。

下文中的 `<python>` 表示已确认版本不低于 3.10 的 Python 解释器：macOS 和 Linux 通常使用 `python3`，Windows 通常使用 `py -3`。

## 开始使用

直接用自然语言说明目标和写入权限：

```text
用 oil-skill-creator 创建一个可公开发布的 Skill。
```

```text
只 Review 这个 Skill，按优先级给出证据，不要修改文件。
```

```text
整改这个现有 Skill；如果需要前后效果对照，先保留旧版基线，再修复和复验。
```

```text
验证新版是否比普通 Agent 或旧版更有效。
```

如果已有文件已经说明用户、输入、输出或平台限制，Skill 会直接读取，不会重复提问。只有缺少的决定会改变结果、需要新权限或可能覆盖内容时，才会集中询问。

## 它重点检查什么

### Skill 是否值得做

先确认它解决的是重复问题，并且相比普通 Agent 有可见改善。一次性任务、简单提醒或已经足够稳定的工作，不会被强行包装成 Skill。

### Agent 与程序是否分工合理

语义、策略、例外和主观质量交给 Agent 或用户判断；结构、格式、按需快照、统计、组装和打包等确定流程交给程序。这样既减少遗漏，也避免把主观问题硬编码成规则树。

### 大型产物是否容易生成和修改

当目标 Skill 容易生成难以维护的巨型单文件时，会检查产物能否按稳定边界拆分、独立验证和局部重做，再由脚本确定性组装。不会按固定行数机械拆分。

### 是否需要可复用操作页面

复杂配置、反复预览或人工确认不必每次临时生成界面。适合时，Skill 会使用固定页面读取 manifest，由程序负责加载和保存，Agent 只串联操作流程。

### 能力较弱的模型能否看懂

检查入口、模式、术语、分支位置和资源读取时机。主文件只保留主流程，阶段细节按需读取，同一规则不在多个文件重复。

## 稳定工具

| 工具 | 用途 |
| --- | --- |
| `scaffold_skill.py` | 预览并创建最小 Skill 骨架，拒绝覆盖已有目录 |
| `validate_skill.py` | 检查结构、链接、重复、个人路径、明文凭据、弱模型风险和宿主中立 |
| `snapshot_skill.py` | 在需要效果对照时保存不可覆盖的旧版基线 |
| `prepare_evaluation.py` | 创建固定的新版、普通 Agent 或旧版对照目录 |
| `aggregate_evaluation.py` | 聚合执行结果、耗时和检查数据 |
| `generate_review.py` | 生成不自动打开浏览器的本地静态评审页 |
| `score_triggers.py` | 统计正向、反向和保留集上的触发表现 |
| `package_skill.py` | 生成内容稳定、默认不覆盖的 `.skill` 发布包 |

查看任一工具的参数：

```text
<python> scripts/validate_skill.py --help
```

公开发布或整改完成前，运行严格校验：

```text
<python> scripts/validate_skill.py <skill-path> --public --strict --weak-model --universal
```

只有产品明确依赖某个宿主时，才省略 `--universal`，并如实说明不兼容范围。

## 效果评估

创建模式比较“使用 Skill”和“普通 Agent”；整改需要证明效果时，比较当前版本和写入前快照。程序负责准备固定目录、检查数据格式和聚合结果，隔离执行者负责分别运行候选，人类负责审美、文案和整体体验等主观结论。

```text
<python> scripts/prepare_evaluation.py <skill-path> --mode create --iteration 1
<python> scripts/aggregate_evaluation.py <iteration-path>
<python> scripts/generate_review.py <iteration-path>
```

没有子 Agent 或等价的隔离执行能力时，仍可完成静态 Review、程序测试和作者试跑，但不能宣称已经完成独立对照。

## 兼容性

| 范围 | 当前状态 |
| --- | --- |
| Python | 3.10+，核心脚本只使用标准库 |
| macOS | 已运行自动化测试 |
| Windows / Linux | 已按标准库和跨平台路径实现，真实平台运行仍待验证 |
| 无浏览器或 GUI | 核心流程可用；评审页只生成文件，不自动打开 |
| 无子 Agent | 创建、静态 Review 和程序测试可用；独立效果对照降级 |
| 离线环境 | 核心脚本只处理本地文件，不联网 |

脚本使用 `pathlib` 和 UTF-8，不依赖 bash、PowerShell、Homebrew 或单平台打开命令。兼容性只描述已经实现或验证过的范围。

## 数据与安全边界

- 只处理用户明确指定的本地文件；普通配置与密钥分开保存；
- 本项目自身无需密钥，也不提供通用凭据适配器；它要求目标 Skill 优先使用系统凭据存储，JSON 只保存非敏感配置和凭据引用；
- 默认拒绝覆盖已有 Skill、快照、评审页、iteration 和发布包；
- 打包默认排除 Git、虚拟环境、缓存、评估数据和运行 workspace；
- 不负责执行目标 Skill 的实际业务任务；
- 不用 AI 自评分数替代视觉、文案等主观评审；
- Review、反馈、版本差异和单次任务记录不会写入正式 Skill。

## 开发与验证

```text
<python> -m unittest discover -s tests -v
<python> scripts/validate_skill.py . --public --strict --weak-model --universal
```

测试覆盖文件保护、快照、基础结构、资源链接、敏感信息、宿主中立、内容重复、弱模型结构、效果评估、触发测试和可重复打包。

需要继续设计 GitHub 首页时，可以使用 [beautify-github-readme](https://github.com/oil-oil/beautify-github-readme) 调整阅读顺序或制作视觉资源；它不是安装或运行依赖。

## 许可证

[MIT](./LICENSE)
