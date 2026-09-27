# 隐私与数据出口

隐私判断先于 Topic、Todo、Journal 和 Outbox。

- `privacy.action=block`、`is_sensitive=true` 或 credential/token/payment/medical/legal/private-chat 等硬敏感标记：只保留审计所需 canonical event，状态 `privacy_blocked`，不调用 FreeTodo、不生成 Outbox。
- `allowed_to_upload` 仍用于任务分析和合作方投递，不作为日报的人工开关。日报逐事件执行自动隐私检测；`action=block`、敏感标记、凭据模式或 `requires_user_confirmation=true` 的事件全部排除，其余事件脱敏后才可进入日报模型。这样 Observer 默认的安全截图和语音事件无需人工逐条授权，同时待确认和敏感内容不会进入模型。
- 安全事件仍做字段级脱敏：邮箱、手机号、疑似 secret/token/password、卡号在进入 FreeTodo、日报和合作方 Outbox 前替换。
- screenshot 路径、exe 路径、PID、raw artifact 不进入 FreeTodo payload。
- `allowed_to_write_long_term_memory=false` 时仍可生成候选，但 `delivery_gate=confirm_required`，合作方不得自动写长期记忆。

日报只读取 Adapter 本地数据库中指定日期的完整事件集合，不读取 Observer `recent` 固定窗口。应用分布、来源 hash 和结构化任务基于全天安全事件；`ELFRED_JOURNAL_MAX_EVENTS` 只控制送入 Prompt 的自由文本代表性明细。代表性选择按时间覆盖全天，并优先保留语音、任务、决策、风险和阻塞事件。

Observer 回填未完成或不可用时，日报状态进入持久重试队列，不会被解释成“当天无事件”。候选内容、远端基线和 lease 均持久化；人工修改优先于自动更新，发布成功后才允许创建硬件计划。

原始 ContextEvent 只在 `elfred_adapter.db` 中用于可追溯、冲突和忘记操作。演示默认没有任何付费 API 调用；测试使用内存 FreeTodo fake，真实 E2E 只访问 `127.0.0.1`。
