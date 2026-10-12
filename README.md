# asterism-code —— 星群工程代码

> 独立 git 仓库。职责：Python 工程代码（包 `asterism.*`）+ 工程工具。
> 设计依据：`asterism-docs/20-design/P5-技术架构`（DDD 四层 / 包结构 / 工程规范 / 技术栈）。
> 关联导航见工作空间根目录 `README.md`；本仓规范随代码走，由 CI 管理。

## 技术栈（实测锁定，2026-10-09）

| 类别 | 组件 | 版本 |
| --- | --- | --- |
| 运行时 | Python（CPython） | 3.13 |
| Web | FastAPI / Uvicorn / Pydantic | 0.143.0 / 0.54.0 / 2.14.0 |
| AI 编排 | LangChain / LangGraph / deepagents | 1.4.4 / 1.2.14 / 0.7.23（MIT） |
| 存储/HTTP | PyYAML / python-dotenv / httpx | 6.0.3 / 1.2.4 / 0.28.1 |
| 构建/质量 | uv / pytest / pytest-cov / ruff / mypy | 0.12.1 / 9.1.1 / 7.1.0 / 0.16.10 / 2.4.0 |

> 版本由 `uv` 实测解析并锁定为精确版本（P5 TC-06：禁止 latest / 范围 / 留空）；
> `uv.lock` 必须入库（TC-07）。AI 编排栈经核实为 MIT（消除 P5「deepagent 许可不明」疑虑；
> P5 所写 `deepagent` 即 PyPI `deepagents`）。

## 工程结构（方案 A：分层优先）

```
asterism/                      # 包根 asterism.*
├── seedwork/                  # 跨层共享内核：错误码/异常/结构化日志/隔离上下文（零框架依赖）
├── interfaces/                # 接口层：HTTP/RPC/消息入口、鉴权、校验、错误码映射
├── application/               # 应用层：用例编排、事务边界、跨域协调
├── domain/                    # 领域层：零框架依赖；仅依赖 seedwork 与插件内核接口
├── infrastructure/            # 基础设施层：持久化/缓存/外部供应商/可观测（实现领域端口）
│   ├── config/                #   配置外部化 + 开关白名单（TC-17/23）
│   └── cache/                 #   缓存抽象（键强制含 tenant_id，TC-13）
├── plugins/                   # 插件区：kernel（APP-PLUGIN）+ model/tool/skill/memory
├── bootstrap/                 # 应用装配区（组合根，root 区）：逐应用 include_router + 装配用例
│   ├── registry.py            #   APP_WIRINGS 注册表 + register_apps(app)
│   ├── compliance.py          #   wire_compliance(app)（横切基座，须先装配）
│   ├── rag.py                 #   wire_rag(app)
│   ├── model.py               #   wire_model(app)
│   └── system.py            #   wire_system(app)（仅独立部署形态装配）
└── main.py                    # 组合根入口（薄）：ASGI 工厂 + 全局异常 + 调 register_apps
tests/                         # 三级测试：unit / integration / e2e
configs/                       # 环境配置覆盖层（base/dev/test/prod）
tools/                         # 工程工具：架构守护契约 + GATE-04 脚本
```

四层下各含 12 个应用子包（core/plugin/model/tool/skill/memory/factory/system/compliance/
observ/nfr/plan，对应 P3 的 12 个 `APP-*`）。`rag` 子包为示范业务应用（内部知识库问答），
展示在框架上构建应用的标准垂直切片。

## 12 个应用子包 · 模块编辑指引

> 依据：`asterism-docs/20-design/P3-应用架构/01-应用划分与边界.md`（12 `APP-*` 职责矩阵）。
> 每个子包默认仅 `__init__.py`（空骨架）。新增业务时，按「领域模型/端口 → 用例 → 接口 →
> 基础设施实现」顺序落码。下表给出**每个应用在各层该放什么模块**，以及它复用的插件/共享内核。
> `rag` 垂直切片是可直接照抄的参考范式。

### 逐应用模块编辑表

