from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field

from ..workflow import build_default_agent


class MemoryRequest(BaseModel):
    user_id: str
    session_id: str
    text: str


class MemoryWriteRequest(BaseModel):
    user_id: str
    session_id: str
    text: str
    task_type: str = "chat"
    memory_scope: str = "auto"
    force_write: bool = False
    source: str = "agent"
    task_goal: Optional[str] = None
    context_summary: Optional[str] = None
    working_memory: list[str] = Field(default_factory=list)
    agent_hints: dict[str, object] = Field(default_factory=dict)
    operation_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class MemoryWritePlanRequest(BaseModel):
    user_id: str
    session_id: str
    text: str
    task_type: str = "chat"
    memory_scope: str = "auto"
    force_write: bool = False
    source: str = "agent"
    task_goal: Optional[str] = None
    context_summary: Optional[str] = None
    working_memory: list[str] = Field(default_factory=list)
    agent_hints: dict[str, object] = Field(default_factory=dict)
    operation_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class MemoryRecallRequest(BaseModel):
    user_id: str
    query_text: str
    session_id: Optional[str] = None
    top_k: int = 5
    include_profile: bool = True
    task_goal: Optional[str] = None
    context_summary: Optional[str] = None
    working_memory: list[str] = Field(default_factory=list)
    response_mode: str = "agent_bundle"


class MemoryReflectRequest(BaseModel):
    user_id: str
    session_id: Optional[str] = None
    persist: bool = False


class MemoryUpdateRequest(BaseModel):
    user_id: str
    session_id: str
    memory_id: str
    text: str
    source: str = "agent"
    task_goal: Optional[str] = None
    context_summary: Optional[str] = None
    working_memory: list[str] = Field(default_factory=list)


class MemoryForgetRequest(BaseModel):
    user_id: str
    session_id: str
    memory_id: str
    reason: Optional[str] = None
    source: str = "agent"


class MemoryBlockRequest(BaseModel):
    user_id: str
    session_id: str
    label: str
    value: str
    description: str = ""
    read_only: bool = False
    source: str = "agent"


class MemoryBlockDeleteRequest(BaseModel):
    user_id: str
    session_id: str
    label: str


class MemoryHistoryRequest(BaseModel):
    user_id: str
    session_id: Optional[str] = None
    memory_id: str


class MemoryRestoreRequest(BaseModel):
    user_id: str
    session_id: str
    memory_id: str
    reason: Optional[str] = None
    source: str = "agent"


class MemorySupersedeRequest(BaseModel):
    user_id: str
    session_id: str
    source_memory_id: str
    replacement_memory_id: str
    reason: Optional[str] = None
    source: str = "agent"


class MemoryMergeRequest(BaseModel):
    user_id: str
    session_id: str
    source_memory_id: str
    target_memory_id: str
    reason: Optional[str] = None
    source: str = "agent"


class FeedbackRequest(BaseModel):
    user_id: str
    session_id: str
    memory_id: str
    feedback_type: str
    query_text: Optional[str] = None
    notes: Optional[str] = None
    signal_weight: Optional[float] = 1.0


class RetrievalBackendRequest(BaseModel):
    backend_name: str
    embedding_dimensions: Optional[int] = None
    embedding_candidate_pool: Optional[int] = None
    change_source: Optional[str] = "api"


def _agent_hints_with_operation_ids(
    agent_hints: dict[str, object],
    *,
    operation_id: str | None,
    idempotency_key: str | None,
) -> dict[str, object]:
    hints = dict(agent_hints or {})
    if operation_id and "operation_id" not in hints:
        hints["operation_id"] = operation_id
    if idempotency_key and "idempotency_key" not in hints:
        hints["idempotency_key"] = idempotency_key
    return hints


