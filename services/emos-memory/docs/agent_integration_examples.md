# Agent Integration Examples

This document is the Week 8 example pack for upper-layer agent integration.

## Preferred Consumption Rule

- Prefer `payload.execution_surface` or report-level `execution_surface` first.
- Use `action_surface` to normalize `recommended_action`, `next_action`, and handoff `mode`.
- Use `policy_input` as the thin decision object for routing.
- Use `agent_handoff` for short operator/agent-facing rationale.
- When `execution_surface` is not present, prefer the top-level `action_surface` before reading raw report fields.
- After the final Week 8 sweep, that full thin surface is also available on retrieval backend review, storage backup / restore-drill / migration-preflight artifacts, long-horizon evidence summaries, and the top-level system report.

## Example 1: Chat Write Planning

Goal: decide whether a new user message should become long-term memory.

Preferred read order:

1. `payload.execution_surface.policy_input`
2. `payload.execution_surface.action_surface`
3. `payload.execution_surface.agent_handoff`
4. `payload.memory_resolution`
5. `payload.block_plan`

Expected cues:

- `policy_input.service_operation = plan_memory_write`
- `policy_input.resolution_flow` is one of:
  - `write_plan_flow`
  - `update_existing_memory_flow`
  - `skip_write_flow`
  - `confirm_then_write_flow`
  - `blocked_write_flow`
- `action_surface.recommended_action` tells the canonical next move.
- `action_surface.next_action` stays aligned with handoff `mode`.

## Example 2: Durable Write Execution

Goal: commit a stable memory when the upper-layer agent is ready to write.

Preferred read order:

1. `payload.execution_surface.policy_input`
2. `payload.execution_surface.action_surface`
3. `payload.execution_surface.execution_policy`
4. `payload.agent_handoff`

Expected cues:

- `policy_input.service_operation = write_memory`
- `policy_input.memory_resolution_action` distinguishes `new_memory`, `deduplicate`, and `suggest_update`
- `action_surface.action_status` distinguishes `completed`, `skipped`, and `ready`
- `execution_policy.resolution.flow` explains whether EMOS wrote a new memory, updated an existing one, or skipped the write

## Example 3: Grounded Recall

Goal: answer from long-term memory without reconstructing memory policy.

Preferred read order:

1. `payload.execution_surface.policy_input`
2. `payload.execution_surface.response_contract`
3. `payload.execution_surface.response_guardrails`
4. `payload.execution_surface.agent_handoff`
5. `payload.memory_context`

Expected cues:

- `policy_input.can_answer_now`
- `policy_input.should_confirm`
- `policy_input.resolution_flow`
- `response_contract.citation_required`
- `agent_handoff.primary_operation`

## Example 4: Lifecycle Resolution

Goal: inspect or resolve revised, forgotten, restored, superseded, or merged memory state.

Preferred read order:

1. `payload.execution_surface.policy_input`
2. `payload.execution_surface.action_surface`
3. `payload.consistency_maintenance`
4. `payload.agent_handoff`

Expected cues:

- `policy_input.service_operation` identifies the lifecycle endpoint directly
- `policy_input.next_action` matches `action_surface.next_action`
- `policy_input.primary_operation` points to the first lifecycle follow-up
- `consistency_maintenance.next_bucket` tells whether the path is `auto_safe`, `confirm_required`, or `manual_review`

## Example 5: Storage / Operator Review

Goal: let an upper-layer agent or operator review delivery posture without parsing raw storage metadata.

Preferred read order:

1. `storage_report.execution_surface`
2. `storage_report.operator_decision_path`
3. `storage_report.operator_acceptance_note`
4. `storage_report.remediation_checklist`

Expected cues:

- `execution_surface.policy_input.primary_mode_status`
- `operator_decision_path.delivery_decision`
- `operator_decision_path.restore_drill_acceptance`
- `operator_decision_path.migration_acceptance`

## Example 6: Reflection And Core Block Flows

Goal: consume reflection and core-block actions through the same action semantics as write/lifecycle flows.

Preferred read order:

1. top-level `action_surface`
2. `agent_handoff`
3. operation-specific payload fields

Expected cues:

- for `set_memory_block` and `delete_memory_block`:
  - `action_surface.next_action`
  - `action_surface.target_block_labels`
- for `reflect_memory`:
  - `action_surface.recommended_action`
  - `agent_handoff.reflection_available`
  - `agent_handoff.recommended_operation`

## Example 7: Report-Facing Review

Goal: let an upper-layer agent read delivery and readiness reports through the same thin action grammar.

Preferred read order:

1. top-level `action_surface`
2. `agent_handoff`
3. report-specific observability or lifecycle surfaces

Expected cues:

- `action_surface.recommended_action` gives the canonical review move
- `action_surface.handoff_mode` matches the report-facing action label
- `agent_handoff.primary_operation` remains the bridge to deeper operator/agent work

## Integration Shortcut

If the upper-layer agent wants one uniform pattern across write and lifecycle flows:

1. read `execution_surface.policy_input`
2. read `execution_surface.action_surface`
3. follow `execution_surface.agent_handoff.primary_operation` when present
4. fall back to `decision_protocol.recommended_action` only if the thin surface is unavailable
