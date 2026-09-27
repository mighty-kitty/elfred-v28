# EMOS Agent API Endpoint Catalog

## Purpose

This catalog is a direct receiver-facing endpoint list.

If the receiving team does not want to scan the codebase first, start here and pair it with:

- [docs/agent_local_deployment_guide.md](docs/agent_local_deployment_guide.md)
- [docs/agent_api_quickstart.md](docs/agent_api_quickstart.md)
- [docs/api_reference.md](docs/api_reference.md)

## Group 1: Discovery And Onboarding

### `GET /`

Purpose:

- API landing surface
- tells the receiver where health, OpenAPI, and manifest live

### `GET /health`

Purpose:

- smallest health probe

### `GET /openapi.json`

Purpose:

- machine-readable OpenAPI 3.1 document
- useful for client generation and request-model inspection

### `GET /system/agent-api-manifest`

Purpose:

- EMOS-specific integration manifest
- tells the upper-layer agent what to call first and how to read the response

## Group 2: Primary Agent Memory Endpoints

### `POST /memory/write-plan`

Purpose:

- ask EMOS whether a piece of content should become durable memory before mutation

Key request fields:

- `user_id`
- `session_id`
- `text`

Common optional fields:

- `task_type`
- `memory_scope`
- `task_goal`
- `context_summary`
- `working_memory`

Preferred response read order:

1. `payload.execution_surface.policy_input`
2. `payload.execution_surface.execution_policy`
3. `payload.execution_surface.action_surface`
4. `payload.execution_surface.agent_handoff`

### `POST /memory/write`

Purpose:

- execute the durable memory write

Key request fields:

- `user_id`
- `session_id`
- `text`

### `POST /memory/recall`

Purpose:

- retrieve grounded memory context for upper-layer agent response generation

Key request fields:

- `user_id`
- `query_text`

Common optional fields:

- `session_id`
- `top_k`
- `include_profile`
- `task_goal`
- `context_summary`
- `working_memory`
- `response_mode`

### `POST /memory/reflect`

Purpose:

- generate a reflection summary

## Group 3: Memory Lifecycle

### `POST /memory/update`

Purpose:

- update an existing memory

### `POST /memory/forget`

Purpose:

- soft-forget a memory

### `POST /memory/history`

Purpose:

- inspect revision history and lifecycle details

### `POST /memory/restore`

Purpose:

- restore a forgotten memory

### `POST /memory/supersede`

Purpose:

- mark an older memory as superseded by a newer memory

### `POST /memory/merge`

Purpose:

- merge one memory into another

## Group 4: Core Memory Blocks

### `POST /memory/block`

Purpose:

- set or update a core memory block

### `POST /memory/block/delete`

Purpose:

- delete a core memory block

### `GET /memory/blocks?user_id=...`

Purpose:

- inspect current blocks for a user

## Group 5: Feedback, Profile, And Export

### `POST /memory/feedback`

Purpose:

- record a feedback signal

### `GET /memory/feedback?user_id=...&limit=...`

Purpose:

- inspect feedback report

### `GET /memory/profile?user_id=...&limit=...`

Purpose:

- inspect user memory snapshot

### `GET /memory/memories?user_id=...&limit=...`

Purpose:

- list raw memory entries

### `GET /memory/report?user_id=...&limit=...`

Purpose:

- inspect a user-level memory report

### `GET /memory/export?user_id=...&limit=...`

Purpose:

- export a user bundle

## Group 6: System, Operator, And Readiness

### `GET /system/report`

Purpose:

- top-level system report

### `GET /system/agent-readiness-summary`

Purpose:

- compact readiness summary for upper-layer orchestration

### `GET /system/release-readiness`

Purpose:

- inspect current release posture

### `GET /system/readiness-baseline`

Purpose:

- inspect active readiness sources and repair order

### `GET /system/user-experience`

Purpose:

- inspect confirmation pressure and UX friction

### `GET /system/training-protocol`

Purpose:

- inspect training signal and protocol readiness

### `GET /system/integration-flow`

Purpose:

- inspect integration readiness and evidence bridging

### `GET /system/consistency-audit`

Purpose:

- inspect consistency issues and maintenance jobs

### `GET /system/memory-hygiene`

Purpose:

- inspect stale, revised, or inactive memory maintenance surfaces

## Group 7: Storage And Delivery

### `GET /system/storage`

Purpose:

- inspect storage health, recovery, migration, and operator checklist

### `GET /system/storage-backup`

Purpose:

- generate a storage backup artifact

### `GET /system/delivery-pack`

Purpose:

- generate a delivery-pack artifact

### `GET /system/offline-review-export`

Purpose:

- export an offline review dataset

## Group 8: Retrieval Backend

### `GET /system/retrieval-backends`

Purpose:

- inspect retrieval backend report

### `POST /system/retrieval-backend`

Purpose:

- switch retrieval backend at runtime

## Group 9: Long-Horizon Validation

### `GET /system/long-horizon-validation`

Purpose:

- run a long-horizon validation pass

### `GET /system/long-horizon-summary`

Purpose:

- inspect recent multi-run drift summary

## Group 10: Legacy Demo Endpoint

### `POST /memory/process`

Purpose:

- legacy single-turn process endpoint

Note:

- it remains available
- it should not be the primary integration path for a new upper-layer agent
- new integrations should prefer:
  - `write-plan`
  - `write`
  - `recall`
  - lifecycle endpoints

## Recommended Integration Order

Smallest useful rollout:

1. `GET /`
2. `GET /openapi.json`
3. `GET /system/agent-api-manifest`
4. `POST /memory/write-plan`
5. `POST /memory/write`
6. `POST /memory/recall`

Second stage:

7. lifecycle endpoints
8. readiness endpoints
9. storage/operator endpoints
