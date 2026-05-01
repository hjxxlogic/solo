# SOLO MVP 规格说明

## 1. 概览

SOLO 是一个本地优先、单用户使用的项目执行与观察底座。SOLO 本身不负责制定项目策略，也不内建固定的 Issue、Task、迁移、测试或发布流程。

SOLO 的职责是：

- 加载被管理项目提供的工作流定义。
- 在指定 repo、branch 或 worktree 中执行项目声明的动作。
- 调用 Codex CLI 帮助项目创建、修改或执行工作流。
- 展示项目提供的进度、状态、日志、diff 和产物。
- 提供 code-server 入口，方便用户进入对应工作区人工处理。

被管理项目的职责是：

- 定义自己的工作流。
- 决定工作项是什么，例如 issue、bug、feature、decoder migration、test batch、release step。
- 决定状态含义，例如 pending、running、review、completed、failed、skipped。
- 提供状态查询方式，例如 YAML 文件、脚本 JSON 输出或日志目录。
- 提供可执行动作，例如 dry-run、run-one、resume、mark-skip、mark-done。

因此，SOLO 是显示层与执行层，不是策略层。策略属于被管理项目。

---

## 2. MVP 范围

### 支持

- 单用户。
- 单个本地 git 仓库。
- 本地执行。
- SQLite 作为本地索引与运行记录缓存。
- 加载项目内的工作流定义。
- 工作流作用域支持 repo 全局、branch、worktree。
- Codex CLI 非交互执行。
- 按需启动 code-server。
- 通过 Server-Sent Events 推送运行状态和日志。
- 从被管理项目查询进度、状态与产物。

### 暂不支持

- 多用户。
- 云端同步。
- 权限系统。
- 容器或强沙箱隔离。
- 内建 PR 平台集成。
- 远程 Agent 执行。
- SOLO 内建具体业务流程策略。

---

## 3. 设计原则

### 项目拥有流程

工作流定义、状态文件、辅助脚本和项目规则都属于被管理项目。SOLO 只读取这些定义，并按定义执行。

### SOLO 只提供通用能力

SOLO 提供通用底层能力：

- 执行 Codex。
- 执行项目声明的本地动作。
- 打开 code-server。
- 管理本地运行记录。
- 查询 git 状态、diff、branch 和 worktree。
- 展示项目报告出来的状态。

### 状态以项目为准

SOLO 的 SQLite 不是项目状态的最终来源。SQLite 只缓存 UI 需要的索引、运行记录和最近一次查询结果。项目工作流返回的状态才是最终状态。

### 工作流可由 Codex 创建

SOLO 提供界面，让用户通过 Codex 在被管理项目中创建或更新工作流。Codex 修改的是项目自己的文件，例如 `.solo/global/`、`.solo/<git branch>/`、`scripts/`、`docs/` 或项目约定的状态脚本。

---

## 4. 核心概念

### Managed Project

被 SOLO 管理的本地 git 项目。SOLO 以该项目为根目录启动。

### Workflow

被管理项目定义的一组流程。Workflow 描述：

- 如何发现工作项。
- 如何查询状态。
- 有哪些可执行动作。
- 哪些视图应该展示给用户。
- 动作应该在哪个作用域执行。

### Scope

Workflow 的执行与查询作用域。

| 作用域 | 含义 |
| --- | --- |
| `global` | 作用于整个 repo，通常在 repo root 执行。 |
| `branch` | 作用于指定 branch，对应一个 checkout 或 worktree。 |
| `worktree` | 作用于指定 worktree，适合隔离任务执行。 |

### Work Item

Workflow 报告出来的工作项。SOLO 不规定 Work Item 的业务含义，只要求它有可展示的 id、标题、状态和原始数据。

### Action

Workflow 声明的可执行动作，例如：

- `dry-run`
- `run-one`
- `resume`
- `status-all`
- `mark-skip`
- `mark-done`
- `open-editor`
- `merge`

Action 可以由 Codex 执行，也可以由项目脚本执行。

### Run

SOLO 对某个 Action 的一次执行记录。Run 记录执行命令、作用域、日志、最终输出和退出码。

### View

