# Legacy Organizer 迁移

原 Organizer 保留在 `elfred_context_organizer_legacy`，不删除、不覆盖。迁移工具读取 legacy SQLite 的 canonical `payload_json`，不会把旧 Markdown 当作 canonical 数据。

先审计：

```powershell
python -m adapter.scripts.migrate_legacy --source-db <legacy.db> --dry-run --report migration_dry_run.json
```

确认 FreeTodo/Adapter 健康后实际迁移：

```powershell
python -m adapter.scripts.migrate_legacy --source-db <legacy.db> --report migration_report.json
```

迁移覆盖 ContextEvent、可解析的 Topic/alias、pending Memory/PA Outbox。每批记录 `migration_batches`、导入事件 ID 和报告。原 legacy DB、文档和 outbox 不被删除。

当前工作区未发现 legacy 运行数据库，因此已实现并测试 synthetic SQLite dry-run/actual/rollback，不能宣称已有生产历史数据完成迁移。
