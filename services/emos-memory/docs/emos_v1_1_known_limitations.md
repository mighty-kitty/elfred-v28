# EMOS v1.1 Known Limitations

## Current Posture

`EMOS v1.1` is being hardened as a local/private-deployment-first memory engine. It is stronger than a demo package, but it should still be described as a `limited_pilot` release posture rather than a fully market-ready platform release.

## Active Limitations

- SQLite may still fall back to JSON in some environments.
- Consistency review is guarded and structured, but not fully auto-cleared.
- Migration readiness is explicit, but upgrade execution still depends on operator review and rollback freshness.
- Long-horizon validation is stronger than benchmark-only review, but it is still a bounded evidence family rather than an unbounded production-duration study.
- This package does not target public-cloud multi-tenant SaaS operation in the current sprint.

## Operational Follow-Ups

- promote SQLite back to the preferred primary runtime path where the environment allows it
- keep restore-drill evidence fresh for each delivery round
- refresh rollback evidence before any storage upgrade execution
- continue reducing manual consistency-review pressure
- expand pilot persona coverage when new upper-layer agent usage patterns appear

## Not A Defect List

The following items are intentional scope boundaries for this release and should not be misread as accidental omissions:

- public-cloud SaaS tenancy
- broad multi-tenant security/governance surface
- fully autonomous consistency cleanup without guarded review
- benchmark-only evaluation as the primary release gate
