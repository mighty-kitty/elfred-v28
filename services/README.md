# 上游服务

主应用（Next + Node 服务）不依赖这里的任何一个进程就能跑。地址可达与业务接通分别验证；健康检查不能代替同步或执行回执。源码在本目录下，各自都带自己的说明与测试。

当前 Elfred 部署使用 `emos-memory/src/memory_system/api/elfred_bridge.py` 作为受限适配入口，启动时由 `scripts/emos-process.mjs` 管理。它使用 EMOS 原生 SQLite 存储，只开放带服务端令牌的 `/v1/memories/:id` 同步契约，保留应用的用户、分配、阶段和证据规则。原生 `/memory/*` 接口不在这个部署入口开放；不宣称已启用其自动抽取、反思或原生召回。遗忘回执也持久保存，旧写入不能恢复已删除内容。

配置：`ELFRED_MEMORY_HUB_URL=http://127.0.0.1:8200`、`ELFRED_MEMORY_HUB_TOKEN`（至少 32 位服务端随机令牌）、`ELFRED_MEMORY_HUB_AUTOSTART=true`、`ELFRED_PYTHON`（Python 3.11+）。数据库固定在应用数据目录的 `emos-memory.sqlite`，不随重启换文件；令牌只放私有环境配置。Skill Foundry 与 PA 网关尚未参与本应用执行，不能只凭健康检查称为接通。

| 目录 | 是什么 | 默认地址 | 健康检查 | 启动 |
| --- | --- | --- | --- | --- |
| `emos-memory/` | 记忆中枢：记忆的抽取、存储、检索与反馈 | 原生 `http://127.0.0.1:8000`；Elfred 适配部署 `8200` | `GET /health` | 原生：`python -m src.memory_system.api.server`；Elfred：由主应用管理 |
| `skill-foundry/` | 能力卡组的来源：从真实上下文生成、版本化并交付 skill | `http://127.0.0.1:8765` | `GET /v1/elfred/health` | `python -m adapter` |
| `pa-gateway/` | 规划与执行的网关：把任务拆成可核对的步骤，接记忆与工具 | `http://127.0.0.1:8790` | `GET /health` | `python -m uvicorn app.main:app --port 8790` |

主应用侧对应 `config/local.env.example` 里的三个地址（`ELFRED_MEMORY_HUB_URL` / `ELFRED_SKILL_FOUNDRY_URL` / `ELFRED_PA_GATEWAY_URL`）；填好之后，第四页设置页的「上游服务状态」会按实时探测显示，不是写死的。

## 各服务的准备

三个服务都是 Python 工程，各自在自己的目录里建虚拟环境、按目录里的依赖清单安装，然后按上表的命令启动。端口如果和本机别的东西撞了，改启动命令里的端口，并把主应用那三个地址一起改掉。

- `emos-memory/`：Python 3.11 及以上，`requirements.txt`（开发另加 `requirements-dev.txt`），配置项见 `.env.example`，跑测试 `python -m pytest -q`。
- `skill-foundry/`：要求 Python 3.12（`pyproject.toml` 里写的 `>=3.12,<3.13`，代码用了 3.12 才允许的写法），用 `uv sync --frozen` 或 `uv run --frozen python -m adapter` 会自动选对解释器；配置项见 `.env.example`，跑测试 `python -m pytest -q`。
- `pa-gateway/`：与上面同一个解释器即可，配置项见 `.env.example`（模型与 Letta 相关项留空即可，默认走确定性的规划器），跑测试 `python -m pytest -q`。

## 目录里没有什么

为了不把运行时产物和私密配置带进仓库，下面这些只在本地存在：各自的 `.env`（只提交 `.env.example`）、虚拟环境、`__pycache__`、数据库文件（`*.db` / `*.sqlite3`）、日志目录，以及记忆中枢里那份官方的 LoCoMo 基准数据集（体积与来源原因，跑基准前按 `emos-memory/docs/benchmark_protocol.md` 取回）。

## 与主应用的边界

主应用只通过 HTTP 健康检查和一个版本化的记忆同步契约跟这些服务打交道，不直接读它们的数据库，也不把用户的私密记忆内容塞进健康检查。任何一个上游挂掉，应用自己的任务、记忆、能力卡都照常可用。