Workflow 声明的 UI 展示入口，例如 board、status table、log、diff、JSON、Markdown、artifact list。

---

## 5. 系统架构

```text
Frontend (React)
├─ Project Dashboard
├─ Workflow Catalog
├─ Work Item Board
├─ Run Detail
├─ Status Viewer
├─ Logs Viewer
├─ Diff Viewer
├─ Artifact Viewer
└─ Open Editor

Backend (FastAPI)
├─ API
├─ Project Manager
├─ Workflow Loader
├─ Scope Resolver
├─ Status Collector
├─ Action Runner
├─ Codex Runner
├─ Editor Manager
├─ Git Manager
├─ Event Stream (SSE)
└─ SQLite Cache

Managed Project
├─ .solo/global/
├─ .solo/<git branch>/
├─ project scripts
├─ project state files
├─ project logs
└─ git repo / branches / worktrees

External
├─ codex CLI
├─ code-server
└─ git
```

---

## 6. 目录布局

SOLO 区分“项目拥有的 SOLO 配置数据”和“SOLO 本地运行时数据”。

```text
repo/
├─ .solo/
│  ├─ global/
│  │  ├─ workflows/
│  │  │  └─ {workflowId}.yaml
│  │  ├─ prompts/
│  │  │  └─ {promptId}.md
│  │  └─ status/
│  │     └─ {workflowId}.yaml
│  └─ {git branch}/
│     ├─ workflows/
│     │  └─ {workflowId}.yaml
│     ├─ prompts/
│     │  └─ {promptId}.md
│     └─ status/
│        └─ {workflowId}.yaml
└─ .solo-runtime/
   ├─ db.sqlite
   ├─ prompts/
   │  └─ {runId}.prompt.txt
   ├─ logs/
   │  ├─ {runId}.log
   │  └─ {runId}.final.txt
   ├─ worktrees/
   │  └─ {runId}/
   └─ editors/
      └─ {runId}.json
```

### 目录说明

- `.solo/`：被管理项目中的 SOLO 特定配置数据目录，可以提交到 git。
- `.solo/global/`：全局配置，也是所有 branch 和 worktree 的默认配置。
- `.solo/<git branch>/`：分支或该分支 worktree 的特定配置。
- `.solo/*/workflows/`：项目拥有的工作流定义。
- `.solo/*/prompts/`：workflow 使用的 prompt 模板。
- `.solo/*/status/`：项目可选的状态快照目录，是否提交由项目决定。
- `.solo-runtime/`：SOLO 本地运行时目录，默认应加入 `.gitignore`。
- `.solo-runtime/db.sqlite`：SOLO 本地缓存，不是项目真实状态来源。

### 配置覆盖规则

SOLO 加载配置时按作用域分层：

1. 先加载 `.solo/global/`。
2. 如果当前 scope 是 branch 或 worktree，再解析该 scope 对应的 git branch 名称。
3. 如果 `.solo/<git branch>/` 存在，则加载该目录。
4. 分支配置优先级高于 `.solo/global/`。

worktree scope 使用该 worktree 当前 checkout 的 git branch 名称作为配置名；MVP 不额外引入 `.solo/<worktree name>/` 目录。detached HEAD worktree 默认只使用 `.solo/global/`。

覆盖规则按名称执行：

- 同名 workflow 文件由 `.solo/<git branch>/workflows/` 覆盖 `.solo/global/workflows/`。
- 同名 prompt 模板由 `.solo/<git branch>/prompts/` 覆盖 `.solo/global/prompts/`。
- 同名 status 快照由 `.solo/<git branch>/status/` 覆盖 `.solo/global/status/`。
- 分支目录中新增的文件会追加到最终配置集中。
- MVP 不做 YAML 深度合并；同名配置文件以分支版本整体替换全局版本。

如果 git branch 名称包含 `/`，目录路径按 git branch 名称展开，例如 `feature/demo` 对应 `.solo/feature/demo/`。

---

## 7. Workflow 定义

MVP 使用 YAML 定义工作流，并使用 PyYAML 解析。后续可以支持项目脚本动态发现。