| 应用（`APP-*` / `BC-*`） | `domain/`（领域层） | `application/`（应用层） | `interfaces/`（接口层） | `infrastructure/`（基础设施层） | 复用插件 / 共享内核 |
| --- | --- | --- | --- | --- | --- |
| **CORE** `BC-RUNTIME`（C01-04,06） | 运行时聚合/编排底座领域服务、领域事件 | `BootstrapUseCase`、`ServiceGovernanceUseCase`（服务规范守护门面） | 通用中间件基类、统一响应封装基类（HTTP 入口在各能力 APP） | 运行时装配实现、服务规范守护实现、分层守护接入 | `seedwork`（异常/日志/上下文） |
| **PLUGIN** `BC-PLUGIN`（C05） | 插件契约领域视图（可选端口） | `RegisterPluginUseCase`、`StartAllUseCase`（生命周期） | 插件管理端点（仅独立部署可选） | —（内核在 `plugins/kernel`） | **`plugins/kernel/base.py`（`Plugin` 协议）+ `registry.py`（注册表）已建**；各插件型 APP 在 `plugins/<kind>/` 实现 `Plugin` 子类 |
| **MODEL** `BC-MODEL`（C08） | 模型调用端口/领域模型（如 `GenerationPort`，见 rag） | `ModelRoutingUseCase`（供应商切换/回退） | `/api/v1/models`（可选） | 供应商配置加载、回退实现 | **`plugins/model/base.py`（`ModelProvider`）+ 各供应商桩/适配（已建 `stub.py`）**；新增供应商加 `plugins/model/<vendor>.py` |
| **TOOL** `BC-TOOL`（C09） | 工具调用端口、领域模型 `ToolCall`/`ToolResult` | `ToolInvokeUseCase`（注册+权限校验+调用审计） | `/api/v1/tools` | 工具实现注册、调用审计落盘 | **`plugins/tool/base.py`（`ToolProvider`）** |
| **SKILL** `BC-SKILL`（C10） | 技能状态机（加载/启用/停用/卸载）、领域模型 | `SkillLifecycleUseCase` | `/api/v1/skills` | 受管控来源加载、沙箱边界实现 | **`plugins/skill/base.py`（`SkillProvider`）** |
| **MEMORY** `BC-MEMORY`（C11） | 记忆聚合（会话/短期）、端口 `MemoryPort`、截断/保留策略 | `MemoryReadUseCase`/`MemoryWriteUseCase`（强制租户/会话隔离） | `/api/v1/memory` | 记忆存储实现（进程内/外部）、租户命名空间隔离 | **`plugins/memory/base.py`（`MemoryProvider`）** |
| **FACTORY** `BC-APPFAB`（C07） | 应用蓝图/模板聚合（RAG/Agent）、默认编排链路 | `CreateAppUseCase`（生成骨架/默认链路） | `/api/v1/apps`（创建） | 蓝图加载、编排链路装配（写入运行态配置） | 装配入口复用 **CORE** 编排底座 |
| **SYSTEM** `BC-SYSMGMT`（C14，仅独立部署） | 用户/角色/菜单/审计查询聚合与规则 | 用户/角色/菜单/审计查询用例 | `/api/v1/sys/*` | 用户/角色/权限存储（仅独立部署；并入星云不启用） | 鉴权读取走 **COMPLIANCE**（IC-07） |
| **COMPLIANCE** `BC-COMPLIANCE`（C12） | 认证/授权模型、审计实体、脱敏规则、break-glass 五要素 | 认证接入、审计埋点、脱敏开关用例（八步链 M1 接入点） | 认证中间件/鉴权依赖注入基类（各 APP 路由复用）+ `/api/v1/audit` 查询 | 认证实现（JWT 等）、审计写入、脱敏实现（接 `seedwork.logging.redact`） | 强审计/脱敏贯穿全应用（等保二级、留存≥180天） |
| **OBSERV** `BC-OBSERV`（C13,17） | 指标/追踪领域模型、计数器、三级测试抽象 | 可观测采集、测试验证用例 | `/metrics` 暴露 + 追踪查询 | 指标采集实现、mock 层（接 `seedwork.logging`） | 埋点契约 IC-09 |
| **NFR** `BC-NFR`（C16,19） | NFR 七类框架模型、量化模板、校验清单聚合 | `NfrValidateUseCase`（生成校验结论供 CI 消费） | 无对外服务（内部消费）；`/api/v1/nfr/report` 可选查询 | 校验清单加载、门禁复用（接 `tools/check_*`） | 校验结论由 CI 门禁（GATE-*）同步消费 |
| **PLAN** `BC-PLAN`（C18） | 规划/子任务/进展聚合与规则 | 规划拆解、状态同步、总览用例 | `/api/v1/plan` | 规划台账存储（**禁止引用生产数据**） | 只读规划契约 |