def _build_agent_api_manifest() -> dict[str, Any]:
    return {
        "contract_version": "agent-api-manifest.v1",
        "service_name": "EMOS Agent API",
        "service_role": "independent memory engine / memory service for upper-layer personal agents",
        "preferred_transport": "http_json",
        "openapi_path": "/openapi.json",
        "health_path": "/health",
        "agent_entrypoints": [
            {
                "method": "POST",
                "path": "/memory/write-plan",
                "operation": "plan_memory_write",
                "purpose": "dry-run durable memory planning before mutation",
                "preferred_response_path": "payload.execution_surface",
            },
            {
                "method": "POST",
                "path": "/memory/write",
                "operation": "write_memory",
                "purpose": "durable memory write / update decision execution",
                "preferred_response_path": "payload.execution_surface",
            },
            {
                "method": "POST",
                "path": "/memory/recall",
                "operation": "recall_memory",
                "purpose": "grounded memory recall for agent response generation",
                "preferred_response_path": "payload.execution_surface",
            },
            {
                "method": "POST",
                "path": "/memory/reflect",
                "operation": "reflect_memory",
                "purpose": "build reflection summary for higher-level planning",
                "preferred_response_path": "payload.execution_surface",
            },
            {
                "method": "POST",
                "path": "/memory/update",
                "operation": "update_memory",
                "purpose": "update an existing memory entry",
                "preferred_response_path": "payload.execution_surface",
            },
            {
                "method": "POST",
                "path": "/memory/forget",
                "operation": "forget_memory",
                "purpose": "soft-forget a memory entry with an operator-auditable deletion receipt",
                "preferred_response_path": "payload.execution_surface",
            },
        ],
        "supporting_entrypoints": [
            {"method": "POST", "path": "/memory/block", "operation": "set_memory_block"},
            {"method": "POST", "path": "/memory/block/delete", "operation": "delete_memory_block"},
            {"method": "POST", "path": "/memory/history", "operation": "get_memory_history"},
            {"method": "POST", "path": "/memory/restore", "operation": "restore_memory"},
            {"method": "POST", "path": "/memory/supersede", "operation": "supersede_memory"},
            {"method": "POST", "path": "/memory/merge", "operation": "merge_memories"},
            {"method": "GET", "path": "/system/agent-readiness-summary", "operation": "agent_readiness_summary"},
            {"method": "GET", "path": "/system/report", "operation": "system_report"},
        ],
        "preferred_read_order": [
            "execution_surface.policy_input",
            "execution_surface.execution_policy",
            "execution_surface.action_surface",
            "execution_surface.agent_handoff",
        ],
        "recommended_call_flows": [
            {
                "name": "chat_write_flow",
                "steps": ["/memory/write-plan", "/memory/write"],
            },
            {
                "name": "grounded_recall_flow",
                "steps": ["/memory/recall"],
            },
            {
                "name": "lifecycle_resolution_flow",
                "steps": ["/memory/history", "/memory/update", "/memory/forget", "/memory/restore"],
            },
        ],
        "notes": [
            "Prefer the thin execution surface over ad-hoc field parsing.",
            "Use /openapi.json for machine-readable request models.",
            "Use /system/agent-readiness-summary before large-scale orchestration.",
        ],
    }