```yaml
id: sigrok-migration
title: Sigrok Decoder Migration
description: Migrate selected sigrok decoders with Codex.
scope:
  type: global | branch | worktree
  defaultRef: main
status:
  type: file | command
  path: .solo/global/status/sigrok-migration.yaml
  command: ["python3", "scripts/workflow_status.py", "--json"]
actions:
  - id: dry-run
    title: Dry Run
    runner: codex | command
    cwd: "{scopePath}"
    promptFile: .solo/global/prompts/dry-run.md
    command: ["python3", "scripts/run_workflow.py", "--dry-run"]
views:
  - id: status
    title: Status
    type: table
    source: status.results
  - id: logs
    title: Logs
    type: log
    source: runtime.logs
```

### 必需字段

- `id`：项目内唯一 workflow id。
- `title`：UI 展示名称。
- `scope.type`：默认作用域。
- `status`：状态来源。
- `actions`：可执行动作列表。
- `views`：UI 展示入口。

### 状态来源

Workflow 可以通过两种方式提供状态：

- `file`：SOLO 读取项目生成的 YAML 文件。
- `command`：SOLO 执行项目声明的状态查询命令，并读取 stdout JSON。

状态数据的建议格式如下。文件来源使用 YAML；命令来源使用等价 JSON 对象。

```yaml
updatedAt: datetime
summary:
  total: 0
  running: 0
  completed: 0
  failed: 0
  skipped: 0
items:
  - id: string
    title: string
    status: string
    scope:
      type: global | branch | worktree
      ref: string
    logPath: string | null
    artifactPath: string | null
    raw: {}
```

SOLO 只要求 `id`、`title`、`status`。其他字段按项目需要扩展。

---

## 8. 数据模型

### Project

```json
{
  "id": "string",
  "name": "string",
  "rootPath": "string",
  "defaultBranch": "string",
  "activeBranch": "string",
  "globalConfigDir": ".solo/global",
  "activeConfigDir": ".solo/<git branch> | null",
  "effectiveWorkflowDirs": [
    ".solo/global/workflows",
    ".solo/<git branch>/workflows"
  ],
  "runtimeDir": ".solo-runtime",
  "createdAt": "datetime",
  "updatedAt": "datetime"
}
```

### Workflow

```json
{
  "id": "string",
  "projectId": "string",
  "title": "string",
  "description": "string",
  "definitionPath": "string",
  "scopeType": "global | branch | worktree",
  "actions": [],
  "views": [],
  "lastStatusAt": "datetime | null",
  "createdAt": "datetime",
  "updatedAt": "datetime"
}
```

### WorkItem

```json
{
  "id": "string",
  "workflowId": "string",
  "externalId": "string",
  "title": "string",
  "status": "string",
  "scopeType": "global | branch | worktree",
  "scopeRef": "string | null",
  "sourcePath": "string | null",
  "raw": {},
  "updatedAt": "datetime"
}
```

### Run

```json
{
  "id": "string",
  "projectId": "string",
  "workflowId": "string",
  "actionId": "string",
  "workItemId": "string | null",
  "runner": "codex | command",
  "status": "created | dry_run | running | completed | failed | stopped",
  "scopeType": "global | branch | worktree",
  "scopeRef": "string | null",
  "cwd": "string",
  "promptPath": "string | null",
  "logPath": "string",
  "finalMessagePath": "string | null",
  "pid": "number | null",
  "returnCode": "number | null",
  "createdAt": "datetime",
  "startedAt": "datetime | null",
  "finishedAt": "datetime | null",
  "updatedAt": "datetime"
}
```

---

## 9. 状态与事件

SOLO 不规定 Work Item 的状态集合。Work Item 状态由项目返回，SOLO 原样展示。

Run 状态由 SOLO 管理：

```text
created -> dry_run
       └-> running -> completed
                     ├-> failed
                     └-> stopped
```

### SSE 事件类型

```text
project_loaded
workflow_loaded
workflow_status_updated
work_item_updated
run_created
run_dry_run
run_started
run_log
run_completed
run_failed
run_stopped
editor_started
```

### 事件格式

```json
{
  "type": "run_log",
  "projectId": "string",
  "workflowId": "string | null",
  "runId": "string | null",
  "timestamp": "datetime",
  "payload": {}
}
```

