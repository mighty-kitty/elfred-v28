# EMOS Agent Local Deployment Guide

## Goal

This guide is for an agent team that needs to deploy EMOS on its own laptop or workstation.

The goal is not to make the receiver read the codebase first. The goal is to let the receiver complete these steps directly:

1. install dependencies
2. start the EMOS API locally
3. verify the API is healthy
4. connect an upper-layer agent through HTTP

## Minimum Handoff Set

Ship at least these files and folders together:

- the project directory itself
- [README.md](README.md)
- [docs/agent_local_deployment_guide.md](docs/agent_local_deployment_guide.md)
- [docs/agent_api_endpoint_catalog.md](docs/agent_api_endpoint_catalog.md)
- [docs/api_reference.md](docs/api_reference.md)
- [docs/agent_api_quickstart.md](docs/agent_api_quickstart.md)
- [examples/agent_api_client.py](examples/agent_api_client.py)
- [examples/agent_api_requests.http](examples/agent_api_requests.http)
- [scripts/run_api.ps1](scripts/run_api.ps1)

## Environment Requirements

- Windows + PowerShell
- Python 3.10+
- working `python` and `pip`

Current dependency footprint:

- runtime: [requirements.txt](requirements.txt)
- dev/test: [requirements-dev.txt](requirements-dev.txt)

## Step 1: Enter The Project Root

```powershell
cd .
```

If the receiver stores the project elsewhere, only the project root matters.

## Step 2: Create A Virtual Environment And Install Dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If the receiver also wants local test commands:

```powershell
pip install -r requirements-dev.txt
```

## Step 3: Understand The Default Startup Behavior

Default startup script:

```powershell
.\scripts\run_api.ps1
```

This script automatically:

- moves to the project root
- enables UTF-8 console output
- creates isolated runtime files
- uses `auto` storage mode
- prefers SQLite
- places the live SQLite runtime under an ASCII-safe local temp path when the workspace path is not SQLite-safe

That means the receiver usually does not need to:

- create a database manually
- prepare `data/runtime` first
- edit source files before first launch

## Step 4: Start The API

Simplest startup path:

```powershell
.\scripts\run_api.ps1
```

Default bind address:

- `http://127.0.0.1:8000`

Expected console line:

```text
Memory API listening on http://127.0.0.1:8000
```

## Step 5: Change Host Or Port If Needed

The API server now supports bind overrides through environment variables. The receiver does not need to edit source files.

Example: change the port to `8010`

```powershell
$env:MEMORY_SYSTEM_API_PORT = "8010"
.\scripts\run_api.ps1
```

Example: allow LAN access from the same local network

```powershell
$env:MEMORY_SYSTEM_API_HOST = "0.0.0.0"
$env:MEMORY_SYSTEM_API_PORT = "8010"
.\scripts\run_api.ps1
```

Defaults:

- `MEMORY_SYSTEM_API_HOST=127.0.0.1`
- `MEMORY_SYSTEM_API_PORT=8000`

## Step 6: Run Discovery Checks First

Do not connect the agent immediately. Verify the discovery surfaces first:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/openapi.json"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/system/agent-api-manifest"
```

Confirm:

- `/health` returns `status=ok`
- `/` returns `openapi` and `agent_api_manifest`
- `/openapi.json` returns an OpenAPI document
- `/system/agent-api-manifest` returns preferred entrypoints and call flows

## Step 7: Run A Local Smoke Check

Before wiring the upper-layer agent, run:

```powershell
.\scripts\run_smoke.ps1
```

If the receiver installed dev/test dependencies, also run:

```powershell
python -B -m pytest tests/test_api.py -q
```

## Step 8: What The Upper-Layer Agent Should Call First

Recommended first integration surface:

- `POST /memory/write-plan`
- `POST /memory/write`
- `POST /memory/recall`

Second-stage integration surface:

- `POST /memory/update`
- `POST /memory/forget`
- `POST /memory/history`
- `POST /memory/restore`
- `POST /memory/supersede`
- `POST /memory/merge`

Preferred response read order:

1. `payload.execution_surface.policy_input`
2. `payload.execution_surface.execution_policy`
3. `payload.execution_surface.action_surface`
4. `payload.execution_surface.agent_handoff`

The upper-layer agent should not reconstruct memory policy from raw retrieval candidates when the thin execution surface already provides a direct answer path.

## Step 9: Recommended First End-To-End Call Chain

### 1. Read The Manifest

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/system/agent-api-manifest"
```

### 2. Run Write Plan

```powershell
$body = @{
  user_id = "demo-user"
  session_id = "demo-session"
  text = "The user prefers black coffee with no sugar."
  task_type = "chat"
  memory_scope = "auto"
  source = "agent"
  task_goal = "capture durable preference"
  context_summary = "personalization update"
  working_memory = @("coffee preference")
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/memory/write-plan" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

### 3. Run Durable Write

Reuse the same body, change the path to:

- `/memory/write`

### 4. Run Grounded Recall

Switch to a recall payload and call:

- `/memory/recall`

## Step 10: Storage And Log Paths

Default path behavior is defined in [config.py](src/memory_system\config.py).

Most important environment variables:

- `MEMORY_SYSTEM_STORAGE_BACKEND`
- `MEMORY_SYSTEM_MEMORY_FILE`
- `MEMORY_SYSTEM_SQLITE_FILE`
- `MEMORY_SYSTEM_RETRIEVAL_SETTINGS_FILE`
- `MEMORY_SYSTEM_FEEDBACK_STORE_FILE`
- `MEMORY_SYSTEM_INTERACTION_LOG_FILE`
- `MEMORY_SYSTEM_OFFLINE_EVAL_DIR`

Common interpretation:

- if the receiver does not override them, EMOS chooses default paths
- if the receiver wants explicit local persistence paths, set environment variables first

Example:

```powershell
$env:MEMORY_SYSTEM_MEMORY_FILE = "D:\emos_runtime\memory_store.json"
$env:MEMORY_SYSTEM_SQLITE_FILE = "D:\emos_runtime\memory_store.sqlite3"
.\scripts\run_api.ps1
```

## Common Issues

### Port already in use

```powershell
$env:MEMORY_SYSTEM_API_PORT = "8010"
.\scripts\run_api.ps1
```

### Need LAN access

```powershell
$env:MEMORY_SYSTEM_API_HOST = "0.0.0.0"
.\scripts\run_api.ps1
```

### SQLite path concern

EMOS already applies guardrails:

- prefer SQLite
- auto-shift the live runtime to an ASCII-safe temp path when needed
- fall back only when SQLite is truly blocked

To force a specific SQLite file:

- set `MEMORY_SYSTEM_SQLITE_FILE`

### Not sure which endpoints to read first

Use this order:

1. `/`
2. `/openapi.json`
3. `/system/agent-api-manifest`
4. `/memory/write-plan`
5. `/memory/write`
6. `/memory/recall`

## Final Recommendation

For a first local deployment, do not connect every endpoint at once.

Recommended rollout:

1. start the service
2. run discovery checks
3. run smoke
4. connect `write-plan / write / recall`
5. connect lifecycle endpoints later

This keeps deployment, integration, and policy issues separated and makes local rollout much faster.
