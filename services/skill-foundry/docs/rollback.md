# 回退与撤回

运行时由上层选择 `ELFRED_CONTEXT_BACKEND=legacy|freetodo`。切到 legacy 不需要删除 Adapter DB 或 FreeTodo 对象；先停止向 Adapter 写入，再切换路由。

单事件撤回使用 `/events/{event_id}/forget`。未被用户修改的 Todo 会删除；共享日报会去掉该来源并重建；检测到手工修改时只解除链接并保留用户内容。FreeTodo 不可用时作业进入 retry，而不是谎报完成。

迁移批回滚：

```powershell
python -m adapter.scripts.migrate_legacy --rollback <batch_id>
```

回滚按逆序执行每个导入事件的 drift-aware forget，原 legacy 数据始终不变。若部分远端不可用，批状态为 `rollback_partial`，应恢复 FreeTodo 后重试/对账。