---

## 10. API

### Project API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/projects/open` | 打开本地项目 |
| `GET` | `/api/projects/:id` | 获取项目详情 |
| `POST` | `/api/projects/:id/refresh` | 重新扫描 workflow 并查询状态 |
| `GET` | `/api/projects/:id/git` | 获取 branch、worktree、dirty 状态 |

### Workflow API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/projects/:id/workflows` | 获取项目 workflow 列表 |
| `GET` | `/api/workflows/:id` | 获取 workflow 定义 |
| `POST` | `/api/projects/:id/workflows/bootstrap` | 使用 Codex 创建或更新 workflow |
| `POST` | `/api/workflows/:id/status` | 执行一次状态查询 |
| `GET` | `/api/workflows/:id/items` | 获取 workflow 报告的 Work Item |
| `GET` | `/api/workflows/:id/views` | 获取 workflow 声明的 UI 视图 |

### Action API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/workflows/:id/actions/:actionId/run` | 执行 workflow action |
| `POST` | `/api/runs/:id/stop` | 停止正在运行的 action |
| `GET` | `/api/runs/:id` | 获取 run 详情 |
| `GET` | `/api/runs/:id/logs` | 获取 run 日志 |
| `GET` | `/api/runs/:id/final` | 获取 Codex 最终输出 |
| `GET` | `/api/runs/:id/diff` | 获取 run 对应 scope 的 git diff |
| `POST` | `/api/runs/:id/open-editor` | 在 run 的 scope 中打开 code-server |

### Event API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/events` | 通过 SSE 推送项目、workflow、run 事件 |

---

## 11. Codex 执行

SOLO 调用 Codex 有两类场景。

### 创建或更新 Workflow

用户在 SOLO UI 中描述希望项目支持的流程。SOLO 在被管理项目中启动 Codex，让 Codex 创建或修改项目自己的 workflow 文件、状态脚本和文档。

示例 prompt：

```text
你正在为当前项目创建 SOLO workflow。

目标：
{user.workflowGoal}

要求：
- 默认工作流定义写入 .solo/global/workflows/{workflowId}.yaml
- 如果用户要求 branch/worktree 特定流程，写入 .solo/<git branch>/workflows/{workflowId}.yaml
- 状态查询必须输出 JSON
- 支持 dry-run、run-one、status-all、resume
- 日志和最终结果路径应可被 SOLO UI 展示
- 不要修改与该 workflow 无关的项目文件
```

### 执行 Workflow Action

当 action 的 runner 是 `codex` 时，SOLO 在 action 声明的作用域中运行：

```bash
codex exec -C {cwd} -o {finalMessagePath} -
```

执行规则：

- Prompt 由 workflow 模板、Work Item 数据和用户输入组合生成。
- 完整 prompt 写入 `.solo-runtime/prompts/{runId}.prompt.txt`。
- stdout 和 stderr 写入 `.solo-runtime/logs/{runId}.log`。
- Codex 最终输出写入 `.solo-runtime/logs/{runId}.final.txt`。
- Codex 退出后，SOLO 重新查询 workflow 状态。

### Dry Run

dry-run 是 workflow action，不是 SOLO 内建业务策略。SOLO 只负责：

- 生成或保存 prompt。
- 记录 Run。
- 不启动 Codex 或项目命令。
- 将 Run 标记为 `dry_run`。

dry-run 的具体业务含义由 workflow 定义。

---

## 12. 项目命令执行

当 action 的 runner 是 `command` 时，SOLO 只执行 workflow 声明的命令，不提供任意 shell 输入框。

```json
{
  "id": "status-all",
  "runner": "command",
  "cwd": "{projectRoot}",
  "command": ["python3", "scripts/workflow.py", "--status-all"]
}
```

命令执行要求：

- `cwd` 必须位于项目 root 或项目声明的 worktree 内。
- 命令必须来自 workflow 定义。
- stdout 和 stderr 写入 run log。
- 命令结束后记录退出码。
- 命令结束后重新查询 workflow 状态。

---

## 13. Git 与 Worktree

