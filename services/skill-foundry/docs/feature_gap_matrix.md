# 功能差距矩阵

| 目标 | FreeTodo 0.1.2 | Legacy Organizer | Adapter 方案 |
|---|---|---|---|
| 真实 ContextEvent 导入 | 无 | 有 | 版本化、unknown-field preserving ingest |
| 同 ID 幂等/冲突 | 无 | 有 | payload hash + versions + conflict job |
| Privacy decision | 无 Elfred 语义 | 有 | 本地 gate、字段级脱敏、audit |
| Todo 产品 UI | 成熟 | 无 | HTTP 映射到 FreeTodo |
| Calendar | 有 | 无 | 复用上游 |
| idea 导向日报 | AI Journal 依赖 LLM | 有摘要骨架 | Adapter deterministic fallback + provider |
| Activity external ingest | 无 | 自有 activity | Adapter 自有 link；未来 fork API |
| Topic alias | tags only | 有 | stable registry + alias seed |
| 来源追溯/forget | 无 | 有 | link snapshots + drift-aware deletion/unlink |
| 手工修改保护 | 无 Elfred link 基线 | 部分 | last-synced canonical snapshot/hash |
| Memory/PA 合同 | 无 | 本地 outbox | v1 JSON Schema + ack/retry |
| Legacy migration | 不适用 | 来源 | dry-run/report/rollback batch |
| 演示离线性 | LLM 提示未配置 | mock 可用 | 默认 deterministic，不调用付费 API |

红线缺口：Activity 不能通过当前 HTTP API 写入；Diary/Activity 前端面板在原版中标为开发中并默认隐藏。演示时 Todo/Calendar/Journal 是已验证产品闭环，Adapter Activity 与日报 API 是补充视图。
