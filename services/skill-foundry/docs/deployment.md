# Windows 演示部署

## 1. FreeTodo 原版后端

依赖安装在隔离 runtime，源码用 `.runtime/FreeTodo` 运行副本；`third_party/FreeTodo` 保持哈希一致。

```powershell
$env:LIFETRACE_DATA_DIR='E:\Observer\.runtime\freetodo_data'
cd E:\Observer\.runtime\FreeTodo
E:\Observer\.runtime\freetodo_backend_venv\Scripts\python.exe -m lifetrace.scripts.start_backend --host 127.0.0.1 --port 8001 --mode dev
```

使用 `adapter.scripts.make_freetodo_config` 可从上游完整 default config 与 `config/freetodo_elfred_overrides.json` 生成运行配置；所有采集/OCR/录音/Activity aggregation job 和 observability 默认关闭。

## 2. FreeTodo 原版前端

```powershell
$env:NEXT_PUBLIC_API_URL='http://127.0.0.1:8001'
cd E:\Observer\.runtime\FreeTodo\free-todo-frontend
npx pnpm dev --hostname 127.0.0.1 --port 3001
```

## 3. Adapter

```powershell
cd E:\Observer\elfred_freetodo_adapter
$env:FREETODO_BASE_URL='http://127.0.0.1:8001'
$env:ELFRED_ADAPTER_DB='E:\Observer\.runtime\adapter_data\elfred_adapter.db'
$env:ELFRED_CONTEXT_BACKEND='freetodo'
.\.venv\Scripts\python.exe -m adapter
```

探针：FreeTodo `GET http://127.0.0.1:8001/health`；Adapter `GET http://127.0.0.1:8765/v1/elfred/health`；UI `http://127.0.0.1:3001`。

真实演示复现命令：

```powershell
.\.venv\Scripts\python.exe -m adapter.scripts.demo_end_to_end --real-http --db E:\Observer\.runtime\adapter_demo\elfred_adapter.db
```

不要在生产中使用 `--reset-demo`；该选项只清除 adapter-owned `demo-20260713-*` Todo 和当日 demo Journal。
