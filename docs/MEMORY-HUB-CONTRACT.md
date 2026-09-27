# 记忆中枢预留接口（elfred-memory-v1）

这是 Elfred 与未来 EmoS 适配服务的协议，不声称是 EmoS 原生 API。未配置时，本地 SQLite 的授权记忆照常工作；外部同步显示未配置。

## 服务端配置

```dotenv
ELFRED_MEMORY_HUB_URL=https://your-memory-adapter.example
ELFRED_MEMORY_HUB_TOKEN=server-only-token
```

只允许 HTTPS 或本机 HTTP，无重定向。配置留在服务端，不放进浏览器。适配服务必须按 `owner` 隔离租户；鉴权凭据与模型 Key 分开配置。

## 写入与停止使用

- `PUT /v1/memories/{id}`：传已自动准入的低风险工作偏好或本人已确认记录；均须未隐藏、未到期、来源仍可读。
- `DELETE /v1/memories/{id}`：否认、删除、替代、隐藏、到期、来源不可读或尚待高风险确认时停止外部使用。不存在也应返回幂等成功回执。
- Header：`Authorization: Bearer <server token>`；`Idempotency-Key: <id>:<revision>:<state_hash>:<intent_sequence>`。
- PUT 正文：`contract, owner, id, revision, content, scope, group, kind, risk, status, learning_mode, allocation, professional_scope, source_refs, alignment, domain_alignment, evidence, expires_at, supersedes_id, state_hash`。
- DELETE 正文：`contract, owner, id, revision, action: "forget", state_hash`。不附旧的私有正文。
- 成功返回：`{"owner":"当前租户","id":"当前对象","revision":3,"state_hash":"请求中的状态摘要"}`，四个字段必须与请求一致。

SQLite 中的 `memory_bridge` 是持久同步队列。旧版本排队事件跳过；回执不匹配或失败保留重试并退避；来源到期即使不改变版本也会排队停止使用；场景证据失效会同步降级后的投影。intent_sequence 保证同一版本的状态改变后恢复，也不会被旧幂等回执吞掉。删除后的错误回执不能被当成删除已完成。

## 应用只读出口

以下入口已实现，使用当前登录会话，客户端不能指定他人的 owner：

- `GET /api/elfred/memory/recall?scope=create&q=产品方案`：返回本人的相关、有效、自动准入或已确认的该领域记忆及来源和阶段；最多六条。
- `GET /api/elfred/memory/hub`：返回是否配置、待同步数量、最近成功回执时间；不返回地址或凭据。

普通子 Agent 对话和本人文字任务实际读取同一份授权本地缓存。Person 只存一份通用偏好，按任务目的和 allowed_systems 提供最少必要字段；私有领域记录默认不跨 Agent 共享；共享项目和群聊不自动注入个人私有记忆。一次任务专用的上下文授权及其衍生物不能扩大成长期画像。配置适配器后仍须验收外部权限、同步、删除和故障恢复，才能称为外部中枢已接通。

## 记忆写入与验证规则

- 本人明确表达的可撤销工作偏好自动记录；范围和风险由完整原句限制，模型缩短引用不能扩大到全局。模型响应不作为本人事实来源。
- 同一次模型调用可返回至多三条有原句的候选，不追加提取调用。健康、身份、财务、价值观等敏感或未识别个人描述待本人核对。临时情绪、单次喜好、引文、一次性要求和密钥不写入画像。
- 初始化已核对的明确选择作为选择事实形成分领域初始理解；不确定和跳过不写成事实，不能由选择直接推断已长期稳定。
- 分配按职责和具体场景；通用偏好只在 Person 保存一份。限定产品方案的偏好不用于周报。共享项目、群聊不自动读取或学习私人画像。
- 自然反馈只有指向本次实际使用的理解时才形成正证据或反证。普通“好”、仅验收、重复表扬和对反馈的回复不升级。不同日期和实际场景的持续支持才自动进入跨时间稳定；数量不是经验值。全局理解的应用证据按使用领域分别判断。
- 纠正只替代相同领域、话题、场景；删除、撤权、到期、源版本改变使相关正反证失效。推断失去依据仍是推断，不自动变成事实。
- 工具方法经验只在已验收的私人真实任务中沉淀，同一领域、工具和版本内复用；不计入用户理解程度，也不改写生产 Skill 工作流。

外部适配器必须保留 allocation 的 holder、allowed_systems、contextual、scenario 和 professional_scope，不能把全部记忆复制给五个 Agent。kind 区分 user_understanding 与 method_experience。返回记忆仍须经过 Elfred 本地权限、目的、来源和有效性检查，外部召回不扩大授权。

实现：`server/elfred/memory-learning.mjs`、`memory-allocation.mjs`、`memory-feedback.mjs`、`memory-validity.mjs`、`memory-hub.mjs`、`knowledge.mjs`、`runtime.mjs`。
测试：`tests/elfred/automatic-memory.test.mjs`、`memory-learning.test.mjs`、`onboarding-choice.test.mjs`。
