# Elfred FreeTodo Adapter

独立 HTTP sidecar：接收 Elfred Observer 的真实 `ContextEvent`，在本地完成隐私判断、幂等、Topic、Todo/Journal 映射、来源链接、forget/reconcile，并向 Memory 与 Personal Agent 暴露版本化 Outbox。它不会导入或修改 FreeTodo Python 包，也不会直写 FreeTodo SQLite。

## 快速启动

```powershell
cd E:\Observer\collaboration\Elfred\elfred_freetodo_adapter\elfred_freetodo_adapter
uv sync --frozen
$env:FREETODO_BASE_URL='http://127.0.0.1:8001'
uv run python -m adapter
```

Adapter 默认监听 `127.0.0.1:8765`，API 前缀为 `/v1/elfred`，交互文档为 `/docs`。

仓库根目录的一键启动默认使用本地自动同步和本地任务投影：

```powershell
# 默认：本地采集、历史/新增事件入队、本地微信任务投影和 FreeTodo 同步
powershell -ExecutionPolicy Bypass -File .\scripts\start_demo.ps1

# 显式同意后：启用 Hermes，并把任务分析限定为微信/Weixin
powershell -ExecutionPolicy Bypass -File .\scripts\start_demo.ps1 -EnableLlmTaskAnalysis
```

真实模型模式通过本机 Hermes Agent 连接 Sub2API 网关。精确模型 ID、上游凭据和本地 Hermes Bearer 只从本机 `.env` 读取，浏览器仅访问 Adapter BFF。它不发送截图图片；一键脚本通过 `ELFRED_TASK_ANALYSIS_CLOUD_APPS=WeChat,Weixin,微信` 只允许微信脱敏 OCR 进入任务分析。直接运行 Adapter 时可按实际授权范围配置该逗号分隔变量；留空表示不额外限制应用。模型返回内容类型、领域分类、任务阶段和已有任务关系。`canonical_tasks` 与 `task_evidence` 让不同截图能够更新同一张 FreeTodo 卡，而不是按截图重复建卡。旧版卡会按严格来源标记安全收养，用户改过的卡不会被覆盖。常见独立凭据格式在 Observer 和 Adapter 两层阻断。模型失败会自动重试，也不会把确定性规则任务冒充成模型任务。

主要审计接口：

- `/v1/elfred/status`
- `/v1/elfred/events/{event_id}/task-analysis`
- `/v1/elfred/tasks`
- `/v1/elfred/tasks/{task_id}`

## 演示

FreeTodo 已启动时运行真实 HTTP 演示：

```powershell
uv run python -m adapter.scripts.demo_end_to_end --real-http --reset-demo
```

完全离线、无付费 API 的验收：

```powershell
uv run python -m adapter.scripts.demo_end_to_end
```

## 被动 Skill Foundry

Adapter 默认在后台观察 FreeTodo 中的已完成任务。它会在本地结合任务类型、
语义、项目和真实轨迹维护“同类任务候选组”；达到最低观察数量后自动生成
持续演化的 Skill 草稿。任务数量只负责触发比较，证据完整度、同类可信度、
流程收敛度、历史对齐和安全样本复演共同决定“提炼就绪度”。因此两个高质量任务可能足够，
十几个互相矛盾或证据稀疏的任务也不会被误判为完成。这个过程不要求用户
手选任务，也不会自动批准或执行 Skill。

- `ELFRED_SKILL_PASSIVE_ENABLED=true|false`：开关后台归类。
- `ELFRED_SKILL_PASSIVE_INTERVAL=15`：扫描间隔（秒）。
- `ELFRED_SKILL_PASSIVE_MIN_TASKS=2`：开始比较规律的最低次数，不是完成门槛。
- `ELFRED_SKILL_PASSIVE_MAX_TASKS=20`：单个版本的有界证据上限。
- `ELFRED_SKILL_CLASSIFICATION_PROVIDER=auto|hermes|deterministic`：语义画像方式。
- `ELFRED_SKILL_CLASSIFICATION_MAX_CHARS=2400`：送入分类器的脱敏文本上限。
- `GET /v1/elfred/skills/passive/status`：候选组和 Worker 状态。
- `GET /v1/elfred/skills/passive/profiles`：不含原始正文的分类审计记录。

已批准 Skill 在自动学习到新证据时仍继续使用原发布版本；新版本保持待审，
只有用户批准后才替换发布版本。启动脚本默认不再写入演示任务，如需演示数据
可显式传入 `-EnableSkillFoundryDemoSeed`。

界面中的 100% 专指 Skill 已满足任务类型化证据、规律收敛、至少两次历史
对齐、至少两次不修改历史任务的安全复演和安全执行适配器门槛。未成熟版本会显示阻断原因和下一步所需证据，
并继续在后台吸收新的完成记录。

## Journal 四硬件输出

Adapter 内置一个独立的 `hardware_output` 模块。它接收已完成 Journal，生成阿福
悬浮件、阿福底座、机械臂和打印机的白名单动作计划，再通过持久化队列执行。
默认四个设备使用 Mock Adapter，因此硬件未到场时也能演示完整的计划、确认、
执行、重试和诊断链路。

Adapter 内的 Journal 生成成功后会自动旁路创建计划，但不会自动执行。dry-run、
硬件关闭或旁路异常都不影响原 Journal 返回；设置
`ELFRED_HARDWARE_AUTO_PLAN_ON_JOURNAL=false` 可单独关闭自动建计划。完整 Memory
暂不接入，仅保留 `HardwareMemoryPort` 扩展接口。

- `GET /v1/elfred/hardware-output/status`：四设备、规划器和 Worker 状态。
- `POST /v1/elfred/hardware-output/journals/ready`：协作者推送完成的 Journal。
- `POST /v1/elfred/hardware-output/plans/{plan_id}/execute`：通用执行入口。
- `GET /v1/elfred/hardware-output/doctor`：现场自检。
- `GET /v1/elfred/hardware-output/support-bundle`：不含 Journal 正文的诊断包。

悬浮件使用已经验证的 XIAO ESP32-S3 Wi-Fi 固件时，可把本地硬件配置中的
`pendant.transport` 设为 `xiao`。该传输复用 `/api/status` 和
`X-Xiao-Token`，但为物理输出保留独立的 `/api/hardware/*` 路由，避免把输入
数据流的 `/api/stop` 误当作物理停止。示例见
`config/hardware_output.xiao.example.json`，固件接口见
`integration_contracts/xiao_hardware_command_v1.md`。未安装命令扩展的现有固件
仍可继续传文件，但 Doctor 会明确显示 `firmware_incompatible`，不会假装输出
已经可用。

默认规则模式不调用云端。只有同时设置
`ELFRED_LLM_CLOUD_CONSENT=true` 和 `ELFRED_HARDWARE_LLM_ENABLED=true`
时，动作建议才通过 Hermes 调用已配置的 Sub2API 模型；模型仍只能选择预设，机械臂始终
需要确认。硬件 HTTP contract、配置和联调步骤见
`integration_contracts/hardware_output_v1.md` 及仓库
`docs/hardware_output_adapter.md`。

## 回退

`ELFRED_CONTEXT_BACKEND=freetodo|legacy` 是上层路由的显式 feature flag。Adapter 会报告当前值；它不会删除或改写 `elfred_context_organizer_legacy`。具体部署和回退见 `docs/`。