SOLO 提供 git 底层能力，但不规定 workflow 如何使用。

MVP 支持：

- 查询当前 branch。
- 查询 worktree 列表。
- 查询 dirty 状态。
- 为 action 创建临时 worktree。
- 展示指定 scope 的 diff。
- 打开指定 scope 的 code-server。

Workflow 可以声明 action 需要的 worktree 策略：

```json
{
  "worktree": {
    "mode": "none | existing | create",
    "baseRef": "main",
    "branchName": "solo/{runId}",
    "path": ".solo-runtime/worktrees/{runId}"
  }
}
```

合并不是 SOLO 默认策略。若项目需要合并动作，应在 workflow 中声明 `merge` action，并由项目规则决定合并方式。

---

## 14. Editor 集成

SOLO 可以在 Project、Workflow、Work Item 或 Run 的作用域中打开 code-server。

```bash
code-server --bind-addr 127.0.0.1:{port} --auth none {scopePath}
```

行为要求：

- 每个 scope 最多复用一个 code-server 实例。
- 如果实例已存在，直接返回现有 URL。
- code-server 只能绑定到 `127.0.0.1`。
- 端口由后端自动分配并记录在 `.solo-runtime/editors/` 中。
- 本地访问 SOLO 时，`open-editor` 返回 `http://127.0.0.1:{port}`，浏览器直连本地 code-server。
- 通过 cloudflared 等远程入口访问 SOLO 时，`open-editor` 根据请求 Host 自动返回 `https://editor-<id>.<solo-host>`。
- `editor-*` Host 由 SOLO 后端反向代理到对应的本地 `127.0.0.1:{port}`，只允许代理 `.solo-runtime/editors/` 中记录且进程仍存活的实例。
- cloudflared 需要把主域名和 wildcard editor 子域都转发到 SOLO，例如 `solo.example.com` 和 `*.solo.example.com`。

---

## 15. UI 行为

### Project Dashboard

- 展示项目根目录、当前 branch、worktree、dirty 状态。
- 展示已发现 workflow。
- 提供 `Refresh` 操作，重新读取项目 workflow 和状态。
- 提供 `Create Workflow with Codex` 操作。

### Workflow Catalog

- 展示 workflow 列表。
- 展示每个 workflow 的作用域、状态来源、可用 actions 和 views。
- 支持按 workflow 进入详情页。

### Workflow Detail

- 展示项目返回的状态摘要。
- 展示 Work Item board 或 table。
- 展示 workflow 声明的 views。
- 展示 workflow actions。
- 支持对全局、branch、worktree 或单个 Work Item 执行动作。

### Run Detail

- 展示 run 状态、执行作用域、命令或 Codex 信息。
- 展示 prompt、过程日志和最终输出。
- 展示关联 diff。
- 提供 `Stop`、`Open Editor` 等通用操作。

---

## 16. 约束

- SOLO 只能管理用户显式打开的本地 repo。
- SOLO 不提供任意 shell 输入框。
- 项目命令必须来自 workflow 定义。
- Codex 和项目命令的 cwd 必须位于项目 root 或项目 worktree 内。
- 后端服务和 code-server 只能绑定到 `127.0.0.1`。
- MVP 不做权限隔离，因此默认只面向可信本机用户。
- SOLO 不自动提交、不自动合并、不自动推送，除非项目 workflow 明确声明对应 action 且用户触发。
- SOLO 不把 SQLite 作为项目状态最终来源。

---

## 17. 最小 CLI

```bash
solo serve /path/to/repo
```

启动后：

- 后端初始化 `.solo-runtime/` 和 SQLite 缓存。
- 后端先扫描 `.solo/global/`，再扫描当前 branch 或 worktree 对应的 `.solo/<git branch>/`。
- 后端启动 FastAPI 服务。
- 前端连接后端 API 和 SSE。
- 用户通过浏览器访问 SOLO UI。

可选辅助命令：

```bash
solo workflow list
solo workflow bootstrap --goal "为项目创建迁移进度 workflow"
solo workflow status {workflowId}
solo action run {workflowId} {actionId}
solo run logs {runId}
solo run diff {runId}
solo run open-editor {runId}
```

