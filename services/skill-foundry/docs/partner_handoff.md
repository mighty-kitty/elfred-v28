# Memory / Personal Agent 对接说明

工作区中没有发现合作方签发的 endpoint、鉴权、重试窗口或删除回执合同。因此本次实现只承诺本地 durable Outbox + ack；外部推送未擅自启用。

Memory 读取 `/v1/elfred/outbox/memory`，校验 `memory_candidate_outbox_v1.schema.json`，仅消费 `delivery_gate=eligible` 或在用户确认后消费 `confirm_required`，成功后调用 `/outbox/{item_id}/ack`。

Personal Agent 读取 `/v1/elfred/outbox/personal-agent`，校验 `personal_agent_context_outbox_v1.schema.json`，使用 `source_event_id` 去重并在使用后 ack。两类 item ID 都由 event ID + payload hash 确定，Adapter 重启或 Observer 重放不会重复。

正式接入前合作方仍需确认：endpoint/auth、consumer identity、多租户边界、max batch、重试/死信、删除/forget 传播、ack 是否需要版本或签名、保留周期。
