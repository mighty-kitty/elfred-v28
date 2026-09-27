# FreeTodo API 审计

原版 OpenAPI 共 94 paths、101 operations。完整机器可读定义见 `freetodo_openapi.json`。

## Elfred 首期使用的 API

| 能力 | Method / path | 采用方式 | 备注 |
|---|---|---|---|
| 健康检查 | `GET /health` | 直接复用 | Adapter readiness 依赖 |
| Todo 查询 | `GET /api/todos` | 通过 API | 用 `uid`/Adapter link 去重 |
| Todo 创建 | `POST /api/todos` | 通过 API | 支持 draft/active、due、tags/categories |
| Todo 详情 | `GET /api/todos/{id}` | 通过 API | forget 前手工修改保护 |
| Todo 更新 | `PUT /api/todos/{id}` | 通过 API | 仅在快照未漂移时自动更新 |
| Todo 删除 | `DELETE /api/todos/{id}` | 通过 API | forget 时受漂移保护 |
| Journal 查询 | `GET /api/journals` | 通过 API | 日报 reconcile |
| Journal 创建 | `POST /api/journals` | 通过 API | 客观记录和 AI 观点分栏 |
| Journal 详情 | `GET /api/journals/{id}` | 通过 API | 来源/手改保护 |
| Journal 更新 | `PUT /api/journals/{id}` | 通过 API | 合并当日新事件 |
| Journal 删除 | `DELETE /api/journals/{id}` | 通过 API | forget/reconcile |
| Scheduler 状态 | `GET /api/scheduler/jobs` | 诊断复用 | 验证采集 jobs 暂停 |

## 不作为 Elfred 写入面的 API

- `GET /api/events*`：只读；无 external Event create。
- `POST /api/activities/manual`：请求是 FreeTodo 内部 Event ID 列表，要求事件结束、未关联，并调用 LLM 生成摘要；不接受 ContextEvent。
- `/api/chat*`、`/api/*search*`、`/api/vector*`：可选产品能力，不作为 Personal Agent 或 Memory 的主合同。
- `/api/ocr*`、`/api/audio*`、`/api/proactive-ocr*`、截图 API：与 Observer 职责重复，演示默认禁用。
- `/api/save-config`：Adapter 不在运行时改写上游配置。

## 模型关键字段

Todo 接受 `uid/name/description/status/priority/due/dtstart/tags/categories/user_notes/parent_todo_id/related_activity_ids`。状态枚举为 `active/completed/canceled/draft`（上游使用单 l 的 `canceled`）。Journal 接受 `uid/name/user_notes/date/content_objective/content_ai/tags/related_todo_ids/related_activity_ids`。
