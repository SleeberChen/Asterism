# asterism-code —— 项目工程目录

> 独立 git 仓库。职责：工程代码 + 开发相关文档。
> 关联导航见工作空间根目录 `README.md`。

## 目录约定

| 目录 | 职责 |
|---|---|
| `asterism/` | 工程根（将承载 `cn.asterism.*` 包） |
| `tools/` | 工程脚手架工具 |

## 当前状态

**工程代码待 P8 阶段生成**。本仓目前仅有目录占位与导航文件。

## 版本管理

- 本仓库**独立版本控制**，与 `asterism-docs` / `asterism-ops` / `nuts-tech` 互不耦合。
- 跨仓引用统一格式：`<repo>:<path>@<ref>`（如 `asterism-docs:10-spec/编号登记册.md@main`）。

## 边界

工程内规范随代码走，由工程 CI 管理（见《文档体系规范》§12.2）。项目全生命周期文档在 `asterism-docs` 仓。
