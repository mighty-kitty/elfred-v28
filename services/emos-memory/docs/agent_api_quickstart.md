# EMOS Agent API Quickstart

## Goal

This document is for an upper-layer agent team that wants to call EMOS as an independent memory engine / memory service.

## Start The API

```powershell
.\scripts\run_api.ps1
```

Default local address:

- `http://127.0.0.1:8000`

## Discovery Endpoints

- `GET /health`
- `GET /openapi.json`
- `GET /system/agent-api-manifest`

Recommended first call:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/system/agent-api-manifest"
```

## Recommended Agent Read Order

For agent-facing memory contracts, prefer reading:

1. `payload.execution_surface.policy_input`
2. `payload.execution_surface.execution_policy`
3. `payload.execution_surface.action_surface`
4. `payload.execution_surface.agent_handoff`

## Core Call Flows

### 1. Plan Then Write

`POST /memory/write-plan`

Use this before writing durable memory when the upper-layer agent wants EMOS to decide:

- whether the content should be durable at all
- whether it should write new memory
- whether it should update / deduplicate instead

Then call:

- `POST /memory/write`

### 2. Grounded Recall

`POST /memory/recall`

Use this when the upper-layer agent wants:

- grounded answer support
- memory-context bundle
- response guardrails
- confirmation guidance

### 3. Lifecycle Resolution

Use:

- `POST /memory/history`
- `POST /memory/update`
- `POST /memory/forget`
- `POST /memory/restore`
- `POST /memory/supersede`
- `POST /memory/merge`

### 4. System Readiness

Use:

- `GET /system/agent-readiness-summary`
- `GET /system/report`

## Minimal Example Payloads

### Write Plan

```json
{
  "user_id": "demo-user",
  "session_id": "demo-session",
  "text": "The user prefers black coffee with no sugar.",
  "task_type": "chat",
  "memory_scope": "auto",
  "source": "agent",
  "task_goal": "capture durable preference",
  "context_summary": "personalization update",
  "working_memory": ["coffee preference came up during planning"]
}
```

### Recall

```json
{
  "user_id": "demo-user",
  "session_id": "demo-session",
  "query_text": "What coffee preference should I remember?",
  "top_k": 5,
  "include_profile": true,
  "task_goal": "answer from long-term memory",
  "context_summary": "agent wants a grounded answer",
  "working_memory": ["answer briefly"],
  "response_mode": "execution_surface"
}
```

## Practical Notes

- EMOS is the memory layer, not the full personal agent.
- The upper-layer agent should not reconstruct memory policy from raw candidates if `execution_surface` already gives a direct answer path.
- For storage / operator review, use `GET /system/report` or `GET /system/storage`, not the memory endpoints.
