<p align="center">
  <img src="./assets/readme/hero.png" width="100%" alt="oil-skill-creator：像做产品一样写 Skill">
</p>

创建、评审和改进 Skill，检查功能边界、首次配置、执行稳定性、兼容性与发布交付。

> 静态校验通过，只能证明已知结构没有问题，不能证明一个 Skill 真的有用。

## 三种使用模式

| 模式 | 什么时候使用 | 默认结果 |
| --- | --- | --- |
| 创建 | 从零设计一个可重复使用的 Skill | 可执行、可验证的 Skill |
| Review | 只想知道现有 Skill 哪里有问题 | 按 P0、P1、P2 排列的只读报告 |
| 整改 | 已经确认需要修复或优化 | 按需保留基线、局部修改并完成复验 |

Review 不修改任何文件。整改时只有需要前后效果对照，才先保存旧版快照。

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

### 运行要求

- Python 3.10+。核心脚本只用标准库，不需要安装依赖、密钥或初始化配置。下文的 `<python>` 在 macOS 和 Linux 通常是 `python3`，Windows 通常是 `py -3`。
- 命令安装需要 `npx`。Node.js 只是安装工具的依赖，核心流程不需要它。
- 可选的凭据输入页需要 Node.js 22.18+。

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

已有文件里写清楚的用户、输入、输出或平台限制，不会再问你。只有缺少的决定会改变结果、需要新权限或可能覆盖内容时，才会一次问完。

## 它重点检查什么

### 值不值得做

先确认它解决的是重复问题，并且相比普通 Agent 有看得到的改善。一次性任务、简单提醒或普通 Agent 已经做得稳定的工作，不会被强行包装成 Skill。

### 触发边界清不清楚

description 写清该接哪些请求、不该接哪些相似请求。需要时用固定的正反向测试集实测触发准确率，不凭关键词或直觉判断。

### Agent 和程序分工是否合理

语义、策略、例外和主观质量交给 Agent 或你来判断；结构、格式、统计、组装和打包这类确定步骤交给程序。这样既减少遗漏，也不会把主观问题硬编码成一棵越长越大的规则树。

### 首次使用顺不顺

能自动发现、风险低、可撤销的准备工作直接完成，登录、密钥、安装和覆盖先问你。失败后保留可用的中间结果，并说明怎么恢复。

### 大型产物和复杂配置

产物容易写成难以维护的巨型单文件时，检查能否按稳定边界拆开、单独验证和局部重做，再由脚本组装；不按固定行数机械拆分。复杂配置或反复预览，用读取 manifest 的固定页面代替每次临时生成界面。

### 密钥输入

目标 Skill 需要在本机输入 API Key 时，可以装上随附的[凭据输入页](references/credential-ui.md)：一个页面填 1 到 16 个 Key，密钥存进系统凭据库（macOS 钥匙串、Windows 凭据管理器或 Linux Secret Service），不经过聊天，也不写进配置文件。已有安全入口时优先复用；OAuth、CI 和远程服务器另按实际需求设计。

### 弱模型能否看懂、Token 花在哪

检查入口、模式、术语、分支位置和资源读取时机。主文件只保留主流程，阶段细节按需读取，同一规则只写在一处。

## 稳定工具

| 工具 | 用途 |
| --- | --- |
| `scaffold_skill.py` | 预览并创建最小 Skill 骨架，拒绝覆盖已有目录 |
| `install_credential_ui.py` | 向现有 Skill 安装凭据输入页，生成非敏感声明并保护已有修改 |
| `validate_skill.py` | 检查结构、链接、重复、个人路径、明文凭据、弱模型风险和宿主中立 |
| `review_requirements.py` | Review 时收集凭据和生成工具线索，供需求适用表逐项核对 |
| `version_skill.py` | 预览或写入 `metadata.version` 的初始版本与升版 |
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

## 效果评估

创建模式比较“使用 Skill”和“普通 Agent”；整改需要证明效果时，比较当前版本和写入前快照。程序负责准备固定目录、检查数据格式和聚合结果，子 Agent 等隔离执行环境分别运行两边，审美、文案和整体体验由人来判断。

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
| 可选凭据输入页 | Node.js 22.18+；macOS 原生保存与回读已验证，Windows / Linux 待实机验证 |

脚本使用 `pathlib` 和 UTF-8，不依赖 bash、PowerShell、Homebrew 或单平台打开命令。兼容性只描述已经实现或验证过的范围。

## 数据与安全边界

- 只处理用户明确指定的本地文件；普通配置与密钥分开保存；
- 本项目核心流程无需密钥；可选凭据输入页用于目标 Skill，JSON 只保存非敏感声明和凭据引用；
- 系统凭据库不能单独隔离同一用户下有任意代码执行权限的 Agent；业务读取程序仍须可信，不向上下文回传密钥；
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

测试覆盖文件保护、快照、基础结构、资源链接、敏感信息、宿主中立、内容重复、弱模型结构、效果评估、触发测试、版本管理和可重复打包。

凭据输入页另有多 key 存储隔离、并发页面会话和多变量注入测试。[跨平台工作流](.github/workflows/credential-ui.yml) 在推送、PR 或手动触发时测试三种桌面系统与两个 Node.js 版本，使用随机假凭据验证真实系统后端。工作流配置完成不等于三端已经通过，需要以实际运行记录为准。

需要继续设计 GitHub 首页时，可以使用 [beautify-github-readme](https://github.com/oil-oil/beautify-github-readme) 调整阅读顺序或制作视觉资源；它不是安装或运行依赖。

## 许可证

[MIT](./LICENSE)
