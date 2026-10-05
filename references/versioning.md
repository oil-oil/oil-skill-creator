# Skill 版本管理

版本号用于标记一个 Skill 对外行为的兼容变化。不是每个临时 Skill 都必须有版本号；需要独立发布、被其他仓库引用或让用户判断升级影响时，再启用版本管理。

## 版本字段

在 `SKILL.md` frontmatter 使用 Agent Skills 规范中的自定义元数据字段：

```yaml
metadata:
  version: "1.2.3"
```

版本使用 `MAJOR.MINOR.PATCH` 三段格式，写成多行映射，用双引号或不加引号，行尾不加注释。很多发版和更新脚本按行读取版本号，单行映射 `metadata: {version: "1.2.3"}`、单引号和行尾注释都会让它们读不到。`validate_skill.py` 会检查格式，并确认按行读取能得到同一个版本号。

`metadata.version` 是 Skill 作者约定的版本信息，不会自动让任何安装器固定或切换版本。具体安装器是否支持版本选择，需要单独验证。

## 何时升级

- **PATCH**：修复错误、改善可靠性或补充说明，不改变原有触发方式、输入、输出和工作流约定。
- **MINOR**：增加可选能力、兼容的输入或扩展流程，不破坏既有用法。
- **MAJOR**：删除或重命名能力，或者不兼容地改变触发边界、输入输出、依赖、权限和主要工作流。

一次提交不一定对应一次发布。确认一组变更要作为新版本交付时，再升版并发布；不要把版本历史或修改记录写进 `SKILL.md` 正文。

## 设置和升版

脚本默认只预览，文件写入必须显式传 `--write`：

```text
<python> <oil-skill-creator>/scripts/version_skill.py <skill-path> --initial 1.0.0
<python> <oil-skill-creator>/scripts/version_skill.py <skill-path> --initial 1.0.0 --write
<python> <oil-skill-creator>/scripts/version_skill.py <skill-path> --bump patch
<python> <oil-skill-creator>/scripts/version_skill.py <skill-path> --bump patch --write
```

`--initial` 只适用于尚无版本的 Skill；`--bump` 要求已有有效版本，并自动将较低位归零。两种操作都不会覆盖 Skill 正文、自动提交 Git、创建标签或发布远端版本。写入后运行 Skill 校验和仓库自己的检查。

## Git 标签与发布

Skill 所在仓库是 Skill 内容的唯一来源。发布时先提交并推送 Skill 和版本字段，再创建 `v<版本号>` 标签，例如 `v1.2.3`。同一个版本号只发布一次；标签已经存在时，先升版再发布。更新说明放在 GitHub Release，不放进 `SKILL.md`。

旧 Skill 尚无版本时，先查看当前功能成熟度、Git 历史和已有标签，再确定初始版本。没有历史标签时，新版本号只作为开始管理版本的基线，不代表过去已经发布过同号版本。
