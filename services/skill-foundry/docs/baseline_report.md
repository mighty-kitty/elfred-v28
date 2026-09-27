# FreeTodo 原版运行基线报告

基线日期：2026-07-13；平台：Windows；源码：未经修改的 `0.1.2` / commit `800cd27344fe1eb99f429d0aec22e99ed189d921` 运行副本。

## 工具链

| 项目 | 实测值 | 结论 |
|---|---:|---|
| Python | 3.12.1 | 满足 `>=3.12,<3.13` |
| Node.js | 25.2.1 | 满足文档的 Node 20+ |
| pnpm | 10.28.1 | 安装 lockfile 成功 |
| uv | 0.11.28 | `uv sync --frozen --no-dev` 成功 |
| 后端依赖 | 189 packages | 完整 lock 安装成功 |
| 前端依赖 | 789 packages | `pnpm install --frozen-lockfile` 成功 |

机器全局 `E:/python` 含损坏的 `_py_iztro.pth`，其 UTF-8 中文路径被系统 site 初始化按错误编码读取，直接启动会触发 `UnicodeDecodeError`。基线通过 `python -S -m venv` 建立隔离环境规避；没有修改用户全局 Python。

## 后端

- 地址：`http://127.0.0.1:8001`
- `/health`：`healthy`
- 数据库：`connected`
- 全部数据库 migration 成功。
- OpenAPI：94 paths、101 operations，已导出为 `freetodo_openapi.json`。
- Scheduler 共注册 7 个 job；recorder、todo_recorder、OCR、activity aggregator、proactive OCR、audio recording 均 `next_run_time=null`，即配置基线下暂停，不产生重复采集。
- LLM、Tavily 未配置；因此 AI 聊天、AI 日记、人工 Activity 摘要等依赖模型的功能不作为本次离线验收项。
- 默认 observability 会尝试本地 Phoenix/OTLP；演示部署应显式关闭，避免无意义连接日志。

## 真实 HTTP 冒烟

使用隔离运行数据库完成并清理：

- Todo：POST、GET/list、PUT、DELETE 成功；
- Journal：POST、GET/list、关系字段、DELETE 成功；
- Activity：`POST /api/activities/manual` 对伪造 external event 返回 404，符合代码合同；
- Event API 没有 create endpoint，仅提供查询、上下文和摘要。

结论：Todo 和 Journal 可以由 sidecar 通过 HTTP 稳定写入。Activity 依赖 FreeTodo 内部 Event 数字 ID 和 LLM，现阶段必须在 Adapter 侧维护，不能通过 HTTP 导入 Elfred ContextEvent，也不能直写 FreeTodo DB。

## 前端

- 地址：`http://127.0.0.1:3001`
- Next.js 16.1.6 启动成功，连接后端 8001。
- 浏览器实测 Todo、Calendar、Settings、Chat 可渲染。
- Diary、Activity 在前端配置中列为 `DEV_IN_PROGRESS_FEATURES`，默认不出现在 Dock；这与任务书期望的成熟 Diary/Activity 演示存在差距。
- Calendar 首次显示月份停留在 2026 年 05 月，而系统日期为 2026-07-13；“今天”单元格存在但首屏月份定位异常，列入上游 UI 风险。

截图：`baseline_frontend_home.png`、`baseline_frontend_calendar.png`、`baseline_dev_panels_hidden.png`。真实 Adapter 数据进入后另有 `demo_todos_real.png` 与 `demo_calendar_today.png`。

## Elfred 专用配置副本验证

由原版完整 default config 与 Adapter override 生成 `.runtime/freetodo_elfred_config/config/config.yaml`，在独立 8002 端口重新完成全部 migration：health healthy、database connected、7 个 scheduler jobs 全部 paused、运行中 job 为 0；验证后正常停止。配置没有写回上游源码。

## 基线结论

原版可作为演示 Todo/Calendar/Journal 的成熟产品底座，但不能把“Activity 外部写入”“日报自动生成”“Elfred 来源追溯/forget”“Memory/PA 对接”宣称为 FreeTodo 原生已具备。这些必须由 Adapter 实现并独立测试。