### 通用编辑规则（四条红线 + 插件纪律）

- **领域层（零框架依赖）**：只放纯逻辑 + 端口（`Protocol`）。禁止 `import fastapi`/`uvicorn`/具体供应商；
  只依赖 `seedwork` 与 `plugins.kernel` 接口（P5 TC-10）。
- **应用层（只编排，不含 IO）**：注入隔离上下文（`seedwork.context`），**禁止手拼租户过滤**（TC-12）；
  异常统一映射为 `AsterismError`（TC-15/16），不吞、不返回 `None`。
- **接口层（只做协议适配）**：Pydantic `Schema` + 路由 + 鉴权依赖；租户上下文由
  `interfaces/rag/router.py` 的 `_resolve_tenant` 模式统一注入（框架注入，缺失抛 `AST-ERR-2004`）。
- **基础设施层（实现领域端口）**：外部依赖/存储驱动放此层；密钥**只写不读**（`settings.SecretRef`，TC-01/02）；
  缓存键**强制含 `tenant_id`**（`cache_key.build_cache_key`，TC-13）；结构化日志走 `seedwork.logging`。
- **插件纪律（TC-11）**：模型/工具/技能/记忆四类能力经 `plugins/<kind>/` 注册，业务逻辑不写进业务层；
  新增供应商/工具 = 新增 `plugins/<kind>/<name>.py` 实现对应 `Provider` 协议，内核不感知。
- **组合根例外**：`main.py` 与 `bootstrap/` 是唯一合法装配点，依赖倒置越界只发生在此处（P5 TC-09）。

### 分层建模规范（模型类型选择）

> **一句话规则**：**越靠外（离框架 / 外部世界越近）越用 Pydantic，越靠内（领域核心）越用纯 Python
> （`dataclass` / 普通类）**；跨框架流转的「状态字典」用 `TypedDict`。
> 依据是 P5 `TC-10`（领域层零框架依赖）——**不一刀切，按层取用**。

#### 1. 分层对照表（含「为什么」与本仓实例）

| 层 / 位置 | 用什么 | 为什么 | 本仓实例 |
| --- | --- | --- | --- |
| **interfaces** 接口层 | **Pydantic `BaseModel`** | 处在信任边界，需要入参校验、序列化、自动生成 OpenAPI | `interfaces/rag/schemas.py`、`interfaces/model/schemas.py`、`interfaces/compliance/schemas.py` |
| **application** 应用层 | **优先 `dataclass`** | DTO 多为进程内传递，无需校验 / 序列化开销；**仅当**需跨进程传输、序列化或强校验时才升级为 Pydantic | 当前用例直接返回领域对象（`application/rag/use_case.py`），未额外建 DTO |
| **domain** 领域层 | **`dataclass` 或普通类** | 领域必须**框架零依赖**（`TC-10`）；`dataclass` 具备构造期行为、默认值与不变量承载能力 | `domain/rag/model.py`、`domain/model/model.py`、`domain/compliance/model.py`、`domain/system/model.py` |
| **infrastructure** 基础设施层 | **Pydantic Settings / `BaseModel`** | 配置与外部客户端参数天然需要校验 + 外部化（`TC-17`）；本层**允许**框架依赖 | 当前为自研 `Settings`（`infrastructure/config/settings.py`，YAML 分层加载 + `SecretRef` 只写不读）；后续引入 `pydantic-settings` 亦符合本规范 |
| **跨框架状态结构** | **`TypedDict`** | 消息状态 / 工作流 State 是**跨框架传递的字典**（如 LangGraph 节点间），只需形状声明 | 本仓暂未落地；校验器与示例见 `seedwork/typeddict.py` + `tests/unit/seedwork/test_typeddict.py` |

#### 2. 判定流程（拿不准时自上而下问）

