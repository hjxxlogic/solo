# solo MVP 规格说明

## 1. 概览

solo 是一个本地优先、单用户使用的 AI 编码 Agent 编排系统。它将 Issue 转换为相互隔离的 Agent 任务，并让每个任务在独立的 git worktree 中运行。

每个任务的目标是：

- 调用 Codex CLI 执行编码任务
- 在独立 worktree 中修改代码
- 产出可审查的 diff
- 通过 code-server 让用户进入任务工作区进行人工审查
- 由用户决定是否合并结果

solo 的工作方式参考 Symphony 类编排系统，但 MVP 只覆盖本地单仓库场景：

- Issue 驱动工作流
- 每个任务独立工作区
- Agent 持续执行
- 人工介入审查与合并

---

## 2. MVP 范围

### 支持

- 单用户
- 单个 git 仓库
- 仅本地执行
- SQLite 数据库
- Codex CLI 非交互模式
- 按需启动 code-server
- Server-Sent Events 实时推送任务事件与日志

### 暂不支持

- 多用户
- 云端同步
- 权限系统
- 容器或沙箱隔离
- GitHub/GitLab PR 集成
- 远程 Agent 执行

---

## 3. 核心概念

### Issue

Issue 表示一个 bug、需求或功能请求，是用户创建任务的入口。

### Task

Task 是 Issue 的一次执行实例。一个 Issue 可以创建一个 Task；MVP 阶段先按一对一关系实现。

### Workspace

Workspace 是 Task 对应的 git worktree。Agent 只在该 worktree 中修改代码。

### Agent

Agent 是为某个 Task 启动的 Codex CLI 进程。

### Editor

Editor 是为某个 Task 启动的 code-server 实例，用于让用户查看和手动修改该 Task 的工作区。

---

## 4. 系统架构

```text
Frontend (React)
├─ Issue Board
├─ Task Board
├─ Task Detail
├─ Logs Viewer
├─ Diff Viewer
└─ Open Editor

Backend (FastAPI)
├─ API
├─ Issue Manager
├─ Task Manager
├─ Workspace Manager
├─ Agent Runner
├─ Editor Manager
├─ Git Manager
├─ Event Stream (SSE)
└─ SQLite DB

External
├─ codex CLI
├─ code-server
└─ git
```

---

## 5. 目录布局

所有 solo 运行时文件都放在目标仓库根目录下的 `.solo/` 中。

```text
repo/
└─ .solo/
   ├─ db.sqlite
   ├─ logs/
   │  └─ {taskId}.log
   ├─ worktrees/
   │  └─ {taskId}/
   └─ runtime/
      └─ editors/
```

---

## 6. 数据模型

### Issue

```json
{
  "id": "string",
  "type": "bug | feature",
  "title": "string",
  "description": "string",
  "status": "open | in_progress | review | done",
  "linkedTaskId": "string | null",
  "createdAt": "datetime",
  "updatedAt": "datetime"
}
```

### Task

```json
{
  "id": "string",
  "issueId": "string",
  "status": "created | running | failed | review | done | stopped",
  "baseBranch": "string",
  "agentBranch": "string",
  "worktreePath": "string",
  "codexPid": "number | null",
  "editorPort": "number | null",
  "createdAt": "datetime",
  "updatedAt": "datetime"
}
```

---

## 7. 状态流转

### Issue 状态

```text
open -> in_progress -> review -> done
```

- `open`：Issue 已创建，尚未运行。
- `in_progress`：Issue 已关联 Task，Agent 正在执行或已准备执行。
- `review`：Agent 执行完成，等待用户审查 diff。
- `done`：用户已合并或标记完成。

### Task 状态

```text
created -> running -> review -> done
                  ├-> failed
                  └-> stopped
```

- `created`：Task 已创建，worktree 尚未或刚刚创建完成。
- `running`：Codex CLI 正在执行。
- `review`：Codex CLI 执行完成，diff 可查看。
- `done`：Task 已合并或被用户确认完成。
- `failed`：Task 执行失败。
- `stopped`：Task 被用户手动停止。

---

## 8. API

### Issue API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/issues` | 创建 Issue |
| `GET` | `/api/issues` | 获取 Issue 列表 |
| `GET` | `/api/issues/:id` | 获取 Issue 详情 |
| `POST` | `/api/issues/:id/run` | 为 Issue 创建并启动 Task |

`POST /api/issues/:id/run` 的行为：

1. 创建 Task 记录。
2. 基于当前主分支创建 git worktree。
3. 启动 Codex CLI。
4. 将 Issue 状态更新为 `in_progress`。

