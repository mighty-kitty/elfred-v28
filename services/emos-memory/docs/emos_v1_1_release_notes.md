# EMOS v1.1 Release Notes

## Release Theme

`EMOS v1.1` focuses on hardening, delivery posture, and upper-layer integration clarity rather than broad new feature expansion.

## What Improved

- storage/recovery surfaces were hardened into operator-facing delivery artifacts
- restore-drill and migration/rollback evidence became explicit acceptance gates
- consistency governance now exposes clearer operator/agent action buckets
- lifecycle, write, recall, block, reflection, and report-facing surfaces converged on a thinner execution contract
- long-horizon validation now complements benchmark evidence with multi-profile and multi-run stability review
- delivery-pack, handoff, and acceptance wording now mirror runtime surface contracts more closely

## Receiver-Facing Highlights

- prefer `execution_surface.policy_input`
- then `execution_surface.action_surface`
- then `execution_surface.agent_handoff`
- fall back to top-level `action_surface` only when a full execution surface is not present

## Release Posture

- deployment mode: local/private-deployment first
- readiness posture: limited pilot
- benchmark / official LoCoMo / arXiv assets: retained

## Recommended Next Focus

- packaging and acceptance evidence finalization
- continued operator friction reduction
- continued consistency automation hardening
- continued storage primary-path hardening