def _build_openapi_spec() -> dict[str, Any]:
    request_models: list[type[BaseModel]] = [
        MemoryRequest,
        MemoryWriteRequest,
        MemoryWritePlanRequest,
        MemoryRecallRequest,
        MemoryReflectRequest,
        MemoryUpdateRequest,
        MemoryForgetRequest,
        MemoryBlockRequest,
        MemoryBlockDeleteRequest,
        MemoryHistoryRequest,
        MemoryRestoreRequest,
        MemorySupersedeRequest,
        MemoryMergeRequest,
        FeedbackRequest,
        RetrievalBackendRequest,
    ]
    component_schemas = {
        model.__name__: model.model_json_schema(ref_template="#/components/schemas/{model}")
        for model in request_models
    }

    def request_body_for(model_name: str) -> dict[str, Any]:
        return {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{model_name}"}
                }
            },
        }

    json_response = {
        "200": {
            "description": "Successful JSON response",
            "content": {"application/json": {"schema": {"type": "object"}}},
        }
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "EMOS Agent API",
            "version": "v1",
            "description": "Machine-readable contract for upper-layer agents calling EMOS memory-service endpoints.",
        },
        "servers": [{"url": "http://127.0.0.1:8000"}],
        "paths": {
            "/health": {"get": {"summary": "Health probe", "responses": json_response}},
            "/system/agent-api-manifest": {
                "get": {
                    "summary": "Agent-facing API manifest",
                    "responses": json_response,
                }
            },
            "/memory/write-plan": {
                "post": {
                    "summary": "Dry-run durable memory planning",
                    "requestBody": request_body_for("MemoryWritePlanRequest"),
                    "responses": json_response,
                }
            },
            "/memory/write": {
                "post": {
                    "summary": "Execute durable memory write",
                    "requestBody": request_body_for("MemoryWriteRequest"),
                    "responses": json_response,
                }
            },
            "/memory/recall": {
                "post": {
                    "summary": "Recall grounded memory context",
                    "requestBody": request_body_for("MemoryRecallRequest"),
                    "responses": json_response,
                }
            },
            "/memory/reflect": {
                "post": {
                    "summary": "Build reflection summary",
                    "requestBody": request_body_for("MemoryReflectRequest"),
                    "responses": json_response,
                }
            },
            "/memory/update": {
                "post": {
                    "summary": "Update a memory entry",
                    "requestBody": request_body_for("MemoryUpdateRequest"),
                    "responses": json_response,
                }
            },
            "/memory/forget": {
                "post": {
                    "summary": "Soft-forget a memory entry with deletion receipt",
                    "requestBody": request_body_for("MemoryForgetRequest"),
                    "responses": json_response,
                }
            },
            "/memory/history": {
                "post": {
                    "summary": "Inspect memory history",
                    "requestBody": request_body_for("MemoryHistoryRequest"),
                    "responses": json_response,
                }
            },
            "/memory/block": {
                "post": {
                    "summary": "Set or update a core memory block",
                    "requestBody": request_body_for("MemoryBlockRequest"),
                    "responses": json_response,
                }
            },
            "/memory/block/delete": {
                "post": {
                    "summary": "Delete a core memory block",
                    "requestBody": request_body_for("MemoryBlockDeleteRequest"),
                    "responses": json_response,
                }
            },
            "/memory/restore": {
                "post": {
                    "summary": "Restore a forgotten memory",
                    "requestBody": request_body_for("MemoryRestoreRequest"),
                    "responses": json_response,
                }
            },
            "/memory/supersede": {
                "post": {
                    "summary": "Mark one memory as superseded by another",
                    "requestBody": request_body_for("MemorySupersedeRequest"),
                    "responses": json_response,
                }
            },
            "/memory/merge": {
                "post": {
                    "summary": "Merge one memory into another",
                    "requestBody": request_body_for("MemoryMergeRequest"),
                    "responses": json_response,
                }
            },
            "/system/agent-readiness-summary": {
                "get": {"summary": "Compact system-facing readiness summary", "responses": json_response}
            },
            "/system/report": {
                "get": {"summary": "Full system report", "responses": json_response}
            },
        },
        "components": {"schemas": component_schemas},
    }


