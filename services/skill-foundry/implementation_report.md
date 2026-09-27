# Elfred × FreeTodo Adapter 实施报告

实施日期：2026-07-13。目标：在不修改 FreeTodo、不删除 legacy Organizer 的前提下，为次日演示建立可验证的 Elfred 组织闭环。

## 已完成

| 阶段 | 结果 | 证据 |
|---|---|---|
| Phase 0 冻结/基线 | 完成 | ZIP SHA-256、官方 commit 逐文件 1172/1172 精确匹配、原版前后端启动、OpenAPI 和截图 |
| Phase 1 复用审计 | 完成 | upstream/license/API/model/reuse/gap 六类文档 |
| Phase 2 Adapter 核心 | 完成 | ingest、幂等冲突、privacy/PII、Todo/Journal、Topic、来源、Outbox、forget/reconcile |
| Phase 3 日报/周报 | 演示闭环完成 | deterministic structured extraction、idea 导向日报、非拼接周报、失败回退；未配置真实云 LLM，因此没有宣称付费 Provider 已实测 |
| Phase 4 产品闭环 | 已验证可用范围 | 原版 Todo/Calendar 可见，Journal HTTP 成功，手改保护与错误路径验证；Diary/Activity 原 UI 属开发中面板 |
| Phase 5 Memory/PA | 本地合同完成 | v1 JSON Schema、durable Outbox、幂等、ack；外部 endpoint/auth 合同缺失，未擅自推送 |
| Phase 6 迁移/交付 | 完成可测范围 | migration dry-run/actual/rollback 代码与测试、Windows path、clean package 工具；没有 legacy 生产 DB 可实迁 |

## 关键工程结果

- `third_party/FreeTodo` 未修改；运行依赖、数据、配置全部在 `.runtime`。
- `elfred_context_organizer` 与 `elfred_context_organizer_legacy` 都保留，107 个文件完全一致。
- Adapter 自有 SQLite 包含任务书要求的 13 类核心表，另有 payload versions、attempts 和 migration batches。
- FreeTodo 只通过 `/health`、Todo 和 Journal HTTP API 调用；没有直接 DB 写入。
- FreeTodo Activity 的 external 写入缺口通过真实 404 与源码合同共同确认，Adapter 使用 `local_only` Activity API。
- `allowed_to_upload=false` 不触发云服务；硬敏感事件 0 个远端调用；手机号/邮箱/secret 字段级脱敏。
- Todo/Journal 写入保存远端 semantic hash，forget/reconcile 前检测漂移，用户修改不覆盖不删除。

## 测试记录

1. `pytest`：27 passed，覆盖任务书 25 类情况，另覆盖 Journal 手改保护与 PII 日报泄漏回归；7.66 秒；唯一 warning 为 Starlette 对 TestClient/httpx 的上游弃用提示。
2. 离线 20 事件：19 synced、1 privacy_blocked、重复事件 duplicate；15 Todo、1 Journal、19+19 Outbox；12 项检查全通过。
3. 原版 FreeTodo 真实 HTTP 20 事件：同样 12 项检查全通过；没有付费 API。
4. Adapter HTTP 冒烟：health、event ingest、duplicate、links、outbox/ack、OpenAPI 全通过。
5. 真实手工修改保护：创建 Todo → 通过 FreeTodo PUT 改名 → Adapter forget；远端对象保留并返回 `preserved_todo_ids`，验证后清理测试对象。
6. 真实 reconcile：手工删除远端 Todo → reconcile 检出 missing=1 → forget 完成。
7. Elfred 专用 FreeTodo 配置副本：独立端口 8002 启动健康，数据库 migration 成功，7/7 scheduler jobs 均 paused，随后正常停止。
8. 浏览器 UI：真实 Todo 列表和 2026-07 Calendar 可见；截图保存在 `docs/freetodo_integration`。

## 明确未宣称完成的外部项

- 无云 LLM key/base URL/模型成本表，故真实付费 Provider 未调用；演示使用已测试 deterministic provider。
- 无 Memory/PA 正式 endpoint、鉴权、删除回执合同，故只提供本地 Outbox/ack。
- 无 legacy 运行数据库，故迁移只在 synthetic schema 上完成 dry-run/actual/rollback 自动测试。
- 无 FreeTodo external Event API，故 Activity 不能写入原版数据库/UI。
- 原版 Diary/Activity 前端被列为 `DEV_IN_PROGRESS_FEATURES`，不把隐藏面板称为成熟可用。

这些边界不影响次日 Todo/Calendar/Journal + 来源/隐私/Outbox 的演示主链。