### Task API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/tasks` | 获取 Task 列表 |
| `GET` | `/api/tasks/:id` | 获取 Task 详情 |
| `POST` | `/api/tasks/:id/start` | 启动或重新启动 Task |
| `POST` | `/api/tasks/:id/stop` | 停止正在运行的 Codex 进程 |
| `GET` | `/api/tasks/:id/logs` | 获取 Task 日志 |
| `GET` | `/api/tasks/:id/diff` | 获取 Task 相对 base branch 的 diff |
| `POST` | `/api/tasks/:id/open-editor` | 为 Task 打开 code-server |
| `POST` | `/api/tasks/:id/merge` | 将 Task 分支合并回 base branch |

### Event API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/events` | 通过 SSE 推送任务事件和日志 |

---

## 9. Git 集成

MVP 默认使用 `main` 作为 base branch，后续可以从仓库当前分支或用户配置中读取。

### 创建 worktree

```bash
git worktree add .solo/worktrees/{taskId} -b agent/{taskId} {baseBranch}
```

### 查看 diff

在 Task 的 worktree 中执行：

```bash
git diff {baseBranch}
```

### 合并结果

在仓库根目录执行：

```bash
git checkout {baseBranch}
git merge agent/{taskId}
```

合并前后端应确认：

- Task 状态为 `review`
- worktree 存在
- agent branch 存在
- 当前没有正在运行的 Codex 进程

---

## 10. Agent Runner

### 启动命令

在 Task worktree 中运行：

```bash
codex exec "<prompt>"
```

### Prompt 模板

```text
你正在一个 git 仓库中工作。

任务标题：
{issue.title}

任务描述：
{issue.description}

执行规则：
- 尽量做最小必要修改
- 不要提交 commit
- 如果条件允许，运行相关编译或测试
- 在输出中总结修改内容、验证方式和遗留问题
```

### 日志

- Codex 的 stdout 和 stderr 写入 `.solo/logs/{taskId}.log`。
- 日志内容通过 `/api/tasks/:id/logs` 查询。
- 新增日志通过 `/api/events` 实时推送。

---

## 11. Editor 集成

### 启动命令

```bash
code-server --bind-addr 127.0.0.1:{port} --auth none {worktreePath}
```

### 返回结果

```text
http://127.0.0.1:{port}
```

### 行为要求

- 每个 Task 最多启动一个 code-server 实例。
- 如果实例已存在，直接返回现有 URL。
- code-server 只能绑定到 `127.0.0.1`。
- 端口由后端自动分配并记录在 Task 中。

---

## 12. UI 行为

### Issue Board

- 展示 Issue 列表。
- 支持创建 Issue。
- 每个可运行 Issue 提供 `Run with Codex` 操作。
- 展示 Issue 当前状态和关联 Task。

### Task Board

- 展示所有 Task。
- 显示 Task 状态、Issue 标题、分支名和创建时间。
- 对运行中的 Task 显示实时状态。

### Task Detail

- 展示 Issue 信息。
- 展示 Task 日志。
- 展示 Task diff。
- 提供 `Stop`、`Open Editor`、`Merge` 操作。
- 对 `failed` Task 显示错误日志入口。

---

## 13. 事件系统

使用 Server-Sent Events 推送任务状态与日志。

### 事件类型

```text
task_created
task_started
task_log
task_finished
task_failed
task_stopped
task_review_ready
task_merged
editor_started
```

### 事件格式

```json
{
  "type": "task_log",
  "taskId": "string",
  "timestamp": "datetime",
  "payload": {}
}
```

---

## 14. 约束

- 只能对用户指定的仓库根目录运行 solo。
- 不提供任意 shell 命令执行接口。
- Codex 只能在 Task worktree 中运行。
- code-server 和后端服务都只能绑定到 `127.0.0.1`。
- MVP 不做权限隔离，因此默认只面向可信本机用户。
- MVP 不自动提交 commit，不自动推送远程分支。

---

## 15. 成功标准

MVP 完成时，用户应能完成以下完整流程：

1. 在 UI 中创建 Issue。
2. 点击 `Run with Codex` 启动任务。
3. 后端为任务创建独立 worktree。
4. Codex 在 worktree 中修改代码。
5. UI 实时显示任务日志和状态。
6. 用户查看 Task diff。
7. 用户按需打开 code-server 审查或手动调整。
8. 用户将任务结果合并回 base branch。

---

## 16. 最小 CLI

```bash
solo serve /path/to/repo
```

启动后：

- 后端初始化 `.solo/` 目录和 SQLite 数据库。
- 后端启动 FastAPI 服务。
- 前端连接后端 API 和 SSE。
- 用户通过浏览器访问 solo UI。
