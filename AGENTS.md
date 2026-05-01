# AGENTS.md

本文件为在本仓库中工作的 Codex/Agent 提供项目级指引。

## 项目定位

SOLO 是本地优先、单用户使用的项目执行与观察底座。

核心原则：

- SOLO 是显示层与执行层，不是策略层。
- 被管理项目拥有自己的 workflow、状态、进度、动作和业务语义。
- SOLO 负责加载 workflow、执行声明动作、展示状态、日志、diff 和产物。
- SQLite 只作为 SOLO 本地缓存，不是被管理项目状态的最终来源。

修改设计文档或实现时，必须保持这个边界，不要把具体业务流程硬编码进 SOLO。

## 关键文档

- `SPEC.md`：SOLO MVP 规格说明，是当前需求和架构的主文档。

## 被管理项目配置约定

被管理项目中的 SOLO 配置位于 `.solo/`：

- `.solo/global/`：全局配置，也是默认配置。
- `.solo/<git branch>/`：分支或该分支 worktree 的特定配置。

加载规则：

1. 先加载 `.solo/global/`。
2. 再根据当前 branch 或 worktree 对应的 git branch 加载 `.solo/<git branch>/`。
3. 分支配置按名称覆盖全局配置。
4. MVP 不做 YAML 深度合并；同名配置文件整体替换。

worktree scope 使用该 worktree 当前 checkout 的 git branch 名称解析配置。detached HEAD 默认只使用 `.solo/global/`。

## 运行时目录约定

SOLO 自身运行时数据位于 `.solo-runtime/`：

- `.solo-runtime/projects/{projectId}/db.sqlite`
- `.solo-runtime/projects/{projectId}/prompts/`
- `.solo-runtime/projects/{projectId}/logs/`
- `.solo-runtime/projects/{projectId}/worktrees/`
- `.solo-runtime/projects/{projectId}/editors/`

`.solo-runtime/` 是本地运行时目录，默认不应提交。

## 修改规则

- 优先保持 `SPEC.md` 中的术语一致：Managed Project、Workflow、Scope、Work Item、Action、Run、View。
- 不要重新引入内建 Issue/Task 策略，除非它只是某个被管理项目 workflow 的示例。
- 不要让 SOLO 自动提交、自动合并或自动推送，除非项目 workflow 明确声明对应 action 且用户触发。
- 项目命令必须来自 workflow 定义；不要设计任意 shell 输入框。
- Codex 和项目命令的 cwd 必须位于项目 root 或项目 worktree 内。
- 后端服务和 code-server 只能绑定到 `127.0.0.1`。
- 任何修改都必须记录到 `Changelog.md`

## 文档风格

- 使用中文描述需求和设计。
- 保留 API path、字段名、命令、状态值等实现标识的英文形式。
- 修改 Markdown 后检查代码块是否闭合。
- 保持设计说明可执行，避免只写抽象愿景。
