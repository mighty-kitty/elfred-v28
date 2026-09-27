# FreeTodo 上游版本与许可审计

审计日期：2026-07-13。

## 固定版本

- 本地归档：`FreeTodo-main.zip`
- SHA-256：`726A08DAEB6A15FFBE44427112F5FAC67E5AC81E68388C539A0A86CC4578A145`
- 项目版本：`0.1.2`
- 官方仓库：<https://github.com/FreeU-group/FreeTodo>
- 固定 tag：`0.1.2`
- 固定 commit：`800cd27344fe1eb99f429d0aec22e99ed189d921`
- commit 时间：`2026-02-06T07:55:45Z`

通过 GitHub recursive tree 的 blob SHA 与本地 Git blob SHA 逐文件比较：远端 1172 个 blob，本地 1172 个文件，缺失 0、内容不同 0、多余 0。因此用户提供的 ZIP 与上述官方 commit 精确一致。

## 许可边界

仓库携带 `FreeU Community License`。许可证文本允许在不修改 FreeTodo 前后端代码的情况下部署和提供服务；基于 FreeTodo 修改、开发并分发衍生产品时声明需要商业许可，其他未特别说明部分受 Apache License 2.0 条款约束。本记录是工程边界说明，不构成法律意见。

本次演示按用户 2026-07-13 的书面指示可复用 FreeTodo 能力，但工程仍保持最容易替换的边界：

- `third_party/FreeTodo` 作为经哈希验证的原版只读源，不修改；
- 运行产生的数据、依赖和配置放在 `.runtime`；
- Elfred 只通过独立 `elfred_freetodo_adapter` 和 FreeTodo HTTP API 对接；
- 原 Organizer 完整保留为 legacy、迁移来源和回退实现；
- 不将 FreeTodo 代码复制进 Adapter。

## 可追溯物

- `upstream_manifest.json`
- `freetodo_upstream.sha256`
- `elfred_context_organizer_legacy.sha256`
- `freetodo_openapi.json`