---

## 18. 试用方法

SOLO 的试用重点是验证“项目拥有流程，SOLO 负责显示与执行”。试用时不要先把流程硬编码进 SOLO，而是让被管理项目先创建自己的 workflow。

### 借鉴模式

可以参考批量 Codex 迁移脚本的模式：

- 项目脚本发现目标。
- 项目脚本生成 prompt。
- 项目脚本维护 `state.yaml`。
- 项目脚本支持 `dry-run`、`resume`、`keep-going`、`only-one`。
- 项目脚本支持 `status-all`、`mark-skip`、`mark-done`。
- 每个目标有独立 log 和最终输出。

在 SOLO 中，上述能力不应写死为 SOLO 策略，而应作为项目 workflow 暴露给 SOLO。

### 推荐试用仓库

创建一个临时项目：

```bash
mkdir -p /tmp/solo-demo
cd /tmp/solo-demo
git init
git checkout -b main
printf 'def add(a, b):\n    return a + b\n' > calc.py
mkdir -p scripts
git add calc.py scripts
git -c user.name=solo -c user.email=solo@example.invalid commit -m "init demo repo"
```

### 启动 SOLO

```bash
solo serve /tmp/solo-demo
```

### 使用 Codex 创建项目 Workflow

在 SOLO UI 中点击 `Create Workflow with Codex`，输入目标：

```text
为这个项目创建一个 demo workflow。
它需要发现 calc.py 中缺失的函数任务，维护 .solo/global/status/demo.yaml，
并提供 dry-run、run-one、status-all、mark-done、mark-skip 动作。
```

期望 Codex 在项目中创建：

- `.solo/global/workflows/demo.yaml`
- `scripts/solo_demo_workflow.py`
- `.solo/global/status/demo.yaml`
- 必要的说明文档

### 查询状态

SOLO 重新扫描 workflow 后，应能：

- 看到 `demo` workflow。
- 调用项目的 status action。
- 展示项目返回的 Work Item。
- 展示项目返回的 summary。

### Dry-run

执行 workflow 的 `dry-run` action。

期望结果：

- SOLO 创建 Run。
- SOLO 保存 prompt 和 run log。
- 项目状态文件可被更新或保持不变，具体由 workflow 定义。
- UI 能展示 dry-run 结果。

### 单项真实执行

执行 workflow 的 `run-one` action。

期望结果：

- SOLO 在项目定义的 scope 中启动 Codex 或项目命令。
- 过程日志写入 `.solo-runtime/logs/{runId}.log`。
- 最终输出写入 `.solo-runtime/logs/{runId}.final.txt`。
- 执行结束后 SOLO 重新查询项目状态。
- UI 展示新的 Work Item 状态和 diff。

### 分支或 Worktree 试用

用户可以让 Codex 为项目增加 branch/worktree 级 workflow：

```text
把 demo workflow 扩展为 worktree 级流程。
每次 run-one 时创建独立 worktree，在该 worktree 中修改代码并写入状态。
```

SOLO 应展示：

- workflow 的 scope 类型。
- 对应 branch 或 worktree。
- 每个 run 的 cwd。
- 该 scope 下的日志、diff 和 editor 入口。

---

## 19. 成功标准

MVP 完成时，用户应能完成以下闭环：

1. 用 `solo serve /path/to/repo` 打开一个本地项目。
2. SOLO 扫描并展示项目已有 workflow。
3. 用户通过 Codex 在项目中创建新的 workflow。
4. SOLO 重新加载该 workflow。
5. SOLO 从项目查询状态并展示 Work Item。
6. 用户触发 workflow action。
7. SOLO 执行 Codex 或项目命令并记录 Run。
8. SOLO 展示日志、最终输出、diff 和状态变化。
9. 用户打开 code-server 进入对应 scope。
10. 项目自己的状态文件或状态命令成为进度来源。

最终判断标准：

- SOLO 没有内建具体业务流程。
- 被管理项目可以定义和演进自己的流程。
- SOLO 能稳定执行项目声明的动作。
- SOLO 能稳定展示项目声明或查询到的状态。
- 全局、branch、worktree 三种作用域都能被表达。
