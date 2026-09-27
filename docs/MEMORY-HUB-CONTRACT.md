# 记忆中枢预留接口（elfred-memory-v1）

这是 Elfred 与未来 EmoS 适配服务的协议，不声称是 EmoS 原生 API。未配置时，本地 SQLite 的授权记忆照常工作；外部同步显示未配置。

## 服务端配置

```dotenv
ELFRED_MEMORY_HUB_URL=https://your-memory-adapter.example
ELFRED_MEMORY_HUB_TOKEN=server-only-token
```

只允许 HTTPS 或本机 HTTP，无重定向。配置留在服务端，不放进浏览器。适配服务必须按 `owner` 隔离租户；鉴权凭据与模型 Key 分开配置。

## 写入与停止使用

- `PUT /v1/memories/{id}`：仅传本人确认、未隐藏、未到期、来源仍可读的记忆。
- `DELETE /v1/memories/{id}`：否认、删除、替代、隐藏、到期、来源不可读或尚未确认时停止外部使用。不存在也应返回幂等成功回执。
- Header：`Authorization: Bearer <server token>`；`Idempotency-Key: <id>:<revision>:<state_hash>:<intent_sequence>`。
- PUT 正文：`contract, owner, id, revision, content, scope, group, source_refs, alignment, evidence, expires_at, supersedes_id, state_hash`。
- DELETE 正文：`contract, owner, id, revision, action: "forget", state_hash`。不附旧的私有正文。
- 成功返回：`{"owner":"当前租户","id":"当前对象","revision":3,"state_hash":"请求中的状态摘要"}`，四个字段必须与请求一致。

SQLite 中的 `memory_bridge` 是持久同步队列。旧版本排队事件跳过；回执不匹配或失败保留重试并退避；来源到期即使不改变版本也会排队停止使用；场景证据失效会同步降级后的投影。intent_sequence 保证同一版本的状态改变后恢复，也不会被旧幂等回执吞掉。删除后的错误回执不能被当成删除已完成。

## 应用只读出口

以下入口已实现，使用当前登录会话，客户端不能指定他人的 owner：

- `GET /api/elfred/memory/recall?scope=create&q=产品方案`：返回本人的相关、已确认、有效、该领域记忆及来源和阶段；最多六条。
- `GET /api/elfred/memory/hub`：返回是否配置、待同步数量、最近成功回执时间；不返回地址或凭据。

普通子 Agent 对话和本人文字任务实际读取同一份授权本地缓存。跨 Agent 默认不共享；共享项目和群聊不自动注入个人私有记忆。一次任务专用的上下文授权及其衍生物不能扩大成长期画像。配置适配器后仍须验收外部权限、同步、删除和故障恢复，才能称为外部中枢已接通。

## 记忆写入与验证规则

- 同一次聊天模型调用返回自然回复和至多三条候选；结构包装不呈现给用户，不另开无额度的提取调用。
- 候选须附当前本人消息中的原句。明确长期价值才进入候选；引用他人、临时情绪、一次性要求和密钥不写入画像。
- 用户核对前不召回。模型响应不是用户事实的来源。
- 初始化具体选择形成分领域的初始假设；不确定、跳过选项不写成事实。后续修改要重评旧理解。
- 任务反馈和长期目标可形成候选；任务验收不自动升级理解。本人额外核对本次使用的理解后才记录场景证据。
- 四阶段按具体证据判断，不将条数、天数、调用量换成经验值；反证、纠正、隐藏和到期影响后续使用。

实现：`server/elfred/memory-learning.mjs`、`memory-hub.mjs`、`knowledge.mjs`、`runtime.mjs`。
测试：`tests/elfred/memory-learning.test.mjs`。
