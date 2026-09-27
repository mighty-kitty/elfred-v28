from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query

from adapter.freetodo_client import FreeTodoError
from adapter.hardware_output.models import (
    AdapterTestRequest,
    ExecutePlanRequest,
    JournalReadyRequest,
    PlanCreateRequest,
)
from adapter.hardware_output.service import HardwareOutputService


def register_hardware_output_routes(
    app: Any,
    service: HardwareOutputService,
    prefix: str = "/v1/elfred",
) -> None:
    root = f"{prefix}/hardware-output"

    @app.get(f"{root}/status")
    def hardware_output_status(probe: bool = Query(default=False)) -> dict[str, Any]:
        detail = service.status(probe=probe)
        worker = getattr(app.state, "hardware_output_worker", None)
        detail["worker"] = (
            worker.status()
            if worker is not None
            else {"state": "disabled"}
        )
        return detail

    @app.get(f"{root}/adapters")
    def list_hardware_adapters(
        probe: bool = Query(default=False),
    ) -> dict[str, Any]:
        items = service.registry.describe(probe=probe)
        return {"total": len(items), "items": items}

    @app.post(f"{root}/adapters/reload")
    def reload_hardware_adapters() -> dict[str, Any]:
        service.registry.reload()
        return service.status(probe=False)

    @app.post(f"{root}/adapters/{{adapter_id}}/probe")
    def probe_hardware_adapter(adapter_id: str) -> dict[str, Any]:
        try:
            return service.probe_adapter(adapter_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post(f"{root}/adapters/{{adapter_id}}/test")
    def test_hardware_adapter(
        adapter_id: str,
        request: AdapterTestRequest,
    ) -> dict[str, Any]:
        try:
            return service.test_adapter(adapter_id, confirm=request.confirm)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(f"{root}/adapters/{{adapter_id}}/stop")
    def stop_hardware_adapter(adapter_id: str) -> dict[str, Any]:
        try:
            return service.stop_adapter(adapter_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(f"{root}/journals")
    def list_hardware_journals(
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, Any]:
        try:
            items = service.list_journals(limit)
        except FreeTodoError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return {"total": len(items), "items": items}

    @app.post(f"{root}/journals/{{journal_id}}/plan")
    def plan_remote_journal(
        journal_id: int,
        planning_mode: str = Query(
            default="auto",
            pattern="^(auto|deterministic|model)$",
        ),
        force: bool = Query(default=False),
    ) -> dict[str, Any]:
        try:
            return service.create_plan_from_remote(
                journal_id,
                planning_mode=planning_mode,
                force=force,
            )
        except FreeTodoError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(f"{root}/journals/ready")
    def journal_ready(request: JournalReadyRequest) -> dict[str, Any]:
        plan = service.create_plan(
            PlanCreateRequest(
                journal=request.journal,
                planning_mode=request.planning_mode,
            )
        )
        response: dict[str, Any] = {"plan": plan, "run": None}
        if request.execute_safe_actions:
            response["run"] = service.queue_plan(
                plan["plan_id"],
                ExecutePlanRequest(
                    idempotency_key=request.idempotency_key,
                ),
            )
        return response

    @app.post(f"{root}/plans")
    def create_hardware_plan(request: PlanCreateRequest) -> dict[str, Any]:
        return service.create_plan(request)

    @app.get(f"{root}/plans")
    def list_hardware_plans(
        limit: int = Query(default=50, ge=1, le=500),
        journal_id: str | None = Query(default=None, alias="journalId"),
    ) -> dict[str, Any]:
        items = service.repository.list_plans(
            limit=limit,
            journal_id=journal_id,
        )
        return {"total": len(items), "items": items}

    @app.get(f"{root}/plans/{{plan_id}}")
    def get_hardware_plan(plan_id: str) -> dict[str, Any]:
        plan = service.repository.get_plan(plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="hardware output plan not found")
        return plan

    @app.post(f"{root}/plans/{{plan_id}}/execute", status_code=202)
    def execute_hardware_plan(
        plan_id: str,
        request: ExecutePlanRequest,
    ) -> dict[str, Any]:
        try:
            return service.queue_plan(plan_id, request)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get(f"{root}/runs")
    def list_hardware_runs(
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, Any]:
        items = service.repository.list_runs(limit)
        return {"total": len(items), "items": items}

    @app.get(f"{root}/runs/{{run_id}}")
    def get_hardware_run(run_id: str) -> dict[str, Any]:
        run = service.repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="hardware output run not found")
        return run

    @app.post(f"{root}/runs/{{run_id}}/retry", status_code=202)
    def retry_hardware_run(run_id: str) -> dict[str, Any]:
        try:
            return service.retry_run(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get(f"{root}/events")
    def hardware_device_events(
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, Any]:
        items = service.repository.recent_device_events(limit)
        return {"total": len(items), "items": items}

    @app.get(f"{root}/doctor")
    def hardware_output_doctor() -> dict[str, Any]:
        return service.doctor()

    @app.get(f"{root}/support-bundle")
    def hardware_output_support_bundle() -> dict[str, Any]:
        return service.support_bundle()
