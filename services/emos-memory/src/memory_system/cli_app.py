from __future__ import annotations

import argparse
import json
from uuid import uuid4

from .workflow import build_default_agent


def render_result(result) -> str:
    payload = {
        "observation": result.observation,
        "emotion": {"label": result.emotion.label, "score": result.emotion.score},
        "memory_committed": result.memory_committed,
        "recalled_memory": result.recalled_memory.text if result.recalled_memory else None,
        "retrieval_candidates": [candidate.to_dict() for candidate in result.retrieval_candidates],
        "reflection": result.reflection,
        "episodic_memory_count": result.episodic_memory_count,
        "semantic_keywords": result.semantic_profile.keywords,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local long-memory agent CLI")
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--session-id", default=f"session-{uuid4().hex[:8]}")
    parser.add_argument("--once", help="Legacy shortcut: process one turn and exit.")

    subparsers = parser.add_subparsers(dest="command")

    process_parser = subparsers.add_parser("process", help="Process one user turn")
    process_parser.add_argument("--text", required=True)

    write_parser = subparsers.add_parser("write-memory", help="Agent-facing long-term memory write API")
    write_parser.add_argument("--text", required=True)
    write_parser.add_argument("--task-type", default="chat")
    write_parser.add_argument("--memory-scope", default="auto")
    write_parser.add_argument("--force-write", action="store_true")
    write_parser.add_argument("--source", default="agent")
    write_parser.add_argument("--task-goal")
    write_parser.add_argument("--context-summary")
    write_parser.add_argument("--working-memory", action="append", default=[])

    plan_write_parser = subparsers.add_parser("plan-write-memory", help="Dry-run memory write planning API")
    plan_write_parser.add_argument("--text", required=True)
    plan_write_parser.add_argument("--task-type", default="chat")
    plan_write_parser.add_argument("--memory-scope", default="auto")
    plan_write_parser.add_argument("--force-write", action="store_true")
    plan_write_parser.add_argument("--source", default="agent")
    plan_write_parser.add_argument("--task-goal")
    plan_write_parser.add_argument("--context-summary")
    plan_write_parser.add_argument("--working-memory", action="append", default=[])

    recall_parser = subparsers.add_parser("recall-memory", help="Agent-facing memory recall API")
    recall_parser.add_argument("--query-text", required=True)
    recall_parser.add_argument("--top-k", type=int, default=5)
    recall_parser.add_argument("--include-profile", action="store_true")
    recall_parser.add_argument("--task-goal")
    recall_parser.add_argument("--context-summary")
    recall_parser.add_argument("--working-memory", action="append", default=[])
    recall_parser.add_argument("--response-mode", default="agent_bundle")

    reflect_parser = subparsers.add_parser("reflect-memory", help="Agent-facing memory reflection API")
    reflect_parser.add_argument("--persist", action="store_true")

    update_parser = subparsers.add_parser("update-memory", help="Agent-facing memory update API")
    update_parser.add_argument("--memory-id", required=True)
    update_parser.add_argument("--text", required=True)
    update_parser.add_argument("--source", default="agent")
    update_parser.add_argument("--task-goal")
    update_parser.add_argument("--context-summary")
    update_parser.add_argument("--working-memory", action="append", default=[])

    forget_parser = subparsers.add_parser("forget-memory", help="Agent-facing memory forget API")
    forget_parser.add_argument("--memory-id", required=True)
    forget_parser.add_argument("--reason")
    forget_parser.add_argument("--source", default="agent")

    block_parser = subparsers.add_parser("set-memory-block", help="Set or update a core memory block")
    block_parser.add_argument("--label", required=True)
    block_parser.add_argument("--value", required=True)
    block_parser.add_argument("--description", default="")
    block_parser.add_argument("--read-only", action="store_true")
    block_parser.add_argument("--source", default="agent")

    delete_block_parser = subparsers.add_parser("delete-memory-block", help="Delete a core memory block")
    delete_block_parser.add_argument("--label", required=True)

    subparsers.add_parser("memory-blocks", help="List persisted core memory blocks")

    history_parser = subparsers.add_parser("memory-history", help="Inspect audit history for a memory entry")
    history_parser.add_argument("--memory-id", required=True)

    restore_parser = subparsers.add_parser("restore-memory", help="Restore a forgotten memory")
    restore_parser.add_argument("--memory-id", required=True)
    restore_parser.add_argument("--reason")
    restore_parser.add_argument("--source", default="agent")

    supersede_parser = subparsers.add_parser("supersede-memory", help="Mark one memory as superseded by another")
    supersede_parser.add_argument("--source-memory-id", required=True)
    supersede_parser.add_argument("--replacement-memory-id", required=True)
    supersede_parser.add_argument("--reason")
    supersede_parser.add_argument("--source", default="agent")

    merge_parser = subparsers.add_parser("merge-memories", help="Merge one memory into another")
    merge_parser.add_argument("--source-memory-id", required=True)
    merge_parser.add_argument("--target-memory-id", required=True)
    merge_parser.add_argument("--reason")
    merge_parser.add_argument("--source", default="agent")

    snapshot_parser = subparsers.add_parser("snapshot", help="Inspect stored memory state")
    snapshot_parser.add_argument("--limit", type=int, default=20)

    report_parser = subparsers.add_parser("report", help="Generate a user memory report")
    report_parser.add_argument("--limit", type=int, default=10)

    export_parser = subparsers.add_parser("export", help="Export a user delivery bundle")
    export_parser.add_argument("--limit", type=int, default=20)

    feedback_parser = subparsers.add_parser("feedback-report", help="Inspect recorded user feedback")
    feedback_parser.add_argument("--user-id")
    feedback_parser.add_argument("--limit", type=int, default=20)

    review_export_parser = subparsers.add_parser("export-offline-review", help="Export offline reevaluation samples")
    review_export_parser.add_argument("--user-id")
    review_export_parser.add_argument("--limit", type=int, default=500)

    subparsers.add_parser("system-report", help="Inspect runtime and benchmark delivery status")
    subparsers.add_parser("storage-report", help="Inspect resolved storage backend and health")
    integration_parser = subparsers.add_parser("integration-flow-report", help="Inspect personal-agent integration flow readiness")
    integration_parser.add_argument("--limit", type=int, default=200)
    integration_parser.add_argument("--integration-session-id")
    training_parser = subparsers.add_parser("training-protocol-report", help="Inspect training/export protocol readiness")
    training_parser.add_argument("--limit", type=int, default=200)
    ux_parser = subparsers.add_parser("user-experience-report", help="Inspect user comfort and interaction risk signals")
    ux_parser.add_argument("--limit", type=int, default=200)
    ux_parser.add_argument("--experience-session-id")
    consistency_parser = subparsers.add_parser("consistency-audit-report", help="Inspect revised, old-fact, and disputed memory consistency risks")
    consistency_parser.add_argument("--limit", type=int, default=50)
    hygiene_parser = subparsers.add_parser("memory-hygiene-report", help="Inspect stale, revised, and inactive memory load")
    hygiene_parser.add_argument("--limit", type=int, default=50)
    release_parser = subparsers.add_parser("release-readiness-report", help="Inspect whether the system is ready for internal use or market pilot")
    release_parser.add_argument("--limit", type=int, default=200)
    release_parser.add_argument("--release-session-id")
    readiness_baseline_parser = subparsers.add_parser("readiness-baseline-report", help="Inspect the Phase A readiness source map and repair sequence")
    readiness_baseline_parser.add_argument("--limit", type=int, default=200)
    readiness_baseline_parser.add_argument("--baseline-session-id")
    agent_ready_parser = subparsers.add_parser("agent-readiness-report", help="Inspect the compact system-facing readiness summary for upper-layer agents")
    agent_ready_parser.add_argument("--limit", type=int, default=200)
    agent_ready_parser.add_argument("--agent-session-id")
    long_horizon_parser = subparsers.add_parser("long-horizon-validation", help="Run a long-horizon workload validation and emit accumulated-memory stability evidence")
    long_horizon_parser.add_argument("--limit", type=int, default=200)
    long_horizon_summary_parser = subparsers.add_parser("long-horizon-summary-report", help="Inspect multi-run long-horizon stability drift across recent validation runs")
    long_horizon_summary_parser.add_argument("--limit", type=int, default=5)
    integration_demo_parser = subparsers.add_parser("run-integration-flows", help="Run a delivery-grade integration flow demo and emit readiness evidence")
    integration_demo_parser.add_argument("--limit", type=int, default=200)
    subparsers.add_parser("storage-backup", help="Create a storage backup artifact")
    subparsers.add_parser("storage-restore-drill", help="Run a restore drill against the latest storage backup artifact")
    subparsers.add_parser("storage-migration-preflight", help="Inspect migration readiness and rollback posture before any storage upgrade")
    subparsers.add_parser("delivery-pack", help="Generate a delivery pack from current artifacts")
    subparsers.add_parser("retrieval-backends", help="Inspect active and available retrieval backends")

    set_backend_parser = subparsers.add_parser("set-retrieval-backend", help="Switch retrieval backend and persist settings")
    set_backend_parser.add_argument("--backend-name", required=True)
    set_backend_parser.add_argument("--embedding-dimensions", type=int)
    set_backend_parser.add_argument("--embedding-candidate-pool", type=int)

    chat_parser = subparsers.add_parser("chat", help="Start interactive chat mode")
    chat_parser.set_defaults(command="chat")
    return parser


def process_once(user_id: str, session_id: str, text: str) -> int:
    agent = build_default_agent()
    result = agent.process_turn(user_id=user_id, session_id=session_id, text=text)
    print(render_result(result))
    return 0


def write_memory(
    user_id: str,
    session_id: str,
    text: str,
    task_type: str,
    memory_scope: str,
    force_write: bool,
    source: str,
    task_goal: str | None,
    context_summary: str | None,
    working_memory: list[str],
) -> int:
    agent = build_default_agent()
    payload = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text=text,
        task_type=task_type,
        memory_scope=memory_scope,
        force_write=force_write,
        source=source,
        task_goal=task_goal,
        context_summary=context_summary,
        working_memory=working_memory,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def plan_write_memory(
    user_id: str,
    session_id: str,
    text: str,
    task_type: str,
    memory_scope: str,
    force_write: bool,
    source: str,
    task_goal: str | None,
    context_summary: str | None,
    working_memory: list[str],
) -> int:
    agent = build_default_agent()
    payload = agent.plan_memory_write(
        user_id=user_id,
        session_id=session_id,
        text=text,
        task_type=task_type,
        memory_scope=memory_scope,
        force_write=force_write,
        source=source,
        task_goal=task_goal,
        context_summary=context_summary,
        working_memory=working_memory,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def recall_memory(
    user_id: str,
    session_id: str,
    query_text: str,
    top_k: int,
    include_profile: bool,
    task_goal: str | None,
    context_summary: str | None,
    working_memory: list[str],
    response_mode: str,
) -> int:
    agent = build_default_agent()
    payload = agent.recall_memory(
        user_id=user_id,
        session_id=session_id,
        query_text=query_text,
        top_k=top_k,
        include_profile=include_profile,
        task_goal=task_goal,
        context_summary=context_summary,
        working_memory=working_memory,
        response_mode=response_mode,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def reflect_memory(user_id: str, session_id: str, persist: bool) -> int:
    agent = build_default_agent()
    payload = agent.reflect_memory(
        user_id=user_id,
        session_id=session_id,
        persist=persist,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def update_memory(
    user_id: str,
    session_id: str,
    memory_id: str,
    text: str,
    source: str,
    task_goal: str | None,
    context_summary: str | None,
    working_memory: list[str],
) -> int:
    agent = build_default_agent()
    payload = agent.update_memory(
        user_id=user_id,
        session_id=session_id,
        memory_id=memory_id,
        text=text,
        source=source,
        task_goal=task_goal,
        context_summary=context_summary,
        working_memory=working_memory,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def forget_memory(user_id: str, session_id: str, memory_id: str, reason: str | None, source: str) -> int:
    agent = build_default_agent()
    payload = agent.forget_memory(
        user_id=user_id,
        session_id=session_id,
        memory_id=memory_id,
        reason=reason,
        source=source,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def set_memory_block(
    user_id: str,
    session_id: str,
    label: str,
    value: str,
    description: str,
    read_only: bool,
    source: str,
) -> int:
    agent = build_default_agent()
    payload = agent.set_memory_block(
        user_id=user_id,
        session_id=session_id,
        label=label,
        value=value,
        description=description,
        read_only=read_only,
        source=source,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def delete_memory_block(user_id: str, session_id: str, label: str) -> int:
    agent = build_default_agent()
    payload = agent.delete_memory_block(
        user_id=user_id,
        session_id=session_id,
        label=label,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def show_memory_blocks(user_id: str) -> int:
    agent = build_default_agent()
    payload = {
        "user_id": user_id,
        "blocks": [block.to_dict() for block in agent.repository.list_memory_blocks(user_id)],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def show_memory_history(user_id: str, session_id: str, memory_id: str) -> int:
    agent = build_default_agent()
    payload = agent.get_memory_history(
        user_id=user_id,
        session_id=session_id,
        memory_id=memory_id,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def restore_memory(user_id: str, session_id: str, memory_id: str, reason: str | None, source: str) -> int:
    agent = build_default_agent()
    payload = agent.restore_memory(
        user_id=user_id,
        session_id=session_id,
        memory_id=memory_id,
        reason=reason,
        source=source,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def supersede_memory(
    user_id: str,
    session_id: str,
    source_memory_id: str,
    replacement_memory_id: str,
    reason: str | None,
    source: str,
) -> int:
    agent = build_default_agent()
    payload = agent.supersede_memory(
        user_id=user_id,
        session_id=session_id,
        source_memory_id=source_memory_id,
        replacement_memory_id=replacement_memory_id,
        reason=reason,
        source=source,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def merge_memories(
    user_id: str,
    session_id: str,
    source_memory_id: str,
    target_memory_id: str,
    reason: str | None,
    source: str,
) -> int:
    agent = build_default_agent()
    payload = agent.merge_memories(
        user_id=user_id,
        session_id=session_id,
        source_memory_id=source_memory_id,
        target_memory_id=target_memory_id,
        reason=reason,
        source=source,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def show_snapshot(user_id: str, limit: int) -> int:
    agent = build_default_agent()
    snapshot = agent.get_user_snapshot(user_id=user_id, limit=limit)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0


def show_report(user_id: str, limit: int) -> int:
    agent = build_default_agent()
    report = agent.generate_user_report(user_id=user_id, limit=limit)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def export_bundle(user_id: str, limit: int) -> int:
    agent = build_default_agent()
    bundle = agent.export_user_bundle(user_id=user_id, limit=limit)
    print(json.dumps(bundle, ensure_ascii=False, indent=2))
    return 0


def show_feedback_report(user_id: str, limit: int) -> int:
    agent = build_default_agent()
    report = agent.repository.get_feedback_report(user_id=user_id, limit=limit)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def export_offline_review(limit: int, user_id: str) -> int:
    agent = build_default_agent()
    payload = agent.repository.export_offline_review_dataset(limit=limit, user_id=user_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def show_system_report() -> int:
    agent = build_default_agent()
    report = agent.build_system_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def show_storage_report() -> int:
    agent = build_default_agent()
    report = agent.get_storage_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def show_integration_flow_report(user_id: str | None, session_id: str | None, limit: int) -> int:
    agent = build_default_agent()
    report = agent.build_integration_flow_report(user_id=user_id, session_id=session_id, limit=limit)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def show_training_protocol_report(user_id: str | None, limit: int) -> int:
    agent = build_default_agent()
    report = agent.build_training_protocol_report(user_id=user_id, limit=limit)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def show_user_experience_report(user_id: str | None, session_id: str | None, limit: int) -> int:
    agent = build_default_agent()
    report = agent.build_user_experience_report(user_id=user_id, session_id=session_id, limit=limit)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def show_consistency_audit_report(user_id: str | None, limit: int) -> int:
    agent = build_default_agent()
    report = agent.build_consistency_audit_report(user_id=user_id, limit=limit)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def show_release_readiness_report(user_id: str | None, session_id: str | None, limit: int) -> int:
    agent = build_default_agent()
    report = agent.build_release_readiness_report(user_id=user_id, session_id=session_id, limit=limit)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def show_readiness_baseline_report(user_id: str | None, session_id: str | None, limit: int) -> int:
    agent = build_default_agent()
    report = agent.build_readiness_baseline_report(user_id=user_id, session_id=session_id, limit=limit)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def show_memory_hygiene_report(user_id: str | None, limit: int) -> int:
    agent = build_default_agent()
    report = agent.build_memory_hygiene_report(user_id=user_id, limit=limit)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def show_agent_readiness_report(user_id: str | None, session_id: str | None, limit: int) -> int:
    agent = build_default_agent()
    report = agent.build_agent_readiness_summary(user_id=user_id, session_id=session_id, limit=limit)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def run_integration_flows(user_id: str, session_id: str, limit: int) -> int:
    agent = build_default_agent()
    payload = agent.run_integration_flow_demo(user_id=user_id, session_id=session_id, limit=limit)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def run_long_horizon_validation(user_id: str, session_id: str, limit: int) -> int:
    agent = build_default_agent()
    payload = agent.run_long_horizon_validation(user_id=user_id, session_id=session_id, limit=limit)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def show_long_horizon_summary(limit: int) -> int:
    agent = build_default_agent()
    payload = agent.build_long_horizon_multi_run_summary(limit=limit)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def create_storage_backup() -> int:
    agent = build_default_agent()
    backup = agent.create_storage_backup()
    print(json.dumps(backup, ensure_ascii=False, indent=2))
    return 0


def run_storage_restore_drill() -> int:
    agent = build_default_agent()
    drill = agent.run_storage_restore_drill()
    print(json.dumps(drill, ensure_ascii=False, indent=2))
    return 0


def run_storage_migration_preflight() -> int:
    agent = build_default_agent()
    payload = agent.run_storage_migration_preflight()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def create_delivery_pack() -> int:
    agent = build_default_agent()
    pack = agent.generate_delivery_pack()
    print(json.dumps(pack, ensure_ascii=False, indent=2))
    return 0


def show_retrieval_backends() -> int:
    agent = build_default_agent()
    payload = agent.build_retrieval_backend_report()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def set_retrieval_backend(backend_name: str, embedding_dimensions: int | None, embedding_candidate_pool: int | None) -> int:
    agent = build_default_agent()
    payload = agent.repository.configure_retrieval_backend(
        backend_name=backend_name,
        embedding_dimensions=embedding_dimensions,
        embedding_candidate_pool=embedding_candidate_pool,
        change_source="cli",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def interactive_chat(user_id: str, session_id: str) -> int:
    agent = build_default_agent()
    print("\u8bb0\u5fc6\u7cfb\u7edf CLI \u5df2\u542f\u52a8\uff0c\u8f93\u5165 exit \u9000\u51fa\u3002")
    while True:
        try:
            text = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\u5df2\u9000\u51fa\u3002")
            return 0

        if not text:
            continue
        if text.lower() in {"exit", "quit", "\u9000\u51fa"}:
            print("\u5df2\u9000\u51fa\u3002")
            return 0

        result = agent.process_turn(user_id=user_id, session_id=session_id, text=text)
        print(render_result(result))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.once:
        return process_once(user_id=args.user_id, session_id=args.session_id, text=args.once)

    if args.command == "process":
        return process_once(user_id=args.user_id, session_id=args.session_id, text=args.text)

    if args.command == "write-memory":
        return write_memory(
            user_id=args.user_id,
            session_id=args.session_id,
            text=args.text,
            task_type=args.task_type,
            memory_scope=args.memory_scope,
            force_write=args.force_write,
            source=args.source,
            task_goal=args.task_goal,
            context_summary=args.context_summary,
            working_memory=args.working_memory,
        )

    if args.command == "plan-write-memory":
        return plan_write_memory(
            user_id=args.user_id,
            session_id=args.session_id,
            text=args.text,
            task_type=args.task_type,
            memory_scope=args.memory_scope,
            force_write=args.force_write,
            source=args.source,
            task_goal=args.task_goal,
            context_summary=args.context_summary,
            working_memory=args.working_memory,
        )

    if args.command == "recall-memory":
        return recall_memory(
            user_id=args.user_id,
            session_id=args.session_id,
            query_text=args.query_text,
            top_k=args.top_k,
            include_profile=args.include_profile,
            task_goal=args.task_goal,
            context_summary=args.context_summary,
            working_memory=args.working_memory,
            response_mode=args.response_mode,
        )

    if args.command == "reflect-memory":
        return reflect_memory(
            user_id=args.user_id,
            session_id=args.session_id,
            persist=args.persist,
        )

    if args.command == "update-memory":
        return update_memory(
            user_id=args.user_id,
            session_id=args.session_id,
            memory_id=args.memory_id,
            text=args.text,
            source=args.source,
            task_goal=args.task_goal,
            context_summary=args.context_summary,
            working_memory=args.working_memory,
        )

    if args.command == "forget-memory":
        return forget_memory(
            user_id=args.user_id,
            session_id=args.session_id,
            memory_id=args.memory_id,
            reason=args.reason,
            source=args.source,
        )

    if args.command == "set-memory-block":
        return set_memory_block(
            user_id=args.user_id,
            session_id=args.session_id,
            label=args.label,
            value=args.value,
            description=args.description,
            read_only=args.read_only,
            source=args.source,
        )

    if args.command == "delete-memory-block":
        return delete_memory_block(
            user_id=args.user_id,
            session_id=args.session_id,
            label=args.label,
        )

    if args.command == "memory-blocks":
        return show_memory_blocks(user_id=args.user_id)

    if args.command == "memory-history":
        return show_memory_history(
            user_id=args.user_id,
            session_id=args.session_id,
            memory_id=args.memory_id,
        )

    if args.command == "restore-memory":
        return restore_memory(
            user_id=args.user_id,
            session_id=args.session_id,
            memory_id=args.memory_id,
            reason=args.reason,
            source=args.source,
        )

    if args.command == "supersede-memory":
        return supersede_memory(
            user_id=args.user_id,
            session_id=args.session_id,
            source_memory_id=args.source_memory_id,
            replacement_memory_id=args.replacement_memory_id,
            reason=args.reason,
            source=args.source,
        )

    if args.command == "merge-memories":
        return merge_memories(
            user_id=args.user_id,
            session_id=args.session_id,
            source_memory_id=args.source_memory_id,
            target_memory_id=args.target_memory_id,
            reason=args.reason,
            source=args.source,
        )

    if args.command == "snapshot":
        return show_snapshot(user_id=args.user_id, limit=args.limit)

    if args.command == "report":
        return show_report(user_id=args.user_id, limit=args.limit)

    if args.command == "export":
        return export_bundle(user_id=args.user_id, limit=args.limit)

    if args.command == "feedback-report":
        return show_feedback_report(user_id=args.user_id, limit=args.limit)

    if args.command == "export-offline-review":
        return export_offline_review(limit=args.limit, user_id=args.user_id)

    if args.command == "system-report":
        return show_system_report()

    if args.command == "storage-report":
        return show_storage_report()

    if args.command == "integration-flow-report":
        return show_integration_flow_report(
            user_id=args.user_id,
            session_id=args.integration_session_id,
            limit=args.limit,
        )

    if args.command == "training-protocol-report":
        return show_training_protocol_report(
            user_id=args.user_id,
            limit=args.limit,
        )

    if args.command == "user-experience-report":
        return show_user_experience_report(
            user_id=args.user_id,
            session_id=args.experience_session_id,
            limit=args.limit,
        )

    if args.command == "consistency-audit-report":
        return show_consistency_audit_report(
            user_id=args.user_id,
            limit=args.limit,
        )

    if args.command == "release-readiness-report":
        return show_release_readiness_report(
            user_id=args.user_id,
            session_id=args.release_session_id,
            limit=args.limit,
        )

    if args.command == "readiness-baseline-report":
        return show_readiness_baseline_report(
            user_id=args.user_id,
            session_id=args.baseline_session_id,
            limit=args.limit,
        )

    if args.command == "memory-hygiene-report":
        return show_memory_hygiene_report(
            user_id=args.user_id,
            limit=args.limit,
        )

    if args.command == "agent-readiness-report":
        return show_agent_readiness_report(
            user_id=args.user_id,
            session_id=args.agent_session_id,
            limit=args.limit,
        )

    if args.command == "run-integration-flows":
        return run_integration_flows(
            user_id=args.user_id,
            session_id=args.session_id,
            limit=args.limit,
        )

    if args.command == "long-horizon-validation":
        return run_long_horizon_validation(
            user_id=args.user_id,
            session_id=args.session_id,
            limit=args.limit,
        )

    if args.command == "long-horizon-summary-report":
        return show_long_horizon_summary(limit=args.limit)

    if args.command == "storage-backup":
        return create_storage_backup()

    if args.command == "storage-restore-drill":
        return run_storage_restore_drill()

    if args.command == "storage-migration-preflight":
        return run_storage_migration_preflight()

    if args.command == "delivery-pack":
        return create_delivery_pack()

    if args.command == "retrieval-backends":
        return show_retrieval_backends()

    if args.command == "set-retrieval-backend":
        return set_retrieval_backend(
            backend_name=args.backend_name,
            embedding_dimensions=args.embedding_dimensions,
            embedding_candidate_pool=args.embedding_candidate_pool,
        )

    return interactive_chat(user_id=args.user_id, session_id=args.session_id)


if __name__ == "__main__":
    raise SystemExit(main())
