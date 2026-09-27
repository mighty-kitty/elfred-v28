# -*- coding: utf-8 -*-
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class PAState(str, Enum):
    draft = "draft"
    onboarding = "onboarding"
    initializing = "initializing"
    calibrating = "calibrating"
    trial_ready = "trial_ready"
    active = "active"
    suspended = "suspended"
    archived = "archived"


class RunState(str, Enum):
    created = "created"
    admitted = "admitted"
    contextualizing = "contextualizing"
    planning = "planning"
    waiting_approval = "waiting_approval"
    executing = "executing"
    verifying = "verifying"
    delivering = "delivering"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    expired = "expired"


class PAProfile(BaseModel):
    pa_id: str
    user_id: str
    letta_agent_id: Optional[str] = None
    profile_version: int = 1
    state: PAState = PAState.onboarding
    persona: dict = Field(default_factory=dict)
    preferences: dict = Field(default_factory=dict)
    boundaries: dict = Field(default_factory=dict)
    knowledge_sources: list = Field(default_factory=list)
    tool_scopes: list = Field(default_factory=list)
    emos_profile_ref: Optional[str] = None
    consent_version: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class Run(BaseModel):
    run_id: str
    pa_id: str
    state: RunState = RunState.created
    query_summary: str = ""
    context_refs: dict = Field(default_factory=dict)
    plan: list = Field(default_factory=list)
    artifacts: list = Field(default_factory=list)
    events: list = Field(default_factory=list)
    tool_calls: list = Field(default_factory=list)
    approval: Optional[dict] = None
    # Tools that received their own (second) approval inside this run.
    approved_tools: list = Field(default_factory=list)
    # A paused run is frozen at its current state: it must not advance (e.g. a run
    # parked at the approval gate cannot be approved) until the user resumes it.
    paused: bool = False
    # revision lineage: a run created from an earlier run's change request
    parent_run_id: Optional[str] = None
    seq: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ToolEnvelope(BaseModel):
    tool_call_id: str
    run_id: str
    status: str
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    result_summary: Optional[str] = None
    artifact_refs: list = Field(default_factory=list)
    evidence_refs: list = Field(default_factory=list)
    error_code: Optional[str] = None
    retryable: bool = False
    # WP-04: the affective tag EMOS attached to this write, when it attached one.
    emotion: Optional[dict] = None


class RunEvent(BaseModel):
    event_id: str
    event_seq: int
    run_id: str
    pa_id: str
    timestamp: str
    type: str
    payload_version: int = 1
    payload: dict = Field(default_factory=dict)


class AcceptRequest(BaseModel):
    user_id: str
    decision: str  # accept | request_changes | reject
    comment: Optional[str] = None


class SessionDevice(BaseModel):
    device_id: str
    role: str = "unknown"          # pc | mobile | other
    joined_at: Optional[str] = None
    last_seen_at: Optional[str] = None


class Session(BaseModel):
    """A paired session: several devices observing/acting on ONE run.

    The run keeps a single lifecycle; the session only records which run the
    devices are looking at, so "mobile approves, PC continues" needs no second
    state machine.
    """
    session_id: str
    pa_id: str
    status: str = "active"          # active | closed
    run_id: Optional[str] = None
    devices: list = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class Feedback(BaseModel):
    """User feedback on a delivered run, plus where it was written back."""
    feedback_id: str
    run_id: str
    pa_id: str
    decision: str                      # accept | request_changes | reject
    comment: Optional[str] = None
    emos: list = Field(default_factory=list)   # per-memory feedback results
    skill: list = Field(default_factory=list)  # per skill-run feedback results
    degraded: list = Field(default_factory=list)
    revision_run_id: Optional[str] = None
    created_at: Optional[str] = None
