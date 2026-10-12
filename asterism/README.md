# asterism —— 工程根（包 `asterism.*`）

> 版本：V0.1（P8 骨架首版，2026-10-09）　状态：已生成骨架 + 核心 + 示范 RAG 应用
> 依据：`asterism-docs/20-design/P5-技术架构`（V0.2）+ 工程提案 `.workbuddy/proposals/P8-项目工程结构提案.md`

本目录承载 Python 包 `asterism.*`，技术栈 Python 3.13 + FastAPI，DDD 四层 + 一切皆插件。

## 结构

- `seedwork/`：跨层共享内核（错误码 `AST-ERR-{4位}` / 异常 / 结构化日志三要素+L0~L4 脱敏 / 八通道隔离上下文）。零框架依赖，领域层可安全引用。
- `interfaces/` `application/` `domain/` `infrastructure/`：DDD 四层；每层含 12 个 `APP-*` 应用子包。
- `plugins/`：插件内核（`kernel` = APP-PLUGIN）+ 四类插件（model/tool/skill/memory）。
- `main.py`：组合根 + ASGI 工厂 + 全局异常映射（不泄露内部细节，TC-16）。

## 关键纪律（落地时已遵守）

- 依赖单向：接口→应用→领域←基础设施；领域零框架依赖（TC-09/10）。
- 插件内核不反向依赖四类插件、四类互不依赖（TC-11）。
- 隔离上下文框架统一注入，业务代码不手拼过滤条件（TC-12）。
- 缓存键强制含 `tenant_id`（TC-13）；密钥不入库、只写不读（TC-01/02）；配置外部化（TC-17）。
- 错误码统一 `AST-ERR-{4位}`；结构化日志带租户/用户/请求三要素并脱敏（TC-14/§4.3）。

## 部署形态双模（P0 CON05）

同一份代码；独立部署自带 `APP-SYSTEM`，并入星云复用星云权限；差异仅出现在兼容点（CP-*）。
