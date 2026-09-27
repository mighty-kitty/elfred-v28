# -*- coding: utf-8 -*-
"""WP-04: the memory tools beyond recall - write, forget, block - and the
memory facts a manifest must carry (retrieval backend, emotion, blocks)."""
import time

import app.main as main_mod
from fastapi.testclient import TestClient

from app.engine import RunEngine
from app.main import app
from app.models import Run

c = TestClient(app)


class _FakeEmos:
    def __init__(self, write_ok=True, recalled_id="mem_old", emotion=None):
        self.write_ok = write_ok
        self.recalled_id = recalled_id
        self.emotion = emotion
        self.calls = []

    def recall(self, user_id, query_text, **kw):
        self.calls.append(("recall", query_text))
        recalled = {"memory_id": self.recalled_id} if self.recalled_id else None
        return {"payload": {"recalled_memory": recalled, "evidence": [],
                            "retrieval_backend": "embedding_rerank",
                            "retrieval_candidates": 12,
                            "retrieval_pipeline": {"backend_name": "embedding_rerank",
                                                   "family": "hybrid_dense",
                                                   "fusion_strategy": "candidate_pool_union",
                                                   "rerank_stage": "deterministic_feature_rerank",
                                                   "recall_stages": ["dense", "hybrid"]},
                            "core_memory_blocks": [
                                {"label": "derived_profile", "value": "interests: 编译器",
                                 "read_only": True, "source": "system_derived"}]}}

    def write(self, user_id, session_id, text, **kw):
        self.calls.append(("write", text))
        if not self.write_ok:
            return {"payload": {"memory_written": False, "memory_id": None,
                                "write_policy": {"reasons": ["low_signal"]}}}
        payload = {"memory_written": True, "memory_id": "mem_new"}
        if self.emotion:
            payload["emotion"] = self.emotion
        return {"payload": payload}

    def forget(self, user_id, session_id, memory_id, reason="", source=""):
        self.calls.append(("forget", memory_id, reason))
        return {"payload": {"memory_id": memory_id, "forgotten": True,
                            "execution_surface": {"operation": "forget_memory"}}}

    def set_block(self, user_id, session_id, label, value, **kw):
        self.calls.append(("set_block", label, value))
        return {"payload": {"label": label, "value": value, "updated": True}}

    def write_plan(self, user_id, session_id, text, **kw):
        return {"payload": {"suggested_action": "write_new_memory"}}


class _StubPlanner:
    name = "stub"

    def __init__(self, steps):
        self._steps = steps

    def plan(self, query, ctx, tools=None):
        return list(self._steps)


def _run(steps, emos, scopes=None):
    engine = main_mod.engine
    original_planner, original_emos = engine.planner, engine.emos
    engine.planner = _StubPlanner(steps)
    engine.emos = emos
    try:
        profile = {"user_id": "u_mem", "consent_version": 1}
        if scopes is not None:
            profile["tool_scopes"] = scopes
        pa = c.post("/v1/pa/profiles", json=profile).json()["pa_id"]
        rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "记住我的偏好"}).json()["run_id"]
        deadline = time.time() + 20
        while time.time() < deadline:
            if c.get(f"/v1/runs/{rid}").json()["state"] == "waiting_approval":
                break
            time.sleep(0.2)
        return c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"}).json()
    finally:
        engine.planner, engine.emos = original_planner, original_emos


def _step(tool, goal, **kw):
    return {"step": 1, "goal": goal, "tool": tool, "risk": "low", **kw}


def _completed(body):
    return [e["payload"].get("tool") for e in body["events"] if e["type"] == "tool.completed"]


def _failed(body):
    return [e["payload"] for e in body["events"] if e["type"] == "tool.failed"]


# ------------------------------------------------------------------ emos_write


def test_emos_write_records_the_memory_and_its_emotion():
    emos = _FakeEmos(emotion={"label": "焦虑", "score": 0.65})
    body = _run([_step("emos_write", "用户更喜欢三点式汇报")], emos)
    assert _completed(body) == ["emos_write"], _failed(body)
    envelope = [t for t in body["tool_calls"] if t["status"] == "completed"][0]
    assert envelope["evidence_refs"] == ["mem_new"]
    assert envelope["emotion"] == {"label": "焦虑", "score": 0.65}
    progress = [e["payload"] for e in body["events"] if e["type"] == "tool.progress"]
    assert any(p.get("emotion", {}).get("label") == "焦虑" for p in progress)


