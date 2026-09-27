# Adapter 接口合同

基准前缀：`/v1/elfred`。机器可读合同见根目录 `openapi.json` 和 `integration_contracts/`。

## 输入和状态

| Method | Path | 语义 |
|---|---|---|
| POST | `/events` | 接收 bare ContextEvent 或 envelope，返回单事件 SyncResult |
| POST | `/events/batch` | `{events:[...]}`，逐事件隔离失败，最多 1000 条 |
| POST | `/import/json` | 导入单对象、envelope 或数组 |
| POST | `/pull-observer` | 从配置的 Observer `/events/recent` 拉取，默认 100 条 |
| GET | `/health` | Adapter 与 FreeTodo 组合健康状态 |
| GET | `/status` | DB 计数、状态和当前 feature flag |
| GET | `/jobs`、`/jobs/{id}` | 同步/重试/reconcile/forget 作业 |
| POST | `/reconcile` | `{repair:false}` 默认只审计；repair 只重建安全的缺失 Todo |

## 追溯、撤回和出口

| Method | Path | 语义 |
|---|---|---|
| GET | `/events/{event_id}/links` | Todo、Journal、Adapter Activity 来源链接 |
| DELETE | `/events/{event_id}` | 仅删除 Adapter canonical event；远端对象不变 |
| POST | `/events/{event_id}/forget` | 漂移感知地删除/解除来源对象 |
| POST | `/events/{event_id}/retry` | 重试已接受事件的未完成同步 |
| GET | `/outbox/memory` | Memory Candidate v1；默认 pending |
| GET | `/outbox/personal-agent` | Personal Agent Context v1；默认 pending |
| POST | `/outbox/{item_id}/ack` | 幂等确认 |
| GET | `/activities` | FreeTodo 无 external Activity API 时的 Adapter 本地视图 |
| GET | `/reports/weekly/{year}/{week}` | 非日报拼接的周度综合 |

相同 `event_id + payload_hash` 返回 `duplicate`；相同 `event_id` 但 hash 不同返回 `conflict`，原 canonical payload 不被覆盖。HTTP 202 表示接收并完成一次同步尝试，不等同于所有远端动作成功；实际状态需读响应里的 `status`。