1. **是不是接口的请求 / 响应？** → Pydantic `BaseModel`（interfaces）
2. **是不是跨框架传递的状态字典（消息 / 工作流 State）？** → `TypedDict`
3. **是不是配置或外部客户端参数？** → Pydantic Settings / `BaseModel`（infrastructure）
4. **是不是领域实体 / 值对象？** → `dataclass`（domain），**禁用 Pydantic**
5. **剩下的应用层 DTO？** → 默认 `dataclass`；需跨进程 / 序列化 / 强校验才用 Pydantic

#### 3. 正例与反例

| 场景 | ✅ 正例 | ❌ 反例 |
| --- | --- | --- |
| HTTP 请求体 | `class QueryRequest(BaseModel)`（interfaces） | 在 domain 用 `BaseModel` 定义请求体 |
| 领域实体 | `@dataclass class Answer`（domain） | `class Answer(BaseModel)` —— 领域被框架污染，违反 `TC-10` |
| 工作流 State | `class RagState(TypedDict)` | 用 `TypedDict` 定义领域实体 `Query`（无构造期校验） |
| 配置 | Pydantic Settings / 自研 `Settings`（infrastructure） | 配置硬编码在 domain |

#### 4. 补充约定与踩坑

- **`TypedDict` 不作领域实体 / 值对象**：它只提供静态类型信息，运行时就是普通 `dict`，
  **无运行时校验**，也没有构造期行为承载能力——那是 `dataclass` 的职责。
- 跨框架 State 若需运行时形状校验：用 `seedwork.typeddict.validate_typed_dict`
  （缺必填键 / 顶层类型不符 → `AST-ERR-3001`，**不吞、不兜底**，`TC-15`/`TC-16`）。
- **实测坑**：定义 `TypedDict` 的模块**不要**启用 `from __future__ import annotations`——
  注解被推迟为字符串后 `NotRequired[...]` 无法识别，可选键会被**误判为必填**（运行期误报缺字段）。
- **自查命令（领域纯净）**：

  ```bash
  grep -rn "TypedDict\|pydantic\|BaseModel" asterism/domain/   # 期望命中 = 0
  uv run python tools/check_layering.py                        # GATE-04 分层守护
  ```

> **权威设计出处**：P5 `20-design/P5-技术架构/14-技术约束与工程规范.md` §2.3（规则定义）；
> P3 `20-design/P3-应用架构/01-应用划分与边界.md` §9.3 为索引（不重定义，防双源漂移）。

### 新增一个应用如何装配（开闭原则）

应用装配按「一应用一文件」下沉到 `asterism/bootstrap/`，`main.py` 不感知任何具体应用：

```
asterism/bootstrap/<app>.py    →  暴露 wire_<app>(app)：include_router + 装配 app.state.<app>_use_case
asterism/bootstrap/registry.py →  APP_WIRINGS 追加一行
asterism/main.py               →  不改动（只调 register_apps(app)）
```

- **为何独立成区**：装配须同时 import `interfaces`（路由）+ `application`（用例）+ `infrastructure`（适配器），
  而依赖矩阵禁止 `interfaces`/`application` → `infrastructure`，故装配代码**不能放进任何一层**，
  只能位于四层之外（与 `main.py` 同属组合根，GATE-04 按 `root` 豁免，已在
  `tools/architecture_layering.toml` 显式登记）。
- **纪律**：`bootstrap/` 只做装配（`include_router` + `app.state.*`），**禁止写业务逻辑**，
  避免本区退化成分层逃生舱。

### 横切复用：鉴权由 APP-COMPLIANCE 统一提供

按 P3 §5 单写者表，**认证态 / 授权判定的权威写者＝`APP-COMPLIANCE`**，其余应用只读复用，
禁止各自实现鉴权（防重复实现、防口径漂移）。已落地的两个复用点：

| 复用件 | 位置 | 用途 |
| --- | --- | --- |
| `resolve_tenant_context` | `interfaces/compliance/deps.py` | 隔离上下文**统一注入点**（TC-12），各应用路由复用；rag / model / system 均已改为依赖它 |
| `require_permission(resource, action)` | 同上 | 可选鉴权开关：判定 + 留痕由 COMPLIANCE 完成，拒绝返回 403（`AST-ERR-2002`）；system 路由已启用 |

