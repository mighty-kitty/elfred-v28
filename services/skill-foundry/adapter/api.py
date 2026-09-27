from __future__ import annotations

from contextlib import asynccontextmanager
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from fastapi import (
    BackgroundTasks,
    Body,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from adapter import __version__
from adapter.agent_routes import register_agent_routes
from adapter.analysis_worker import AnalysisWorker
from adapter.config import Settings
from adapter.freetodo_client import FreeTodoError
from adapter.hardware_output.routes import register_hardware_output_routes
from adapter.hardware_output.worker import HardwareOutputWorker
from adapter.observer_sync import ObserverAutoSync
from adapter.journal.routes import register_journal_routes
from adapter.journal.worker import JournalWorker
from adapter.service import AdapterService
from adapter.skill_foundry.passive import PassiveSkillFoundryWorker


ELFRED_WEB_ORIGINS = ["http://127.0.0.1:8002", "http://localhost:8002"]


class BatchRequest(BaseModel):
    events: list[dict[str, Any]] = Field(min_length=1, max_length=1000)


class PullRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000)


class ReconcileRequest(BaseModel):
    repair: bool = False


class SkillDraftRequest(BaseModel):
    taskIds: list[int] = Field(min_length=2, max_length=20)
    skillId: str | None = None
    asyncBuild: bool = False


class SkillRunRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    taskContext: dict[str, Any] = Field(default_factory=dict)


class SkillApprovalRequest(BaseModel):
    allowHeuristic: bool = False


class SkillAutoExecuteRequest(BaseModel):
    enabled: bool = False


