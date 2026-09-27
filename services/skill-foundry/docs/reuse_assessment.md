# 功能复用审计

| 能力 | 判定 | 理由/落点 |
|---|---|---|
| Todo CRUD、状态、优先级、DDL | 通过 API 复用 | 上游模型和 UI 成熟；Adapter 负责映射/幂等 |
| Calendar | 直接复用 | Todo 的时间字段在原 UI 展示 |
| Journal CRUD 和关系 | 通过 API 复用 | Adapter 生成 idea 导向内容 |
| Activity 查询/UI | 有限复用 | 只能显示 FreeTodo 自己生成的 Activity |
| Elfred Activity 写入 | 需要 Adapter | 上游无 external Event API |
| Topic registry | 需要 Adapter | tags/categories 不具备稳定 ID/alias/父子关系 |
| ContextEvent ingest | 需要 Adapter | 上游无合同或写入口 |
| 隐私 gate/redaction | 需要 Adapter | Observer 字段不能直接透传 |
| 来源追溯、forget | 需要 Adapter | 上游没有 Elfred event link |
| Memory/PA outbox | 需要 Adapter | 合作方合同与 FreeTodo 解耦 |
| LLM 结构化抽取 | 需要 Adapter | mock/offline 和 provider 必须可替换 |
| FreeTodo 自带 chat/agent | 关闭为主链 | 避免替代 Personal Agent；演示可人工打开 |
| OCR/截图/录音采集 | 关闭 | 与 Observer 重复 |
| Activity external API | 需要 fork 扩展 | 仅在未来有独立 fork 决策后考虑 |
| 品牌/前端来源筛选 | 放弃首期改造 | sidecar 阶段保持上游原样 |

原 Organizer 的 ContextEvent 兼容、privacy、topic alias、outbox、mock provider、forget/reconcile 测试思路可复用为迁移知识，但不把 legacy 运行库作为 Adapter 隐式依赖。