演示策略：请求须带 `X-User-Id`；`admin` / `grant` / `break_glass` 类动作须 `X-User-Id: admin`。

### 统一响应规范（强制）

所有 HTTP 响应必须经 `asterism/interfaces/common/result.py` 的 `ApiResult[T]` 信封包裹；
错误映射集中在 `asterism/main.py` 的全局异常处理器，路由内**不得**手写
`JSONResponse(exc.to_dict())`。这是强制规范（2026-10-12 落地，覆盖全部接口层）。

- **信封形态**：`{code, message, data, request_id}`
  - 成功：`code="0"`、`message="ok"`、`data=<业务负载>`、`request_id=<链路标识>`；
    路由返回 `ApiResult[<业务 Schema>]`，`response_model` 同步设为 `ApiResult[...]`，业务负载置于 `data`。
  - 失败：`code=AST-ERR-*`、`message=<用户可读信息>`、`data=null`、`request_id=<链路标识>`；
    由全局处理器把 `AsterismError` / `RequestValidationError`（→422，`AST-ERR-3001`）/ 未预期异常
    （→500，`AST-ERR-5001`）统一映射为 `ApiResult.fail(...)`。
- **路由内禁令（强制）**：禁止在路由中 `try/except AsterismError → JSONResponse(...)`，
  失败一律上抛交全局处理器包裹；鉴权依赖（`deps.py`）抛 `BusinessError`，同样由全局处理器映射
  （含「鉴权未装配即拒绝服务」的 403 `AST-ERR-2002`，不兜底）。
- **豁免**：`204 No Content` 与 `/healthz` 探针按设计不包裹（无响应体）。
- **SSE 流式**：成功帧为 `ApiResult[<ChunkSchema>]` 逐帧序列化；错误帧为 `ApiResult.fail(...)`
  配 `event: error`，与 JSON 接口同信封。
- **测试断言**：成功业务字段取 `resp.json()["data"][...]`；错误取 `resp.json()["code"]`（信封顶层）。

### 运行形态双模（P0 CON05 / P3 §7.1）

同一套业务代码，由 `configs/base.yaml` 的 `deployment.mode` 决定 APP-SYSTEM 是否启用：

```bash
uv run python -m asterism.main                              # standalone（默认）：12/12 应用
ASTERISM__DEPLOYMENT__MODE=nebula uv run python -m asterism.main   # 并入星云：11/12，sys 路由不注册
```

- `standalone`：独立部署，自带最小系统管理（用户 / 角色 / 菜单）；
- `nebula`：用户 / 权限由星云公共权限服务（`BC-TENANT` / `BC-PERM`）提供，`APP-SYSTEM` 自动跳过装配。

## 依赖方向（P5 TC-09 / §2.2）

`接口层 → 应用层 → 领域层 ← 基础设施层`；领域层零框架依赖；插件内核不反向依赖四类插件、
四类插件互不依赖（TC-10/11）。`tools/check_layering.py` 为机器守护（GATE-04）。

## 快速开始

```bash
uv sync                      # 安装依赖（含 dev 组），创建 .venv
uv run python -m asterism.main   # 启动 ASGI 服务（默认 :8000）
curl -X POST localhost:8000/api/v1/rag/query \
  -H 'X-Tenant-Id: demo-tenant' -H 'Content-Type: application/json' \
  -d '{"query":"Asterism 采用什么架构？"}'
```

## 测试

```bash
uv run pytest                 # 三级测试（单元/集成/端到端）
uv run pytest --cov=asterism --cov-report=term-missing   # 覆盖率（核心域行覆盖≥80%/底线60%）
uv run python tools/check_layering.py   # 分层依赖守护（GATE-04）
```

## 质量门禁

P5 定义 14 条 CI 门禁（GATE-01~14）。当前 `asterism-ops/ci-cd/` 已实装 4 条（GATE-05/11/12/14），
差值 10 待本工程真实代码落地后补齐（详见 P5 第 14 章）。本仓自带的 `tools/check_layering.py`
对应 GATE-04（分层依赖），可在合入前本地运行。

## 版本管理

本仓库独立版本控制；跨仓引用统一 `<repo>:<path>@<ref>`（如 `asterism-docs:10-spec/编号登记册.md@main`）。
