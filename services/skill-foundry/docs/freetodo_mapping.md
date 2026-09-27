# ContextEvent → FreeTodo 映射

## Todo

任务来源按 `content.tasks` 和 `suggestions.task_card_suggestions` 合并并在事件内去重。标题规范化后写入 `name`；合法 ISO 时间、`今天`、`明天`可转换到 `due`，无法确定的时间保持空值，不猜 DDL；priority 仅允许 `high/medium/low/none`。

置信度低于 `ELFRED_ACTIVE_TASK_THRESHOLD`（默认 0.70）或事件要求用户确认时，状态写为 `draft`，否则为 `active`。Topic 映射到 tags/categories。`uid`、Adapter link table 和 `user_notes` 中的 `ELFRED_SOURCE` 标记共同提供幂等和反查。

## Journal

每天使用稳定 UID `elfred-daily-YYYY-MM-DD` 维护一篇 Journal：

- `content_objective`：今日主线、关键进展、任务变化、来源索引；
- `content_ai`：新想法与认识、关键决策、风险与卡点、等待与依赖、下一步；
- `related_todo_ids`：当日已同步 Todo；
- tags：稳定 Elfred Topic 名称。

当前实现的 deterministic provider 不调用 LLM，也不把日报写成原始事件流水账。周报按主题和 idea/decision/risk/waiting 重新综合，不拼接七篇日报。

## Activity

FreeTodo 0.1.2 的 `POST /api/activities/manual` 只接受 FreeTodo 内部数字 Event ID，并要求内部事件已结束、未关联且 LLM 可用；FreeTodo 没有 external Event create API。因此 Adapter 维护 `local_only` Activity，并通过 `/activities` 展示，不直写上游数据库。此能力只有未来 fork 新增 external API 后才能转为 FreeTodo Activity。

## 手工修改保护

每次创建或更新记录 FreeTodo 返回对象的 canonical semantic hash。forget、日报更新和 reconcile 前重新读取远端：hash 漂移时标记 `manual_modified`/`preserved_user_modified`，不覆盖、不删除、不偷偷重建。