def test_emos_write_refuses_to_report_a_write_emos_did_not_make():
    body = _run([_step("emos_write", "低信号内容")], _FakeEmos(write_ok=False))
    assert _completed(body) == []
    assert _failed(body) and _failed(body)[0]["error"] == "INVALID_OUTPUT"
    assert "low_signal" in _failed(body)[0]["detail"]


def test_a_profile_without_the_scope_cannot_write_memory():
    body = _run([_step("emos_write", "越权写入")], _FakeEmos(), scopes=["emos_recall"])
    assert _completed(body) == []
    assert "emos_write" not in [s.get("tool") for s in
                                c.get(f"/v1/runs/{body['run_id']}").json()["plan"]]


# ----------------------------------------------------------------- emos_forget


def test_emos_forget_targets_the_recalled_memory_and_keeps_the_reason():
    emos = _FakeEmos(recalled_id="mem_target")
    body = _run([_step("emos_forget", "忘掉我上个月说的那个预算")], emos)
    assert _completed(body) == ["emos_forget"], _failed(body)
    assert ("forget", "mem_target", "忘掉我上个月说的那个预算") in emos.calls
    envelope = [t for t in body["tool_calls"] if t["status"] == "completed"][0]
    assert envelope["evidence_refs"] == ["forget:mem_target"]


def test_emos_forget_says_so_when_there_is_nothing_to_forget():
    body = _run([_step("emos_forget", "随便忘点什么")], _FakeEmos(recalled_id=None))
    assert _completed(body) == []
    assert "nothing in memory matched" in _failed(body)[0]["detail"]


# -------------------------------------------------------------- emos_block_set


def test_emos_block_set_writes_a_named_block():
    emos = _FakeEmos()
    body = _run([_step("emos_block_set", "汇报必须给数字", label="report_style")], emos)
    assert _completed(body) == ["emos_block_set"], _failed(body)
    assert ("set_block", "report_style", "汇报必须给数字") in emos.calls
    envelope = [t for t in body["tool_calls"] if t["status"] == "completed"][0]
    assert envelope["evidence_refs"] == ["block:report_style"]


# ---------------------------------------------------------- the memory manifest


def test_context_records_the_retrieval_backend_blocks_and_mirror_mode():
    engine = RunEngine(store=main_mod.store, emos=_FakeEmos())
    run = Run(run_id="run_mem", pa_id="pa_mem", query_summary="我最近在忙什么",
              created_at="now", updated_at="now")
    ctx, _log = engine._build_context(run)
    assert ctx["memory_retrieval"]["backend"] == "embedding_rerank"
    assert ctx["memory_retrieval"]["candidate_count"] == 12
    assert ctx["memory_retrieval"]["pipeline"]["fusion"] == "candidate_pool_union"
    assert ctx["memory_retrieval"]["pipeline"]["stages"] == "dense, hybrid"
    assert ctx["core_memory_blocks"][0]["label"] == "derived_profile"
    assert ctx["letta_mirror"]["mode"] == "request_context"
    # the block value must survive redaction, or the agent would never see it
    assert ctx["core_memory_blocks"][0]["value"] == "interests: 编译器"


def test_context_carries_an_emotion_tag_when_emorys_recall_has_one():
    engine = RunEngine(store=main_mod.store, emos=_FakeEmos())
    run = Run(run_id="run_emo", pa_id="pa_mem", query_summary="心情",
              created_at="now", updated_at="now")
    payload = {"emotion": {"label": "平静", "score": 0.4}, "recalled_memory": None}
    assert engine._emotion_of(payload) == {"label": "平静", "score": 0.4}
    recalled = {"recalled_memory": {"memory_id": "m1", "emotion": {"label": "焦虑",
                                                                  "score": 0.7}}}
    assert engine._emotion_of(recalled) == {"label": "焦虑", "score": 0.7}
    assert engine._emotion_of({"recalled_memory": {"memory_id": "m2"}}) == {}


def test_manifest_publishes_the_memory_facts():
    from app.manifest import build_manifest
    ctx = {"memory_refs": ["m1"], "memory_retrieval": {"backend": "embedding_rerank"},
           "memory_emotion": {"label": "平静", "score": 0.4},
           "core_memory_blocks": [{"label": "derived_profile", "value": "x"}]}
    manifest = build_manifest("run_1", "q", None, ctx, [])
    assert manifest["memory_retrieval"]["backend"] == "embedding_rerank"
    assert manifest["memory_emotion"]["label"] == "平静"
    assert manifest["core_memory_blocks"][0]["label"] == "derived_profile"