class SkillFeedbackRequest(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    outcome: str | None = None
    comment: str | None = None
    corrections: list[dict[str, Any]] = Field(default_factory=list)


class DemoSkillTaskRequest(BaseModel):
    title: str = "读取新文档并生成三点摘要"
    sourceText: str = Field(min_length=20)
    currentApp: str = "Elfred Web"


def create_app(settings: Settings | None = None, service: AdapterService | None = None) -> FastAPI:
    service = service or AdapterService(settings or Settings.from_env())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        observer_sync: ObserverAutoSync | None = None
        analysis_worker: AnalysisWorker | None = None
        passive_foundry: PassiveSkillFoundryWorker | None = None
        hardware_output_worker: HardwareOutputWorker | None = None
        journal_worker: JournalWorker | None = None
        journal_task: asyncio.Task[None] | None = None
        if service.task_analyzer is not None or getattr(service.journal, "generator", None) is not None:
            service.harness.start()
        if service.settings.analysis_worker_interval_seconds > 0:
            analysis_worker = AnalysisWorker(service)
            analysis_worker.start()
        if service.settings.observer_auto_sync_interval_seconds > 0:
            observer_sync = ObserverAutoSync(service)
            observer_sync.start()
        if service.settings.skill_passive_enabled:
            passive_foundry = PassiveSkillFoundryWorker(service)
            passive_foundry.start()
        if service.settings.hardware_output_enabled:
            hardware_output_worker = HardwareOutputWorker(service.hardware_output)
            hardware_output_worker.start()
        def journal_source_ready() -> bool:
            if observer_sync is None:
                return True
            sync_status = observer_sync.status()
            if sync_status.get("state") != "watching":
                return False
            if sync_status.get("mode") == "feed_backfill":
                return sync_status.get("has_more") is False
            return True

        service.journal_coordinator.set_source_ready_provider(
            journal_source_ready
        )
        if service.settings.journal_worker_interval_seconds > 0:
            journal_worker = JournalWorker(
                service.journal_coordinator,
                interval_seconds=service.settings.journal_worker_interval_seconds,
                source_ready=journal_source_ready,
            )
            journal_worker.start()
        app.state.observer_sync = observer_sync
        app.state.analysis_worker = analysis_worker
        app.state.passive_foundry = passive_foundry
        app.state.hardware_output_worker = hardware_output_worker
        app.state.journal_worker = journal_worker
        if service.settings.journal_enabled:
            journal_task = asyncio.create_task(
                _midnight_journal_loop(journal_source_ready)
            )
        app.state.journal_task = journal_task
        try:
            yield
        finally:
            if journal_task:
                journal_task.cancel()
                try:
                    await journal_task
                except asyncio.CancelledError:
                    pass
            if journal_worker:
                journal_worker.stop()
            if observer_sync:
                observer_sync.stop()
            if analysis_worker:
                analysis_worker.stop()
            if passive_foundry:
                passive_foundry.stop()
            if hardware_output_worker:
                hardware_output_worker.stop()
            service.harness.close()

    app = FastAPI(
        title="Elfred FreeTodo Adapter",
        version=__version__,
        description="HTTP-only sidecar between Elfred ContextEvent and the slimmed FreeTodo service.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ELFRED_WEB_ORIGINS,
        allow_methods=["GET"],
        allow_headers=["Accept", "Content-Type"],
    )

    @app.middleware("http")
    async def local_control_cors(request: Request, call_next):
        path = request.url.path
        is_skill_foundry = path.startswith("/v1/elfred/skills") or path.startswith(
            "/v1/elfred/skill-runs"
        )
        is_hardware_output = path.startswith("/v1/elfred/hardware-output")
        is_agent = path.startswith("/v1/elfred/agent")
        is_local_control = is_skill_foundry or is_hardware_output or is_agent
        origin = request.headers.get("origin")
        if (
            is_local_control
            and request.method == "OPTIONS"
            and origin in ELFRED_WEB_ORIGINS
            and request.headers.get("access-control-request-method", "").upper()
            in {"POST", "PATCH", "DELETE"}
        ):
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE",
                    "Access-Control-Allow-Headers": "Accept, Content-Type",
                    "Access-Control-Max-Age": "600",
                    "Vary": "Origin",
                },
            )
        response = await call_next(request)
        if is_local_control and origin in ELFRED_WEB_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        return response

    app.state.service = service
    app.state.observer_sync = None
    app.state.analysis_worker = None
    app.state.passive_foundry = None
    app.state.hardware_output_worker = None
    app.state.journal_worker = None
    prefix = "/v1/elfred"

    def ingest_processor():
        return (
            service.enqueue_payload
            if service.task_analyzer is not None
            else service.process_payload
        )

    @app.get(f"{prefix}/health")
    def health() -> dict[str, Any]:
        detail = service.health()
        if app.state.observer_sync:
            detail["observer_auto_sync"].update(app.state.observer_sync.status())
        if app.state.analysis_worker:
            detail["analysis_worker"].update(app.state.analysis_worker.status())
        if app.state.passive_foundry:
            detail["passive_skill_foundry"] = app.state.passive_foundry.status()
        if app.state.hardware_output_worker:
            detail["hardware_output"]["worker"] = (
                app.state.hardware_output_worker.status()
            )
        if app.state.journal_worker:
            detail["journal_worker"] = app.state.journal_worker.status()
        return detail

    @app.get(f"{prefix}/status")
    def status() -> dict[str, Any]:
        detail = service.status()
        if app.state.observer_sync:
            detail["observer_auto_sync"] = app.state.observer_sync.status()
        if app.state.analysis_worker:
            detail["analysis_worker"] = app.state.analysis_worker.status()
        if app.state.passive_foundry:
            detail["passive_skill_foundry"] = app.state.passive_foundry.status()
        if app.state.hardware_output_worker:
            detail["hardware_output"]["worker"] = (
                app.state.hardware_output_worker.status()
            )
        if app.state.journal_worker:
            detail["journal_worker"] = app.state.journal_worker.status()
        return detail

    @app.post(f"{prefix}/events", status_code=202)
    def ingest_event(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            return ingest_processor()(payload).model_dump(mode="json")
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(f"{prefix}/events/batch", status_code=202)
    def ingest_batch(request: BatchRequest) -> dict[str, Any]:
        results = []
        processor = ingest_processor()
        for payload in request.events:
            try:
                results.append(processor(payload).model_dump(mode="json"))
            except Exception as error:  # one malformed event must not drop the full Observer batch
                results.append({"event_id": payload.get("event_id"), "status": "rejected", "error": str(error)})
        counts: dict[str, int] = {}
        for result in results:
            counts[result["status"]] = counts.get(result["status"], 0) + 1
        return {"total": len(results), "counts": counts, "results": results}

    @app.post(f"{prefix}/import/json", status_code=202)
    def import_json(payload: Any = Body(...)) -> dict[str, Any]:
        events = payload.get("events") if isinstance(payload, dict) and isinstance(payload.get("events"), list) else payload
        if isinstance(events, list):
            return ingest_batch(BatchRequest(events=events))
        if isinstance(events, dict):
            return ingest_event(events)
        raise HTTPException(status_code=422, detail="Expected a ContextEvent, an envelope, or an events array")

    @app.post(f"{prefix}/pull-observer", status_code=202)
    def pull_observer(request: PullRequest) -> dict[str, Any]:
        url = service.settings.observer_base_url + "/events/recent?" + urllib.parse.urlencode({"limit": request.limit})
        try:
            with urllib.request.urlopen(url, timeout=service.settings.request_timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=503, detail=f"Observer unavailable: {error}") from error
        events = data.get("events") if isinstance(data, dict) else data
        if not isinstance(events, list):
            raise HTTPException(status_code=502, detail="Observer response has no events array")
        return ingest_batch(BatchRequest(events=events))

    @app.get(f"{prefix}/jobs")
    def jobs(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, Any]:
        items = service.store.jobs(limit)
        return {"total": len(items), "jobs": items}

    @app.get(f"{prefix}/jobs/{{job_id}}")
    def job(job_id: str) -> dict[str, Any]:
        item = service.store.job(job_id)
        if not item:
            raise HTTPException(status_code=404, detail="job not found")
        return item

    @app.post(f"{prefix}/reconcile", status_code=202)
    def reconcile(request: ReconcileRequest) -> dict[str, Any]:
        return service.reconcile(request.repair)

    @app.get(f"{prefix}/events/{{event_id}}/links")
    def event_links(event_id: str) -> dict[str, Any]:
        if not service.store.get_event(event_id, include_deleted=True):
            raise HTTPException(status_code=404, detail="event not found")
        return {"event_id": event_id, "links": service.store.remote_links(event_id)}

    @app.get(f"{prefix}/events/{{event_id}}/task-analysis")
    def event_task_analysis(event_id: str) -> dict[str, Any]:
        item = service.store.task_analysis(event_id)
        if not item:
            raise HTTPException(status_code=404, detail="task analysis not found")
        return item

    @app.get(f"{prefix}/tasks")
    def canonical_tasks(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, Any]:
        items = service.store.canonical_task_candidates(limit)
        return {"total": len(items), "tasks": items}

    @app.get(f"{prefix}/tasks/{{task_id}}")
    def canonical_task(task_id: str) -> dict[str, Any]:
        item = service.store.canonical_task(task_id)
        if not item:
            raise HTTPException(status_code=404, detail="canonical task not found")
        item["evidence"] = service.store.task_evidence(task_id=task_id)
        return item

    def process_skill_build(
        build_id: str, task_ids: list[int], skill_id: str | None
    ) -> None:
        try:
            service.skill_foundry.create_draft(
                task_ids, skill_id=skill_id, build_id=build_id
            )
        except Exception:
            # create_draft persists the failed build and its user-visible reason.
            return

    @app.post(f"{prefix}/skills/drafts/from-tasks")
    def create_skill_draft(
        request: SkillDraftRequest, background_tasks: BackgroundTasks
    ) -> dict[str, Any]:
        try:
            if request.asyncBuild:
                build = service.skill_foundry.start_draft(request.taskIds)
                background_tasks.add_task(
                    process_skill_build,
                    build["build_id"],
                    request.taskIds,
                    request.skillId,
                )
                return {"accepted": True, "build": build}
            return service.skill_foundry.create_draft(
                request.taskIds, skill_id=request.skillId
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="skill not found") from error
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except FreeTodoError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get(f"{prefix}/skills/builds/{{build_id}}")
    def skill_build(build_id: str) -> dict[str, Any]:
        item = service.skill_foundry.registry.build(build_id)
        if not item:
            raise HTTPException(status_code=404, detail="skill build not found")
        return item

    @app.get(f"{prefix}/skills")
    def skills() -> dict[str, Any]:
        items = service.skill_foundry.registry.list()
        return {"total": len(items), "skills": items}

    @app.get(f"{prefix}/skills/passive/status")
    def passive_skill_status() -> dict[str, Any]:
        if app.state.passive_foundry:
            return app.state.passive_foundry.status()
        return {
            "state": "disabled",
            "groups": [],
            "enabled": bool(service.settings.skill_passive_enabled),
        }

    @app.get(f"{prefix}/skills/passive/profiles")
    def passive_skill_profiles(
        limit: int = Query(default=200, ge=1, le=1000)
    ) -> dict[str, Any]:
        items = service.skill_foundry.semantic_profiler.profiles(limit)
        return {"total": len(items), "profiles": items}

    @app.post(f"{prefix}/skills/passive/scan")
    def scan_passive_skills() -> dict[str, Any]:
        if not app.state.passive_foundry:
            raise HTTPException(
                status_code=409, detail="passive Skill Foundry is disabled"
            )
        return app.state.passive_foundry.process_once()

    @app.post(f"{prefix}/skills/match")
    def match_skills(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        matches = service.skill_foundry.match(payload)
        return {"total": len(matches), "matches": matches}

    @app.get(f"{prefix}/skills/matches")
    def stored_skill_matches(
        freetodoTodoId: int | None = Query(default=None, ge=1),
        limit: int = Query(default=500, ge=1, le=5000),
    ) -> dict[str, Any]:
        matches = service.skill_foundry.registry.task_matches(
            freetodo_todo_id=freetodoTodoId,
            limit=limit,
        )
        return {"total": len(matches), "matches": matches}

    @app.post(f"{prefix}/skills/matches/scan")
    def scan_skill_matches() -> dict[str, Any]:
        try:
            return service.skill_foundry.scan_active_task_matches()
        except FreeTodoError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post(f"{prefix}/skills/demo/seed")
    def seed_skill_demo() -> dict[str, Any]:
        try:
            return service.skill_foundry.seed_demo()
        except FreeTodoError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post(f"{prefix}/skills/demo/tasks")
    def create_skill_demo_task(
        request: DemoSkillTaskRequest,
    ) -> dict[str, Any]:
        try:
            return service.skill_foundry.create_demo_task(
                title=request.title,
                source_text=request.sourceText,
                current_app=request.currentApp,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except FreeTodoError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get(f"{prefix}/skills/{{skill_id}}")
    def skill(skill_id: str) -> dict[str, Any]:
        item = service.skill_foundry.registry.get(skill_id)
        if not item:
            raise HTTPException(status_code=404, detail="skill not found")
        return item

    @app.post(f"{prefix}/skills/{{skill_id}}/approve")
    def approve_skill(
        skill_id: str,
        request: SkillApprovalRequest = Body(default=SkillApprovalRequest()),
    ) -> dict[str, Any]:
        try:
            return service.skill_foundry.approve(
                skill_id, allow_heuristic=request.allowHeuristic
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="skill not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(f"{prefix}/skills/{{skill_id}}/auto-execute")
    def set_skill_auto_execute(
        skill_id: str,
        request: SkillAutoExecuteRequest,
    ) -> dict[str, Any]:
        try:
            return service.skill_foundry.set_auto_execute(
                skill_id,
                request.enabled,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail="skill not found"
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(f"{prefix}/skills/{{skill_id}}/run")
    def run_skill(
        skill_id: str, request: SkillRunRequest
    ) -> dict[str, Any]:
        try:
            return service.skill_foundry.run_skill(
                skill_id,
                inputs=request.inputs,
                task_context=request.taskContext,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="skill not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get(f"{prefix}/skill-runs")
    def skill_runs(
        limit: int = Query(default=100, ge=1, le=1000)
    ) -> dict[str, Any]:
        items = service.skill_foundry.registry.runs(limit)
        return {"total": len(items), "runs": items}

    @app.get(f"{prefix}/skill-runs/{{run_id}}")
    def skill_run(run_id: str) -> dict[str, Any]:
        item = service.skill_foundry.registry.run(run_id)
        if not item:
            raise HTTPException(status_code=404, detail="skill run not found")
        item["feedback"] = service.skill_foundry.registry.feedback_for_run(
            run_id
        )
        return item

    @app.post(f"{prefix}/skill-runs/{{run_id}}/feedback")
    def skill_run_feedback(
        run_id: str, request: SkillFeedbackRequest
    ) -> dict[str, Any]:
        try:
            return service.skill_foundry.record_feedback(
                run_id,
                rating=request.rating,
                outcome=request.outcome,
                comment=request.comment,
                corrections=request.corrections,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="skill run not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.delete(f"{prefix}/events/{{event_id}}")
    def delete_event(event_id: str) -> dict[str, Any]:
        try:
            return service.delete_event(event_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="event not found") from error

    @app.post(f"{prefix}/events/{{event_id}}/forget", status_code=202)
    def forget_event(event_id: str) -> dict[str, Any]:
        try:
            return service.forget_event(event_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="event not found") from error
        except FreeTodoError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post(f"{prefix}/events/{{event_id}}/retry", status_code=202)
    def retry_event(event_id: str) -> dict[str, Any]:
        try:
            return service.retry_event(event_id).model_dump(mode="json")
        except KeyError as error:
            raise HTTPException(status_code=404, detail="event not found") from error

    @app.get(f"{prefix}/outbox/memory")
    def memory_outbox(
        status: str | None = Query(default="pending"), limit: int = Query(default=100, ge=1, le=1000)
    ) -> dict[str, Any]:
        items = service.store.outbox("memory", status, limit)
        return {"total": len(items), "items": items}

    @app.get(f"{prefix}/outbox/personal-agent")
    def personal_agent_outbox(
        status: str | None = Query(default="pending"), limit: int = Query(default=100, ge=1, le=1000)
    ) -> dict[str, Any]:
        items = service.store.outbox("personal_agent", status, limit)
        return {"total": len(items), "items": items}

    @app.post(f"{prefix}/outbox/{{item_id}}/ack")
    def ack_outbox(item_id: str) -> dict[str, Any]:
        if not service.store.ack_outbox(item_id):
            raise HTTPException(status_code=404, detail="outbox item not found")
        return {"item_id": item_id, "status": "acknowledged"}

    @app.get(f"{prefix}/activities")
    def activities(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, Any]:
        with service.store.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM freetodo_activity_links ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["detail"] = json.loads(item.pop("detail_json"))
            items.append(item)
        return {"total": len(items), "items": items, "storage": "adapter_local"}

    @app.get(f"{prefix}/reports/weekly/{{iso_year}}/{{iso_week}}")
    def weekly_report(iso_year: int, iso_week: int) -> dict[str, Any]:
        if not 1 <= iso_week <= 53:
            raise HTTPException(status_code=422, detail="iso_week must be 1..53")
        return service.weekly_report(iso_year, iso_week)

    register_journal_routes(app, service.journal_coordinator, prefix)
    register_hardware_output_routes(app, service.hardware_output, prefix)
    register_agent_routes(app, service.settings, prefix, client=service.harness)

    import asyncio
    from datetime import datetime, timedelta

    from adapter.journal.schedule import (
        journal_day_for_boundary,
        next_boundary,
        previous_day,
        resolve_timezone,
        wait_until_boundary,
    )

    async def _midnight_journal_loop(
        source_ready: Callable[[], bool],
    ) -> None:
        if not service.settings.journal_enabled:
            return
        import logging
        _log = logging.getLogger("elfred.journal")
        _log.setLevel(logging.INFO)
        if not _log.handlers:
            _log.addHandler(logging.StreamHandler())

        journal_timezone = resolve_timezone(service.settings.journal_timezone)
        now = datetime.now(journal_timezone)
        yesterday = previous_day(now)
        service.journal_coordinator.enqueue(yesterday, trigger="startup")
        _log.info("Startup catch-up queued journal for %s", yesterday)

        while not source_ready():
            await asyncio.sleep(0.5)

        reconcile_through = previous_day(
            datetime.now(journal_timezone)
        )
        source_days = service.store.event_days_through(reconcile_through)
        for source_day in source_days:
            service.journal_coordinator.enqueue(
                source_day,
                trigger="startup_reconcile",
            )
        _log.info(
            "Startup journal reconciliation queued %d source days through %s",
            len(source_days),
            reconcile_through,
        )

        boundary = next_boundary(
            datetime.now(journal_timezone),
            service.settings.journal_generation_hour,
        )
        while True:
            await wait_until_boundary(
                boundary,
                now=lambda: datetime.now(journal_timezone),
                sleep=asyncio.sleep,
            )
            try:
                journal_day = journal_day_for_boundary(boundary)
                _log.info("Scheduled journal generation for %s", journal_day)
                service.journal_coordinator.enqueue(
                    journal_day,
                    trigger="schedule",
                )
            except Exception:
                import traceback
                _log.error("Scheduled journal failed:\n%s", traceback.format_exc())
            boundary += timedelta(days=1)

    return app
