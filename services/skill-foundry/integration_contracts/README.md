# Elfred integration contracts

这些 JSON Schema 是本次 Adapter 的本地 `v1` 合同。当前工作区没有发现 Memory 或 Personal Agent 团队签发的独立 endpoint/auth 合同，因此两份 Outbox Schema 是经过真实 Observer 数据验证的 provisional contract，不冒充合作方最终合同。

兼容规则：生产者可新增字段；消费者必须忽略未知字段；破坏性变化发布新的 major schema；Outbox 通过稳定 item ID 幂等并显式 ack。