def write_json_response(handler: BaseHTTPRequestHandler, payload: dict[str, object], status: int = HTTPStatus.OK) -> None:
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def create_handler():
    agent = build_default_agent()

    class MemoryHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)

            if self.path == "/memory/process":
                try:
                    request = MemoryRequest.model_validate_json(body)
                except Exception as exc:  # pragma: no cover
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return

                result = agent.process_turn(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    text=request.text,
                )
                payload = {
                    "observation": result.observation,
                    "emotion": result.emotion.label,
                    "emotion_score": result.emotion.score,
                    "memory_committed": result.memory_committed,
                    "recalled_memory": result.recalled_memory.to_dict() if result.recalled_memory else None,
                    "retrieval_candidates": [candidate.to_dict() for candidate in result.retrieval_candidates],
                    "reflection": result.reflection,
                    "episodic_memory_count": result.episodic_memory_count,
                    "semantic_profile": result.semantic_profile.to_dict(),
                }
                write_json_response(self, payload)
                return

            if self.path == "/memory/write":
                try:
                    request = MemoryWriteRequest.model_validate_json(body)
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return

                payload = agent.write_memory(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    text=request.text,
                    task_type=request.task_type,
                    memory_scope=request.memory_scope,
                    force_write=request.force_write,
                    source=request.source,
                    task_goal=request.task_goal,
                    context_summary=request.context_summary,
                    working_memory=request.working_memory,
                    agent_hints=_agent_hints_with_operation_ids(
                        request.agent_hints,
                        operation_id=request.operation_id,
                        idempotency_key=request.idempotency_key,
                    ),
                )
                write_json_response(self, payload)
                return

            if self.path == "/memory/write-plan":
                try:
                    request = MemoryWritePlanRequest.model_validate_json(body)
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return

                payload = agent.plan_memory_write(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    text=request.text,
                    task_type=request.task_type,
                    memory_scope=request.memory_scope,
                    force_write=request.force_write,
                    source=request.source,
                    task_goal=request.task_goal,
                    context_summary=request.context_summary,
                    working_memory=request.working_memory,
                    agent_hints=_agent_hints_with_operation_ids(
                        request.agent_hints,
                        operation_id=request.operation_id,
                        idempotency_key=request.idempotency_key,
                    ),
                )
                write_json_response(self, payload)
                return

            if self.path == "/memory/recall":
                try:
                    request = MemoryRecallRequest.model_validate_json(body)
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return

                payload = agent.recall_memory(
                    user_id=request.user_id,
                    query_text=request.query_text,
                    session_id=request.session_id,
                    top_k=request.top_k,
                    include_profile=request.include_profile,
                    task_goal=request.task_goal,
                    context_summary=request.context_summary,
                    working_memory=request.working_memory,
                    response_mode=request.response_mode,
                )
                write_json_response(self, payload)
                return

            if self.path == "/memory/reflect":
                try:
                    request = MemoryReflectRequest.model_validate_json(body)
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return

                payload = agent.reflect_memory(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    persist=request.persist,
                )
                write_json_response(self, payload)
                return

            if self.path == "/memory/update":
                try:
                    request = MemoryUpdateRequest.model_validate_json(body)
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return

                payload = agent.update_memory(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    memory_id=request.memory_id,
                    text=request.text,
                    source=request.source,
                    task_goal=request.task_goal,
                    context_summary=request.context_summary,
                    working_memory=request.working_memory,
                )
                write_json_response(self, payload)
                return

            if self.path == "/memory/forget":
                try:
                    request = MemoryForgetRequest.model_validate_json(body)
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return

                payload = agent.forget_memory(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    memory_id=request.memory_id,
                    reason=request.reason,
                    source=request.source,
                )
                write_json_response(self, payload)
                return

            if self.path == "/memory/block":
                try:
                    request = MemoryBlockRequest.model_validate_json(body)
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return

                payload = agent.set_memory_block(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    label=request.label,
                    value=request.value,
                    description=request.description,
                    read_only=request.read_only,
                    source=request.source,
                )
                write_json_response(self, payload)
                return

            if self.path == "/memory/block/delete":
                try:
                    request = MemoryBlockDeleteRequest.model_validate_json(body)
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return

                payload = agent.delete_memory_block(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    label=request.label,
                )
                write_json_response(self, payload)
                return

            if self.path == "/memory/history":
                try:
                    request = MemoryHistoryRequest.model_validate_json(body)
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return

                payload = agent.get_memory_history(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    memory_id=request.memory_id,
                )
                write_json_response(self, payload)
                return

            if self.path == "/memory/restore":
                try:
                    request = MemoryRestoreRequest.model_validate_json(body)
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return
                payload = agent.restore_memory(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    memory_id=request.memory_id,
                    reason=request.reason,
                    source=request.source,
                )
                write_json_response(self, payload)
                return

            if self.path == "/memory/supersede":
                try:
                    request = MemorySupersedeRequest.model_validate_json(body)
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return
                payload = agent.supersede_memory(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    source_memory_id=request.source_memory_id,
                    replacement_memory_id=request.replacement_memory_id,
                    reason=request.reason,
                    source=request.source,
                )
                write_json_response(self, payload)
                return

            if self.path == "/memory/merge":
                try:
                    request = MemoryMergeRequest.model_validate_json(body)
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return
                payload = agent.merge_memories(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    source_memory_id=request.source_memory_id,
                    target_memory_id=request.target_memory_id,
                    reason=request.reason,
                    source=request.source,
                )
                write_json_response(self, payload)
                return

            if self.path == "/memory/feedback":
                try:
                    request = FeedbackRequest.model_validate_json(body)
                    payload = agent.repository.record_feedback(
                        user_id=request.user_id,
                        session_id=request.session_id,
                        memory_id=request.memory_id,
                        feedback_type=request.feedback_type,
                        query_text=request.query_text,
                        notes=request.notes,
                        signal_weight=request.signal_weight or 1.0,
                    )
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return
                write_json_response(self, payload)
                return

            if self.path == "/system/retrieval-backend":
                try:
                    request = RetrievalBackendRequest.model_validate_json(body)
                    payload = agent.repository.configure_retrieval_backend(
                        backend_name=request.backend_name,
                        embedding_dimensions=request.embedding_dimensions,
                        embedding_candidate_pool=request.embedding_candidate_pool,
                        change_source=request.change_source or "api",
                    )
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return
                write_json_response(self, payload)
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Unknown route")

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)

            if parsed.path == "/":
                write_json_response(
                    self,
                    {
                        "service": "EMOS Agent API",
                        "status": "ok",
                        "health": "/health",
                        "openapi": "/openapi.json",
                        "agent_api_manifest": "/system/agent-api-manifest",
                    },
                )
                return

            if parsed.path == "/health":
                write_json_response(self, {"status": "ok"})
                return

            if parsed.path == "/openapi.json":
                write_json_response(self, _build_openapi_spec())
                return

            if parsed.path == "/system/agent-api-manifest":
                write_json_response(self, _build_agent_api_manifest())
                return

            if parsed.path == "/memory/profile":
                user_id = params.get("user_id", [None])[0]
                if not user_id:
                    self.send_error(HTTPStatus.BAD_REQUEST, "Missing user_id")
                    return
                limit = int(params.get("limit", ["20"])[0])
                write_json_response(self, agent.get_user_snapshot(user_id=user_id, limit=limit))
                return

            if parsed.path == "/memory/memories":
                user_id = params.get("user_id", [None])[0]
                if not user_id:
                    self.send_error(HTTPStatus.BAD_REQUEST, "Missing user_id")
                    return
                limit = int(params.get("limit", ["20"])[0])
                payload = {
                    "user_id": user_id,
                    "memories": [entry.to_dict() for entry in agent.repository.list_memories(user_id=user_id, limit=limit)],
                }
                write_json_response(self, payload)
                return

            if parsed.path == "/memory/report":
                user_id = params.get("user_id", [None])[0]
                if not user_id:
                    self.send_error(HTTPStatus.BAD_REQUEST, "Missing user_id")
                    return
                limit = int(params.get("limit", ["10"])[0])
                write_json_response(self, agent.generate_user_report(user_id=user_id, limit=limit))
                return

            if parsed.path == "/memory/export":
                user_id = params.get("user_id", [None])[0]
                if not user_id:
                    self.send_error(HTTPStatus.BAD_REQUEST, "Missing user_id")
                    return
                limit = int(params.get("limit", ["20"])[0])
                write_json_response(self, agent.export_user_bundle(user_id=user_id, limit=limit))
                return

            if parsed.path == "/memory/feedback":
                user_id = params.get("user_id", [None])[0]
                limit = int(params.get("limit", ["20"])[0])
                write_json_response(self, agent.repository.get_feedback_report(user_id=user_id, limit=limit))
                return

            if parsed.path == "/memory/blocks":
                user_id = params.get("user_id", [None])[0]
                if not user_id:
                    self.send_error(HTTPStatus.BAD_REQUEST, "Missing user_id")
                    return
                write_json_response(
                    self,
                    {
                        "user_id": user_id,
                        "blocks": [block.to_dict() for block in agent.repository.list_memory_blocks(user_id)],
                    },
                )
                return

            if parsed.path == "/memory/history":
                user_id = params.get("user_id", [None])[0]
                memory_id = params.get("memory_id", [None])[0]
                session_id = params.get("session_id", [None])[0]
                if not user_id or not memory_id:
                    self.send_error(HTTPStatus.BAD_REQUEST, "Missing user_id or memory_id")
                    return
                write_json_response(
                    self,
                    agent.get_memory_history(
                        user_id=user_id,
                        session_id=session_id,
                        memory_id=memory_id,
                    ),
                )
                return

            if parsed.path == "/system/report":
                write_json_response(self, agent.build_system_report())
                return

            if parsed.path == "/system/retrieval-backends":
                write_json_response(self, agent.build_retrieval_backend_report())
                return

            if parsed.path == "/system/storage":
                write_json_response(self, agent.get_storage_report())
                return

            if parsed.path == "/system/integration-flow":
                user_id = params.get("user_id", [None])[0]
                session_id = params.get("session_id", [None])[0]
                limit = int(params.get("limit", ["200"])[0])
                write_json_response(
                    self,
                    agent.build_integration_flow_report(
                        user_id=user_id,
                        session_id=session_id,
                        limit=limit,
                    ),
                )
                return

            if parsed.path == "/system/training-protocol":
                user_id = params.get("user_id", [None])[0]
                limit = int(params.get("limit", ["200"])[0])
                write_json_response(
                    self,
                    agent.build_training_protocol_report(
                        user_id=user_id,
                        limit=limit,
                    ),
                )
                return

            if parsed.path == "/system/user-experience":
                user_id = params.get("user_id", [None])[0]
                session_id = params.get("session_id", [None])[0]
                limit = int(params.get("limit", ["200"])[0])
                write_json_response(
                    self,
                    agent.build_user_experience_report(
                        user_id=user_id,
                        session_id=session_id,
                        limit=limit,
                    ),
                )
                return

            if parsed.path == "/system/consistency-audit":
                user_id = params.get("user_id", [None])[0]
                limit = int(params.get("limit", ["50"])[0])
                write_json_response(
                    self,
                    agent.build_consistency_audit_report(
                        user_id=user_id,
                        limit=limit,
                    ),
                )
                return

            if parsed.path == "/system/release-readiness":
                user_id = params.get("user_id", [None])[0]
                session_id = params.get("session_id", [None])[0]
                limit = int(params.get("limit", ["200"])[0])
                write_json_response(
                    self,
                    agent.build_release_readiness_report(
                        user_id=user_id,
                        session_id=session_id,
                        limit=limit,
                    ),
                )
                return

            if parsed.path == "/system/readiness-baseline":
                user_id = params.get("user_id", [None])[0]
                session_id = params.get("session_id", [None])[0]
                limit = int(params.get("limit", ["200"])[0])
                write_json_response(
                    self,
                    agent.build_readiness_baseline_report(
                        user_id=user_id,
                        session_id=session_id,
                        limit=limit,
                    ),
                )
                return

            if parsed.path == "/system/agent-readiness-summary":
                user_id = params.get("user_id", [None])[0]
                session_id = params.get("session_id", [None])[0]
                limit = int(params.get("limit", ["200"])[0])
                write_json_response(
                    self,
                    agent.build_agent_readiness_summary(
                        user_id=user_id,
                        session_id=session_id,
                        limit=limit,
                    ),
                )
                return

            if parsed.path == "/system/long-horizon-validation":
                user_id = params.get("user_id", [None])[0] or "long-horizon-user"
                session_id = params.get("session_id", [None])[0] or "long-horizon-session"
                limit = int(params.get("limit", ["200"])[0])
                write_json_response(
                    self,
                    agent.run_long_horizon_validation(
                        user_id=user_id,
                        session_id=session_id,
                        limit=limit,
                    ),
                )
                return

            if parsed.path == "/system/long-horizon-summary":
                limit = int(params.get("limit", ["5"])[0])
                write_json_response(
                    self,
                    agent.build_long_horizon_multi_run_summary(limit=limit),
                )
                return

            if parsed.path == "/system/memory-hygiene":
                user_id = params.get("user_id", [None])[0]
                limit = int(params.get("limit", ["50"])[0])
                write_json_response(
                    self,
                    agent.build_memory_hygiene_report(
                        user_id=user_id,
                        limit=limit,
                    ),
                )
                return

            if parsed.path == "/system/storage-backup":
                write_json_response(self, agent.create_storage_backup())
                return

            if parsed.path == "/system/delivery-pack":
                write_json_response(self, agent.generate_delivery_pack())
                return

            if parsed.path == "/system/offline-review-export":
                user_id = params.get("user_id", [None])[0]
                limit = int(params.get("limit", ["500"])[0])
                write_json_response(self, agent.repository.export_offline_review_dataset(limit=limit, user_id=user_id))
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Unknown route")

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    return MemoryHandler


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), create_handler())
    print(f"Memory API listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server(
        host=os.environ.get("MEMORY_SYSTEM_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("MEMORY_SYSTEM_API_PORT", "8000")),
    )
