# Changelog

## 2026-05-01

- 支持基于 `--repo` 的单项目启动模式，UI 不再提供项目选择入口。
- 将 `.solo-runtime` 调整为按 Managed Project 隔离的 `.solo-runtime/projects/{projectId}/` 结构。
- 新增 `solo init` 和 Codex hook 记录能力，用于缓存每个 Codex session 的首句 prompt 摘要、turn 数和结束状态。
- 修正 `solo serve --repo` 的工作目录切换，Codex、项目命令和 code-server 均在指定 repo 或其 worktree 内运行。
- 加固 code-server 启动逻辑：优先使用 SOLO 自带 code-server，清理 VS Code/Electron 相关环境变量，隔离 code-server 配置、用户数据、扩展目录和 session socket，避免打开外层 VS Code Server 环境。
